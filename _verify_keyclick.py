# -*- coding: utf-8 -*-
"""验证：真人鼠标点击只输一位；程序化 click 仍正常；真人点击有落指反馈。"""
import os
from playwright.sync_api import sync_playwright

ROOT = r"G:\weixin-auto"
ENH = os.path.join(ROOT, "enhance")
CSS = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
       "wechat_modern.css", "human_actions.css", "transfer_ui.css", "send_image_ui.css",
       "peer_pages.css", "block_ui.css", "video_player.css", "homepage_exact.css"]
JS = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js", "wxemoji_map.js",
      "emoji_map.js", "transfer_ui.js", "send_image_ui.js", "video_player.js",
      "peer_pages.js", "block_ui.js"]


def rd(p):
    return open(p, encoding="utf-8").read()


ok = True


def check(name, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("  %-40s %-22s %s" % (name, repr(got), "OK" if good else "FAIL(期望 %r)" % (want,)))


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 600, "height": 1300})
    pg.goto("http://localhost:8080/#/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.add_style_tag(content=".welcome { display: none !important; }")
    for f in CSS:
        pg.add_style_tag(content=rd(os.path.join(ENH, f)))
    for f in JS:
        pg.evaluate(rd(os.path.join(ENH, f)))
    pg.evaluate(rd(os.path.join(ENH, "keyboard.js")))
    pg.wait_for_timeout(600)

    pg.evaluate("window.__wxTransfer.openPanel()")
    pg.wait_for_timeout(400)
    pg.evaluate("window.__wxTransfer.openAmount('小星')")
    pg.wait_for_timeout(1400)

    def mouse_click(sel):
        el = pg.query_selector(sel)
        box = el.bounding_box()
        pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    print("--- 金额页 ---")
    mouse_click('#taKeyboard .tkr-key[data-key="1"]')
    pg.wait_for_timeout(350)
    check("真人鼠标点「1」一次", pg.evaluate("window.__wxTransfer.getAmount()"), "1")
    mouse_click('#taKeyboard .tkr-key[data-key="."]')
    mouse_click('#taKeyboard .tkr-key[data-key="0"]')
    pg.wait_for_timeout(350)
    check("再点「.」「0」", pg.evaluate("window.__wxTransfer.getAmount()"), "1.0")

    # 程序化 click（main.py 路径）
    pg.evaluate("window.__wxTransfer.setAmount('')")
    pg.evaluate("()=>{document.querySelector('#taKeyboard .tkr-key[data-key=\"7\"]').click();}")
    pg.wait_for_timeout(250)
    check("程序化 click 点「7」一次", pg.evaluate("window.__wxTransfer.getAmount()"), "7")

    # 落指反馈：真人点击后键上应出现 .tkr-press
    box = pg.query_selector('#taKeyboard .tkr-key[data-key="5"]').bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pg.mouse.down()
    pg.wait_for_timeout(40)
    check("真人点击时有落指类 .tkr-press",
          pg.evaluate("()=>document.querySelector('#taKeyboard .tkr-key[data-key=\"5\"]').classList.contains('tkr-press')"),
          True)
    check("落指时 scale < 1",
          pg.evaluate("()=>{const t=getComputedStyle(document.querySelector('#taKeyboard .tkr-key[data-key=\"5\"]')).transform;return t!=='none' && new DOMMatrixReadOnly(t).a<0.999;}"),
          True)
    pg.mouse.up()
    pg.wait_for_timeout(400)
    check("抬指后动画已清",
          pg.evaluate("()=>document.querySelector('#taKeyboard .tkr-key[data-key=\"5\"]').classList.contains('tkr-press')"),
          False)

    print("--- 密码面板 ---")
    pg.evaluate("window.__wxTransfer.openPassword('7','')")
    pg.wait_for_timeout(1600)
    mouse_click('#pwKeyboard .tkr-key[data-key="1"]')
    pg.wait_for_timeout(350)
    check("真人鼠标点密码「1」一次", pg.evaluate("window.__wxTransfer.getState().password"), "1")
    pg.evaluate("()=>{document.querySelector('#pwKeyboard .tkr-key[data-key=\"2\"]').click();}")
    pg.wait_for_timeout(250)
    check("程序化 click 密码「2」", pg.evaluate("window.__wxTransfer.getState().password"), "12")
    check("密码点已填充", pg.evaluate("()=>document.querySelectorAll('#payBoxes i.filled').length"), 2)

    b.close()

print("\n结果:", "全部通过" if ok else "存在失败项")
