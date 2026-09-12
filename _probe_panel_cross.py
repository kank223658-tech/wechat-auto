# -*- coding: utf-8 -*-
"""探针：表情面板→「+」面板切换过程中，+ 面板是否半透明（穿模根因）。
一次性验证实例（8080 + 8002 渲染器无关，自建浏览器），只读页面状态。
判定：
  before(修复前) attach 面板 opacity 在上滑过程中从 0 渐变到 1（半透明=表情内容透出）
  after(修复后)  attach 面板 opacity 全程恒为 1
"""
import json
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
ENH = r"G:/weixin-auto/enhance/"

# 与 main.py inject_overlays() / _embed_boot.js 同序（embed boot 需要编辑器 8000
# 提供 /enhance 静态文件，这里直接从磁盘读、按序注入，等价且不依赖 8000）
CSS_BASE = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
            "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css",
            "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
            "homepage_exact.css"]
JS_ORDER = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
            "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "transfer_detail.js",
            "send_image_ui.js", "video_player.js", "peer_pages.js", "block_ui.js", "homepage.js"]
CSS_POST = ["chat_exact.css", "panel_switch.css", "wx_icons.css", "moments_exact.css",
            "discover_exact.css"]

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

SWITCH_JS = r"""
() => new Promise((resolve) => {
  const P = window.__wxPanels;
  if (!P) { resolve({error: 'no __wxPanels'}); return; }
  P.set('emoji');
  setTimeout(() => {
    const at = document.getElementById('wxTransferPanel');
    const em = document.querySelector('.wx-emoji-panel');
    const samples = [];
    const t0 = performance.now();
    P.set('attach');
    function tick() {
      const t = Math.round(performance.now() - t0);
      const a = document.getElementById('wxTransferPanel');
      const e = document.querySelector('.wx-emoji-panel');
      const ca = a ? getComputedStyle(a) : null;
      const ce = e ? getComputedStyle(e) : null;
      samples.push({
        t,
        attachOpacity: ca ? ca.opacity : null,
        attachVis: ca ? ca.visibility : null,
        attachTf: ca ? ca.transform : null,
        emojiOpacity: ce ? ce.opacity : null,
        emojiTf: ce ? ce.transform : null,
      });
      if (performance.now() - t0 < 450) requestAnimationFrame(tick);
      else {
        const ca2 = getComputedStyle(document.getElementById('wxTransferPanel'));
        resolve({samples, restOpacity: ca2.opacity, restVis: ca2.visibility});
      }
    }
    requestAnimationFrame(tick);
  }, 700);
})
"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 620, "height": 1340})
    pg.goto(URL, wait_until="domcontentloaded")
    pg.evaluate("document.querySelector('.welcome') && (document.querySelector('.welcome').style.display='none')")
    for n in CSS_BASE:
        pg.add_style_tag(content=read(ENH + n))
    # 与 main.py 一致：先注入默认场景（config.js applyPersistentDefaults 会应用）
    pg.evaluate("window.__wxDefaultScene = %s" % read(r"G:/weixin-auto/scene.json"))
    for n in JS_ORDER:
        pg.add_script_tag(content=read(ENH + n))
    for n in CSS_POST:
        pg.add_style_tag(content=read(ENH + n))
    pg.wait_for_function("!!window.__wxChatExt && !!window.__wxTransfer", timeout=30000)
    # panel_switch.js 单独补（main.py 里是内联注入）
    pg.add_script_tag(content=read(ENH + "panel_switch.js"))
    pg.wait_for_function("!!window.__wxPanels", timeout=10000)
    # 兜底：探针页面无 main.py 的 apply() 触发链，显式应用场景 + 直接进聊天路由
    pg.evaluate("window.__wxConfig.applyScene(window.__wxDefaultScene)")
    pg.evaluate("location.hash = '#/wechat/dialogue'")
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(600)
    pg.wait_for_timeout(1500)
    print("route:", pg.evaluate("() => { const a=document.getElementById('app'); return a && a.__vue__ ? a.__vue__.$route.fullPath : 'novm'; }"))
    print("cells:", pg.evaluate("""
      () => {
        const sels = ['#wechat .wechat-list .weui-cell', '.weui-cell', '.chat-cell', '.wechat-list', '#wechat'];
        for (const s of sels) { const n = document.querySelectorAll(s); if (n.length) return s + ' x' + n.length; }
        return 'none';
      }
    """))
    pg.evaluate("""
      () => {
        const cells = document.querySelectorAll('#wechat .wechat-list .weui-cell');
        if (cells.length) { cells[0].click(); return 'clicked'; }
        return 'no-cell';
      }
    """)
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(600)
    out = pg.evaluate(SWITCH_JS)
    s = out.get('samples', [])
    # 压缩输出：打印每帧关键字段
    for f in s:
        print(f"t={f['t']:>3}ms attachOpacity={f['attachOpacity']} vis={f['attachVis']} emojiTf={f['emojiTf']}")
    print("REST:", out.get('restOpacity'), out.get('restVis'))
    b.close()
