# -*- coding: utf-8 -*-
"""完全复刻真实流程：store 写入 + 应用内导航进朋友圈，验证贴片渲染与滚动容器。"""
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
POSTS = [{"author":"小星","text":"九宫格。","images":["/images/avatar/110_158_夏天就要大胆穿__5_不吃饭了__来自小红书网页版_20260831_185134_593.jpg","/images/avatar/枯木_20260903_141720_316.jpg","/images/avatar/学习急救班素材_20260908_155548_722.png","/images/avatar/女友生气怎么哄教学_20260905_155312_388.png","/images/avatar/聊天技巧图片_20260905_154410_890.png","/images/avatar/一楼一饭店__1_Sabrina_来自小红书网页版_20260909_185707_580.jpg","/images/avatar/落日下海风拂面_1_纵鸠_来自小红书网页版_1_20260831_184706_666.jpg","/images/avatar/IMG_0512_20260901_140118_982.png","/images/avatar/IMG_0491_20260903_144508_035.png"],"time":"2分钟前","likes":[],"comments":[]},{"author":"铁木君","text":"四张图。","images":["/images/avatar/学习急救班素材_20260908_155548_722.png","/images/avatar/女友生气怎么哄教学_20260905_155312_388.png","/images/avatar/聊天技巧图片_20260905_154410_890.png","/images/avatar/110_158_夏天就要大胆穿__5_不吃饭了__来自小红书网页版_20260831_185134_593.jpg"],"time":"20分钟前","likes":[],"comments":[]},{"author":"月亮","text":"单图。","images":["/images/avatar/女友生气怎么哄教学_20260905_155312_388.png"],"time":"1小时前","likes":[],"comments":[]}]
_POSTS_OLD = [{"author":"小星","text":"九宫格。",
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

def dump_structure(page):
    return page.evaluate("""() => {
        const m = document.getElementById('moments');
        const out = { hash: location.hash, momentsExists: !!m };
        if (m) {
            out.children = Array.from(m.children).map(c =>
                c.tagName.toLowerCase() + '.' + String(c.className).split(' ').join('.'));
            const cands = [m.querySelector('.wpm-scroll'), m,
                           document.querySelector('#moments.sub-page')];
            out.scrollers = cands.map((el, i) => el ? {
                i, cls: String(el.className).slice(0, 40),
                sh: el.scrollHeight, ch: el.clientHeight, st: el.scrollTop } : null);
        }
        const img = document.querySelectorAll('.my-gallery .thumbnail img')[2];
        if (img) { const r = img.getBoundingClientRect();
            out.tile3 = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }
        return out;
    }""")

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
    # 真实序列：只写 store，不直接 renderPosts
    page.evaluate("(p) => window.__wxConfig.setMomentsPosts(p)", POSTS)
    # 应用内切「发现」Tab
    page.locator('#wx-nav nav dl:has(dd:text-is("发现"))').first.click()
    page.wait_for_timeout(900)
    # 点击「朋友圈」入口（应用内路由导航）
    page.locator('[data-wx-action="moments"]:visible').first.click()
    page.wait_for_timeout(1500)
    which = sys.argv[1] if len(sys.argv) > 1 else ''
    if which == 'disc':
        page.add_style_tag(content=open(os.path.join(ENH, 'discover_exact.css'), encoding='utf-8').read())
        page.wait_for_timeout(800)
    elif which == 'chat':
        page.add_style_tag(content=open(os.path.join(ENH, 'chat_exact.css'), encoding='utf-8').read())
        page.wait_for_timeout(800)
    print("进朋友圈后:", dump_structure(page))
    # 滚动：优先 .wpm-scroll，退回 #moments
    page.evaluate("""() => {
        const sc = document.querySelector('#moments .wpm-scroll') || document.getElementById('moments');
        sc.scrollTop = 420;
    }""")
    page.wait_for_timeout(800)
    info = dump_structure(page)
    print("滚动后:", info)
    page.screenshot(path=os.path.join(OUT, "realflow_%s.png" % (which or "base")))
    br.close()
    print("已存 realflow.png")

import numpy as np
from PIL import Image
cover = np.asarray(Image.open(os.path.join(OUT, "true_cover.png")).convert("RGB").resize((196,196))).astype(np.int16)
im = Image.open(os.path.join(OUT, "realflow_%s.png" % (which or "base"))).convert("RGB")
t = info.get("tile3")
if t:
    box = (int(t[0])*3, int(t[1])*3, int(t[0]+t[2])*3, int(t[1]+t[3])*3)
    a = np.asarray(im.crop(box).resize((196,196))).astype(np.int16)
    d = np.abs(a - cover)
    print("贴片3 vs true_cover: 平均差 %.1f  >30像素 %d" % (d.mean(), (d.max(axis=2)>30).sum()))
    im.crop(box).save(os.path.join(OUT, "v3", "realflow_tile3.png"))
