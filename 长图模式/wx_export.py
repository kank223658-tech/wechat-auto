# -*- coding: utf-8 -*-
"""
长图模式 · 微信仿真长图导出器
==============================
不自己画微信，直接驱动项目里的 vue-WeChat 仿真系统（dialogue.vue + chat_exact.css
的像素级微信深色聊天页）渲染整段对话，输出：
  1. wxshot_*.png            —— 正宗微信样式的聊天长图（状态栏+顶栏+全部消息）
  2. wxshot_*.manifest.json  —— 每条消息的精确矩形真值（截图像素坐标），
                                供 render_longimg.py --wxshot 做零猜测动态镜头

数据入口与运行时完全同源：window.__wxConfig.setMe / setHomeList（enhance/config.js），
消息类型支持 text / image / emoji / voice / link；点评行（蓝=她 黄=我 红=CTA）
作为 DOM 元素插到气泡下方参与排版与截图，坐标一并入清单。

用法（用系统 Python，playwright 只装在系统 py）：
  C:/Users/mik/AppData/Local/Programs/Python/Python314/python.exe 长图模式/wx_export.py ^
      --config 配置.json --out-dir "_工作文件/_参考_长图模式/wx长图"
前提：vue-WeChat dev server 已在 8080 运行（main.py 会自动拉起，先跑一次即可）。
"""
import argparse
import json
import os
import socket
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENHANCE = os.path.join(ROOT, "enhance")
BASE_URL = "http://localhost:8080/#/"
PORT = 8080
VIEW_W, VIEW_H = 600, 1300
MAX_SHOT_PX = 16000          # Chromium 截图安全上限（单边像素）

NOTE_BLUE = "#56B4EB"
NOTE_YELLOW = "#FFD246"
NOTE_RED = "#FF5656"

# ---- 导出覆盖样式：主页(.outter)整体隐藏，聊天浮层(.sub-page)转入文档流，
#      让整段对话自然排开；其余微信深色样式（chat_exact.css）原样保留 ----
EXPORT_CSS = """
* { animation: none !important; transition: none !important; }
html, body, #app { height: auto !important; max-height: none !important; overflow: visible !important; }
body { background: #101010 !important; }
.welcome { display: none !important; }
.outter { display: none !important; }
.sub-page { position: static !important; width: 600px !important; height: auto !important;
            min-height: 0 !important; transform: none !important; }
body.wx-chat .dialogue { position: static !important; height: auto !important; min-height: 0 !important;
                         overflow: visible !important; background: #101010 !important; }
/* 顶栏/状态栏：转文档流但必须保留定位上下文（relative 而非 static）——
   两栏的所有子元素（返回箭头/99胶囊/标题/时钟/定位/信号/电池）都是 absolute 定位，
   static 会让它们集体飞到整页顶上挤成一行（99 角标穿膜压时钟的根因）。
   relative 保持文档流布局不变，同时让 absolute 子元素照旧锚在各自栏内，
   导出顺序=状态栏(79) → 顶栏(71) → 消息，与真机一致。 */
body.wx-chat .dialogue #wx-header { position: relative !important; }
#ios-statusbar { position: relative !important; top: 0 !important; }
body.wx-chat .dialogue-section {
    position: static !important;
    top: auto !important; height: auto !important; min-height: 0 !important;
    width: 600px !important;
    overflow: visible !important;
    background: var(--wx-chat-bg, #101010) !important;
    background-attachment: scroll !important;
    padding-bottom: 120px !important;
}
body.wx-chat .dialogue-footer { display: none !important; }
/* ★导出必须关掉聊天背景层（0916 修「开头十几条没头像、后面才显示」）：
   chat_exact.css 把背景画在 .dialogue::before（absolute + z-index:0，专治运行态
   背景钉屏）。运行态 .dialogue-section 是定位元素、整层压在背景上没事；但导出
   布局把 .dialogue-section 改成 static —— 静态内容（头像 img）画到 z-index:0 的
   ::before 之下，被它盖住；::before 的 height:100% 又解析成视口高（1300），
   于是分界线以上头像全黑、以下正常。气泡/点评是定位元素幸免，更具迷惑性。
   导出时禁用之，.dialogue-section 自带 var(--wx-chat-bg) 背景色，观感不变。 */
html body.wx-chat .dialogue::before { content: none !important; display: none !important; }
/* 带点评的行收紧下边距（chat_exact.css 的 26px !important 行内样式压不过，
   必须用更高优先级规则）；点评行自身 padding 负责与下一条消息的间隔 */
body.wx-chat .dialogue-section .row:has(+ .wx-longnote) { margin-bottom: 4px !important; }
#chat-right-pill, .new-msg-count, .new-msg-dot { display: none !important; }
#msg-more { display: none !important; }
.wx-longnote {
    clear: both;
    position: relative;
    z-index: 5;            /* 压过气泡（p.text 是定位元素，会盖住非定位的注释） */
    font-weight: 700;
    font-size: 22px;
    line-height: 1.35;
    margin-top: -14px;     /* 压住气泡底缘约 6px（z-index:5 保证字在泡上面） */
    padding: 0 0 24px;
    letter-spacing: 0.5px;
}
.wx-longnote.wx-ending {
    margin-top: 0;
    padding-top: 36px;     /* 参考视频：CTA 与点评字之间留一大截空隙 */
}
"""

