# -*- coding: utf-8 -*-
"""终极复现：直接复用 main.py 的 inject_overlays()（注入序列逐字节一致）。"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402  (仅用其注入函数; __main__ 守卫保证不会启动主流程)
from playwright.sync_api import sync_playwright  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_fs")
VW, VH = main.VIEWPORT_W, main.VIEWPORT_H
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

with sync_playwright() as pw:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    br = pw.chromium.launch(headless=True, executable_path=chrome if os.path.isfile(chrome) else None,
                            args=["--disable-background-timer-throttling",
                                  "--disable-backgrounding-occluded-windows",
                                  "--disable-renderer-backgrounding",
                                  "--disable-features=CalculateNativeWinOcclusion"])
    ctx = br.new_context(viewport={"width":VW,"height":VH}, device_scale_factor=main.DEVICE_SCALE_FACTOR,
        user_agent=main.MOBILE_UA, is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
    main.inject_overlays(page)          # ★ 与真实运行完全相同的注入
    page.wait_for_timeout(800)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.wait_for_timeout(300)
    page.evaluate("(p) => window.__wxConfig.setMomentsPosts(p)", POSTS)
    page.locator('#wx-nav nav dl:has(dd:text-is("发现"))').first.click()
    page.wait_for_timeout(900)
    # screencast（与真实运行同参数）
    cdp = ctx.new_cdp_session(page)
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
        "everyNthFrame": 1, "maxWidth": 2600, "maxHeight": 3900})
    page.locator('[data-wx-action="moments"]:visible').first.click()
    page.wait_for_timeout(1500)
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
    page.wait_for_timeout(900)
    info = page.evaluate("""() => {
        const img = document.querySelectorAll('.my-gallery .thumbnail img')[2];
        const r = img.getBoundingClientRect();
        const cs = getComputedStyle(img);
        return { rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                 objectFit: cs.objectFit };
    }""")
    page.screenshot(path=os.path.join(OUT, "full_inject.png"))
    br.close()
    print("贴片3:", info, "已存 full_inject.png")

cover = np.asarray(Image.open(os.path.join(OUT, "true_cover.png")).convert("RGB").resize((196,196))).astype(np.int16)
im = Image.open(os.path.join(OUT, "full_inject.png")).convert("RGB")
box = (346*3, 324*3, (346+112)*3, (324+112)*3)
a = np.asarray(im.crop(box).resize((196,196))).astype(np.int16)
d = np.abs(a - cover)
print("贴片3 vs true_cover: 平均差 %.1f  >30像素 %d" % (d.mean(), (d.max(axis=2)>30).sum()))
