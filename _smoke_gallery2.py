# -*- coding: utf-8 -*-
"""场景编辑器 / 并发生产 的图片库面板冒烟。需先起编辑器服务（8765）。"""
import sys

BASE = "http://localhost:8765"
OK = 0
BAD = 0


def check(name, cond, extra=""):
    global OK, BAD
    if cond:
        OK += 1
        print("[ok]   %s %s" % (name, extra))
    else:
        BAD += 1
        print("[FAIL] %s %s" % (name, extra))


from playwright.sync_api import sync_playwright

errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    pg = br.new_page(viewport={"width": 1680, "height": 1050})
    pg.on("pageerror", lambda e: errs.append("scene/concurrent pageerror: " + str(e)))
    # 资源加载失败（页面本来就缺一批旧素材）单独记录，只对 /api/ 接口报错
    pg.on("response", lambda r: errs.append("接口 %s -> %s" % (r.status, r.url))
          if r.status >= 400 and "/api/" in r.url and "/api/live" not in r.url else None)
    pg.on("console", lambda m: errs.append("console.%s: %s" % (m.type, m.text))
          if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.on("dialog", lambda d: d.dismiss())

    # ---------- 场景编辑器 ----------
    pg.goto(BASE + "/scene.html", wait_until="networkidle")
    pg.wait_for_function("() => !!window.__wxPick")
    pg.evaluate("() => { try { localStorage.removeItem('wx-lib-cat'); } catch(e){} }")
    pg.evaluate("() => document.getElementById('btnLib').click()")
    pg.wait_for_selector("#libMask.show .lib-typebtn", timeout=8000)
    pg.wait_for_timeout(900)
    active = pg.evaluate("() => (document.querySelector('#libCats .lib-typebtn.on')||{}).getAttribute('data-cat')")
    check("[scene] 首次打开默认「配图素材」", active == "asset", "-> %r" % active)
    check("[scene] 分类按钮带张数", pg.evaluate(
        "() => /^\\d+$/.test((document.querySelector('#libCats .lib-typebtn.on span:last-child')||{}).textContent || '')"))
    check("[scene] 有排序下拉", pg.evaluate(
        "() => (document.getElementById('libSort')||{}).options && document.getElementById('libSort').options.length >= 3"))
    check("[scene] 有「⚙ 分类」按钮", pg.evaluate("() => !!document.getElementById('libCatMgr')"))
    check("[scene] 有批量操作按钮", pg.evaluate("() => (document.getElementById('libBatch')||{}).textContent.indexOf('批量操作') >= 0"))
    upcat = pg.evaluate("() => (document.getElementById('libUpcat')||{}).value")
    check("[scene] 上传目标跟随当前分类", upcat == "asset", "-> %r" % upcat)
    pg.evaluate("() => document.getElementById('libCatMgr').click()")
    pg.wait_for_selector(".wxp-cm.show .wxp-cm-row", timeout=5000)
    check("[scene] ⚙分类 打开共享分类管理", pg.evaluate("() => document.querySelectorAll('.wxp-cm-row').length") >= 6)
    pg.evaluate("() => document.getElementById('wxp-cm-close').click()")
    pg.screenshot(path="_shot/gallery_scene_lib.png")

    # 记忆：切 emoji → 关闭 → 再开应还在 emoji
    pg.evaluate("() => document.querySelector('#libCats .lib-typebtn[data-cat=\\\"emoji\\\"]').click()")
    pg.wait_for_timeout(300)
    pg.evaluate("() => document.getElementById('libClose').click()")
    pg.wait_for_timeout(200)
    pg.evaluate("() => document.getElementById('btnLib').click()")
    pg.wait_for_selector("#libMask.show .lib-typebtn", timeout=8000)
    pg.wait_for_timeout(700)
    active2 = pg.evaluate("() => (document.querySelector('#libCats .lib-typebtn.on')||{}).getAttribute('data-cat')")
    check("[scene] 再次打开停在上次的分类 (emoji)", active2 == "emoji", "-> %r" % active2)
    pg.evaluate("() => document.getElementById('libClose').click()")

    # ---------- 并发生产 ----------
    pg.goto(BASE + "/concurrent.html", wait_until="networkidle")
    pg.wait_for_function("() => !!window.__wxPick")
    pg.evaluate("() => { try { localStorage.removeItem('wx-lib-cat'); } catch(e){} }")
    pg.evaluate("() => [...document.querySelectorAll('.panel-tabs button')].find(b => b.getAttribute('data-tab') === 'library').click()")
    pg.wait_for_selector("#panelBody .lib-typebtn", timeout=8000)
    pg.wait_for_timeout(900)
    active3 = pg.evaluate("() => (document.querySelector('#panelBody .lib-typebtn.on')||{}).getAttribute('data-cat')")
    check("[conc] 首次打开默认「配图素材」", active3 == "asset", "-> %r" % active3)
    check("[conc] 分类按钮带张数", pg.evaluate(
        "() => /\\d/.test((document.querySelector('#panelBody .lib-typebtn.on')||{}).textContent || '')"))
    check("[conc] 有排序下拉", pg.evaluate("() => !!document.getElementById('libSort')"))
    check("[conc] 有「⚙ 分类」按钮", pg.evaluate("() => !!document.getElementById('libCatMgr')"))
    pg.evaluate("() => document.getElementById('libCatMgr').click()")
    pg.wait_for_selector(".wxp-cm.show .wxp-cm-row", timeout=5000)
    check("[conc] ⚙分类 打开共享分类管理", pg.evaluate("() => document.querySelectorAll('.wxp-cm-row').length") >= 6)
    pg.evaluate("() => document.getElementById('wxp-cm-close').click()")
    pg.screenshot(path="_shot/gallery_conc_lib.png")
    br.close()

check("两页无 JS 报错", not errs, "-> " + ("; ".join(errs[:4]) if errs else "干净"))
print("\n小结：通过 %d，失败 %d" % (OK, BAD))
sys.exit(1 if BAD else 0)
