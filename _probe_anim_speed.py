# -*- coding: utf-8 -*-
"""动画速度曲线探针（在页面内 rAF 采样，最准）。

「触发 + 逐帧采样」在同一个求值单元内完成，避免 Python↔浏览器往返吃掉动画开头。

判读口径：
  · 位移型（滑入/滑出）→ 归一化成 0..1 进度，看 25/50/75% 时间点的进度与速度峰值时刻；
      先快后缓：25% 时间点进度远大于 25%，速度峰值 < 42% 时刻；
      先慢后快：25% 时间点进度接近 0，速度峰值 > 58% 时刻。
  · 脉冲型（弹出/落指）→ 首尾同值，改用「偏离基线的幅度峰值」与出现时刻判定。

用法: py _probe_anim_speed.py
"""
import os
from playwright.sync_api import sync_playwright

ROOT = r"G:\weixin-auto"
ENH = os.path.join(ROOT, "enhance")

CSS = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
       "wechat_modern.css", "human_actions.css", "transfer_ui.css",
       "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
       "homepage_exact.css"]
CSS_TFD = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
           "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css"]
JS = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js", "wxemoji_map.js",
      "emoji_map.js", "transfer_ui.js", "send_image_ui.js", "video_player.js",
      "peer_pages.js", "block_ui.js"]
JS_TFD = ["config.js", "chat_extra.js", "iphone_frame.js", "transfer_ui.js", "transfer_detail.js"]


def rd(p):
    return open(p, encoding="utf-8").read()


SAMPLER = """
(a) => new Promise(res => {
  const {trigger, sel, idx, ms, pseudo} = a;
  const el = document.querySelector(sel);
  if (!el) return res('NO-ELEMENT:' + sel);
  const read = () => {
    const cs = getComputedStyle(el, pseudo || undefined);
    const t = cs.transform;
    const m = new DOMMatrixReadOnly(!t || t === 'none' ? '' : t);
    return idx === 'scale' ? m.a : (idx === 'tx' ? m.m41 : m.m42);
  };
  const out = [[0, read()]];
  try { eval(trigger); } catch (e) { return res('TRIGGER-ERR:' + e.message); }
  const t0 = performance.now();
  const tick = () => {
    out.push([performance.now() - t0, read()]);
    if (performance.now() - t0 < ms) requestAnimationFrame(tick); else res(out);
  };
  requestAnimationFrame(tick);
})
"""


