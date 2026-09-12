# -*- coding: utf-8 -*-
"""诊断：缺角标的 host 是谁 + scene 404 的 URL 是什么 + index hover 时浮层状态时序"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
not_found = []

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-proxy-server"])
    pg = browser.new_page(viewport={"width": 1500, "height": 950})
    pg.on("response", lambda r: not_found.append(r.url) if r.status == 404 else None)

    for page, path in [("scene", "/scene.html"), ("concurrent", "/concurrent.html")]:
        not_found.clear()
        pg.goto(BASE + path, wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        missing = pg.evaluate("""() => {
          return [...document.querySelectorAll('.qt-host')].filter(h => !h.querySelector(':scope > .qt-badge'))
            .map(h => h.tagName + '#' + (h.id || h.className));
        }""")
        print(page, "缺角标:", missing)
        print(page, "404:", not_found[:6])

    # index hover 时序诊断
    pg.goto(BASE + "/index.html", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    box = pg.locator("#btnRun").bounding_box()
    print("btnRun box:", box)
    pg.locator("#btnRun").hover()
    for ms in (50, 200, 500):
        pg.wait_for_timeout(ms if ms == 50 else ms - (50 if ms == 200 else 200))
        st = pg.evaluate("""() => { const p = document.querySelector('.qt-pop');
          return p ? {show: p.classList.contains('show'), txt: (p.textContent||'').slice(0,20), top: p.style.top} : null; }""")
        print(f"hover后{ms}ms 浮层:", st)
    browser.close()
