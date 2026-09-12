# -*- coding: utf-8 -*-
"""悬停问号提示冒烟：三页加载无报错、? 角标存在、悬停出说明浮层、按钮点击不受影响。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
results, all_errors = [], []

def check(name, ok, extra=""):
    results.append((name, ok, extra))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-proxy-server"])
    pg = browser.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: all_errors.append(f"[pageerror] {e}"))
    pg.on("console", lambda m: all_errors.append(f"[console.{m.type}] {m.text}") if m.type == "error" else None)

    for page, path, hover_id in [
        ("index", "/index.html", "btnRun"),
        ("scene", "/scene.html", "btnRun"),
        ("concurrent", "/concurrent.html", "btnRunAll"),
    ]:
        errs_before = len(all_errors)
        pg.goto(BASE + path, wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        n_tip = pg.eval_on_selector_all("[data-tip]", "els => els.length")
        n_badge = pg.eval_on_selector_all(".qt-badge", "els => els.length")
        n_host = pg.eval_on_selector_all(".qt-host", "els => els.length")
        n_expect = pg.evaluate("[...document.querySelectorAll('.qt-host')].filter(h => !['INPUT','SELECT','TEXTAREA','IMG','BR'].includes(h.tagName)).length")
        if n_badge != n_expect:
            pg.wait_for_timeout(400)  # 页面可能刚重写按钮文字，等补角标防抖走完
            n_badge = pg.eval_on_selector_all(".qt-badge", "els => els.length")
        check(f"{page}: data-tip 控件数>10", n_tip > 10, n_tip)
        check(f"{page}: 角标数=非void host数", n_badge == n_expect, f"badge={n_badge} expect={n_expect}")
        # 悬停出浮层
        loc = pg.locator(f"#{hover_id}")
        loc.hover()
        pg.wait_for_timeout(350)
        vis = pg.eval_on_selector(".qt-pop", "el => el.classList.contains('show') && el.textContent.length > 5")
        check(f"{page}: 悬停 #{hover_id} 出浮层", bool(vis))
        # 移开消失
        pg.mouse.move(700, 600)
        pg.wait_for_timeout(250)
        hidden = pg.eval_on_selector(".qt-pop", "el => !el.classList.contains('show')")
        check(f"{page}: 移开后浮层隐藏", hidden)
        check(f"{page}: 本页无 JS 报错", len(all_errors) == errs_before,
              all_errors[errs_before:errs_before+3])

    # index 视图切换仍正常（角标不挡点击）
    pg.goto(BASE + "/index.html", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.locator("#btnViewScript").click()
    pg.wait_for_timeout(600)
    ok_script = pg.evaluate("() => { const el = document.querySelector('#scriptView,#viewScript,.script-mode,[data-view=script]'); "
                            "return !!el || document.body.innerHTML.includes('btnTranslate'); }")
    check("index: 点剧本模式按钮后 btnTranslate 存在(切换生效)", bool(ok_script))
    # 菜单下拉仍能开
    pg.locator("#btnFileMenu").click()
    pg.wait_for_timeout(300)
    menu_open = pg.evaluate("() => { const m = document.querySelector('#btnFileMenu').closest('.menu-wrap').querySelector('.menu');"
                            " return m && getComputedStyle(m).display !== 'none'; }")
    check("index: 文件下拉菜单能打开", bool(menu_open))
    # 并发页动态图片库：打开后 libSort 的 title 被运行时转成 data-tip
    pg.goto(BASE + "/concurrent.html", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.locator("#btnCcToolMenu").click()
    pg.wait_for_timeout(300)
    pg.locator("#btnLib").click()
    pg.wait_for_timeout(900)
    lib_ok = pg.evaluate("() => { const el = document.getElementById('libSort');"
                         " return el && el.hasAttribute('data-tip') && !el.hasAttribute('title'); }")
    check("concurrent: 动态图片库下拉框 title 自动转 data-tip", bool(lib_ok))

    browser.close()

fails = [r for r in results if not r[1]]
print(f"\n== {len(results)-len(fails)}/{len(results)} PASS ==")
if all_errors:
    print("JS 报错汇总:")
    for e in all_errors[:10]:
        print("  " + e[:200])
sys.exit(1 if fails else 0)
