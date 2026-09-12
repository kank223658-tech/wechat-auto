# -*- coding: utf-8 -*-
"""冒烟：发表情包 / emoji 之后【直接切到键盘】（表情下滑 + 键盘同帧上滑，A→B 直线）。

在页面里用 rAF 逐帧采样 .dialogue-footer 的 translateY(m42)：
  · 起点 = 表情面板态（输入栏被抬到 --emoji-h）
  · 终点 = 键盘态（输入栏被抬到 --kb-h）
  · 判据：整段位移【单调】(不回头) 且【不经过 0】（不退回聊天底部），
          末态 body 带 wxkb-open、__wxKeyboard.visible === true。
另外采样表情面板自身的 m42（应朝 +100% 方向下滑）与消息区高度。
"""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

WORK = [{"name": "小星", "lastText": "七点老地方见", "time": "18:26", "unread": 0,
         "messages": [{"dir": "peer", "kind": "text", "text": "在忙吗？", "time": "18:20"},
                      {"dir": "me", "kind": "text", "text": "刚忙完，怎么啦"},
                      {"dir": "peer", "kind": "text", "text": "晚上一起吃饭？"},
                      {"dir": "me", "kind": "text", "text": "好啊，几点"}]}]

SAMPLER = """(cfg) => new Promise((res) => {
    const f = document.querySelector('.dialogue-footer');
    const sec = document.querySelector('.dialogue-section');
    const t0 = performance.now();
    const frames = [];
    const cls = [];
    let lastCls = '';
    const tick = () => {
        const m = new DOMMatrixReadOnly(getComputedStyle(f).transform);
        const p = document.querySelector('.wx-emoji-panel');
        const pm = p ? new DOMMatrixReadOnly(getComputedStyle(p).transform) : null;
        frames.push([+(performance.now() - t0).toFixed(0), +m.m42.toFixed(1),
                     pm ? +pm.m42.toFixed(1) : null,
                     sec ? +sec.getBoundingClientRect().height.toFixed(1) : null]);
        const c = document.body.className;
        if (c !== lastCls) { cls.push([+(performance.now() - t0).toFixed(0), c]); lastCls = c; }
        if (performance.now() - t0 < cfg.ms) requestAnimationFrame(tick);
        else res({frames: frames, cls: cls,
                  kbVisible: !!(window.__wxKeyboard && window.__wxKeyboard.visible),
                  cur: window.__wxPanels ? window.__wxPanels.current() : '?'});
    };
    requestAnimationFrame(tick);
    /* 触发端：脚本动作（与 main.py 的 _chat_ext 同一入口） */
    if (cfg.kind === 'emoji3d') window.__wxChatExt.selfEmoji3D(cfg.payload, null, 'kb');
    else window.__wxChatExt.selfEmoji(cfg.payload, null, 'kb');
})"""


