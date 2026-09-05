# -*- coding: utf-8 -*-
"""Verify the EDITED main.py bootstrap end-to-end (exactly as recording would inject it):
serve vue-WeChat/public, inject M._rime_bootstrap_js(), await ready, then process a few inputs
to confirm real Rime candidates come back. Reuses the switched worker_local.js + prebuilt build."""
import os, time, threading, http.server, functools, sys, json
from playwright.sync_api import sync_playwright
import main as M

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PUB = os.path.join(M.FRONTEND_DIR, "public")
PORT = 8930


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


with sync_playwright() as pw:
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 600, "height": 1300})
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")

    js = M._rime_bootstrap_js()
    print("== bootstrap uses worker_local.js:", "/worker_local.js" in js,
          "| has BUILD_FILES:", "__BUILD_FILES" in js, "| has BUILD_BASE:", "__BUILD_BASE" in js)

    t0 = time.time()
    pg.evaluate("(js)=>{const s=document.createElement('script');s.type='module';s.textContent=js;document.head.appendChild(s);}", js)
    try:
        pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=120_000)
        print(f"ENGINE READY in {time.time()-t0:.2f}s")
    except Exception as e:
        print("NOT READY:", e)

    try:
        r = pg.evaluate("() => window.__rimeEngine.process('nihao')")
        data = json.loads(r) if isinstance(r, str) else r
        cands = [c.get("text") for c in data.get("candidates", [])]
        print("process('nihao') ->", cands[:10])
    except Exception as e:
        print("process('nihao') err:", e)

    try:
        r2 = pg.evaluate("() => window.__rimeEngine.process('women')")
        data2 = json.loads(r2) if isinstance(r2, str) else r2
        cands2 = [c.get("text") for c in data2.get("candidates", [])]
        print("process('women') ->", cands2[:10])
    except Exception as e:
        print("process('women') err:", e)

    browser.close()
