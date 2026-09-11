# -*- coding: utf-8 -*-
"""测试不同 Rime 方案 + 提交选中，验证简体候选与选字上屏。结果写文件。"""
import os, sys, threading, http.server, functools, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve")
PORT = 8793

def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd

httpd = serve()
lines = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
    page.wait_for_function("window.__pocReady && window.__pocReady()", timeout=60000)

    # 试几个方案 + 各自 process
    for ime in ["luna_pinyin", "luna_pinyin_simp", "luna_pinyin_fluency", "double_pinyin"]:
        try:
            page.evaluate("(i) => window.__setIme(i)", ime)
            page.wait_for_timeout(400)
            r = page.evaluate("() => window.__process('nihao')")
            lines.append(f"[{ime}] nihao -> {r}")
        except Exception as e:
            lines.append(f"[{ime}] ERR {e}")

    # 用 luna_pinyin_simp 验证选字：先输入 w o m e n，查看候选，选中第 0 个
    try:
        page.evaluate("() => window.__setIme('luna_pinyin_simp')")
        page.wait_for_timeout(300)
        r = page.evaluate("() => window.__process('women')")
        lines.append("[select test] process(women) -> " + r)
        sel = page.evaluate("() => window.__select(0)")
        lines.append("[select test] select(0) -> " + sel)
    except Exception as e:
        lines.append("[select test] ERR " + str(e))

    with open("_poc_result.txt", "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(lines))
    browser.close()
httpd.shutdown()
print("written _poc_result.txt")