# ---- 清单测量 + 点评注入（在页面里执行；单对象参数）----
PAGE_JS = r"""
(payload) => {
  const notes = payload.notes || [];
  const ending = payload.ending || {};
  const sec = document.querySelector('.dialogue-section');
  if (!sec) return { error: 'no .dialogue-section' };

  // 1) 点评行：插到气泡行后面做兄弟块（行是 flex，塞进去会被挤没）。
  //    定位用 margin 偏移而非 padding 挤压——padding 方案会把内容宽度压到
  //    跟气泡一样窄，短泡下文字一字一行竖排（实测 bug）。
  const secRect = sec.getBoundingClientRect();
  const scs = getComputedStyle(sec);
  const cLeft = secRect.left + parseFloat(scs.paddingLeft || 0);
  const cRight = secRect.right - parseFloat(scs.paddingRight || 0);
  const secW = cRight - cLeft;
  const rows = [...sec.querySelectorAll(':scope > .row')];
  rows.forEach((row, i) => {
    const n = notes[i];
    if (!n || !n.text) return;
    const bubble = row.querySelector('p.text');
    const d = document.createElement('div');
    d.className = 'wx-longnote';
    d.textContent = n.text;
    d.style.color = n.color;
    row.insertAdjacentElement('afterend', d);
    if (!bubble) {                       // 无文字泡（图片消息等）：全宽左对齐
      d.style.textAlign = 'left';
      return;
    }
    const br = bubble.getBoundingClientRect();
    // 先量文字自然宽度（inline-block + nowrap 量完即恢复），再定位
    d.style.display = 'inline-block';
    d.style.whiteSpace = 'nowrap';
    const tw = d.getBoundingClientRect().width;
    d.style.display = '';
    d.style.whiteSpace = '';
    if (tw >= secW - 8) {                // 文字几乎全宽：整行排版不定位
      d.style.width = '100%';
      d.style.textAlign = row.classList.contains('self') ? 'center' : 'left';
      return;
    }
    if (row.classList.contains('self')) {
      // 黄字：居中于气泡下方
      const ml = (br.left + br.right) / 2 - tw / 2 - cLeft;
      d.style.marginLeft = Math.max(0, Math.min(ml, secW - tw)) + 'px';
    } else {
      // 蓝字：对齐泡内文字栏起点（泡左缘 + 泡自身内边距）
      const bpl = parseFloat(getComputedStyle(bubble).paddingLeft || 0);
      d.style.marginLeft = Math.min(br.left - cLeft + bpl, secW - tw) + 'px';
    }
  });

  // 2) 结尾 CTA：红字居中，插在消息区末尾（wx-ending 类与点评行区分）。
  //    清单里存「文字」的实际范围（Range 量测），供镜头做结尾全景取景
  let endingRect = null;
  if (ending.text) {
    const d = document.createElement('div');
    d.className = 'wx-longnote wx-ending';
    d.textContent = ending.text;
    d.style.color = ending.color || '#FF5656';
    d.style.width = '100%';
    d.style.textAlign = 'center';
    sec.appendChild(d);
    const rng = document.createRange();
    rng.selectNodeContents(d);
    const tr = rng.getBoundingClientRect();
    if (tr.width > 0) {
      endingRect = { x0: tr.left, y0: tr.top, x1: tr.right, y1: tr.bottom };
    }
  }

  // 3) 量测（页面无滚动，rect 即文档坐标；点评行挂到前一条消息上）
  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return { x0: r.left, y0: r.top, x1: r.right, y1: r.bottom };
  };
  const items = [];
  for (const el of sec.children) {
    const cl = el.classList;
    if (cl.contains('row')) {
      const bubble = el.querySelector('p.text');
      const head = el.querySelector('img.header');
      items.push({
        type: 'msg',
        side: cl.contains('self') ? 'R' : 'L',
        row: rectOf(el),
        bubble: bubble ? rectOf(bubble) : null,
        avatar: head ? rectOf(head) : null,   // 头像真值：镜头横向取景要整颗入画
        note: null,
      });
    } else if (cl.contains('wx-ending')) {
      // CTA 矩形已在上方用 Range 量过（endingRect），此处跳过
    } else if (cl.contains('wx-longnote')) {
      if (items.length && items[items.length - 1].type === 'msg') {
        const r0 = rectOf(el);
        // 文字实际范围（Range 量测）：点评 div 是块级整行宽，div 矩形≠文字宽，
        // 长蓝字配短泡时镜头要按文字宽度拉远装下（清单里存 tx0/tx1）
        const rng = document.createRange();
        rng.selectNodeContents(el);
        const tr = rng.getBoundingClientRect();
        r0.tx0 = tr.left; r0.tx1 = tr.right;
        items[items.length - 1].note = r0;
      }
    } else if (cl.contains('msg-time')) {
      items.push({ type: 'time', rect: rectOf(el) });
    } else if (cl.contains('msg-system')) {
      items.push({ type: 'system', rect: rectOf(el) });
    }
  }
  const dump = [...sec.querySelectorAll('.wx-longnote')].slice(0, 3)
    .map(el => ({ txt: (el.textContent || '').slice(0, 6),
                  top: Math.round(el.getBoundingClientRect().top) }));
  return { items, section: rectOf(sec),
           docH: document.documentElement.scrollHeight, noteDump: dump,
           ending: endingRect };
}
"""


