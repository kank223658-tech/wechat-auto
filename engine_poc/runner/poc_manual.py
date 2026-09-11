# -*- coding: utf-8 -*-
"""验证手动雾凇部署（仅 my-worker，无 micro-plum/esbuild）。结果写文件。"""
import os, sys, threading, http.server, functools, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
DIST=os.path.join(os.path.dirname(os.path.abspath(__file__)),"serve")
PORT=8797
handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=DIST)
httpd=http.server.ThreadingHTTPServer(("127.0.0.1",PORT),handler)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
with sync_playwright() as p:
    b=p.chromium.launch(); page=b.new_page()
    console=[]; page.on("console",lambda m:console.append(f"[{m.type}] {m.text}"))
    page.goto(f"http://127.0.0.1:{PORT}/manual.html",wait_until="load")
    page.wait_for_timeout(2000)
    # 等待 READY（手动部署：下载+编译，约 30s）
    try:
        page.wait_for_function("window.__READY===true || /ERR/.test((window.__LOG||[]).join(''))",timeout=120000)
    except Exception as e:
        pass
    ready=page.evaluate("() => window.__READY")
    log=page.evaluate("() => (window.__LOG||[]).join('\\n')")
    errs=page.evaluate("() => (window.__E||[]).join('\\n')")
    lines=["READY="+str(ready),"LOG:\n"+log,"ERRS:\n"+errs]
    if ready:
        for inp in ["nihao","wo"]:
            lines.append("process(%s) -> %s"%(inp, page.evaluate("(i)=>window.__rimeEngine.process(i)",inp)))
    lines.append("CONSOLE:\n"+"\n".join(console[-12:]))
    open("_manual.txt","w",encoding="utf-8").write("\n".join(lines))
    b.close()
httpd.shutdown()
print("written _manual.txt")