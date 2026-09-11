# -*- coding: utf-8 -*-
"""真机复刻复现 v2：+功能面板(含输入栏联动) → 金额页(键盘延迟升起) → 输入金额。"""
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
              "peer_pages.css","block_ui.css","video_player.css","homepage_exact.css",
              "chat_exact.css","wx_icons.css","moments_exact.css","discover_exact.css"]:
        pg.add_style_tag(content=rd(ENH+"\\"+f))
    for f in ["config.js","chat_extra.js","moments_extra.js","iphone_frame.js",
              "wxemoji_map.js","emoji_map.js","transfer_ui.js","send_image_ui.js",
              "video_player.js","peer_pages.js","block_ui.js"]:
        pg.evaluate(rd(ENH+"\\"+f))
    pg.evaluate(rd(ENH+"\\keyboard.js"))
    pg.wait_for_timeout(400)
    # 进入聊天页（与 main.py 打开聊天同款 DOM click）
    ok = pg.evaluate("""() => {
        const lis = Array.from(document.querySelectorAll('.wechat-list li'));
        const li = lis.find(l => { const a = l.querySelector('.desc-author'); return a && a.textContent.trim() === 'D'; })
                  || lis.find(l => l.querySelector('.desc-author'));
        if (!li) return false;
        const info = li.querySelector('.list-info');
        (info || li).click();
        return true;
    }""")
    print("enter chat:", ok)
    pg.wait_for_timeout(1000)

    # 1) 打开 + 功能面板（输入栏应一起上移）
    pg.evaluate("window.__wxTransfer.openPanel()")
    pg.wait_for_timeout(500)
    pg.screenshot(path=r"G:\weixin-auto\_np_panel.png")

    # 2) 点「转账」→ 金额页滑入，键盘延迟升起
    pg.evaluate("document.querySelector('#wxTransferPanel .tp-transfer').click()")
    pg.wait_for_timeout(350)   # 页面滑入完成、键盘未升
    pg.screenshot(path=r"G:\weixin-auto\_np_amount_mid.png")
    pg.wait_for_timeout(700)   # 键盘已升起
    pg.screenshot(path=r"G:\weixin-auto\_np_amount.png")

    # 3) 输入金额 1
    pg.evaluate("(d)=>{const k=document.querySelector('#taKeyboard .tkr-key[data-key=\"'+d+'\"]'); if(k) k.click();}", "1")
    pg.wait_for_timeout(300)
    pg.screenshot(path=r"G:\weixin-auto\_np_filled.png")
    b.close()
print("DONE")