def _read(name):
    with open(os.path.join(ENHANCE, name), "r", encoding="utf-8") as f:
        return f.read()


def _port_open(port):
    """端口是否有人监听。

    ⚠️ 不能用 connect_ex + settimeout：Windows 上带超时的 socket 是非阻塞的，
    connect_ex 立刻返回 WSAEWOULDBLOCK(10035)，会把「前端在跑」误判成「没在跑」。
    改用阻塞 connect()（内部按 timeout 等待），失败重试 3 次。
    """
    for _ in range(3):
        s = socket.socket()
        s.settimeout(2.0)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.3)
        finally:
            try:
                s.close()
            except OSError:
                pass
    return False


def _msg_kind(b):
    """判定一条 block 的消息类型（老的 side/text/img 写法完全不变）。

    显式 kind 优先（截图模式用），否则按字段猜：有 img→image、有 emoji/voice/link→对应类型。
    """
    k = (b.get("kind") or "").strip().lower()
    if k in ("text", "image", "emoji", "voice", "link"):
        return k
    if (b.get("img") or b.get("image") or "").strip():
        return "image"
    if (b.get("emoji") or "").strip():
        return "emoji"
    if b.get("voice"):
        return "voice"
    if isinstance(b.get("link"), dict) or b.get("link"):
        return "link"
    return "text"


def blocks_to_payload(cfg):
    """长图模式 JSON → setHomeList 消息 + 点评清单。

    支持 text / image / emoji / voice / link 五类消息（与仿真运行时 config.js 同口径）：
      {"kind":"emoji", "image": "/images/wxemoji3d/x.gif"}
      {"kind":"voice", "seconds": 6}
      {"kind":"link",  "title": "花艺课", "image": "/images/link/男生.jpg", "source": "恋爱技巧"}
    """
    meta = cfg.get("meta") or {}
    msgs, notes = [], []
    for b in cfg.get("blocks") or []:
        kind = _msg_kind(b)
        text = (b.get("text") or "").strip()
        img = (b.get("img") or b.get("image") or "").strip()
        if kind == "text" and not text:
            continue
        if kind == "image" and not img:
            continue
        side = b.get("side", "peer")
        m = {"dir": "me" if side == "me" else "other", "kind": kind}
        if kind == "image":
            m["image"] = img
            if text:
                m["text"] = text
        elif kind == "emoji":
            m["image"] = (b.get("emoji") or img or "").strip()
        elif kind == "voice":
            try:
                m["seconds"] = max(1, int(float(b.get("voice") or b.get("seconds") or 1)))
            except (TypeError, ValueError):
                m["seconds"] = 1
        elif kind == "link":
            lk = b.get("link") if isinstance(b.get("link"), dict) else {"title": b.get("link")}
            m["title"] = (lk.get("title") or text or "").strip()
            m["image"] = (lk.get("image") or b.get("img") or "").strip()
            m["source"] = (lk.get("source") or "").strip()
        else:
            m["text"] = text
        if b.get("time"):
            m["time"] = b["time"]
        msgs.append(m)
        note = (b.get("note") or "").strip()
        notes.append({
            "text": note,
            "color": b.get("note_color") or (NOTE_YELLOW if side == "me" else NOTE_BLUE),
        })
    ending = cfg.get("ending") or {}
    return meta, msgs, notes, {
        "text": (ending.get("note") or "").strip(),
        "color": {"red": NOTE_RED, "blue": NOTE_BLUE,
                  "yellow": NOTE_YELLOW}.get(ending.get("color"), NOTE_RED),
    }