def report(tag, res, canvas_scale):
    fr = res["frames"]
    t_ps = None
    for t, c in res["cls"]:
        if "wx-pswitch" in c and t_ps is None:
            t_ps = t
    print(f"\n===== {tag} =====")
    print("末态：body=%s  __wxKeyboard.visible=%s  __wxPanels.current=%s"
          % (res["cls"][-1][1], res["kbVisible"], res["cur"]))
    print("body 类时间线:")
    prev = None
    for t, c in res["cls"]:
        print("    t=%4dms  %s" % (t, c))
    if t_ps is None:
        print("  ★ 未观察到 .wx-pswitch（没有走直接切换）")
        return
    # ---- 只分析「直接切换」这一段：从挂上 .wx-pswitch 的那一帧起 ----
    win = [f for f in fr if t_ps - 20 <= f[0] <= t_ps + 420]
    ys = [f[1] for f in win]
    ts = [f[0] for f in win]
    print("  切换段 t=%dms 起，共 %d 帧" % (t_ps, len(win)))
    print("    时间: " + " ".join("%.0f" % t for t in ts))
    print("    位移: " + " ".join("%.0f" % y for y in ys))
    d = [round(ys[k + 1] - ys[k], 1) for k in range(len(ys) - 1)]
    signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in d if abs(v) > 0.4]
    mono = (not signs) or all(s == signs[0] for s in signs)
    y0, y1 = ys[0], ys[-1]
    # 运动帧：与起点、终点都差 >2px（避免把静止平台算进时长）
    mv = [i for i, y in enumerate(ys) if abs(y - y0) > 2 and abs(y - y1) > 2]
    dur = (ts[mv[-1]] - ts[mv[0]]) if mv else 0
    print("    → 行程 %.0fpx（画布 %.0fpx） 实测可见运动 %dms（CSS 声明 230ms；"
          "72px 小行程下 S 曲线两端为亚像素，故测得略短）"
          % (y1 - y0, (y1 - y0) * canvas_scale, dur))
    print("    → 单调性: %s" % ("单向直达 ✓" if mono else "★非单调 " + str(signs)))
    near0 = [y for y in ys[1:-1] if abs(y) < 20]
    print("    → 是否经过 0（即先退回收起态）: %s"
          % ("是 ★ 中途出现 " + str(near0) if near0 else "否 ✓（全程在 %d~%d 之间）" % (min(ys), max(ys))))
    pmy = [f[2] for f in win if f[2] is not None]
    if pmy:
        print("    → 表情面板 translateY 在切换段: %.0f → %.0f（增大到 100%% = 滑出屏）"
              % (pmy[0], pmy[-1]))
    secy = [f[3] for f in win if f[3] is not None]
    if secy:
        print("    → 消息区高度: %.0f → %.0f" % (secy[0], secy[-1]))


with sync_playwright() as pw:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    br = pw.chromium.launch(headless=True,
                            executable_path=chrome if os.path.isfile(chrome) else None)
    ctx = br.new_context(viewport={"width": main.VIEWPORT_W, "height": main.VIEWPORT_H},
                         device_scale_factor=main.DEVICE_SCALE_FACTOR,
                         user_agent=main.MOBILE_UA, is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
    main.inject_overlays(page)
    page.wait_for_timeout(900)
    page.evaluate("(d) => window.__wxConfig && window.__wxConfig.setHomeList(d)", WORK)
    page.wait_for_timeout(300)
    page.evaluate("""() => { const li = document.querySelector('.wechat-list li .list-info');
                             if (li) li.click(); }""")
    page.wait_for_timeout(1400)
    print("进入聊天页，当前面板态:", page.evaluate("window.__wxPanels.current()"))

    # ---- 场景 1：emoji（3D 小表情）发完 → 直接切键盘 ----
    # 先摆到「键盘 → 表情」的稳态起点（脚本真实链路就是先开键盘再开面板）
    page.evaluate("window.__wxKeyboard.show()")
    page.wait_for_timeout(500)
    page.evaluate("window.__wxChatExt.selfEmoji3D([3], null, 'close')")
    page.wait_for_timeout(2600)      # 等它按原逻辑收起，回到「收起」态
    print("\n[准备] 场景1 之前的面板态:", page.evaluate("window.__wxPanels.current()"))

    res1 = page.evaluate(SAMPLER, {"kind": "emoji3d", "payload": [3], "ms": 3200})
    report("场景1  emoji3D → 键盘（直接切换）", res1, 1.0)

    page.wait_for_timeout(600)
    print("\n[场景1 结束] 面板态:", page.evaluate("window.__wxPanels.current()"),
          " 键盘可见:", page.evaluate("window.__wxKeyboard && window.__wxKeyboard.visible"))

    # ---- 场景 2：表情包贴纸发完 → 直接切键盘 ----
    lk = page.evaluate("() => window.__wxPreWarmDump ? '' : "
                       "'/images/avatar/赵本山表情包_20260903_193137_046.jpg'")
    print("\n[准备] 贴纸素材:", lk)
    if lk:
        page.evaluate("window.__wxKeyboard.show()")
        page.wait_for_timeout(500)
        res2 = page.evaluate(SAMPLER, {"kind": "sticker", "payload": lk, "ms": 3200})
        report("场景2  表情包贴纸 → 键盘（直接切换）", res2, 1.0)

    br.close()
print("\n[完成]")
