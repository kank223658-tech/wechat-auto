# -*- coding: utf-8 -*-
import os, sys, threading, http.server, functools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
DIST=os.path.join(os.path.dirname(os.path.abspath(__file__)),"serve")
PORT=8795
handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=DIST)
httpd=http.server.ThreadingHTTPServer(("127.0.0.1",PORT),handler)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
with sync_playwright() as p:
    b=p.chromium.launch(); page=b.new_page()
    page.goto(f"http://127.0.0.1:{PORT}/probe.html",wait_until="load")
    page.wait_for_timeout(2500)
    ok=page.evaluate("() => window.__DONE || 'not-run'")
    errs=page.evaluate("() => window.__E || []")
    open("_probe.txt","w",encoding="utf-8").write("DONE: "+str(ok)+"\nERRS: "+"\n".join(errs))
    b.close()
httpd.shutdown()
print("written _probe.txt")