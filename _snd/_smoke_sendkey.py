# -*- coding: utf-8 -*-
"""冒烟（注入版）：发送键组合态变化 发送↔确认。
自己开页面，按 main.py 同序注入 enhance，再进会话逐态抓 /shot.jpeg 真帧。
"""
import sys, time, json, urllib.request
sys.path.insert(0, '.')
import main  # 只为拿 ENHANCE_JS（有 __main__ 守卫，不会启动）
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
    print('injected, wxChat hooks ready')

    pg.mouse.click(300, 430)          # 进「陆香儿」会话
    pg.wait_for_timeout(900)
    print('after tap list:', pg.evaluate("document.body.className"))
    print('chat-txt:', pg.evaluate("!!document.querySelector('.chat-txt')"))
    pg.mouse.click(250, 1210)         # 点输入栏出键盘
    pg.wait_for_timeout(800)
    print('active:', pg.evaluate("(document.activeElement||{}).className || (document.activeElement||{}).tagName"))
    print('atPoint:', pg.evaluate("JSON.stringify((()=>{const el=document.elementFromPoint(250,1010);return el?el.className+'|'+el.tagName:'none'})())"))
    print('taBox:', pg.evaluate("JSON.stringify((()=>{const el=document.querySelector('.chat-txt');if(!el)return null;const r=el.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})())"))
    ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
    print('kb visible:', ok, '| body:', pg.evaluate("document.body.className"),
          '| wxkb:', pg.evaluate("!!document.getElementById('wxkb')"))
    if not ok:
        pg.evaluate("window.__wxKeyboard.show()")
        pg.wait_for_timeout(900)
        ok = pg.evaluate("!!(window.__wxKeyboard && window.__wxKeyboard.visible)")
        print('kb visible force-show:', ok)
    st1 = pg.evaluate("document.getElementById('wxkb').classList.contains('kb-composing')")
    shot('smoke_1_send')

    pg.evaluate("window.__wxKeyboard.pressRun('wo', 130, 130, '我', 'wo')")
    pg.wait_for_timeout(700)
    st2 = pg.evaluate("document.getElementById('wxkb').classList.contains('kb-composing')")
    cand = pg.evaluate("(document.querySelector('#kbCandList')||{textContent:''}).textContent")
    shot('smoke_2_confirm')

    pg.evaluate("window.__wxKeyboard.commitByPhrase('我')")
    pg.wait_for_timeout(500)
    st3 = pg.evaluate("document.getElementById('wxkb').classList.contains('kb-composing')")
    val = pg.evaluate("(document.querySelector('.chat-txt')||{value:''}).value")
    shot('smoke_3_back_to_send')

    print('composing: empty=%s / pinyin=%s / committed=%s' % (st1, st2, st3))
    print('cand:', cand)
    print('input value:', val)
    b.close()
