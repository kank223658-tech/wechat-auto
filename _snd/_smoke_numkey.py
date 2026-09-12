# -*- coding: utf-8 -*-
"""冒烟（注入版）：数字键盘页发送键组合态变化 确认↔发送。
字母页组合态 → 切 123 数字页组合态保持（灰「确认」/空格「选定」）→
按确认上屏 → 回蓝「发送」→ 打数字仍「发送」。逐态截图 + 键面像素探针。
"""
import sys, time, json, urllib.request
sys.path.insert(0, '.')
import main
from playwright.sync_api import sync_playwright

def read_e(n):
    return main._read_enhance(n)

_g = {}
def shot(name):
    _g['pg'].screenshot(path=f'_snd/{name}.png')
    print('shot', name)

CSS1 = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
        "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css",
        "send_image_ui.css", "peer_pages.css", "block_ui.css", "video_player.css",
        "homepage_exact.css"]
JS1 = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
       "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "transfer_detail.js",
       "send_image_ui.js", "video_player.js", "peer_pages.js", "block_ui.js"]
CSS2 = ["chat_exact.css", "panel_switch.css", "wx_icons.css", "moments_exact.css", "discover_exact.css"]
JS2 = ["panel_switch.js", "human_actions.js", "homepage.js"]

def probe_send(pg, tag):
    """发送键面像素探针：蓝=发送态、深灰=确认态。只取可见(宽度>10)的 send 键。"""
    rects = json.loads(pg.evaluate("""JSON.stringify([...document.querySelectorAll('#wxkb .kb-key.kb-send')]
        .map(e=>{const b=e.getBoundingClientRect();return [b.x|0,b.y|0,b.width|0,b.height|0]}))"""))
    print(tag, 'send rects:', rects)
    x, y, w, h = [t for t in rects if t[2] > 10][0]
    from PIL import Image
    im = Image.open(f'_snd/{tag}.png').convert('RGB')
    crop = im.crop((x + 8, y + 8, x + w - 8, y + h - 8))
    px = list(crop.getdata()); n = len(px)
    blue = sum(1 for p in px if p[2] > 150 and p[2]-p[0] > 40)
    gray = sum(1 for p in px if abs(p[0]-78) < 14 and abs(p[1]-78) < 14 and abs(p[2]-78) < 14)
    key = sum(1 for p in px if abs(p[0]-112) < 10 and abs(p[1]-112) < 10 and abs(p[2]-112) < 10)
    txt = pg.evaluate("""[...document.querySelectorAll('#wxkb .kb-key.kb-send')]
        .find(e=>e.getBoundingClientRect().width>10).textContent""")
    print(f'{tag}: blue={blue/n:.2%} fnGray={gray/n:.2%} keyGray={key/n:.2%} text={txt}')

def tap_key(pg, sel):
    r = json.loads(pg.evaluate(f"""JSON.stringify((()=>{{
        const els=[...document.querySelectorAll('{sel}')];
        const el=els.find(e=>e.getBoundingClientRect().width>10)||els[0];
        if(!el)return null;const b=el.getBoundingClientRect();
        return [b.x+b.width/2,b.y+b.height/2]}})())"""))
    pg.mouse.click(r[0], r[1])

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 600, 'height': 1300})
    _g['pg'] = pg
    pg.goto('http://localhost:8080', wait_until='networkidle')
    pg.wait_for_timeout(600)
    for c in CSS1:
        pg.add_style_tag(content=read_e(c))
    for j in JS1:
        pg.evaluate(read_e(j))
    pg.add_script_tag(content=read_e("pinyin_data.js"))
    pg.evaluate(read_e("keyboard.js"))
    pg.evaluate(main.ENHANCE_JS)
    for j in JS2:
        pg.evaluate(read_e(j))
    for c in CSS2:
        pg.add_style_tag(content=read_e(c))
    pg.evaluate("window.__wxDebugAgent = 1")

    pg.mouse.click(300, 430)          # 进会话
    pg.wait_for_timeout(900)
    pg.mouse.click(250, 1210)         # 输入栏出键盘
    pg.wait_for_timeout(800)
    ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
    if not ok:
        pg.mouse.click(250, 1184)
        pg.wait_for_timeout(800)
        ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
    if not ok:
        pg.evaluate("window.__wxKeyboard.show()")
        pg.wait_for_timeout(800)
        pg.mouse.click(250, 1184)
        pg.wait_for_timeout(500)
        ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
    print('kb visible:', ok)

    shot('num_0_letters_send'); probe_send(pg, 'num_0_letters_send')

    # 态2 打拼音 → 组合态；键盘弹出后按实测 rect 点击聚焦
    r = json.loads(pg.evaluate("JSON.stringify((()=>{const el=document.querySelector('.chat-txt');"
                               "const b=el.getBoundingClientRect();return [b.x,b.y,b.width,b.height]})())"))
    pg.mouse.click(r[0] + r[2] / 2, r[1] + r[3] / 2)
    pg.wait_for_timeout(300)
    pg.evaluate("document.querySelector('.chat-txt').focus()")
    pg.wait_for_timeout(200)
    print('focused:', pg.evaluate("(document.activeElement||{}).className"))
    pg.evaluate("window.__wxKeyboard.pressRun('wo', 130, 130, '我', 'wo')")
    pg.wait_for_timeout(700)
    print('composing after pressRun:',
          pg.evaluate("document.getElementById('wxkb').classList.contains('kb-composing')"))
    shot('num_1_letters_confirm'); probe_send(pg, 'num_1_letters_confirm')

    # 态3 切数字页，组合态应保持
    tap_key(pg, '#wxkb .kb-key[data-key="123"]')
    pg.wait_for_timeout(700)
    print('wxkb class after 123:', pg.evaluate("document.getElementById('wxkb').className"))
    shot('num_2_numkey_confirm'); probe_send(pg, 'num_2_numkey_confirm')
    print('space text:', pg.evaluate("""[...document.querySelectorAll('#wxkb .kb-key.kb-space')]
        .find(e=>e.getBoundingClientRect().width>10).textContent"""))

    # 态4 数字页按「确认」→ 拼音原样上屏 → 回发送态
    pg.evaluate("window.__pd=[]; document.getElementById('wxkb').addEventListener('pointerdown', e=>window.__pd.push(e.target.dataset.key||'x'), true)")
    tap_key(pg, '#wxkb .kb-key.kb-send')
    pg.wait_for_timeout(600)
    print('pd events:', pg.evaluate("window.__pd"))
    print('dbg tail:', pg.evaluate("(window.__wxDelDebug||[]).slice(-8).map(d=>d.location+':'+d.message+':'+JSON.stringify(d.data))"))
    print('composing after send tap:', pg.evaluate("document.getElementById('wxkb').classList.contains('kb-composing')"))
    shot('num_3_numkey_send'); probe_send(pg, 'num_3_numkey_send')
    print('input value:', pg.evaluate("(document.querySelector('.chat-txt')||{value:''}).value"))

    # 态5 数字页打数字 → 保持发送态
    pg.evaluate("document.querySelector('.chat-txt').focus()")
    pg.wait_for_timeout(200)
    for k in ['1', '2', '3']:
        tap_key(pg, f'#wxkb .kb-key[data-key="{k}"]')
        pg.wait_for_timeout(350)
    print('input value after digits:', pg.evaluate("(document.querySelector('.chat-txt')||{value:''}).value"))
    shot('num_4_digits'); probe_send(pg, 'num_4_digits')

    b.close()
