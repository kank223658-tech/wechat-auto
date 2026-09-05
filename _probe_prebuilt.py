# -*- coding: utf-8 -*-
"""Decisive: after writing prebuilt build files into /rime/build/, measure whether
(A) deploy() skips compilation (fast), and (B) skipping deploy + just setIME() works.
Each runs in a fresh browser context. Times deploy/setIME and sanity-processes 'nihao'."""
import os, time, threading, http.server, functools, json
from playwright.sync_api import sync_playwright

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
PORT = 8923
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
BUILD_FILES = [
    "default.yaml", "rime_ice.schema.yaml", "rime_ice.table.bin",
    "rime_ice.reverse.bin", "rime_ice.prism.bin",
]


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


def bootstrap(mode):
    files = json.dumps(FILES)
    build = json.dumps(BUILD_FILES)
    return f"""
const __FILES={files};const __BUILD={build};
const __BASE='/engine/rime-ice/';const __BUILDBASE='/engine/rime-ice/build/';const __ENG='/engine';
async function __ensureDir(FS,path){{let i=1;while((i=path.indexOf('/',i)+1)>0){{const d=path.slice(0,i);try{{await FS.lstat(d)}}catch{{await FS.mkdir(d)}}}}}}
(async()=>{{
  const t0=performance.now();window.__log=[];function log(s){{window.__log.push([Math.round(performance.now()-t0),s]);}}
  try{{
    const mw=await import(__ENG+'/my-worker.js');
    const worker=new mw.LambdaWorker(__ENG+'/worker_local.js');
    const FS=mw.asyncFS(worker);
    const setIME=worker.register('setIME'),setPageSize=worker.register('setPageSize'),deploy=worker.register('deploy');
    const processFn=worker.register('process');
    window.__rimeEngine={{ready:false,process:(i)=>processFn(String(i)).then(r=>JSON.stringify(r))}};
    for(const f of __FILES){{const p='/rime/'+f;try{{const r=await fetch(__BASE+f);if(r.ok){{await __ensureDir(FS,p);await FS.writeFile(p,new Uint8Array(await r.arrayBuffer()));}}}}catch(e){{}}}}
    try{{await __ensureDir(FS,'/rime/default.custom.yaml');await FS.writeFile('/rime/default.custom.yaml','patch:\\n  schema_list:\\n    - schema: rime_ice\\n');}}catch(e){{}}
    log('wrote yaml');
    // write prebuilt build files from static /engine/rime-ice/build/ into /rime/build/
    let wrote=0;
    for(const f of __BUILD){{
      const p='/rime/build/'+f;
      try{{const r=await fetch(__BUILDBASE+f);if(r.ok){{await __ensureDir(FS,p);await FS.writeFile(p,new Uint8Array(await r.arrayBuffer()));wrote++;}}}}catch(e){{log('build fetch fail '+f+' '+e)}}
    }}
    log('wrote '+wrote+' prebuilt build files');
    const MODE={json.dumps(mode)};
    let dep='skipped';
    if(MODE==='deploy'){{log('deploy start');await deploy();dep='deployed';log('deploy done');}}
    log('setIME start');await setIME('rime_ice');setPageSize(10);window.__rimeEngine.ready=true;log('setIME done');
    const r=await processFn('nihao');
    log('proc done len='+r.length);
    window.__depMode=dep; window.__procLen=r.length; window.__proc=r;
  }}catch(e){{console.error('boot err',String(e));window.__rimeEngine=window.__rimeEngine||{{ready:false}};window.__proc='ERR:'+String(e);}}
}})();
"""


def run(mode):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 600, "height": 1300})
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")
        t0 = time.time()
        pg.evaluate("(js)=>{const s=document.createElement('script');s.type='module';s.textContent=js;document.head.appendChild(s);}", bootstrap(mode))
        try:
            pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=120_000)
            print(f"[{mode}] ready in {time.time()-t0:.2f}s")
        except Exception as e:
            print(f"[{mode}] NOT READY: {e}")
        for ms, s in pg.evaluate("()=>window.__log||[]"):
            print(f"    {ms:7.0f}ms  {s}")
        print(f"[{mode}] process('nihao') len=", pg.evaluate("()=>window.__procLen"))
        b.close()


if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    run("deploy")
    run("noDeploy")
