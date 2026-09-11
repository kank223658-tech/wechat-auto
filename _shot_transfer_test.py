# -*- coding: utf-8 -*-
"""渲染转账卡片测试页并截图（验证用，临时脚本）"""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 600, "height": 1000})
    pg.goto("http://localhost:8080/_transfer_test.html?v=%d" % int(time.time()))
    pg.wait_for_timeout(600)
    pg.screenshot(path=r"G:\weixin-auto\_transfer_render.png")
    b.close()
print("shot ok")
