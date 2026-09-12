# -*- coding: utf-8 -*-
"""探针：+面板/表情面板稳态下，输入栏是否盖住最后一条消息。
量几何：消息区底边 vs 输入栏顶边 vs 最后一条消息行底边；scrollTop 是否贴底。
"""
import json
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
ENH = r"G:/weixin-auto/enhance/"

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

MEASURE_JS = r"""
(label) => {
  const sec = document.querySelector('.dialogue-section');
  const footer = document.querySelector('.dialogue-footer');
  const bar = document.querySelector('.component-dialogue-bar-person');
  if (!sec || !footer) return {label, error: 'no sec/footer'};
  const sr = sec.getBoundingClientRect();
  const fr = footer.getBoundingClientRect();
  const br = bar ? bar.getBoundingClientRect() : null;
  const rows = sec.querySelectorAll('.row');
  const last = rows.length ? rows[rows.length - 1] : null;
  const lr = last ? last.getBoundingClientRect() : null;
  const max = sec.scrollHeight - sec.clientHeight;
  const csR = getComputedStyle(document.documentElement);
  const vars = {};
  ['--wxp-h', '--emoji-h', '--chat-bar-base', '--chat-grow'].forEach(v => vars[v] = getComputedStyle(document.body).getPropertyValue(v).trim() || csR.getPropertyValue(v).trim());
  const footerTf = getComputedStyle(footer).transform;
  const host = sec.parentElement;
  return {
    label,
    secBottom: Math.round(sr.bottom), secTop: Math.round(sr.top),
    secClientH: sec.clientHeight, secScrollH: sec.scrollHeight,
    secComputedH: getComputedStyle(sec).height,
    footerTop: Math.round(fr.top),
    barTop: br ? Math.round(br.top) : null,
    footerTf,
    hostH: host ? host.clientHeight : null,
    vars,
    lastRowBottom: lr ? Math.round(lr.bottom) : null,
    covered: lr ? (lr.bottom > fr.top + 0.5) : null,
    coverPx: lr ? Math.round(lr.bottom - fr.top) : null,
    scrollTop: Math.round(sec.scrollTop), scrollMax: Math.round(max),
    scrollShort: Math.round(max - sec.scrollTop),
    rows: rows.length,
  };
}
"""

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 620, "height": 1340})
    pg.goto(URL, wait_until="domcontentloaded")
    pg.evaluate("document.querySelector('.welcome') && (document.querySelector('.welcome').style.display='none')")
    for n in CSS_BASE:
        pg.add_style_tag(content=read(ENH + n))
    pg.evaluate("window.__wxDefaultScene = %s" % read(r"G:/weixin-auto/scene.json"))
    for n in JS_ORDER:
        pg.add_script_tag(content=read(ENH + n))
    for n in CSS_POST:
        pg.add_style_tag(content=read(ENH + n))
    pg.wait_for_function("!!window.__wxChatExt && !!window.__wxTransfer", timeout=30000)
    pg.add_script_tag(content=read(ENH + "panel_switch.js"))
    pg.wait_for_function("!!window.__wxPanels", timeout=10000)
    pg.evaluate("window.__wxConfig.applyScene(window.__wxDefaultScene)")
    pg.evaluate("location.hash = '#/wechat/dialogue'")
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(600)
    # 直接 DOM 塞几行（几何探针只需 .row 存在）
    pg.evaluate("""
      () => {
        const sec = document.querySelector('.dialogue-section');
        for (let i = 1; i <= 8; i++) {
          const d = document.createElement('div');
          d.className = 'row' + (i % 2 ? '' : ' right');
          d.innerHTML = '<div class="bubble"><p class="text" style="margin:0;padding:10px 14px;background:#3eb575;border-radius:8px;color:#fff;max-width:60vw">测试消息 ' + i + ' 好东西一起看看</p></div>';
          sec.appendChild(d);
        }
        return sec.querySelectorAll('.row').length;
      }
    """)
    pg.wait_for_timeout(300)
    pg.evaluate("const s=document.querySelector('.dialogue-section'); s.scrollTop=s.scrollHeight")
    pg.wait_for_timeout(200)
    for state in ['none', 'emoji', 'attach']:
        pg.evaluate("st => window.__wxPanels.set(st)", state)
        pg.wait_for_timeout(600)
        out = pg.evaluate(MEASURE_JS, state)
        print(json.dumps(out, ensure_ascii=False))
    b.close()
