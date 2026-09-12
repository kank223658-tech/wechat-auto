# -*- coding: utf-8 -*-
"""探针：转账气泡上屏动画 vs 文本气泡（一次性验证，无录制污染）。
复刻 main.py inject_overlays 的注入顺序（跳过键盘/Rime/真人行为层，与转账上屏无关），
再分别用 store 路径上屏「文本」与「转账」两条消息，逐帧采样行的 computed style。
"""
import json
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(ROOT, "enhance")


def _read(name):
    with open(os.path.join(ENH, name), encoding="utf-8") as f:
        return f.read()


CSS_BASE = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
            "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css",
            "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
            "homepage_exact.css"]
JS_ORDER = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
            "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "transfer_detail.js",
            "send_image_ui.js", "video_player.js", "peer_pages.js", "block_ui.js"]
CSS_POST = ["chat_exact.css", "panel_switch.css", "wx_icons.css", "moments_exact.css",
            "discover_exact.css", "contacts_exact.css", "self_exact.css"]

SAMPLE_JS_TMPL = r"""
() => new Promise((resolve) => {
  const sec = document.querySelector('.dialogue-section');
  if (!sec) { resolve({error: 'no dialogue-section'}); return; }
  const before = new Set(Array.from(sec.querySelectorAll('.row')));
  const fire = FN_BODY;
  const samples = [];
  const t0 = performance.now();
  function tick() {
    const rows = Array.from(sec.querySelectorAll('.row'));
    let fresh = null;
    for (let i = rows.length - 1; i >= 0; i--) {
      if (!before.has(rows[i])) { fresh = rows[i]; break; }
    }
    if (fresh) {
      const cs = getComputedStyle(fresh);
      samples.push({
        t: Math.round(performance.now() - t0),
        rowOpacity: cs.opacity,
        rowTransform: cs.transform,
        rowAnim: cs.animationName + '/' + cs.animationDuration,
        cls: fresh.className,
      });
    } else {
      samples.push({ t: Math.round(performance.now() - t0), row: 'not-yet' });
    }
    if (performance.now() - t0 < 900) requestAnimationFrame(tick);
    else resolve(samples);
  }
  requestAnimationFrame(tick);
})
"""

FIRE_TEXT = ("() => { const vm = document.getElementById('app').__vue__;"
             " const mid = vm.$route.query.mid;"
             " const cur = vm.$store.state.msgList.baseMsg.find(it => String(it.mid) === String(mid));"
             " cur.msg.push({ name:'d', headerUrl:'/images/avatar/2_20260831_184618_874.jpg',"
             " date:Date.now(), text:'探针文本' }); vm.$forceUpdate(); }")
FIRE_TRANSFER = "() => window.__wxChatExt.selfTransfer('测试', '50.00', '探针备注')"

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 620, "height": 1340})
    pg.goto("http://127.0.0.1:8080/", wait_until="domcontentloaded")
    pg.wait_for_function("document.getElementById('app') && document.getElementById('app').children.length", timeout=30000)

    # --- 复刻 main.py 注入（场景先行，键盘/Rime/真人层省略——与转账上屏无关） ---
    pg.add_style_tag(content=".welcome { display: none !important; }")
    pg.add_style_tag(content="#webpack-dev-server-client-overlay { pointer-events: none !important; }")
    for c in CSS_BASE:
        pg.add_style_tag(content=_read(c))
    scene = open(os.path.join(ROOT, "scene.json"), encoding="utf-8").read()
    pg.evaluate("window.__wxDefaultScene = %s" % scene)
    for j in JS_ORDER:
        pg.evaluate(_read(j))
    pg.evaluate("window.__wxDebugAgent = false")
    for c in CSS_POST:
        pg.add_style_tag(content=_read(c))
    pg.add_style_tag(content=(
        "html, body { height: 100% !important; overflow: clip !important;"
        " contain: paint !important; width: 600px !important; max-width: 600px !important; }"
        "#app { overflow: clip !important; position: relative !important; contain: paint !important;"
        " width: 600px !important; max-width: 600px !important;"
        " height: 100% !important; min-height: 100% !important; }"))
    pg.evaluate("window.__wxConfig && window.__wxConfig.apply && window.__wxConfig.apply()")
    pg.wait_for_timeout(1200)

    # --- 点开第一个会话（main.py open_chat 同款 DOM 点击） ---
    print("open:", pg.evaluate("""
      () => {
        const lis = Array.from(document.querySelectorAll('.wechat-list li'));
        if (!lis.length) return 'no-li';
        const info = lis[0].querySelector('.list-info');
        (info || lis[0]).click();
        return 'clicked:' + (lis[0].querySelector('.desc-author') || {}).textContent;
      }
    """))
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(600)

    # --- 文本（store 路径，等价打字上屏后的行渲染） ---
    text_samples = pg.evaluate(SAMPLE_JS_TMPL.replace("FN_BODY", FIRE_TEXT))

    # --- 转账（与支付成功后完全相同的上屏 API） ---
    tr_samples = pg.evaluate(SAMPLE_JS_TMPL.replace("FN_BODY", FIRE_TRANSFER))

    print("=== TEXT ===")
    print(json.dumps([s for s in text_samples if s.get("row") != "not-yet"][:6], ensure_ascii=False))
    print("=== TRANSFER ===")
    print(json.dumps([s for s in tr_samples if s.get("row") != "not-yet"][:6], ensure_ascii=False))
    print("transfer samples total:", len(tr_samples), "text samples total:", len(text_samples))
    b.close()
