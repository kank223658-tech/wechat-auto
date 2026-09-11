# -*- coding: utf-8 -*-
"""冲洗实验第二轮：更大动作的失效手段。
  g1_scrollbig  scrollTop +200 再回来（大幅重光栅）
  g2_wheel      派发 wheel 事件滚动（模拟真人滚动的失效路径）
  g3_zoom       body.zoom 1 -> 1.0001 -> 1（全局重排+重光栅）
  g4_nuke       documentElement display none -> 恢复（核弹级全量重绘）
  g5_paintprobe 使用 Chrome paint 计数不可能，改用 CDP Page.captureSnapshot 前后比对
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")
OUT = os.path.join(BASE, "_fs")
os.makedirs(OUT, exist_ok=True)
VW, VH = 600, 1300

CSS_ORDER = [
    "harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
    "wechat_modern.css", "human_actions.css", "transfer_ui.css",
    "send_image_ui.css", "peer_pages.css", "video_player.css",
    "homepage_exact.css", "wx_icons.css", "moments_exact.css",
]
JS_ORDER = [
    "config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
    "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
    "video_player.js", "peer_pages.js",
]

POSTS = [
    {"author": "小星", "text": "九宫格。",
     "images": ["/images/avatar/110_158_夏天就要大胆穿__5_不吃饭了__来自小红书网页版_20260831_185134_593.jpg",
                "/images/avatar/枯木_20260903_141720_316.jpg",
                "/images/avatar/学习急救班素材_20260908_155548_722.png",
                "/images/avatar/女友生气怎么哄教学_20260905_155312_388.png",
                "/images/avatar/聊天技巧图片_20260905_154410_890.png",
                "/images/avatar/一楼一饭店__1_Sabrina_来自小红书网页版_20260909_185707_580.jpg",
                "/images/avatar/落日下海风拂面_1_纵鸠_来自小红书网页版_1_20260831_184706_666.jpg",
                "/images/avatar/IMG_0512_20260901_140118_982.png",
                "/images/avatar/IMG_0491_20260903_144508_035.png"],
     "time": "2分钟前", "likes": [], "comments": []},
]


def read(name):
    p = os.path.join(ENH, name)
    return open(p, "r", encoding="utf-8").read() if os.path.isfile(p) else None


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        br = pw.chromium.launch(headless=True,
                                executable_path=chrome if os.path.isfile(chrome) else None)
        ctx = br.new_context(viewport={"width": VW, "height": VH},
                             device_scale_factor=3,
                             user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
                             is_mobile=True, has_touch=True, locale="zh-CN")
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
        page.add_style_tag(content=".welcome { display: none !important; }")
        for n in CSS_ORDER:
            c = read(n)
            if c:
                page.add_style_tag(content=c)
        for n in JS_ORDER:
            c = read(n)
            if c:
                page.evaluate(c)
        page.wait_for_timeout(600)
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(300)
        page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        page.evaluate("(s) => window.__wxMoments.renderPosts(s)", POSTS)
        page.wait_for_timeout(600)
        page.evaluate("() => { document.getElementById('moments').scrollTop = 420; }")
        page.wait_for_timeout(400)
        page.screenshot(path=os.path.join(OUT, "g0_fresh.png"))

        page.evaluate("() => window.__wxMoments.openImage(1, 3)")
        page.wait_for_timeout(150)
        page.wait_for_timeout(1200)
        page.evaluate("() => window.__wxMoments.closeImage()")
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(OUT, "g0_ghost.png"))
        print("已存 g0_fresh / g0_ghost")

        flushes = [
            ("g1_scrollbig", """() => {
                const el = document.getElementById('moments');
                const y = el.scrollTop;
                el.scrollTop = y + 200;
                void el.offsetHeight;
                el.scrollTop = y;
            }"""),
            ("g2_wheel", """() => {
                const el = document.getElementById('moments');
                el.dispatchEvent(new WheelEvent('wheel',
                    { deltaY: 120, bubbles: true, cancelable: true }));
                el.scrollTop += 60;
                void el.offsetHeight;
                el.scrollTop -= 60;
            }"""),
            ("g3_zoom", """() => {
                document.body.style.zoom = '1.0001';
                void document.body.offsetHeight;
                document.body.style.zoom = '';
            }"""),
            ("g4_nuke", """() => {
                const de = document.documentElement;
                de.style.display = 'none';
                void de.offsetWidth;
                de.style.display = '';
            }"""),
        ]
        for name, js in flushes:
            page.evaluate(js)
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(OUT, "%s.png" % name))
            print("已存", name)

        br.close()


if __name__ == "__main__":
    main()
