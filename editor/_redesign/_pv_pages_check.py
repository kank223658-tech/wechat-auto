# -*- coding: utf-8 -*-
"""快速核查真机预览里 通讯录/我的/个人信息 页面渲染（截图人看）"""
from playwright.sync_api import sync_playwright
import sys
sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-proxy-server"])
    pg = b.new_page(viewport={"width": 760, "height": 1400})
    pg.goto("http://127.0.0.1:8000/wxpv/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    for route, name in [("#/contact", "_pvchk_contact.png"),
                        ("#/self", "_pvchk_self.png"),
                        ("#/self/profile", "_pvchk_profile.png")]:
        pg.evaluate(f"location.hash = '{route}'")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f"editor/_redesign/{name}")
        print("shot", name)
    b.close()
print("OK")
