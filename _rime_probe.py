# -*- coding: utf-8 -*-
"""Decisive: capture build files (bytes) after deploy, then restore in a fresh worker + deploy, timed."""
import os, sys, time, threading, http.server, functools, json, base64
from playwright.sync_api import sync_playwright

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
PORT = 8917
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


PRE = r"""
const __FILES=%FILES%;const __BASE='/engine/rime-ice/';const __ENG='/engine';
async function __ensureDir(FS,path){let i=1;while((i=path.indexOf('/',i)+1)>0){const d=path.slice(0,i);try{await FS.lstat(d)}catch{await FS.mkdir(d)}}}
function b64e(u8){let s='';for(let i=0;i<u8.length;i++)s+=String.fromCharCode(u8[i]);return btoa(s);}
function b64d(s){const bin=atob(s);const u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);return u;}
function mtime(st){if(st&&st.mtime&&typeof st.mtime==='object'&&typeof st.mtime.getTime==='function')return st.mtime.getTime();if(st&&st.mtime&&typeof st.mtime==='number')return st.mtime*1000;return 0;}
(async()=>{
  const t0=performance.now();window.__log=[];function log(s){window.__log.push([Math.round(performance.now()-t0),s]);}
  try{
    const mw=await import(__ENG+'/my-worker.js');
    const worker=new mw.LambdaWorker(__ENG+'/worker_local.js');
    const FS=mw.asyncFS(worker);
    const setIME=worker.register('setIME'),setPageSize=worker.register('setPageSize'),deploy=worker.register('deploy');
    window.__rimeEngine={ready:false};
    for(const f of __FILES){const p='/rime/'+f;try{const r=await fetch(__BASE+f);if(r.ok){await __ensureDir(FS,p);await FS.writeFile(p,new Uint8Array(await r.arrayBuffer()));}}catch(e){}}
    try{await __ensureDir(FS,'/rime/default.custom.yaml');await FS.writeFile('/rime/default.custom.yaml','patch:\n  schema_list:\n    - schema: rime_ice\n');}catch(e){}
    log('wrote yaml');
    const PHASE='%PHASE%';
    if(PHASE==='1'){
      log('deploy start');await deploy();log('deploy done');
      await setIME('rime_ice');setPageSize(10);window.__rimeEngine.ready=true;log('setIME done');
      async function collect(dir,out){let es;try{es=await FS.readdir(dir)}catch(e){return}for(const e of es){if(e==='.'||e==='..')continue;const p=dir+'/'+e;let st;try{st=await FS.lstat(p)}catch(er){continue}if(st&&st.mode&&(st.mode&61440)===16384){await collect(p,out)}else{let bn='';try{bn=b64e(await FS.readFile(p))}catch(er){bn=''}out[p]=[st.size, mtime(st), bn];}}}
      let out={};try{await collect('/rime/build',out)}catch(e){out={ERR:String(e)}}
      window.__buildList=out;log('collected '+Object.keys(out).length);
    } else {
      const snap=window.__SNAP;let restored=0;
      for(const p in snap){if(!p.startsWith('/rime/build/'))continue;if(!snap[p][2])continue;try{await __ensureDir(FS,p);await FS.writeFile(p,b64d(snap[p][2]));restored++;}catch(e){}}
      log('restored '+restored+' build files');
      log('deploy start');await deploy();log('deploy done');
      await setIME('rime_ice');setPageSize(10);window.__rimeEngine.ready=true;log('engine READY');
    }
  }catch(e){console.error('boot err',String(e));window.__rimeEngine=window.__rimeEngine||{ready:false};}
})();
"""


def run_phase(phase, snap=None):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 600, "height": 1300})
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")
        if snap is not None:
            pg.evaluate("(s)=>{window.__SNAP=s;}", snap)
        pg.evaluate("(js)=>{const s=document.createElement('script');s.type='module';s.textContent=js;document.head.appendChild(s);}", PRE.replace("%FILES%", json.dumps(FILES)).replace("%PHASE%", phase))
        try:
            pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=150_000)
        except Exception as e:
            print(f"[phase {phase}] NOT READY: {e}")
        print(f"[phase {phase}] logs: {pg.evaluate('()=>window.__log')}")
        blist = pg.evaluate("()=>window.__buildList||null")
        b.close()
        return blist


if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    bl = run_phase("1")
    if not bl:
        print("no build list"); sys.exit(0)
    n = len(bl)
    tot = sum(v[0] for v in bl.values())
    print(f"build files={n} total={tot//1024}KB")
    for p, (sz, mt, _b) in sorted(bl.items()):
        print(f"    {p}  {sz/1024:.0f}KB  mt={mt}")
    run_phase("2", snap=bl)
