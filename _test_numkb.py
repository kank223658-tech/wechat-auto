# -*- coding: utf-8 -*-
"""数字键盘冒烟 v2：显式 123 闪键翻页 / pressType 数字高亮 / 拼音翻回 / 热区-贴图像素对齐校验。"""
from playwright.sync_api import sync_playwright
from PIL import Image
import numpy as np

URL = 'http://localhost:8080/_test_numkb.html'
OUT = '_numref'
TEX = np.array(Image.open('vue-WeChat/public/images/chatbar/kb_body_num.png').convert('RGB'), dtype=np.int16)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 640, 'height': 1360})
    pg.goto(URL)
    pg.wait_for_timeout(300)
    pg.evaluate("window.__wxKeyboard.show()")
    pg.focus('.chat-txt')
    pg.wait_for_timeout(400)

    # 1) 显式按 123：应先闪 123 键（字母页仍在），~150ms 后翻页
    pg.evaluate("window.__wxKeyboard.pressKey('123', 400)")
    pg.wait_for_timeout(60)
    pg.screenshot(path=f'{OUT}/_v2_flash123.png')     # 字母页 + 123 键高亮
    pg.wait_for_timeout(400)
    pg.screenshot(path=f'{OUT}/_v2_symbols.png')      # 数字页
    lay = pg.evaluate("window.__wxKeyboard && document.querySelector('#wxkb').classList.contains('kb-num')")
    print('kb-num class on #wxkb:', lay)

    # 2) 热区-贴图对齐校验：数字页每个键热区中心 取截图像素 vs 贴图像素
    shot = np.array(Image.open(f'{OUT}/_v2_symbols.png').convert('RGB'), dtype=np.int16)
    keys = pg.evaluate("""() => {
        const out = [];
        document.querySelectorAll('#wxkb .kb-grid:nth-of-type(2) .kb-key[data-key]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0) out.push({k: el.dataset.key, x: r.x + r.width/2, y: r.y + r.height/2});
        });
        return out;
    }""")
    kb_top = 1300 - 513          # #wxkb 顶在页面里的 y
    bad = 0
    for it in keys:
        cx, cy = int(round(it['x'])), int(round(it['y']))
        tx, ty = int(round(cx * 1179 / 600)), int(round((cy - kb_top) * 1179 / 600))
        sp = shot[cy, cx]; tp = TEX[ty, tx]
        d = int(np.abs(sp - tp).sum())
        if d > 60:
            bad += 1
            print(f"  MISMATCH {it['k']!r}: shot={tuple(sp)} tex={tuple(tp)}")
    print(f'align check: {len(keys)} keys, mismatches={bad}')

    # 3) pressType 打数字：'3' '0' 高亮 + 写入
    pg.evaluate("window.__wxKeyboard.pressType('3', 500)")
    pg.wait_for_timeout(80)
    pg.screenshot(path=f'{OUT}/_v2_press3.png')
    pg.wait_for_timeout(300)
    pg.evaluate("window.__wxKeyboard.pressType('0', 500)")
    pg.wait_for_timeout(500)
    v1 = pg.evaluate("document.querySelector('.chat-txt').value")

    # 4) 切回字母页：pressType('a') 自动硬切
    pg.evaluate("window.__wxKeyboard.pressType('a', 500)")
    pg.wait_for_timeout(80)
    pg.screenshot(path=f'{OUT}/_v2_back_letters.png')
    pg.wait_for_timeout(300)
    v2 = pg.evaluate("document.querySelector('.chat-txt').value")
    cur = pg.evaluate("window.__wxKeyboard && !document.querySelector('#wxkb').classList.contains('kb-num')")
    print('input:', repr(v1), '->', repr(v2), '| back on letters:', cur)
    b.close()
print('done')