def _inject_overlays(page):
    """与 main.py inject_overlays 同源的增强注入（裁掉打字/键盘等录制专属层）。"""
    page.add_style_tag(content=".welcome { display: none !important; }")
    page.add_style_tag(content="#webpack-dev-server-client-overlay { pointer-events: none !important; }")
    page.add_style_tag(content=_read("harmony_font.css"))
    page.add_style_tag(content=_read("iphone_frame.css"))
    page.add_style_tag(content=_read("weui_tokens.css"))
    page.add_style_tag(content=_read("wechat_modern.css"))
    page.add_style_tag(content=_read("transfer_ui.css"))
    page.add_style_tag(content=_read("send_image_ui.css"))
    page.add_style_tag(content=_read("peer_pages.css"))
    page.add_style_tag(content=_read("block_ui.css"))
    page.add_style_tag(content=_read("video_player.css"))
    page.add_style_tag(content=_read("homepage_exact.css"))
    for name in ("config.js", "chat_extra.js", "iphone_frame.js",
                 "wxemoji_map.js", "emoji_map.js", "transfer_ui.js",
                 "send_image_ui.js", "video_player.js", "peer_pages.js",
                 "block_ui.js"):
        page.evaluate(_read(name))
    page.add_style_tag(content=_read("chat_exact.css"))   # 必须最后（压过 JS 注入的样式）


def _wait_imgs(page, timeout=8000):
    """只等消息区里「可见的图」解码完成（隐藏的失效贴纸图等不出 naturalWidth）。"""
    page.wait_for_function(
        "() => [...document.querySelectorAll('.dialogue-section img')]"
        ".every(i => i.complete && (!i.offsetWidth || i.naturalWidth > 0))",
        timeout=timeout)


