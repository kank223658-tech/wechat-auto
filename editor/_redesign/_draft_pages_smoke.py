# -*- coding: utf-8 -*-
"""示意稿 通讯录/我 两页冒烟：切 Tab、截图、断言内容"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

errs = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-proxy-server"])
    pg = b.new_page(viewport={"width": 760, "height": 1700})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8000/scene.html", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(1500)
    # 确保在示意稿视图
    pg.locator('#btnViewDraft').click()
    pg.wait_for_timeout(500)
    # 点通讯录 Tab
    pg.locator('[data-navtab="通讯录"]').first.click(force=True)
    pg.wait_for_timeout(400)
    info1 = pg.evaluate("({camView, funcs: document.querySelectorAll('.wxc-func').length, rows: document.querySelectorAll('.wxc-row').length, active: document.querySelector('.tab.active .lb') ? document.querySelector('.tab.active .lb').textContent : ''})")
    pg.screenshot(path="editor/_redesign/_dp_contact.png")
    # 点我 Tab
    pg.locator('[data-navtab="我"]').first.click(force=True)
    pg.wait_for_timeout(400)
    info2 = pg.evaluate("({camView, name: (document.querySelector('.wxs-name')||{}).textContent, rows: document.querySelectorAll('.wxs-row').length, active: document.querySelector('.tab.active .lb') ? document.querySelector('.tab.active .lb').textContent : ''})")
    pg.screenshot(path="editor/_redesign/_dp_self.png")
    # 回微信 Tab
    pg.locator('[data-navtab="微信"]').first.click(force=True)
    pg.wait_for_timeout(300)
    back = pg.evaluate("camView")
    b.close()

print("contacts:", info1)
print("self:", info2)
print("back camView:", back)
print("pageerrors:", errs or "none")
ok = (info1.get("camView") == "contacts" and info1.get("funcs") == 4 and info1.get("rows", 0) >= 5
      and info1.get("active") == "通讯录" and info2.get("camView") == "self"
      and info2.get("rows") == 6 and info2.get("active") == "我" and back == "list" and not errs)
print("ALL PASS" if ok else "FAIL")
