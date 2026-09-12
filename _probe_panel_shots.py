# -*- coding: utf-8 -*-
"""视觉确认：表情→更多切换中途截图（配合 _probe_panel_cross.py 的数值结论）。"""
from playwright.sync_api import sync_playwright

exec(open(r"G:/weixin-auto/_probe_panel_cross.py", encoding="utf-8").read().split("with sync_playwright")[0])

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 620, "height": 1340})
    pg.goto(URL, wait_until="domcontentloaded")
    pg.evaluate("document.querySelector('.welcome') && (document.querySelector('.welcome').style.display='none')")
    for n in CSS_BASE:
        pg.add_style_tag(content=read(ENH + n))
    pg.evaluate("window.__wxDefaultScene = %s" % read(r"G:/weixin-auto/scene.json"))
    for n in JS_ORDER:
        pg.add_script_tag(content=read(ENH + n))
    for n in CSS_POST:
        pg.add_style_tag(content=read(ENH + n))
    pg.wait_for_function("!!window.__wxChatExt && !!window.__wxTransfer", timeout=30000)
    pg.add_script_tag(content=read(ENH + "panel_switch.js"))
    pg.wait_for_function("!!window.__wxPanels", timeout=10000)
    pg.evaluate("window.__wxConfig.applyScene(window.__wxDefaultScene)")
    pg.evaluate("location.hash = '#/wechat/dialogue'")
    pg.wait_for_selector(".dialogue-section", timeout=15000)
    pg.wait_for_timeout(600)
    # 塞几条消息，模拟用户截图的「最后一条被输入栏盖住」场景
    pg.evaluate("""
      () => {
        const sec = document.querySelector('.dialogue-section');
        for (let i = 1; i <= 8; i++) {
          const d = document.createElement('div');
          d.className = 'row' + (i % 2 ? '' : ' right');
          d.innerHTML = '<div class="bubble"><p class="text" style="margin:0;padding:10px 14px;background:#3eb575;border-radius:8px;color:#fff;max-width:60vw">' + (i === 8 ? '转发：好东西一起看看' : '测试消息 ' + i) + '</p></div>';
          sec.appendChild(d);
        }
        sec.scrollTop = sec.scrollHeight;
      }
    """)
    pg.wait_for_timeout(300)
    # 打开表情面板 → 稳定 → 切更多，中途连拍
    pg.evaluate("window.__wxPanels.set('emoji')")
    pg.wait_for_timeout(700)
    pg.evaluate("window.__wxPanels.set('attach')")
    for i, delay in enumerate([60, 115, 170]):
        pg.wait_for_timeout(delay)
        pg.screenshot(path=f"_panelpeek/fix_mid_{i}.png")
    pg.wait_for_timeout(400)
    pg.screenshot(path="_panelpeek/fix_rest.png")
    print("shots saved")
    b.close()
