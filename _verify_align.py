# -*- coding: utf-8 -*-
"""验证「候选-上屏首位对齐微调」：对若干此前会不对齐的词，敲全拼音后
候选第一项 == 本段要上屏的字/词（且 commitByPhrase 后文字一致）。

复刻 _probe_prebuilt 的引擎引导（worker_local + 预编译 build），再注入
pinyin_data.js + keyboard.js + 一个测试输入框，模拟主驱动打字。
"""
import os, time, threading, http.server, functools, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
import main as M

ROOT = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(ROOT, "vue-WeChat", "public")
PORT = 8931

# 用 main.py 自己的引导（worker_local + 预编译 build），复刻录屏真实引擎启动
ENGINE_BOOT = M._rime_bootstrap_js()


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=PUB)
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()


def run_case(pg, word, py, engine):
    """在测试输入框里敲 py 字母，稍等引擎候选，返回 (候选第一项, 输入值)。"""
    pg.evaluate("""() => {
        const el = document.getElementById('ti');
        el.value = '';
        el.focus();
        window.__wxKeyboard.show();
        window.__wxKeyboard.setTopHint(%s, %s);
    }""" % (json.dumps(word), json.dumps(py)))
    pg.type("#ti", py)
    pg.wait_for_timeout(700 if engine else 60)
    first = pg.evaluate(
        "() => { const c=document.querySelector('#kbCandList .kb-cand-item'); return c ? (c.dataset.chars||'') : ''; }")
    committed = pg.evaluate(
        "() => { window.__wxKeyboard.commitByPhrase(%s); return document.getElementById('ti').value; }"
        % json.dumps(word))
    return first, committed


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 600, "height": 1300})
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/engine/", wait_until="domcontentloaded")
        pg.add_script_tag(path=os.path.abspath(os.path.join(ROOT, "enhance", "pinyin_data.js")))
        pg.add_script_tag(content=open(os.path.join(ROOT, "enhance", "keyboard.js"), encoding="utf-8").read())
        pg.evaluate("""() => { const inp=document.createElement('input'); inp.id='ti'; inp.type='text';
            inp.style.position='fixed'; inp.style.top='0'; inp.style.left='0'; inp.style.width='500px'; inp.style.height='40px';
            document.body.appendChild(inp); }""")
        pg.evaluate(
            "(js) => { const s=document.createElement('script'); s.type='module'; s.textContent=js; document.head.appendChild(s); }",
            ENGINE_BOOT)
        engine = False
        try:
            pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=90_000)
            engine = True
            print("[引擎] 就绪")
        except Exception as e:
            print("[引擎] 未就绪，仅测离线:", e)

        cases = [
            ("甩", "shuai"),
            ("帅", "shuai"),
            ("窜出来", "cuanchulai"),
            ("洗洗", "xixi"),
            ("回话", "huihua"),
            ("我们", "women"),
            ("陆香儿", "luxianger"),
        ]
        mismatch = 0
        for word, py in cases:
            first, committed = run_case(pg, word, py, engine)
            ok = (first == word)
            if not ok:
                mismatch += 1
            flag = "OK " if ok else "MISMATCH"
            print(f"  [{flag}] target={word!r} py={py!r} cand0={first!r} committed={committed!r}")
        print("mismatches:", mismatch)
        b.close()


if __name__ == "__main__":
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    main()
