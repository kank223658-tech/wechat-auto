# -*- coding: utf-8 -*-
"""Capture /rime/build files to disk via POST (avoids huge evaluate round-trip)."""
import os, time, threading, http.server, functools, json, base64, sys
from playwright.sync_api import sync_playwright

PUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
PORT = 8920
DEST = os.path.join(PUB, "engine", "rime-ice", "build")
FILES = ["rime_ice.schema.yaml", "default.yaml", "symbols_v.yaml", "rime_ice.dict.yaml",
    "cn_dicts/8105.dict.yaml", "cn_dicts/base.dict.yaml", "cn_dicts/ext.dict.yaml",
    "cn_dicts/tencent.dict.yaml", "cn_dicts/others.dict.yaml",
    "lua/select_character.lua", "lua/date_translator.lua", "lua/lunar.lua", "lua/uuid.lua",
    "lua/unicode.lua", "lua/number_translator.lua", "lua/calc_translator.lua", "lua/force_gc.lua",
    "lua/corrector.lua", "lua/autocap_filter.lua", "lua/v_filter.lua", "lua/pin_cand_filter.lua",
    "lua/long_word_filter.lua", "lua/reduce_english_filter.lua", "lua/search.lua",
    "lua/convert_ar_num_to_zh.lua"]


class Handler(http.server.SimpleHTTPRequestHandler):
    directory = PUB
    def do_POST(self):
        if self.path.startswith("/save/"):
            rel = self.path[len("/save/"):]
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = base64.b64decode(body)
            except Exception as e:
                self.send_response(400); self.end_headers(); self.wfile.write(str(e).encode()); return
            fp = os.path.join(DEST, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as fh:
                fh.write(data)
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
            print(f"  saved {rel}  {len(data)/1024:.0f}KB")
            return
        super().do_POST()


def serve():
    # 关键：SimpleHTTPRequestHandler.__init__ 会用 directory 参数覆盖类属性，必须用
    # functools.partial 把 PUB 作为 directory 传进去，否则会以 cwd 为根导致 /engine/ 404。
    handler = functools.partial(Handler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


PRE = r"""
const __FILES=%FILES%;const __BASE='/engine/rime-ice/';const __ENG='/engine';
async function __ensureDir(FS,path){let i=1;while((i=path.indexOf('/',i)+1)>0){const d=path.slice(0,i);try{await FS.lstat(d)}catch{await FS.mkdir(d)}}}
function b64e(u8){let s='';const CH=16384;for(let i=0;i<u8.length;i+=CH){s+=String.fromCharCode.apply(null,u8.subarray(i,i+CH));}return btoa(s);}
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
    log('wrote yaml');log('deploy start');await deploy();log('deploy done');
    await setIME('rime_ice');setPageSize(10);window.__rimeEngine.ready=true;log('setIME done');
    async function walk(dir,out){let es;try{es=await FS.readdir(dir)}catch(e){return}for(const e of es){if(e==='.'||e==='..')continue;const p=dir+'/'+e;let st;try{st=await FS.lstat(p)}catch(er){continue}if(st&&st.mode&&(st.mode&61440)===16384){await walk(p,out)}else{out.push(p)}}}
    let names=[];try{await walk('/rime/build',names)}catch(e){names=[String(e)]}
    log('listed '+names.length);
    let saved=0;
    for(const p of names){
      const rel=p.replace('/rime/build/','');
      if(rel===p) continue; // not under build
      try{ const buf=await FS.readFile(p); const s=b64e(buf); await fetch('/save/'+rel,{method:'POST',body:s}); saved++; }catch(e){ window.__log.push([Math.round(performance.now()-t0),'readfail '+rel+' '+String(e)]); }
    }
    log('saved '+saved);
    window.__saveDone = saved;   // 存完置标志，供 Python 等完成再关浏览器
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
    pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=300_000)
    try:
        pg.wait_for_function("() => window.__saveDone !== undefined", timeout=600_000)
    except Exception as e:
        print("saveDone wait err:", e)
    print("logs:", pg.evaluate("()=>window.__log"))
    print("saveDone:", pg.evaluate("()=>window.__saveDone"))
    b.close()
