# -*- coding: utf-8 -*-
"""真实环境复现：按 main.py 的注入顺序加载全部增强层，进聊天，打开转账各阶段截图。"""
import sys, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080/#/"
ENH = r"G:\weixin-auto\enhance"

def rd(p):
    return open(p, encoding="utf-8").read()

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 600, "height": 1300})
    pg.goto(BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(1500)
    # 与 main.py inject_overlays 相同顺序（省略 rime/pinyin，与本次验证无关）
    pg.add_style_tag(content=".welcome { display: none !important; }")
    for f in ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
              "wechat_modern.css", "human_actions.css", "transfer_ui.css", "send_image_ui.css",
              "peer_pages.css", "block_ui.css", "video_player.css", "homepage_exact.css"]:
        pg.add_style_tag(content=rd(ENH + "\\" + f))
    for f in ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
              "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
              "video_player.js", "peer_pages.js", "block_ui.js"]:
        pg.evaluate(rd(ENH + "\\" + f))
    pg.evaluate(rd(ENH + "\\keyboard.js"))
    pg.wait_for_timeout(800)
    # 进入聊天（小星）
    ok = pg.evaluate("""(name) => {
        const lis = Array.from(document.querySelectorAll('.wechat-list li'));
        let li = lis.find(l => { const a = l.querySelector('.desc-author');
                                 return a && a.textContent.trim() === name; });
        if (!li) li = lis.find(l => { const a = l.querySelector('.desc-author');
                                      return a && a.textContent.indexOf(name) !== -1; });
        if (!li) return false;
        (li.querySelector('.list-info') || li).click(); return true;
    }""", "小星")
    print("enter chat:", ok)
    pg.wait_for_timeout(900)
    # 1) + 功能面板
    pg.evaluate("window.__wxTransfer && window.__wxTransfer.openPanel()")
    pg.wait_for_timeout(600)
    pg.screenshot(path=r"G:\weixin-auto\_real_1_panel.png")
    # 2) 金额页
    pg.evaluate("window.__wxTransfer && window.__wxTransfer.openAmount('小星')")
    pg.wait_for_timeout(800)
    pg.screenshot(path=r"G:\weixin-auto\_real_2_amount.png")
    # 诊断头部元素状态
    diag = pg.evaluate("""() => {
        const q = s => document.querySelector(s);
        const top = q('#wxTransferAmount .ta-top');
        const rec = q('#wxTransferAmount .ta-recipient');
        const page = q('#wxTransferAmount');
        const cs = el => el ? getComputedStyle(el) : null;
        const r = el => el ? el.getBoundingClientRect() : null;
        return {
            pageRect: r(page),
            topDisplay: cs(top) && cs(top).display,
            topRect: r(top),
            recRect: r(rec),
            recVisibility: cs(rec) && cs(rec).visibility,
            recOpacity: cs(rec) && cs(rec).opacity,
            topHTML: top ? top.outerHTML.slice(0, 120) : null,
            recText: rec ? rec.innerText.slice(0, 60) : null,
        };
    }""")
    for k, v in diag.items():
        print(k, "=", v)
    b.close()
print("DONE")
