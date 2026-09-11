# -*- coding: utf-8 -*-
"""关图后 tile 绘制错误的「冲洗」实验：逐个施加手段 + 截图对比。

背景：关闭 PhotoSwipe 后，被打开过的那张缩略图绘制成「整图压扁」错误内容
（computed 样式全部正常、元素栈干净）。视频里滚动能冲掉它。本探针逐个尝试：
  f1_scroll    容器 scrollTop +1 再回来（视频里已证实有效）
  f2_translate img 临时 translateZ(0) 再移除（强迫该 img 重新分层/光栅）
  f3_src       img.src = img.src 重新赋值（强迫重新解码/绘制）
  f4_visibility img 临时 visibility:hidden 再恢复
  f5_clone     用克隆节点替换 img（强迫全新元素）
每个手段后截图 _fs/fN_*.png，肉眼+像素差对比哪个恢复 cover 裁切。
"""
import base64
import json
import os
import sys
import threading

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

        # 基准截图（开图前）
        page.screenshot(path=os.path.join(OUT, "f0_before.png"))

        page.evaluate("() => window.__wxMoments.openImage(1, 3)")
        page.wait_for_timeout(150)
        page.wait_for_timeout(1200)
        page.evaluate("() => window.__wxMoments.closeImage()")
        page.wait_for_timeout(1000)   # 稳态：幽灵应已出现

        page.screenshot(path=os.path.join(OUT, "f0_ghost.png"))
        print("已存 f0_before / f0_ghost")

        flushes = [
            ("f1_scroll", """() => {
                const el = document.getElementById('moments');
                const y = el.scrollTop;
                el.scrollTop = y + 1; el.scrollTop = y;
            }"""),
            ("f2_translate", """() => {
                const img = document.querySelector('#moments .moments__post .my-gallery')
                    .children[2].querySelector('img');
                img.style.transform = 'translateZ(0)';
                void img.offsetWidth;
                setTimeout(() => { img.style.transform = ''; }, 60);
            }"""),
            ("f3_src", """() => {
                const img = document.querySelector('#moments .moments__post .my-gallery')
                    .children[2].querySelector('img');
                const s = img.src;
                img.src = ''; img.src = s;
            }"""),
            ("f4_visibility", """() => {
                const img = document.querySelector('#moments .moments__post .my-gallery')
                    .children[2].querySelector('img');
                img.style.visibility = 'hidden';
                void img.offsetWidth;
                setTimeout(() => { img.style.visibility = ''; }, 60);
            }"""),
            ("f5_clone", """() => {
                const img = document.querySelector('#moments .moments__post .my-gallery')
                    .children[2].querySelector('img');
                const cl = img.cloneNode(true);
                img.parentNode.replaceChild(cl, img);
            }"""),
        ]
        for name, js in flushes:
            page.evaluate(js)
            page.wait_for_timeout(350)
            page.screenshot(path=os.path.join(OUT, "%s.png" % name))
            print("已存", name)

        br.close()


if __name__ == "__main__":
    main()
