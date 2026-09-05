# -*- coding: utf-8 -*-
"""临时：比较 evaluate(str) vs add_script_tag(content) 注入 pinyin_data.js 的耗时。运行后删除。"""
import os, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

js = open(os.path.join("enhance", "pinyin_data.js"), encoding="utf-8").read()
print("size MB =", round(len(js)/1e6, 2))

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content("<!doctype html><html><body></body></html>")
    t0 = time.time(); page.evaluate(js); t1 = time.time()
    print(f"evaluate: {t1-t0:.2f}s ok={page.evaluate('!!window.__WX_PINYIN')}")
    browser.close()

    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content("<!doctype html><html><body></body></html>")
    t2 = time.time(); page.add_script_tag(content=js); t3 = time.time()
    print(f"add_script_tag: {t3-t2:.2f}s ok={page.evaluate('!!window.__WX_PINYIN')}")
    browser.close()
print("done")