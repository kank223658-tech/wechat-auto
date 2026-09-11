# -*- coding: utf-8 -*-
"""真实环境全链路复现：金额页(空/有值)→toast→付款面板→加载态→成功页 截图。"""
from playwright.sync_api import sync_playwright

ENH = r"G:\weixin-auto\enhance"
def rd(p): return open(p, encoding="utf-8").read()

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 600, "height": 1300})
    pg.goto("http://localhost:8080/#/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.add_style_tag(content=".welcome { display: none !important; }")
    for f in ["harmony_font.css","keyboard.css","iphone_frame.css","weui_tokens.css",
              "wechat_modern.css","human_actions.css","transfer_ui.css","send_image_ui.css",
              "peer_pages.css","block_ui.css","video_player.css","homepage_exact.css"]:
        pg.add_style_tag(content=rd(ENH+"\\"+f))
    for f in ["config.js","chat_extra.js","moments_extra.js","iphone_frame.js",
              "wxemoji_map.js","emoji_map.js","transfer_ui.js","send_image_ui.js",
              "video_player.js","peer_pages.js","block_ui.js"]:
        pg.evaluate(rd(ENH+"\\"+f))
    pg.evaluate(rd(ENH+"\\keyboard.js"))
    pg.wait_for_timeout(500)
    pg.evaluate("window.__wxTransfer.openAmount('小星')")
    pg.wait_for_timeout(700)
    pg.screenshot(path=r"G:\weixin-auto\_ph_empty.png")
    # 输入 1.00
    for k in ["1",".","0","0"]:
        pg.evaluate("(d)=>{const k=document.querySelector('#taKeyboard .tkr-key[data-key=\"'+d+'\"]'); if(k) k.click();}", k)
        pg.wait_for_timeout(120)
    pg.wait_for_timeout(300)
    pg.screenshot(path=r"G:\weixin-auto\_ph_filled.png")
    # 点转账 → toast
    pg.evaluate("()=>{const k=document.querySelector('#taKeyboard .tkr-ok'); if(k) k.click();}")
    pg.wait_for_timeout(700)
    pg.screenshot(path=r"G:\weixin-auto\_ph_toast.png")
    # 面板滑起
    pg.wait_for_timeout(2300)
    pg.screenshot(path=r"G:\weixin-auto\_ph_sheet.png")
    # 输密码 6 位 → 加载态
    for d in "123456":
        pg.evaluate("(d)=>{const k=document.querySelector('#pwKeyboard .tkr-key[data-key=\"'+d+'\"]'); if(k) k.click();}", d)
        pg.wait_for_timeout(150)
    pg.wait_for_timeout(500)
    pg.screenshot(path=r"G:\weixin-auto\_ph_loading.png")
    # 成功页
    pg.wait_for_timeout(1400)
    pg.screenshot(path=r"G:\weixin-auto\_ph_success.png")
    b.close()
print("DONE")
