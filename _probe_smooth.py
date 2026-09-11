# -*- coding: utf-8 -*-
"""2x2 复现：滚动方式(瞬时/平滑rAF) × screencast(关/开)。3帖可滚数据。"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")
OUT = os.path.join(BASE, "_fs")
VW, VH = 600, 1300
CSS_ORDER = ["harmony_font.css","keyboard.css","iphone_frame.css","weui_tokens.css",
 "wechat_modern.css","human_actions.css","transfer_ui.css","send_image_ui.css",
 "peer_pages.css","video_player.css","homepage_exact.css","wx_icons.css","moments_exact.css"]
JS_ORDER = ["config.js","chat_extra.js","moments_extra.js","iphone_frame.js",
 "wxemoji_map.js","emoji_map.js","transfer_ui.js","send_image_ui.js","video_player.js","peer_pages.js"]
POSTS = [
 {"author":"小星","text":"九宫格。",
  "images":["/images/avatar/110_158_夏天就要大胆穿__5_不吃饭了__来自小红书网页版_20260831_185134_593.jpg",
   "/images/avatar/枯木_20260903_141720_316.jpg","/images/avatar/学习急救班素材_20260908_155548_722.png",
   "/images/avatar/女友生气怎么哄教学_20260905_155312_388.png","/images/avatar/聊天技巧图片_20260905_154410_890.png",
   "/images/avatar/一楼一饭店__1_Sabrina_来自小红书网页版_20260909_185707_580.jpg",
   "/images/avatar/落日下海风拂面_1_纵鸠_来自小红书网页版_1_20260831_184706_666.jpg",
   "/images/avatar/IMG_0512_20260901_140118_982.png","/images/avatar/IMG_0491_20260903_144508_035.png"],
  "time":"2分钟前","likes":[],"comments":[]},
 {"author":"铁木君","text":"四张图。",
  "images":["/images/avatar/学习急救班素材_20260908_155548_722.png",
   "/images/avatar/女友生气怎么哄教学_20260905_155312_388.png",
   "/images/avatar/聊天技巧图片_20260905_154410_890.png",
   "/images/avatar/110_158_夏天就要大胆穿__5_不吃饭了__来自小红书网页版_20260831_185134_593.jpg"],
  "time":"20分钟前","likes":[],"comments":[]},
 {"author":"月亮","text":"单图。",
  "images":["/images/avatar/女友生气怎么哄教学_20260905_155312_388.png"],
  "time":"1小时前","likes":[],"comments":[]}]

def read(n):
    p = os.path.join(ENH, n)
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else None

def run(pw, chrome, name, smooth, screencast):
    br = pw.chromium.launch(headless=True, executable_path=chrome if os.path.isfile(chrome) else None)
    ctx = br.new_context(viewport={"width":VW,"height":VH}, device_scale_factor=3,
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
        is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
    page.add_style_tag(content=".welcome { display: none !important; }")
    for n in CSS_ORDER:
        c = read(n)
        if c: page.add_style_tag(content=c)
    for n in JS_ORDER:
        c = read(n)
        if c: page.evaluate(c)
    page.wait_for_timeout(600)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.wait_for_timeout(300)
    page.evaluate("(p) => window.__wxConfig.setMomentsPosts(p)", POSTS)
    page.locator('#wx-nav nav dl:has(dd:text-is("发现"))').first.click()
    page.wait_for_timeout(900)
    if screencast:
        cdp = ctx.new_cdp_session(page)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
            "everyNthFrame": 1, "maxWidth": 2600, "maxHeight": 3900})
    page.locator('[data-wx-action="moments"]:visible').first.click()
    page.wait_for_timeout(1500)
    if smooth:
        # 复刻 main.py 的 rAF 缓动滚动（起步加速+收尾减速，~400ms）
        page.evaluate("""() => {
            const n = document.querySelector('#moments .wpm-scroll') || document.getElementById('moments');
            const start = n.scrollTop, dist = 420 - start;
            const t0 = performance.now(), dur = 400;
            const ease = (x) => (x < 0.5 ? 4*x*x*x : 1 - Math.pow(-2*x+2, 3)/2);
            const step = (now) => {
                const p = Math.min(1, (now - t0) / dur);
                n.scrollTop = start + dist * ease(p);
                if (p < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
        }""")
    else:
        page.evaluate("""() => {
            const n = document.querySelector('#moments .wpm-scroll') || document.getElementById('moments');
            n.scrollTop = 420;
        }""")
    page.wait_for_timeout(900)
    info = page.evaluate("""() => {
        const img = document.querySelectorAll('.my-gallery .thumbnail img')[2];
        const r = img.getBoundingClientRect();
        return [Math.round(r.x), Math.round(r.y)];
    }""")
    page.screenshot(path=os.path.join(OUT, "sq_%s.png" % name))
    br.close()
    print(name, "tile3 rect:", info, "已存截图")

from playwright.sync_api import sync_playwright
import numpy as np
from PIL import Image
cover = np.asarray(Image.open(os.path.join(OUT, "true_cover.png")).convert("RGB").resize((196,196))).astype(np.int16)
with sync_playwright() as pw:
    chrome = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
    run(pw, chrome, "M1_smooth_sc", True, True)
    run(pw, chrome, "M2_smooth_only", True, False)
    run(pw, chrome, "M3_instant_sc", False, True)
for name in ["M1_smooth_sc", "M2_smooth_only", "M3_instant_sc"]:
    im = Image.open(os.path.join(OUT, "sq_%s.png" % name)).convert("RGB")
    # 贴片在 (346,324) viewport（滚动后），DSF3
    box = (346*3, 324*3, (346+112)*3, (324+112)*3)
    a = np.asarray(im.crop(box).resize((196,196))).astype(np.int16)
    d = np.abs(a - cover)
    print("%-14s vs true_cover: 平均差 %6.1f  >30像素 %6d" % (name, d.mean(), (d.max(axis=2)>30).sum()))
