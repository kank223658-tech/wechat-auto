# -*- coding: utf-8 -*-
"""最终验证：微信 Tab 图标（未选中态=发现页 / 选中态=首页）气泡居中测量 + 拼图。"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "_shot")
sys.path.insert(0, BASE)

from playwright.sync_api import sync_playwright
from PIL import Image

ENH = os.path.join(BASE, "enhance")
VW, VH = 600, 1300

CSS_ORDER = [
    "harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
    "wechat_modern.css", "human_actions.css", "transfer_ui.css",
    "send_image_ui.css", "peer_pages.css", "video_player.css",
    "homepage_exact.css", "wx_icons.css", "moments_exact.css", "discover_exact.css",
]
JS_ORDER = [
    "config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
    "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
    "video_player.js", "peer_pages.js",
]

def read(n):
    p = os.path.join(ENH, n)
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else None

def shoot(page, url, out):
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.wait_for_timeout(300)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    p = os.path.join(OUT, out + ".png")
    page.screenshot(path=p + ".warm.png")
    page.wait_for_timeout(400)
    page.screenshot(path=p)
    return p

def bubble_bbox(img, x0, y0, x1, y1, thr=120):
    """在区域内找亮色（白描边/绿气泡）像素 bbox。"""
    px = img.load()
    minx, miny, maxx, maxy = 10**9, 10**9, -1, -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if (r + g + b) / 3 > thr and not (abs(r-g) < 18 and abs(g-b) < 18 and r < 70):
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    return minx, miny, maxx, maxy

with sync_playwright() as pw:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    br = pw.chromium.launch(headless=True, executable_path=chrome if os.path.isfile(chrome) else None)
    ctx = br.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=1,
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
    page.wait_for_timeout(800)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.wait_for_timeout(300)

    home_p = shoot(page, "http://127.0.0.1:8080/#/", "tab_state_home")
    page.evaluate("() => { const vm=document.querySelector('#app').__vue__; if(vm&&vm.$store) vm.$store.state.newMsgCount=42; }")
    page.wait_for_timeout(600)
    exp_p = shoot(page, "http://127.0.0.1:8080/#/explore", "tab_state_explore")
    br.close()

home = Image.open(home_p).convert("RGB")
exp = Image.open(exp_p).convert("RGB")

# dt 区域（微信 Tab）：x 53.5~96.5, y 1175~1218 → 稍扩
X0, Y0, X1, Y1 = 45, 1165, 106, 1230
cx_dt, cy_dt = 75.0, 1196.5  # dt 中心

for name, im in (("首页选中态", home), ("发现页未选中态", exp)):
    b = bubble_bbox(im, X0, Y0, X1, Y1)
    cx = (b[0] + b[2]) / 2; cy = (b[1] + b[3]) / 2
    print(f"{name}: 气泡bbox={b} 中心=({cx:.1f},{cy:.1f})  dt中心=({cx_dt},{cy_dt})  偏差=({cx-cx_dt:+.1f},{cy-cy_dt:+.1f})")

# 拼图：左侧首页选中态 Tab 区，右侧发现页未选中态 Tab 区，标注中心线
tab_h = Y1 - Y0
canvas = Image.new("RGB", ((X1-X0)*2 + 16, tab_h + 60), (40, 40, 40))
canvas.paste(home.crop((X0, Y0, X1, Y1)), (0, 40))
canvas.paste(exp.crop((X0, Y0, X1, Y1)), ((X1-X0) + 16, 40))
from PIL import ImageDraw
d = ImageDraw.Draw(canvas)
for ox, label in ((0, "selected(home)"), ((X1-X0)+16, "unselected(explore)")):
    d.line([(ox + (cx_dt - X0), 40), (ox + (cx_dt - X0), tab_h + 40)], fill=(255, 60, 60), width=1)
    d.text((ox + 4, 8), label, fill=(230, 230, 230))
out_cmp = os.path.join(OUT, "tab_states_final_cmp.png")
canvas.save(out_cmp)
print("cmp:", out_cmp)
