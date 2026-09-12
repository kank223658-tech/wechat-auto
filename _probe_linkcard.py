# -*- coding: utf-8 -*-
"""验证链接卡片：来源名默认「恋爱技巧」+ 恒定宽度 368px（短标题不缩水）。
复用 _tail_verify.py 模式：自起浏览器 + 8080 dev server + 注入 enhance。输出 _linkcard_verify.png"""
import json
import sys
from playwright.sync_api import sync_playwright

SCENE = {
    "me": {"name": "d", "avatar": "/images/avatar/2_20260831_184618_874.jpg"},
    "home": [
        {
            "name": "陆香儿",
            "messages": [
                {"dir": "peer", "kind": "text", "text": "最近在看的两篇，分享给你"},
                {"dir": "peer", "kind": "link", "title": "周末徒步组队啦",
                 "image": "男生.jpg", "time": "15:40"},
                {"dir": "me", "kind": "link", "title": "第一次约会去哪不冷场",
                 "image": "男生.jpg", "time": "15:41"},
            ],
        }
    ],
}

CSS_FILES = [
    "harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
    "wechat_modern.css", "human_actions.css", "transfer_ui.css",
    "transfer_detail.css", "send_image_ui.css", "peer_pages.css",
    "block_ui.css", "video_player.css", "homepage_exact.css",
    "chat_exact.css", "panel_switch.css", "wx_icons.css",
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 600, "height": 1300},
                                device_scale_factor=2)
        page.goto("http://localhost:8080/", wait_until="networkidle")
        # 注意：裸 dev server 页面联系人列表为空（默认场景已由 main.py 注入，这里没有），
        # 必须先注入 config.js + applyScene，再等会话列表行。
        for js in ["emoji_map.js", "config.js"]:
            with open(r"G:\weixin-auto\enhance\\" + js, "r", encoding="utf-8") as fh:
                page.evaluate(fh.read())
        page.wait_for_function("() => !!window.__wxConfig", timeout=15000)
        for css in CSS_FILES:
            with open(r"G:\weixin-auto\enhance\\" + css, "r", encoding="utf-8") as fh:
                page.add_style_tag(content=fh.read())
        ok = page.evaluate("(s) => window.__wxConfig.applyScene(s)", SCENE)
        print("applyScene:", ok)
        page.wait_for_selector(".wechat-list li", timeout=15000)
        page.evaluate("""() => {
            const lis = Array.from(document.querySelectorAll('.wechat-list li'));
            const li = lis.find(l => {
                const a = l.querySelector('.desc-author');
                return a && a.textContent.indexOf('陆香儿') > -1;
            });
            if (!li) throw new Error('row not found');
            li.querySelector('.list-info').click();
        }""")
        page.wait_for_selector(".dialogue-section .row", timeout=8000)
        page.wait_for_timeout(1500)
        page.evaluate("""() => {
            const sec = document.querySelector('.dialogue-section');
            if (sec) sec.scrollTop = sec.scrollHeight;
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=r"G:\weixin-auto\_linkcard_verify.png")
        # 数值探针：链接卡片宽度应恒为 368，来源名应为「恋爱技巧」
        probe = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.dialogue-section .msg-link').forEach(el => {
                const r = el.getBoundingClientRect();
                out.push({
                    width: +r.width.toFixed(1),
                    source: (el.querySelector('.lk-name') || {}).textContent || '',
                    title: (el.querySelector('.lk-title') || {}).textContent || '',
                    self: el.closest('.row').classList.contains('self'),
                });
            });
            return out;
        }""")
        print(json.dumps(probe, ensure_ascii=False, indent=1))
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
