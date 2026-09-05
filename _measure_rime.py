# -*- coding: utf-8 -*-
"""Measure Rime engine deploy timing in a headless chromium, static-serving vue-WeChat/public.
Tests two worker variants:
  - local: worker.js patched to load rime.js/wasm/data from /engine/ (same-origin)
  - (optionally) cdn: default worker.js (loads from jsdelivr CDN)
"""
import os, sys, time, threading, http.server, functools, json
from playwright.sync_api import sync_playwright

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
PORT = 8912
EXTRA = {"Content-Type": "application/javascript"}  # .js served correctly


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


# bootstrap JS mirror of main._rime_bootstrap_js but with BASE/ENG pointed at local server
FILES = [
    "rime_ice.schema.yaml", "default.yaml", "symbols_v.yaml", "rime_ice.dict.yaml",
    "cn_dicts/8105.dict.yaml", "cn_dicts/base.dict.yaml", "cn_dicts/ext.dict.yaml",
    "cn_dicts/tencent.dict.yaml", "cn_dicts/others.dict.yaml",
    "lua/select_character.lua", "lua/date_translator.lua", "lua/lunar.lua", "lua/uuid.lua",
    "lua/unicode.lua", "lua/number_translator.lua", "lua/calc_translator.lua", "lua/force_gc.lua",
    "lua/corrector.lua", "lua/autocap_filter.lua", "lua/v_filter.lua", "lua/pin_cand_filter.lua",
    "lua/long_word_filter.lua", "lua/reduce_english_filter.lua", "lua/search.lua",
    "lua/convert_ar_num_to_zh.lua",
]


def boostrap_js(worker_url, base, eng):
    files = json.dumps(FILES)
    base = json.dumps(base)
    eng = json.dumps(eng)
    return f"""
const __FILES={files};
const __BASE={base};
const __ENG={eng};
async function __ensureDir(FS, path){{let i=1;while((i=path.indexOf('/',i)+1)>0){{const d=path.slice(0,i);try{{await FS.lstat(d)}}catch{{await FS.mkdir(d)}}}}}}
(async()=>{{
  const t0=performance.now(); window.__log=[];
  function log(s){{window.__log.push([performance.now()-t0, s]);}}
  try {{
    const mw = await import(__ENG + '/my-worker.js'); log('import my-worker');
    const worker = new mw.LambdaWorker(__ENG + '/worker_local.js'); log('worker spawned');
    const FS = mw.asyncFS(worker);
    const setIME=worker.register('setIME'), setPageSize=worker.register('setPageSize'), deploy=worker.register('deploy');
    const processFn=worker.register('process');
    window.__rimeEngine={{ ready:false, process:(i)=>processFn(String(i)).then(r=>JSON.stringify(r)) }};
    let wrote=0;
    for (const f of __FILES) {{
      const p='/rime/'+f;
      try {{ const r=await fetch(__BASE+f); if(r.ok){{ await __ensureDir(FS,p); await FS.writeFile(p,new Uint8Array(await r.arrayBuffer())); wrote++; }} }} catch(e){{}}
    }}
    log('wrote '+wrote+' yaml files');
    try {{ await __ensureDir(FS,'/rime/default.custom.yaml'); await FS.writeFile('/rime/default.custom.yaml','patch:\\n  schema_list:\\n    - schema: rime_ice\\n'); }} catch(e){{}}
    log('wrote default.custom.yaml');
    try {{ log('deploy start'); await deploy(); log('deploy done'); await setIME('rime_ice'); setPageSize(10); window.__rimeEngine.ready=true; log('engine READY'); }} catch(e){{ console.error('rime deploy err', e); }}
  }} catch(e) {{ console.error('rime engine boot err', e); window.__rimeEngine = window.__rimeEngine || {{ready:false}}; }}
}})();
"""


def run(variant):
    # make a local worker copy only if not present
    worker_src = os.path.join(PUB, "engine", "worker.js")
    worker_local = os.path.join(PUB, "engine", "worker_local.js")
    if variant == "local":
        txt = open(worker_src, "r", encoding="utf-8").read()
        txt = txt.replace("https://cdn.jsdelivr.net/npm/@libreservice/my-rime@0.10.9/dist/", "/engine/")
        open(worker_local, "w", encoding="utf-8").write(txt)
        wurl = "worker_local.js"
    else:
        wurl = "worker.js"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 600, "height": 1300})
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")
        t00 = time.time()
        pg.evaluate("(js) => { const s=document.createElement('script'); s.type='module'; s.textContent=js; document.head.appendChild(s); }",
                    boostrap_js(wurl, "/engine/rime-ice/", "/engine"))
        try:
            pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=120_000)
            print(f"[{variant}] ready in {time.time()-t00:.2f}s")
        except Exception as e:
            print(f"[{variant}] NOT READY within timeout: {e}")
        logs = pg.evaluate("() => window.__log || []")
        for ms, s in logs:
            print(f"    {ms:7.0f}ms  {s}")
        # sanity: run a process through the engine
        try:
            r = pg.evaluate("() => window.__rimeEngine.process('nihao')")
            print(f"[{variant}] process('nihao') -> {r}")
        except Exception as e:
            print(f"[{variant}] process err {e}")
        b.close()


if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    for v in sys.argv[1:] or ["local"]:
        run(v)
