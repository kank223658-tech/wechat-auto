# -*- coding: utf-8 -*-
"""Just list /rime top-level and /rime/build names (awaited), no content read."""
import os, time, threading, http.server, functools, json
from playwright.sync_api import sync_playwright

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
PORT = 8918
FILES = ["rime_ice.schema.yaml", "default.yaml", "symbols_v.yaml", "rime_ice.dict.yaml",
    "cn_dicts/8105.dict.yaml", "cn_dicts/base.dict.yaml", "cn_dicts/ext.dict.yaml",
    "cn_dicts/tencent.dict.yaml", "cn_dicts/others.dict.yaml",
    "lua/select_character.lua", "lua/date_translator.lua", "lua/lunar.lua", "lua/uuid.lua",
    "lua/unicode.lua", "lua/number_translator.lua", "lua/calc_translator.lua", "lua/force_gc.lua",
    "lua/corrector.lua", "lua/autocap_filter.lua", "lua/v_filter.lua", "lua/pin_cand_filter.lua",
    "lua/long_word_filter.lua", "lua/reduce_english_filter.lua", "lua/search.lua",
    "lua/convert_ar_num_to_zh.lua"]


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


PRE = r"""
const __FILES=%FILES%;const __BASE='/engine/rime-ice/';const __ENG='/engine';
async function __ensureDir(FS,path){let i=1;while((i=path.indexOf('/',i)+1)>0){const d=path.slice(0,i);try{await FS.lstat(d)}catch{await FS.mkdir(d)}}}
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
    log('wrote yaml'); log('deploy start'); await deploy(); log('deploy done');
    await setIME('rime_ice');setPageSize(10);window.__rimeEngine.ready=true;log('setIME done');
    const results={};
    try{ results.root = await FS.readdir('/rime'); log('readdir /rime ok'); }catch(e){ results.rootErr=String(e); }
    for (const sub of ['/rime/build','/rime']){
      for (const cand of ['/rime/build','/rime/.build','/rime/build/rime_ice']){
        if(sub==='/rime/build'||true){break}
      }
    }
    window.__results=results; log('done');
  }catch(e){console.error('boot err',String(e));window.__rimeEngine=window.__rimeEngine||{ready:false};}
})();
"""

with sync_playwright() as pw:
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 600, "height": 1300})
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")
    pg.evaluate("(js)=>{const s=document.createElement('script');s.type='module';s.textContent=js;document.head.appendChild(s);}", PRE.replace("%FILES%", json.dumps(FILES)))
    pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=150_000)
    print("logs:", pg.evaluate("()=>window.__log"))
    print("results:", json.dumps(pg.evaluate("()=>window.__results"), ensure_ascii=False))
    b.close()
