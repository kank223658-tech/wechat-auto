# DOM 真值探针: 键盘组合→提交瞬间, rAF 采样空格/发送键状态, 判断是否存在「灰底无字」帧
import sys, time, json
sys.path.insert(0, '.')
import main
from playwright.sync_api import sync_playwright

def read_e(n):
    return main._read_enhance(n)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={'width': 600, 'height': 1300})
    pg.goto('http://localhost:8080/')
    pg.wait_for_timeout(2500)
    pg.mouse.click(300, 430)          # 进会话
    pg.wait_for_timeout(1000)
    pg.add_style_tag(content=read_e('chat_exact.css'))
    pg.add_style_tag(content=read_e('keyboard.css'))
    pg.evaluate(read_e('pinyin_data.js'))
    pg.evaluate(read_e('keyboard.js'))
    pg.evaluate('main.ENHANCE_JS' in dir(main) and '1' or '1')
    pg.evaluate(main.ENHANCE_JS)
    pg.evaluate(read_e('chat_extra.js'))
    pg.add_style_tag(content=read_e('panel_switch.css'))
    pg.wait_for_timeout(800)

    pg.evaluate("window.__wxKeyboard.show()")
    pg.wait_for_timeout(900)
    pg.mouse.click(250, 1210)
    pg.wait_for_timeout(500)
    focused = pg.evaluate("(document.activeElement||{}).className")
    print('focused:', focused)
    if 'chat-txt' not in (focused or ''):
        pg.evaluate("document.querySelector('.chat-txt').focus()")
        pg.wait_for_timeout(300)

    # 打拼音出组合
    pg.evaluate("window.__wxKeyboard.pressRun('hao', 120, 120, '好', 'hao')")
    pg.wait_for_timeout(800)
    print('composing before:', pg.evaluate("document.getElementById('wxkb').classList.contains('kb-composing')"))

    # 装 rAF 采样器: 记录每帧 space/send 的 text + composing class
    pg.evaluate("""
    window.__samp = [];
    (() => {
      const root = document.getElementById('wxkb');
      const sk = root.querySelector('.kb-key.kb-space');
      const sd = root.querySelector('.kb-key.kb-send');
      const t0 = performance.now();
      const tick = () => {
        __samp.push([Math.round(performance.now()-t0), root.classList.contains('kb-composing'),
                     sk.textContent, sd.textContent, getComputedStyle(sk).backgroundColor]);
        if (__samp.length < 600) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    })()""")

    # 提交
    pg.evaluate("window.__wxKeyboard.commitByPhrase('好')")
    pg.wait_for_timeout(1200)
    samples = pg.evaluate("window.__samp.splice(0)")
    # 只打印状态变化行
    prev = None
    for s in samples:
        key = (s[1], s[2], s[3], s[4])
        if key != prev:
            print('t=%sms composing=%s space=%r send=%r bg=%s' % (s[0], s[1], s[2], s[3], s[4]))
            prev = key
    b.close()
