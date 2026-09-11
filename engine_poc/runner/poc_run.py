# -*- coding: utf-8 -*-
"""PoC runner：本地服务加载 Rime WASM 引擎(worker.js)，在无头 Chromium 里 process('nihao') 看候选。"""
import os, sys, threading, http.server, functools, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve")
PORT = 8792

def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd

httpd = serve()
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context()
    # 允许 WASM / 网络
    page = ctx.new_page()
    all_console = []
    page.on("console", lambda m: all_console.append(f"[{m.type}] {m.text}"))
    page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
    # 等引擎 boot + 首次 process（WASM+词库加载较慢）
    page.wait_for_function("window.__RIME_RESULT && window.__RIME_RESULT !== 'init'", timeout=60000)
    res = page.evaluate("window.__RIME_RESULT")
    # 再喂其他拼音看候选
    lines = []
    lines.append("process(nihao) -> " + res)
    for inp in ["women", "shijian", "kaixin", "wo"]:
        r = page.evaluate("(i) => window.__pocRun(i)", inp)
        lines.append(f"process({inp}) -> " + r)
    with open("_poc_result.txt", "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(lines))
    print("RESULT written to _poc_result.txt")
    print("PAGE_CONSOLE_TAIL:", "\n".join(all_console[-12:]))
    browser.close()
httpd.shutdown()
print("done")