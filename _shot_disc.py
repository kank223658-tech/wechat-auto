# -*- coding: utf-8 -*-
"""临时工具：渲染「发现」页并截图，与 参考图片/朋友圈制作视频/发现页面.jpg 对比。

用法:
    py _shot_disc.py                # 截图 _shot/disc_now.png
    py _shot_disc.py --cmp          # 与参考图并排拼图 + 输出几何指标
"""
import os
import sys
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")
OUT = os.path.join(BASE, "_shot")
VW, VH = 600, 1300
REF = os.path.join(BASE, "参考图片", "朋友圈制作视频", "发现页面.jpg")

CSS_ORDER = [
    "harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
    "wechat_modern.css", "human_actions.css", "transfer_ui.css",
    "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
    "homepage_exact.css", "wx_icons.css", "moments_exact.css", "discover_exact.css",
]
JS_ORDER = [
    "config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
    "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
    "video_player.js", "peer_pages.js", "block_ui.js",
]


def read(name):
    p = os.path.join(ENH, name)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="disc_now")
    ap.add_argument("--cmp", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        br = pw.chromium.launch(headless=True,
                                executable_path=chrome if os.path.isfile(chrome) else None)
        ctx = br.new_context(viewport={"width": VW, "height": VH},
                             device_scale_factor=1,
                             user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
                             is_mobile=True, has_touch=True, locale="zh-CN")
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
        page.add_style_tag(content=".welcome { display: none !important; }")
        for n in CSS_ORDER:
            c = read(n)
            if c:
                page.add_style_tag(content=c)
            else:
                print("  (skip css)", n)
        for n in JS_ORDER:
            c = read(n)
            if c:
                page.evaluate(c)
            else:
                print("  (skip js)", n)
        page.wait_for_timeout(800)
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(300)
        page.goto("http://127.0.0.1:8080/#/explore", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        # 强制微信 Tab 未读徽标为参考图的 42（store 初始数据不是 42）
        page.evaluate("""() => {
            const app = document.querySelector('#app');
            const vm = app && app.__vue__;
            if (vm && vm.$store) vm.$store.state.newMsgCount = 42;
        }""")
        path = os.path.join(OUT, args.out + ".png")
        page.wait_for_timeout(900)
        page.screenshot(path=path + ".warm.png")
        page.wait_for_timeout(500)
        page.screenshot(path=path)
        print("shot:", path)
        box = page.evaluate("""() => {
            const q = (s) => document.querySelector(s);
            const bb = (el) => { if(!el) return null; const b=el.getBoundingClientRect();
                return {x:+b.x.toFixed(1),y:+b.y.toFixed(1),w:+b.width.toFixed(1),h:+b.height.toFixed(1)}; };
            return {
                onExp: document.body.classList.contains('wx-on-explore'),
                cells: Array.from(document.querySelectorAll('#explore .disc-cell')).map(bb),
                labels: Array.from(document.querySelectorAll('#explore .disc-label')).map(e=>e.textContent),
                pill: bb(q('#wx-delivery-pill')),
                nav: bb(q('#wx-nav nav')),
                dts: Array.from(document.querySelectorAll('#wx-nav nav dt')).map(bb),
                header: bb(q('.app-header')),
                sb: bb(q('#ios-statusbar')),
            };
        }""")
        print(json.dumps(box, ensure_ascii=False))
        br.close()

    if args.cmp:
        from PIL import Image
        ref = Image.open(REF).convert("RGB").resize((VW, VH), Image.LANCZOS)
        cur = Image.open(path).convert("RGB")
        canvas = Image.new("RGB", (VW * 2 + 12, VH), (60, 60, 60))
        canvas.paste(ref, (0, 0))
        canvas.paste(cur, (VW + 12, 0))
        cp = os.path.join(OUT, "disc_cmp.png")
        canvas.save(cp)
        print("cmp:", cp)


if __name__ == "__main__":
    main()
