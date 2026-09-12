# -*- coding: utf-8 -*-
"""独立验证聊天气泡尖角：自起浏览器 + 8080 dev server + 注入 chat_exact.css，
不占用共享的真渲染器（main.py --editmode）。输出 _tail_verify.png"""
import json
import sys
from playwright.sync_api import sync_playwright

SCENE = {
    "me": {"name": "d", "avatar": "/images/avatar/2_20260831_184618_874.jpg"},
    "home": [
        {
            "name": "陆香儿",
            "messages": [
                {"dir": "peer", "kind": "text", "text": "我今晚好想哭，我要哭一晚。"},
                {"dir": "me", "kind": "text", "text": "哭什么"},
                {"dir": "me", "kind": "text", "text": "下次过去我早点"},
                {"dir": "me", "kind": "text", "text": "你先不要难过了，我今晚加完班就过去找你，带上你喜欢吃的那个草莓蛋糕，我们出去走走，回来再看部好看的片子好不好？"},
                {"dir": "peer", "kind": "text", "text": "好，那我等你，我先把眼泪擦干，等你到了叫我，我下楼接你。"},
                {"dir": "peer", "kind": "emoji", "image": "/images/wxemoji3d/e01.png"},
                {"dir": "me", "kind": "emoji", "image": "/images/wxemoji3d/e03.png"},
                {"dir": "peer", "kind": "emoji", "image": "/images/emoji/1f300.png"},
                {"dir": "me", "kind": "image", "image": "/images/asset/e25.png"},
            ],
        }
    ],
}

CSS_FILES = [
    # 与 main.py 注入顺序一致（_ensure_enhance），顺序影响级联结果
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
        page.wait_for_selector(".wechat-list li", timeout=20000)
        for js in ["emoji_map.js", "config.js"]:
            with open(r"G:\weixin-auto\enhance\\" + js, "r", encoding="utf-8") as fh:
                page.evaluate(fh.read())
        page.wait_for_function("() => !!window.__wxConfig", timeout=15000)
        for css in CSS_FILES:
            with open(r"G:\weixin-auto\enhance\\" + css, "r", encoding="utf-8") as fh:
                page.add_style_tag(content=fh.read())
        ok = page.evaluate("(s) => window.__wxConfig.applyScene(s)", SCENE)
        print("applyScene:", ok)
        page.evaluate("""() => {
            const lis = Array.from(document.querySelectorAll('.wechat-list li'));
            const li = lis.find(l => {
                const a = l.querySelector('.desc-author');
                return a && a.textContent.indexOf('陆香儿') > -1;
            });
            if (!li) throw new Error('row not found');
            const info = li.querySelector('.list-info');
            info.click();
        }""")
        page.wait_for_selector(".dialogue-section .row", timeout=8000)
        page.wait_for_timeout(1500)
        # 滚到底
        page.evaluate("""() => {
            const sec = document.querySelector('.dialogue-section');
            if (sec) sec.scrollTop = sec.scrollHeight;
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=r"G:\weixin-auto\_tail_verify.png")
        # 数值探针：每个 .row 的第一个 .text 是否有可见 ::before（content 非 none）
        probe = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.dialogue-section .row').forEach(r => {
                const t = r.querySelector('.text');
                if (!t) return;
                const st = getComputedStyle(t, '::before');
                const kind = t.className.replace('text', '').trim() || 'text';
                out.push({
                    kind: kind,
                    self: r.classList.contains('self'),
                    content: st.content,
                    display: st.display,
                    bw: st.borderRightWidth + '/' + st.borderLeftWidth,
                    bc: st.borderRightColor + '/' + st.borderLeftColor,
                });
            });
            return out;
        }""")
        print(json.dumps(probe, ensure_ascii=False, indent=1))
        geo = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.dialogue-section .row').forEach(r => {
                const h = r.querySelector('.header'), t = r.querySelector('.text');
                if (!h || !t) return;
                const hb = h.getBoundingClientRect(), tb = t.getBoundingClientRect();
                out.push({self: r.classList.contains('self'),
                          avatarTop: +hb.top.toFixed(1), avatarH: +hb.height.toFixed(1),
                          textTop: +tb.top.toFixed(1), textH: +tb.height.toFixed(1)});
            });
            return out;
        }""")
        for g2 in geo:
            print('ALIGN', g2)
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
