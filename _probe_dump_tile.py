# -*- coding: utf-8 -*-
"""在探针环境里 dump 贴片3 的 DOM 与计算样式，验证 object-fit 是否真的生效。"""
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
POSTS = [{"author":"小星","text":"九宫格。",
 "images":["/images/avatar/110_158_夏天就要大胆穿__5_不吃饭了__来自小红书网页版_20260831_185134_593.jpg",
  "/images/avatar/枯木_20260903_141720_316.jpg","/images/avatar/学习急救班素材_20260908_155548_722.png",
  "/images/avatar/女友生气怎么哄教学_20260905_155312_388.png","/images/avatar/聊天技巧图片_20260905_154410_890.png",
  "/images/avatar/一楼一饭店__1_Sabrina_来自小红书网页版_20260909_185707_580.jpg",
  "/images/avatar/落日下海风拂面_1_纵鸠_来自小红书网页版_1_20260831_184706_666.jpg",
  "/images/avatar/IMG_0512_20260901_140118_982.png","/images/avatar/IMG_0491_20260903_144508_035.png"],
 "time":"2分钟前","likes":[],"comments":[]}]

def read(n):
    p = os.path.join(ENH, n)
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else None

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    chrome = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
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
    page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    page.evaluate("(s) => window.__wxMoments.renderPosts(s)", POSTS)
    page.wait_for_timeout(1800)
    info = page.evaluate("""() => {
        const imgs = document.querySelectorAll('.my-gallery .thumbnail img');
        const img = imgs[2];
        if (!img) return { error: '找不到贴片3', count: imgs.length };
        const cs = getComputedStyle(img);
        const chain = [];
        let el = img;
        while (el && el !== document.documentElement) {
            const s = getComputedStyle(el);
            if (s.transform !== 'none' || s.zoom !== '1' || s.filter !== 'none'
                || s.willChange !== 'auto' || s.contain !== 'none'
                || s.contentVisibility !== 'visible' || s.imageRendering !== 'auto') {
                chain.push({ tag: el.tagName + '.' + (el.className || ''),
                             transform: s.transform, zoom: s.zoom, filter: s.filter,
                             willChange: s.willChange, contain: s.contain,
                             contentVisibility: s.contentVisibility,
                             imageRendering: s.imageRendering });
            }
            el = el.parentElement;
        }
        const r = img.getBoundingClientRect();
        return {
            count: imgs.length,
            outer: img.outerHTML.slice(0, 300),
            rect: { x: r.x, y: r.y, w: r.width, h: r.height },
            natural: { w: img.naturalWidth, h: img.naturalHeight },
            computed: { objectFit: cs.objectFit, width: cs.width, height: cs.height,
                        zoom: cs.zoom, transform: cs.transform, imageRendering: cs.imageRendering,
                        filter: cs.filter, contain: cs.contain },
            suspiciousAncestors: chain,
            src: img.currentSrc || img.src
        };
    }""")
    import json
    print(json.dumps(info, ensure_ascii=False, indent=1))
    page.screenshot(path=os.path.join(OUT, "dump_tile3.png"))
    br.close()
