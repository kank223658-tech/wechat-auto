# -*- coding: utf-8 -*-
"""最小复现：裸 HTML + 这张 PNG，逐项叠加 CSS 成分，找触发绘错的配方。"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_fs")
os.makedirs(OUT, exist_ok=True)
SRC = "/images/avatar/学习急救班素材_20260908_155548_722.png"

CASES = [
    ("m1_bare",        '<img src="%s" style="width:112px;height:112px;object-fit:cover">' % SRC),
    ("m2_overflow",    '<div style="width:112px;height:112px;overflow:hidden"><img src="%s" style="width:112px;height:112px;object-fit:cover"></div>' % SRC),
    ("m3_radiusfig",   '<div style="width:112px;height:112px;overflow:hidden;border-radius:4px"><img src="%s" style="width:112px;height:112px;object-fit:cover"></div>' % SRC),
    ("m4_radiusimg",   '<div style="width:112px;height:112px;overflow:hidden"><img src="%s" style="width:112px;height:112px;object-fit:cover;border-radius:4px"></div>' % SRC),
    ("m5_tz",          '<div style="width:112px;height:112px;overflow:hidden"><img src="%s" style="width:112px;height:112px;object-fit:cover;transform:translateZ(0)"></div>' % SRC),
    ("m6_100pct",      '<div style="width:112px;height:112px;overflow:hidden"><img src="%s" style="width:100%%;height:100%%;object-fit:cover"></div>' % SRC),
]
HTML = ("<html><head><style>body{margin:0;background:#262626}"
        ".row{display:flex;flex-wrap:wrap;gap:8px;padding:8px}"
        "</style></head><body><div class='row'>"
        + "".join("<div id='%s'>%s</div>" % (n, h) for n, h in CASES)
        + "</div><script>window.scrollTo(0,0)</script></body></html>")

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    chrome = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
    for dsf in (3, 1):
        br = pw.chromium.launch(headless=True,
                                executable_path=chrome if os.path.isfile(chrome) else None)
        ctx = br.new_context(viewport={"width": 800, "height": 400},
                             device_scale_factor=dsf)
        page = ctx.new_page()
        page.set_content(HTML.replace("/images/", "http://127.0.0.1:8080/images/"))
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(OUT, "min_dsf%d.png" % dsf))
        print("已存 min_dsf%d" % dsf)
        br.close()