def run_once(cfg, dsf, shot_path, opts=None):
    """跑一遍导出，返回 (量测数据, 页面高度)。

    opts（截图模式用，全部可选，默认 None = 长图模式原行为，逐字节不变）：
      hide_statusbar / hide_header  不画 iOS 状态栏 / 微信顶栏
      badge        顶栏未读胶囊的数字；''=隐藏（默认由 chat_extra.js 写 99）
      bg           聊天背景图 URL（/images/bg/xxx.jpg）；导出态改为纵向平铺
      want_manifest 是否量测消息矩形（长图模式要，截图默认不需要，但量测本身几乎不耗时）
    """
    opts = opts or {}
    from playwright.sync_api import sync_playwright

    meta, msgs, notes, ending = blocks_to_payload(cfg)
    peer_name = meta.get("peer_name") or "朋友"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": VIEW_W, "height": VIEW_H},
            device_scale_factor=dsf)
        page = ctx.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_selector(".app-content, .wechat-list, #app .weui-tab", timeout=60_000)
        _inject_overlays(page)

        # 数据注入：与运行时同一入口
        me = {}
        if meta.get("my_name"):
            me["name"] = meta["my_name"]
        if meta.get("my_avatar"):
            me["avatar"] = meta["my_avatar"]
        if me:
            page.evaluate("(m) => window.__wxConfig.setMe(m)", me)
        page.evaluate(
            "(p) => window.__wxConfig.setHomeList([p])",
            {"name": peer_name,
             "avatar": meta.get("peer_avatar") or "",
             "messages": msgs, "read": True, "newMsgCount": 0})
        # 聊天背景：写入 --wx-chat-bg（导出态 .dialogue-section 直接吃这个变量）。
        # 必须在进聊天页前后、加导出 CSS 之前设置，避免被后续 apply() 覆盖。
        bg = (opts.get("bg") or "").strip()
        if bg:
            page.evaluate("(u) => window.__wxConfig.setChatBg(u)", bg)

        # 进入聊天页
        url = BASE_URL + "wechat/dialogue?mid=1000&name=%s&group_num=1" \
            % urllib.parse.quote(peer_name)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector(".dialogue-section .row", timeout=30_000)
        # 顶栏未读胶囊（chat_extra.js 默认挂一个写死 99 的 .nav-unread）：
        # 截图模式可指定数字或 '' 隐藏；不传则完全不动它。
        if "badge" in opts and opts.get("badge") is not None:
            page.evaluate("""(v) => {
                const hd = document.querySelector('.dialogue #wx-header');
                if (!hd) return;
                let el = hd.querySelector('.nav-unread');
                if (!el) {
                    el = document.createElement('span');
                    el.className = 'nav-unread';
                    hd.appendChild(el);
                }
                if (v === '') { el.style.display = 'none'; }
                else { el.style.display = ''; el.textContent = String(v); }
            }""", str(opts.get("badge")))

        n_rows = page.evaluate("document.querySelectorAll('.dialogue-section > .row').length")
        if n_rows != len(notes):
            print("[警告] 行数 %d != 消息数 %d（清单按实际行对齐）" % (n_rows, len(notes)))
            notes = notes[:n_rows] + [None] * max(0, n_rows - len(notes))
        _wait_imgs(page)
        try:
            page.evaluate("() => document.fonts.ready")
        except Exception:                                 # noqa: BLE001
            pass
        page.wait_for_timeout(400)

        # 导出覆盖 + 注释注入 + 量测
        css = EXPORT_CSS
        if opts.get("hide_statusbar"):
            # ★选择器必须带 body.wx-chat:not(.wx-chat-persist) 前缀：chat_exact.css 里
            # 有一条同属性的 display:block !important（更高优先级），裸 #id 压不过它
            css += ("\nhtml body.wx-chat:not(.wx-chat-persist) #ios-statusbar"
                    " { display: none !important; }\n")
        if opts.get("hide_header"):
            css += "\nbody.wx-chat .dialogue #wx-header { display: none !important; }\n"
        if bg:
            # 导出态的长图可以上万像素高，聊天背景必须纵向平铺而不是 cover
            # （cover 在 600×8000 的条幅上会放大到只剩图心一块，完全不是微信观感）。
            css += ("\nbody.wx-chat .dialogue-section {"
                    " background-size: 600px auto !important;"
                    " background-repeat: repeat-y !important;"
                    " background-position: top center !important; }\n")
        page.add_style_tag(content=css)
        # 状态栏节点是 iphone_frame.js 在 body 末尾 appendChild 的，转文档流后会
        # 掉到整张长图最底部；挪到 body 首位，让「状态栏→顶栏→消息」顺序与真机一致
        page.evaluate("""() => {
            const sb = document.getElementById('ios-statusbar');
            if (sb && sb !== document.body.firstChild) {
                document.body.insertBefore(sb, document.body.firstChild);
            }
        }""")
        page.evaluate("(a) => { window.scrollTo(0, 0); }")
        data = page.evaluate(PAGE_JS, {"notes": notes, "ending": ending})
        if data and data.get("error"):
            raise RuntimeError("量测失败: %s" % data["error"])
        page.wait_for_timeout(200)
        _wait_imgs(page)

        page.screenshot(path=shot_path, full_page=True, type="png")
        browser.close()

    h_css = data["docH"]
    return data, h_css


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", default=os.path.join(
        ROOT, "_工作文件", "_参考_长图模式", "wx长图"))
    ap.add_argument("--tag", default=time.strftime("%m%d_%H%M"))
    args = ap.parse_args()

    if not _port_open(PORT):
        print("[错误] 前端 8080 未运行：先随便跑一次 main.py / 启动.bat 把 vue-WeChat 拉起来")
        return 1

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    os.makedirs(args.out_dir, exist_ok=True)
    stem = os.path.join(args.out_dir, "wxshot_" + args.tag)

    # 第一遍 dsf=1 量高度 → 选 dsf（截图单边 ≤ MAX_SHOT_PX）→ 第二遍正式出图
    _, h_css = run_once(cfg, 1, stem + "_probe.png")
    try:
        os.remove(stem + "_probe.png")
    except OSError:
        pass
    dsf = max(1, min(3, int(MAX_SHOT_PX // max(1, h_css))))
    if dsf < 3:
        print("[提示] 长图较高（%dpx），倍率降为 %dx" % (h_css, dsf))
    shot = stem + ".png"
    data, _ = run_once(cfg, dsf, shot)

    manifest = {
        # 存项目相对路径：项目在 U 盘里，盘符随电脑变，绝对路径换机即失效
        "image": os.path.relpath(shot, ROOT).replace("\\", "/"),
        "css_width": VIEW_W,
        "dsf": dsf,
        "width_px": VIEW_W * dsf,
        "section": data.get("section"),
        "items": data["items"],
        "ending": data.get("ending"),
    }
    mpath = stem + ".manifest.json"
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("[完成] 长图: %s (%dx%d)" % (shot, manifest["width_px"],
                                       int(data["docH"] * dsf)))
    print("[完成] 清单: %s (%d 条目)" % (mpath, len(data["items"])))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
