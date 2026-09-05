# -*- coding: utf-8 -*-
"""Two-phase test:
Phase 1: deploy rime_ice, capture all files under /rime (source yaml + build output) with mtimes.
Phase 2 (fresh worker/context): write source yamls only, then restore captured build files,
   call deploy, measure whether deploy skips (fast) or recompiles (slow). Also try setting build
   file mtimes ahead of source to defeat up-to-date check.
"""
import os, sys, time, threading, http.server, functools, json, base64
from playwright.sync_api import sync_playwright

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
PORT = 8913
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


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


def bootstrap(phase):
    return f"""
const __FILES={json.dumps(FILES)};
const __BASE={json.dumps('/engine/rime-ice/')};
const __ENG={json.dumps('/engine')};
async function __ensureDir(FS,path){{let i=1;while((i=path.indexOf('/',i)+1)>0){{const d=path.slice(0,i);try{{await FS.lstat(d)}}catch{{await FS.mkdir(d)}}}}}}
function ls(FS, dir, out){{
  let ents; try{{ents=FS.readdir(dir)}}catch(e){{return}}
  for(const e of ents){{ if(e==='.'||e==='..')continue; const p=dir+'/'+e; let st; try{{st=FS.lstat(p)}}catch(er){{continue}}
    if(FS.isDir(st.mode)){{ ls(FS,p,out); }} else {{ try{{ out.push({{p:p, size:st.size, mt:st.mtime.getTime(), b64:base64enc(FS.readFile(p))}}); }}catch(er){{}} }}
  }}
}}
function base64enc(u8){{ let s=''; for(let i=0;i<u8.length;i++) s+=String.fromCharCode(u8[i]); return btoa(s); }}
function base64dec(s){{ const bin=atob(s); const u=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i); return u; }}
(async()=>{{
  const t0=performance.now(); window.__log=[]; function log(s){{window.__log.push([performance.now()-t0,s]);}}
  try {{
    const mw = await import(__ENG+'/my-worker.js');
    const worker = new mw.LambdaWorker(__ENG+'/worker_local.js');
    const FS = mw.asyncFS(worker);
    const setIME=worker.register('setIME'), setPageSize=worker.register('setPageSize'), deploy=worker.register('deploy');
    const processFn=worker.register('process');
    window.__rimeEngine={{ready:false}};
    let wrote=0;
    for(const f of __FILES){{ const p='/rime/'+f; try{{ const r=await fetch(__BASE+f); if(r.ok){{ await __ensureDir(FS,p); await FS.writeFile(p,new Uint8Array(await r.arrayBuffer())); wrote++; }} }}catch(e){{}} }}
    try{{ await __ensureDir(FS,'/rime/default.custom.yaml'); await FS.writeFile('/rime/default.custom.yaml','patch:\\n  schema_list:\\n    - schema: rime_ice\\n'); }}catch(e){{}}
    const PHASE={json.dumps(phase)};
    if(PHASE==='1'){{
      log('deploy start'); await deploy(); log('deploy done');
      await setIME('rime_ice'); setPageSize(10);
      log('setIME done');
      let out=[]; ls(FS,'/rime',out);
      window.__rimeEngine={{ready:true, snap:out}};
      log('snapshot: '+out.length+' files');
    }} else {{
      // phase 2: restore build files BEFORE deploy
      const snap=window.__SNAP;
      let restored=0;
      for(const f of snap){{
        if(!f.p.startsWith('/rime/build/')) continue;
        try{{ await __ensureDir(FS,f.p); await FS.writeFile(f.p, base64dec(f.b64)); restored++; }}catch(e){{}}
      }}
      log('restored build files: '+restored);
      log('deploy start'); await deploy(); log('deploy done');
      await setIME('rime_ice'); setPageSize(10); window.__rimeEngine={{ready:true}}; log('engine READY');
    }}
  }}catch(e){{ console.error('boot err', e); window.__rimeEngine=window.__rimeEngine||{{ready:false}}; }}
}})();
"""


def run_phase(p, variant, snap_b64=None):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 600, "height": 1300})
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")
        if snap_b64 is not None:
            pg.evaluate("(s) => { window.__SNAP = JSON.parse(atob(s)); }", snap_b64)
        t00 = time.time()
        pg.evaluate("(js) => { const s=document.createElement('script'); s.type='module'; s.textContent=js; document.head.appendChild(s); }",
                    bootstrap(variant))
        pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=180_000)
        print(f"[phase {variant}] ready in {time.time()-t00:.2f}s")
        for ms, s in pg.evaluate("() => window.__log || []"):
            print(f"    {ms:7.0f}ms  {s}")
        snap = pg.evaluate("() => window.__rimeEngine.snap || null")
        b.close()
        return snap


if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    # phase 1: deploy and snapshot
    snap = run_phase(1, "1")
    if snap:
        b64 = base64.b64encode(json.dumps(snap).encode("utf-8")).decode("utf-8")
        print(f"snapshot files={len(snap)} total={sum(f['size'] for f in snap)//1024}KB")
        # save snapshot to disk
        with open("_rime_snap.json", "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False)
        # phase 2: fresh run, restore build, deploy
        run_phase(2, "2", snap_b64=b64)
    else:
        print("phase1 got no snapshot")
