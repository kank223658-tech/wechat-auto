# -*- coding: utf-8 -*-
# 验证编辑器对方主页预览：预设套用 → 预览对齐真机 → 改字段实时刷新
import os, time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "_cmp_ref_home")
URL = "http://localhost:8000/scene"

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1720, "height": 1000})
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    time.sleep(1.5)

    # 1) 进对方主页预览视图
    page.evaluate("() => { setPanelTab('peer'); }")
    time.sleep(0.8)
    print("camView =", page.evaluate("() => camView"))

    # 2) 套用预设「花店店主·林晚晚」
    page.evaluate("""() => {
        const sel = document.getElementById('peerPresetSel');
        sel.value = '花店店主·林晚晚';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
        const btn = document.querySelector('[data-act="peer-apply-preset"]');
        btn.click();
    }""")
    time.sleep(1.0)

    # 3) 断言预览结构与真机一致
    checks = page.evaluate("""() => {
        const q = (s) => document.querySelector('#phoneInner ' + s);
        const nick = q('.wpp-nick');
        return {
            camView: camView,
            name: (q('.wpp-name-t') || {}).textContent,
            nicknameRow: nick ? nick.textContent : null,
            wxidText: (q('.wpp-wxid') || {}).textContent,
            genderShown: !!(q('.wpp-gender') && q('.wpp-gender').offsetWidth > 0),
            descHasBeiwang: ((q('.wpp-cell-desc') || {}).textContent || '').includes('备注、'),
            iconMsgBg: getComputedStyle(q('.wpp-ic-msg')).backgroundImage.includes('icon_msg'),
            iconCallBg: getComputedStyle(q('.wpp-ic-call')).backgroundImage.includes('icon_call'),
            wxidBlur: getComputedStyle(q('.wpp-wxid')).filter,
            thumbs: Array.from(document.querySelectorAll('#phoneInner .wpp-moments-cell .wpp-thumbs img')).map(i => i.getAttribute('src')),
        };
    }""")
    for k, v in checks.items():
        print(" ", k, "=", v)
    page.screenshot(path=os.path.join(OUT, "ed_preview_1.png"))

    # 4) 实时刷新：在面板里改「名字」和动态文案，看预览是否跟着变
    page.evaluate("""() => {
        const inp = document.querySelector('#panelBody [data-set$=".name"]');
        inp.value = '实时预览测试';
        inp.dispatchEvent(new Event('input', {bubbles: true}));
    }""")
    time.sleep(0.6)
    name_now = page.evaluate("() => document.querySelector('#phoneInner .wpp-name-t').textContent")
    print("改名字后预览 =", name_now)

    # 改第一条动态文案（若存在）
    has_post = page.evaluate("""() => {
        const inp = document.querySelector('#panelBody [data-set*=".posts[0].text"]');
        if (!inp) return false;
        inp.value = '预览实时刷新验证成功';
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        return true;
    }""")
    time.sleep(0.6)
    if has_post:
        txt = page.evaluate("() => { const t = document.querySelector('#phoneInner .wpm-texts'); return t ? t.textContent.slice(0, 30) : null; }")
        print("改动态文案后预览 =", txt)
    page.screenshot(path=os.path.join(OUT, "ed_preview_2.png"))

    b.close()
print("done")
