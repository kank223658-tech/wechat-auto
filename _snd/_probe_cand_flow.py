# 端到端候选流验证: 引擎注入 + keyboard, 逐键检查候选条内容
import sys, json
sys.path.insert(0, '.')
import main
from playwright.sync_api import sync_playwright

def read_e(n):
    return main._read_enhance(n)

def cand_text(pg):
    return pg.evaluate("""[...document.querySelectorAll('#kbCandList .kb-cand-item')].map(b=>b.dataset.chars||b.textContent.trim())""")

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={'width': 600, 'height': 1300})
    pg.goto('http://localhost:8080/')
    pg.wait_for_timeout(2000)
    pg.mouse.click(300, 430)          # 进会话
    pg.wait_for_timeout(900)
    pg.add_style_tag(content=read_e('chat_exact.css'))
    pg.add_style_tag(content=read_e('keyboard.css'))
    pg.evaluate(read_e('pinyin_data.js'))
    pg.evaluate(read_e('keyboard.js'))
    pg.evaluate(main.ENHANCE_JS)
    pg.evaluate(read_e('chat_extra.js'))
    pg.add_style_tag(content=read_e('panel_switch.css'))
    # 引擎注入（与管线同款）
    pg.evaluate("(js) => { const s=document.createElement('script'); s.type='module'; s.textContent=js; document.head.appendChild(s); }",
                main._rime_bootstrap_js())
    print('waiting rime ready...')
    pg.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true", timeout=90_000)
    pg.wait_for_timeout(300)

    pg.evaluate("window.__wxKeyboard.show()")
    pg.wait_for_timeout(700)
    pg.mouse.click(250, 1210)
    pg.wait_for_timeout(400)
    focused = pg.evaluate("(document.activeElement||{}).className")
    if 'chat-txt' not in (focused or ''):
        pg.evaluate("document.querySelector('.chat-txt').focus()")
        pg.wait_for_timeout(200)
    print('focused:', pg.evaluate("(document.activeElement||{}).className"))

    # 模拟逐键打 "nihao"（用管线同款 pressType 单键）
    pg.evaluate("window.__wxKeyboard.pressType('n', 60)")
    pg.wait_for_timeout(600)
    print('n   ->', cand_text(pg)[:8], '| value=', repr(pg.evaluate("document.querySelector('.chat-txt').value")))
    pg.evaluate("window.__wxKeyboard.pressType('i', 60)")
    pg.wait_for_timeout(600)
    print('ni  ->', cand_text(pg)[:8])
    pg.evaluate("window.__wxKeyboard.pressType('h', 60)")
    pg.wait_for_timeout(600)
    print('nih ->', cand_text(pg)[:8])
    pg.evaluate("window.__wxKeyboard.pressType('a', 60); window.__wxKeyboard.pressType('o', 60)")
    pg.wait_for_timeout(700)
    print('nihao ->', cand_text(pg)[:8])
    # 选定上屏（按空格=上屏首候选）
    pg.evaluate("window.__wxKeyboard.pressType('space', 80)")
    pg.wait_for_timeout(500)
    print('上屏后 value =', repr(pg.evaluate("document.querySelector('.chat-txt').value")), '候选:', cand_text(pg)[:5])
    # 再打 hao
    for k in 'hao':
        pg.evaluate(f"window.__wxKeyboard.pressType('{k}', 60)")
        pg.wait_for_timeout(200)
    pg.wait_for_timeout(500)
    print('再打 hao ->', cand_text(pg)[:8])
    # 退格两下
    pg.evaluate("window.__wxKeyboard.pressType('backspace', 60)")
    pg.wait_for_timeout(400)
    print('退格1 ->', cand_text(pg)[:5])
    pg.evaluate("window.__wxKeyboard.pressType('backspace', 60)")
    pg.wait_for_timeout(400)
    print('退格2 ->', cand_text(pg)[:5])
    b.close()