def report(name, samples, note="", want="fast"):
    if isinstance(samples, str) or not samples or len(samples) < 4:
        print("  %-16s 采样失败: %s" % (name, samples))
        return
    v0, v1 = samples[0][1], samples[-1][1]
    span = v1 - v0

    # ---- 脉冲型：首尾同值 ----
    if abs(span) < 1e-6:
        dev = max(abs(s[1] - v0) for s in samples)
        if dev < 1e-6:
            print("  %-16s 无任何变化" % name)
            return
        peak_s = max(samples, key=lambda s: abs(s[1] - v0))
        t_ext = [s[0] for s in samples if abs(abs(s[1] - v0) - dev) < dev * 0.03]
        last = max([s[0] for s in samples if abs(s[1] - v0) > dev * 0.03] or [peak_s[0]])
        shape = "、".join("%dms:%+.3f" % (s[0], s[1] - v0)
                         for s in samples[::max(1, len(samples) // 8)][:8])
        print("  %-16s 脉冲型 时长≈%3dms 极值%+.3f(基线%.3f) 出现在 %d~%dms"
              % (name, round(last), peak_s[1] - v0, v0, round(min(t_ext)), round(max(t_ext))))
        print("  %-16s 波形 %s   %s" % ("", shape, note))
        return

    # ---- 位移型 ----
    last = samples[-1][0]
    for i in range(len(samples) - 1, 0, -1):
        if abs(samples[i][1] - samples[i - 1][1]) > abs(span) * 0.002:
            last = samples[i][0]
            break
    marks = []
    for frac in (0.25, 0.5, 0.75):
        near = min(samples, key=lambda s: abs(s[0] - last * frac))
        marks.append((frac, (near[1] - v0) / span * 100))
    best, bestT = 0.0, 0.0
    for i in range(1, len(samples)):
        dt = samples[i][0] - samples[i - 1][0]
        if dt > 0:
            sp = abs(samples[i][1] - samples[i - 1][1]) / dt
            if sp > best:
                best, bestT = sp, samples[i][0]
    peak = round(bestT / last * 100) if last else 0
    if want == "fast":
        verdict = "先快后缓 ✓" if peak < 42 else ("偏匀速" if peak <= 58 else "先慢后快 ✗")
    elif want == "slow":
        verdict = "先慢后快 ✓" if peak > 58 else ("偏匀速" if peak >= 42 else "先快后缓 ✗")
    else:
        verdict = "-"
    print("  %-16s 位移型 时长≈%3dms  %s" % (name, round(last),
          "  ".join("%d%%时间→%3d%%进度" % (f * 100, p) for f, p in marks)))
    print("  %-16s 速度峰值在 %2d%% 时刻 → %s   %s" % ("", peak, verdict, note))


def boot(pg, css, js, keyboard=False):
    pg.goto("http://localhost:8080/#/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.add_style_tag(content=".welcome { display: none !important; }")
    for f in css:
        pg.add_style_tag(content=rd(os.path.join(ENH, f)))
    for f in js:
        pg.evaluate(rd(os.path.join(ENH, f)))
    if keyboard:
        pg.evaluate(rd(os.path.join(ENH, "keyboard.js")))
    pg.wait_for_timeout(500)


# 让转账层脱离 display:none（Chrome 对 display:none 子树把 transform 解析为 none）
SHOW = "()=>{const e=document.querySelector('#wxTransferAmount');if(e)e.parentElement.style.display='block';}"


def run(pg, name, trigger, sel, idx, ms, want="fast", note="", pseudo=None):
    report(name, pg.evaluate(SAMPLER, {"trigger": trigger, "sel": sel, "idx": idx,
                                       "ms": ms, "pseudo": pseudo}), note, want)


def cls(sel, op, c):
    s = sel.replace('"', '\\"')
    return "(function(){document.querySelector(\"%s\").classList.%s(\"%s\");})()" % (s, op, c)


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 600, "height": 1300})
    boot(pg, CSS, JS, keyboard=True)

    print("=== 一、金额页 / 金额键盘（目标：更快 + 先快后缓 / 退场先慢后快） ===")
    pg.evaluate("window.__wxTransfer.openAmount('小星')")
    pg.wait_for_timeout(1400)
    pg.evaluate(SHOW)
    pg.evaluate(cls("#wxTransferAmount", "remove", "open"))
    pg.wait_for_timeout(500)
    run(pg, "金额页推入", cls("#wxTransferAmount", "add", "open"),
        "#wxTransferAmount", "tx", 600, "fast", "（原 260ms 对称缓动）")

    pg.wait_for_timeout(400)
    pg.evaluate(cls("#taKeyboard", "remove", "kb-up") + ";" + cls("#taKeyboard", "remove", "kb-down"))
    pg.wait_for_timeout(500)
    run(pg, "金额键盘升起", cls("#taKeyboard", "add", "kb-up"),
        "#taKeyboard", "ty", 700, "fast", "（原 300ms 对称缓动）")
    pg.wait_for_timeout(200)
    run(pg, "金额键盘落下", cls("#taKeyboard", "add", "kb-down"),
        "#taKeyboard", "ty", 600, "slow", "（原 280ms 对称缓动）")

    print("\n=== 二、微信支付 toast / 付款面板（目标：更快 + 先快后缓） ===")
    pg.evaluate(cls("#wxPayToast", "remove", "show"))
    pg.wait_for_timeout(400)
    run(pg, "toast 卡片弹出", cls("#wxPayToast", "add", "show"),
        "#wxPayToast .pay-toast-card", "scale", 600, "pop", "（原 200ms ease，无过冲）")
    pg.wait_for_timeout(300)
    pg.evaluate(cls("#wxPaySheet", "remove", "open"))
    pg.wait_for_timeout(500)
    run(pg, "付款面板滑起", cls("#wxPaySheet", "add", "open"),
        "#wxPaySheet .pay-sheet", "ty", 700, "fast", "（原 300ms 对称缓动）")

    print("\n=== 三、密码点 / 按键落指（脉冲型，目标：过冲/下压，打破「瞬间出现」） ===")
    pg.wait_for_timeout(600)
    run(pg, "密码点落位",
        "(function(){document.querySelector('#pwKeyboard .tkr-key[data-key=\"1\"]').click();})()",
        "#payBoxes i:nth-child(1)", "scale", 400, "pop", "（原：瞬间出现，无过程）", pseudo="::after")
    run(pg, "按键落指",
        "(function(){document.querySelector('#pwKeyboard .tkr-key[data-key=\"2\"]').click();})()",
        "#pwKeyboard .tkr-key[data-key=\"2\"]", "scale", 400, "pop", "（原：仅 100ms 底色，无位移）")

    print("\n=== 四、支付成功页（目标：更快 + 先快后缓） ===")
    pg2 = b.new_page(viewport={"width": 600, "height": 1300})
    boot(pg2, CSS, JS)
    pg2.evaluate(SHOW)
    run(pg2, "成功页滑入", cls("#wxPaySuccess", "add", "open"),
        "#wxPaySuccess", "ty", 700, "fast", "（原 320ms 对称缓动）")

    print("\n=== 五、转账详情页（目标：更快 + 先快后缓） ===")
    pg3 = b.new_page(viewport={"width": 600, "height": 1300})
    boot(pg3, CSS_TFD, JS_TFD)
    run(pg3, "详情页推入", cls("#wxTfDetail", "add", "open"),
        "#wxTfDetail", "tx", 800, "fast", "（原 400ms 对称缓动）")

    b.close()
print("\nPROBE DONE")
