# -*- coding: utf-8 -*-
"""生成「朋友圈多图排版总览」预览图：2/3/4/5/6/9 张各一条，拼成一张 PNG。

用法: py _preview_grid.py
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")
OUT = os.path.join(BASE, "preview")
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
LABELS = ["2 张图", "3 张图", "4 张图（田字格）", "5 张图", "6 张图", "9 张图"]


def read(name):
    p = os.path.join(ENH, name)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    from playwright.sync_api import sync_playwright
    shots = []
    with sync_playwright() as pw:
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        br = pw.chromium.launch(headless=True,
                                executable_path=chrome if os.path.isfile(chrome) else None)
        ctx = br.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2,
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
        page.wait_for_timeout(800)
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(200)
        with open(os.path.join(BASE, "_probe_scene.json"), "r", encoding="utf-8") as fh:
            page.evaluate("(s) => window.__wxConfig && window.__wxConfig.applyScene(s)",
                          json.load(fh))
        page.wait_for_timeout(300)
        page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
        page.wait_for_timeout(1600)

        for i in range(6):
            page.evaluate("""(n) => {
                const el = document.getElementById('moments');
                const p = document.querySelectorAll('#moments .moments__post')[n];
                const top = p.getBoundingClientRect().top;
                el.scrollTop = (el.scrollTop || 0) + top - 96;
            }""", i)
            page.wait_for_timeout(700)
            box = page.evaluate("""(n) => {
                const p = document.querySelectorAll('#moments .moments__post')[n];
                const gal = p.querySelector('.thumbnails');
                const b = (gal || p).getBoundingClientRect();
                return { y: Math.max(0, b.y - 96), h: Math.min(1180, b.height + 130) };
            }""", i)
            # 丢掉可能没稳定的一帧
            page.screenshot(path=os.path.join(OUT, "_tmp.png"))
            page.wait_for_timeout(250)
            path = os.path.join(OUT, "_grid_%d.png" % i)
            page.screenshot(path=path, clip={"x": 60, "y": box["y"], "width": 500,
                                             "height": box["h"]})
            shots.append(path)
            print("panel %d: y=%.0f h=%.0f" % (i + 1, box["y"], box["h"]))
        br.close()

    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 30)
    except Exception:
        font = ImageFont.load_default()

    panels = [Image.open(p).convert("RGB") for p in shots]
    # 截图是 DPR=2 出的，统一缩到 500 宽再拼，否则面板会互相压住
    panels = [im.resize((500, max(1, round(im.height * 500 / im.width))), Image.LANCZOS)
              for im in panels]
    pad, gap, label_h = 16, 18, 46
    cw = 500
    rows = []
    for r in range(2):
        rows.append(panels[r * 3:r * 3 + 3])
    col_h = max(max(im.height for im in row) for row in rows)
    W = pad * 2 + cw * 3 + gap * 2
    H = pad * 2 + (label_h + col_h) * 2 + gap
    canvas = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(canvas)
    for r, row in enumerate(rows):
        for c, im in enumerate(row):
            x = pad + c * (cw + gap)
            y = pad + r * (label_h + col_h + gap)
            d.text((x + 6, y), LABELS[r * 3 + c], fill=(230, 230, 230), font=font)
            canvas.paste(im, (x, y + label_h))
            d.rectangle([x - 1, y + label_h - 1, x + im.width, y + label_h + im.height],
                        outline=(70, 70, 70))
    out = os.path.join(OUT, "朋友圈_多图排版.png")
    canvas.save(out)
    print("out:", out, canvas.size)
    for p in shots:
        os.remove(p)
    tmp = os.path.join(OUT, "_tmp.png")
    if os.path.isfile(tmp):
        os.remove(tmp)


if __name__ == "__main__":
    main()
