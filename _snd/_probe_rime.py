# 引擎候选真值探针: 按管线同款方式注入雾凇, 查若干拼音的候选列表
import sys, time, json
sys.path.insert(0, '.')
import main
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={'width': 600, 'height': 1300})
    pg.goto('http://localhost:8080/')
    pg.wait_for_timeout(2000)
    pg.evaluate("(js) => { const s=document.createElement('script'); s.type='module'; s.textContent=js; document.head.appendChild(s); }",
                main._rime_bootstrap_js())
    print('waiting rime ready...')
    pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=90_000)
    print('ready.')
    def cands(q):
        r = pg.evaluate(f"window.__rimeEngine.process({json.dumps(q)}).then(r=>r)")
        d = json.loads(r)
        return [c.get('text', '') for c in (d.get('candidates') or [])][:3], d.get('body', '')

    print('ni ->', cands('ni'))
    print('+h ->', cands('h'))
    print('{Escape} ->', cands('{Escape}'))
    print('清空后 hao ->', cands('hao'))
    print('{BackSpace} ->', cands('{BackSpace}'))
    print('{Escape} 再清 ->', cands('{Escape}'))
    print('ma ->', cands('ma'))
    b.close()
