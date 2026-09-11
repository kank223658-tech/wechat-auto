# -*- coding: utf-8 -*-
"""决定性探针：关图稳态后，同刻对比 screencast 帧 vs page.screenshot vs DOM 元素栈。

判定：
- screenshot 干净 + screencast 有幽灵 → 纯采集（合成器/推帧）问题
- 两者都有幽灵        → 页面真实绘制了幽灵，elementsFromPoint 揪元素
"""
import base64
import json
import os
import sys
import threading
import time

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
        # 滚到帖子可见（对齐工作流：滚动 420）
        page.evaluate("() => { const el = document.getElementById('moments'); el.scrollTop = 420; }")
        page.wait_for_timeout(400)

        # ---- 启动 screencast（对齐 main.py 参数）----
        cdp = ctx.new_cdp_session(page)
        frames = {}
        ack_lock = threading.Lock()

        def on_frame(p):
            ts = p.get("metadata", {}).get("timestamp", 0)
            with ack_lock:
                frames[ts] = base64.b64decode(p["data"])
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 92, "everyNthFrame": 1,
            "maxWidth": 2600, "maxHeight": 3900,
        })
        page.wait_for_timeout(500)

        # ---- 打开 / 关闭（对齐 open_moment_image 节奏）----
        tile_js = """() => {
            const gal = document.querySelector('#moments .moments__post .my-gallery');
            const f = gal.children[2];   // 第 3 张
            const r = f.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2,
                     rect: [r.x, r.y, r.width, r.height] };
        }"""
        tile = page.evaluate(tile_js)
        print("tile3 中心:", tile["x"], tile["y"], "rect:", tile["rect"])

        page.evaluate("() => window.__wxMoments.openImage(1, 3)")
        page.wait_for_timeout(150)
        page.wait_for_timeout(1200)
        page.evaluate("() => window.__wxMoments.closeImage()")
        page.wait_for_timeout(300)

        # 重绘强推（对齐 main.py 修复）
        repaint_js = """() => {
            const el = document.getElementById('moments');
            if (!el) return false;
            el.style.willChange = 'transform';
            el.style.opacity = '0.999';
            void el.offsetWidth;
            setTimeout(() => { el.style.willChange = ''; el.style.opacity = ''; }, 40);
            return true;
        }"""
        page.evaluate(repaint_js)
        page.wait_for_timeout(150)
        page.evaluate(repaint_js)
        page.wait_for_timeout(150)
        page.wait_for_timeout(400)   # 到达「稳态」，总 ~+1.0s

        # ---- 同刻抓三样 ----
        stack = page.evaluate(r"""([x, y]) => {
            const els = document.elementsFromPoint(x, y).map(el => ({
                tag: el.tagName, cls: (el.className || '').toString().slice(0, 60),
                id: el.id || null,
                rect: (r => [Math.round(r.x), Math.round(r.y),
                             Math.round(r.width), Math.round(r.height)])(el.getBoundingClientRect()),
                op: getComputedStyle(el).opacity,
                disp: getComputedStyle(el).display,
                z: getComputedStyle(el).zIndex,
                pos: getComputedStyle(el).position,
            }));
            const gal = document.querySelector('#moments .moments__post .my-gallery');
            const img = gal.children[2].querySelector('img');
            const cs = getComputedStyle(img);
            return { stack: els.slice(0, 8),
                     img: { fit: cs.objectFit, w: cs.width, h: cs.height,
                            transform: cs.transform.slice(0, 60) },
                     pswpDisp: getComputedStyle(document.querySelector('.pswp')).display };
        }""", [tile["x"], tile["y"]])
        print("\n== 元素栈 (tile3 中心) ==")
        print(json.dumps(stack, ensure_ascii=False, indent=1))

        page.screenshot(path=os.path.join(OUT, "g3_screenshot.png"))

        with ack_lock:
            tss = sorted(frames)
        print("\n收到的 screencast 帧数:", len(tss))
        if tss:
            last_ts = tss[-1]
            with open(os.path.join(OUT, "g3_screencast_last.jpg"), "wb") as f:
                f.write(frames[last_ts])
            # 关闭前后各存一帧
            # 打开时刻附近找帧：关闭 click≈T，找 T-0.2 与 T+0.6
            print("最后帧 ts=%.3f" % last_ts)

        cdp.send("Page.stopScreencast")
        br.close()


if __name__ == "__main__":
    main()
