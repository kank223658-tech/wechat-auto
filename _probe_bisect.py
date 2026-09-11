# -*- coding: utf-8 -*-
"""二分定位：真实流程 vs 探针的差异成分，谁让 tile3 变成「整图挤压」。

基线（已证正确）：13 个 CSS + 10 个 JS + renderPosts + scrollTop=420。
变体 A：基线 + main.py 的 html/body/#app contain:paint 内联片段。
变体 B：基线 + keyboard.js（表情 new Image() 预热）。
变体 C：变体 A 基础上，渲染后用 contain:none 覆盖回去（验证可就地拯救）。
"""
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
CONTAIN_SNIPPET = (
    "html, body { height: 100% !important; overflow: clip !important;"
    " contain: paint !important; width: 600px !important; max-width: 600px !important; }"
    "#app { overflow: clip !important; position: relative !important;"
    " contain: paint !important;"
    " width: 600px !important; max-width: 600px !important;"
    " height: 100% !important; min-height: 100% !important; }")
UNDO_SNIPPET = (
    "html, body { contain: none !important; }"
    "#app { contain: none !important; }")
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

def run_variant(pw, chrome, name, add_contain=False, add_keyboard=False, undo_contain=False, disable_prefetch=False, add_screencast=False, extra_css=None):
    br = pw.chromium.launch(headless=True, executable_path=chrome if os.path.isfile(chrome) else None)
    ctx = br.new_context(viewport={"width":VW,"height":VH}, device_scale_factor=3,
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
        is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
    page.add_style_tag(content=".welcome { display: none !important; }")
    if add_contain:
        page.add_style_tag(content=CONTAIN_SNIPPET)
    for n in CSS_ORDER:
        c = read(n)
        if c: page.add_style_tag(content=c)
    js = list(JS_ORDER) + (["keyboard.js"] if add_keyboard else [])
    for n in js:
        c = read(n)
        if c: page.evaluate(c)
    page.wait_for_timeout(600)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.wait_for_timeout(300)
    if add_screencast:
        cdp = ctx.new_cdp_session(page)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92,
            "everyNthFrame": 1, "maxWidth": 2600, "maxHeight": 3900})
    if extra_css:
        page.add_style_tag(content=extra_css)
        page.wait_for_timeout(200)
    page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    if disable_prefetch:
        page.evaluate("() => { if (window.__wxMoments) window.__wxMoments.prefetchGallery = function () {}; }")
    page.evaluate("(s) => window.__wxMoments.renderPosts(s)", POSTS)
    page.wait_for_timeout(1800)
    if undo_contain:
        page.add_style_tag(content=UNDO_SNIPPET)
        page.wait_for_timeout(400)
    page.evaluate("() => { document.getElementById('moments').scrollTop = 420; }")
    page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(OUT, "bis_%s.png" % name))
    br.close()
    print("已存 bis_%s.png" % name)

from playwright.sync_api import sync_playwright
import numpy as np
from PIL import Image
def quantify(name):
    def load(p, box=None, size=(196,196)):
        im = Image.open(p).convert("RGB")
        if box: im = im.crop(box)
        return np.asarray(im.resize(size)).astype(np.int16)
    cover = load(os.path.join(OUT, "true_cover.png"))
    BOX3 = (1035, 981, 1035+336, 981+336)
    a = load(os.path.join(OUT, "bis_%s.png" % name), BOX3)
    d = np.abs(a - cover)
    print("%-14s vs true_cover: 平均差 %6.1f  >30像素 %6d" % (name, d.mean(), (d.max(axis=2)>30).sum()))

if __name__ == "__main__" or True:
    which = sys.argv[1] if len(sys.argv) > 1 else "ABC"
    with sync_playwright() as pw:
        chrome = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
        if "A" in which: run_variant(pw, chrome, "A_contain", add_contain=True)
        if "B" in which: run_variant(pw, chrome, "B_kbd", add_keyboard=True)
        if "C" in which: run_variant(pw, chrome, "C_contain_undo", add_contain=True, undo_contain=True)
        if "D" in which: run_variant(pw, chrome, "D_nopf_full", add_contain=True, add_keyboard=True, disable_prefetch=True)
        if "E" in which: run_variant(pw, chrome, "E_contain_only", add_contain=True, disable_prefetch=True)
        if "F" in which: run_variant(pw, chrome, "F_kbd_only", add_keyboard=True, disable_prefetch=True)
        if "L" in which: run_variant(pw, chrome, "L_screencast", add_screencast=True, disable_prefetch=True)
        if "G" in which: run_variant(pw, chrome, "G_chat_css", extra_css=open(os.path.join(ENH, "chat_exact.css"), encoding="utf-8").read(), disable_prefetch=True)
        if "H" in which: run_variant(pw, chrome, "H_disc_css", extra_css=open(os.path.join(ENH, "discover_exact.css"), encoding="utf-8").read(), disable_prefetch=True)
    names = {"A":"A_contain","B":"B_kbd","C":"C_contain_undo","D":"D_nopf_full","E":"E_contain_only","F":"F_kbd_only","L":"L_screencast","G":"G_chat_css","H":"H_disc_css"}
    for k in which:
        if k in names: quantify(names[k])
