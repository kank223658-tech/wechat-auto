# -*- coding: utf-8 -*-
"""雾凇部署：先探测导入是否OK，再尝试部署 rime_ice。结果写文件。"""
import os, sys, threading, http.server, functools, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
DIST=os.path.join(os.path.dirname(os.path.abspath(__file__)),"serve")
PORT=8796
handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=DIST)
httpd=http.server.ThreadingHTTPServer(("127.0.0.1",PORT),handler)
threading.Thread(target=httpd.serve_forever,daemon=True).start()
with sync_playwright() as p:
    b=p.chromium.launch(); page=b.new_page()
    console=[]; page.on("console",lambda m:console.append(f"[{m.type}] {m.text}"))
    page.goto(f"http://127.0.0.1:{PORT}/index.html",wait_until="load")
    # 等模块就绪（probe: window.__READY 由部署成功后置 true；先看模块是否 loading）
    page.wait_for_timeout(4000)
    has=page.evaluate("() => typeof window.__deployWusong")
    ok0=page.evaluate("() => window.__READY")
    log0=page.evaluate("() => (window.__LOG||[]).join('\\n')")
    lines=["typeof __deployWusong="+str(has), "READY="+str(ok0), "LOG0:\n"+log0]
    if has=="function":
        t0=time.time()
        ret=page.evaluate("() => window.__deployWusong()")
        dt=time.time()-t0
        log1=page.evaluate("() => (window.__LOG||[]).join('\\n')")
        lines.append("DEPLOY_RET="+str(ret))
        lines.append("DEPLOY_SEC=%.1f"%dt)
        lines.append("LOG1:\n"+log1)
        if str(ret).startswith("ok"):
            import json
            man = page.evaluate("() => JSON.stringify(window.__MANIFEST || [])")
            lines.append("MANIFEST:\n" + man)
            for inp in ["nihao","women","shijian","kaixin"]:
                lines.append("process(%s) -> %s"%(inp, page.evaluate("(i)=>window.__process(i)",inp)))
    lines.append("CONSOLE:\n"+"\n".join(console[-20:]))
    open("_poc_wusong.txt","w",encoding="utf-8").write("\n".join(lines))
    b.close()
httpd.shutdown()
print("written _poc_wusong.txt")