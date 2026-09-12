"""端到端冒烟：场景编辑器「实时预览」（同源嵌入真实前端）。

覆盖：
  1) 默认视图 = 实时预览，iframe 就绪（__wxEmbedReady）
  2) 预览里显示的就是 scene.json 里的会话（逐条比对名字）
  3) 空闲 6 秒 0 请求（不卡的硬证据）
  4) 右侧面板改字段 → 预览跟着变；改完还原
  5) 预览锁定 1:1（缩放会让浏览器把 iframe 渲染成黑屏）+ 滚轮上下平移能看到底部
  6) 预览可点击：真实鼠标点会话行 → 进入对话页并渲染出消息
  7) 三个视图（实时预览 / 真机运行 / 示意稿）互切正常
  8) 无页面报错
"""
import asyncio
import io
import json
import urllib.parse

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
PV = "document.getElementById('stagePv').contentWindow"
PVD = PV + ".document"

FIRST_NAME = "() => { const e = %s.querySelector('.wechat-list li.list-row .desc-author'); " \
             "return e ? e.textContent.trim() : null; }" % PVD


async def frame_ready(p, timeout=40000):
    await p.wait_for_function(
        "() => { const f = document.getElementById('stagePv');"
        " try { return !!(f && f.contentWindow && f.contentWindow.__wxEmbedReady); }"
        " catch (e) { return false; } }", timeout=timeout)


async def main():
    scene = json.load(io.open(r"G:/weixin-auto/scene.json", encoding="utf-8"))
    want = [(it.get("name") or it.get("group") or "") for it in scene.get("home", [])][:6]

    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        p = await b.new_page(viewport={"width": 1600, "height": 1000})
        errs = []
        p.on("pageerror", lambda e: errs.append("PAGEERR " + str(e)))
        p.on("console", lambda m: errs.append("CONSOLE " + m.text) if m.type == "error" else None)
        reqs = []
        p.on("request", lambda r: reqs.append(r.url.split("8000")[-1]))

        await p.goto(BASE + "/scene.html", wait_until="domcontentloaded")
        print("1) stageView =", await p.evaluate("stageView"))
        await frame_ready(p)
        print("   pvReady =", await p.evaluate("pvReady"), "| 预览渲染器已就绪")

        await p.wait_for_timeout(1500)
        got = await p.evaluate(
            "() => [...%s.querySelectorAll('.wechat-list li.list-row .desc-author')]"
            ".map(e => e.textContent.trim())" % PVD)
        print("2) 场景前 6 条:", want)
        print("   预览实际显示:", got[:6])
        assert got[:6] == want, "预览内容与场景不一致"

        await p.wait_for_timeout(1500)
        n0 = len(reqs)
        await p.wait_for_timeout(6000)
        idle = reqs[n0:]
        print("3) 空闲 6s 新增请求:", len(idle), idle[:6])
        assert not idle, "空闲期仍在发请求（会卡）：%s" % idle[:6]

        newname = "预览同步测试_改名"
        target = await p.evaluate(
            "(want) => { const all = [...document.querySelectorAll('#panelBody input')];"
            " return all.findIndex(e => (e.value || '').trim() === want); }", want[0])
        assert target >= 0, "找不到会话名输入框"
        await p.locator("#panelBody input").nth(target).fill(newname)
        await p.wait_for_timeout(1800)
        first = await p.evaluate(FIRST_NAME)
        print("4) 面板改名后预览第一行:", first)
        assert first == newname, "预览没跟着编辑更新（还是 %r）" % first

        st = await p.evaluate(
            "() => { const before = zoom;"
            " const stage = document.getElementById('stage');"
            " for (let i = 0; i < 3; i++) stage.dispatchEvent(new WheelEvent('wheel',"
            "   { deltaY: 300, bubbles: true, cancelable: true }));"
            " const a = stage.getBoundingClientRect();"
            " const ph = document.querySelector('.phone').getBoundingClientRect();"
            " return { before: before, after: zoom, panY: Math.round(panY),"
            "          phBottom: Math.round(ph.bottom), stBottom: Math.round(a.bottom) }; }")
        print("5) 滚轮后:", st)
        assert st["before"] == 1 and st["after"] == 1, "预览里应锁定 1:1，实际 %s→%s" % (st["before"], st["after"])
        # 向下滚 → 画面上移（panY 变负），手机底部进入舞台视野
        assert st["panY"] < 0, "滚轮没有平移画面"
        assert st["phBottom"] <= st["stBottom"] + 1, "平移后手机底部仍看不到（%s > %s）" % (
            st["phBottom"], st["stBottom"])
        await p.evaluate("panY = 0; applyZoom();")

        await p.evaluate("scrollTo(0, 0)")
        await p.wait_for_timeout(300)
        box = await p.locator("#stagePv").bounding_box()
        inner = await p.evaluate(
            "(want) => { const au = [...%s.querySelectorAll('.wechat-list li.list-row .desc-author')]"
            ".find(e => e.textContent.trim() === want);"
            " if (!au) return null;"
            " const r = au.getBoundingClientRect();"
            " const h = %s.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);"
            " return { x: r.x + r.width / 2, y: r.y + r.height / 2, name: au.textContent.trim(),"
            "          hit: h ? h.tagName + '.' + h.className : 'null' }; }" % (PVD, PVD), want[1])
        assert inner, "找不到第二行会话行：%s" % want[1]
        print("   点击点命中元素:", inner["hit"])
        z = await p.evaluate("zoom")
        await p.mouse.click(box["x"] + inner["x"] * z, box["y"] + inner["y"] * z)
        await p.wait_for_timeout(1800)
        nav = await p.evaluate(
            "() => { const w = %s; const d = w.document;"
            " const sec = d.querySelector('.dialogue-section');"
            " return { hash: w.location.hash, hasDialogue: !!d.querySelector('.dialogue'),"
            "          msg: sec ? sec.textContent.slice(0, 80) : null }; }" % PV)
        print("6) 点击会话行 %r →" % inner["name"], nav)
        assert "/wechat/dialogue" in nav["hash"], "点击没有进入对话页：%s" % nav["hash"]
        assert urllib.parse.quote(inner["name"]) in nav["hash"], "点开的不是这一行：%s" % nav["hash"]
        assert nav["hasDialogue"], "对话页没有渲染出来"
        assert nav["msg"], "对话页里没有消息"

        await p.locator("#btnViewDraft").click()
        await p.wait_for_timeout(300)
        s7 = await p.evaluate(
            "() => ({ v: stageView, pvHidden: document.getElementById('stagePv').hidden,"
            " draftVisible: document.getElementById('phoneInner').style.visibility !== 'hidden' })")
        print("7) 切到示意稿:", s7)
        assert s7["v"] == "draft" and s7["pvHidden"] and s7["draftVisible"]

        await p.locator("#btnViewLive").click()
        await p.wait_for_timeout(400)
        s8 = await p.evaluate("() => stageView")
        print("   切到真机运行:", s8)
        assert s8 == "live"

        await p.locator("#btnViewPv").click()
        await p.wait_for_timeout(800)
        s9 = await p.evaluate(
            "() => ({ v: stageView, zoom: zoom, pvHidden: document.getElementById('stagePv').hidden,"
            " emptyHidden: document.getElementById('stagePvEmpty').hidden })")
        print("   切回实时预览:", s9)
        assert s9["v"] == "pv" and not s9["pvHidden"] and s9["emptyHidden"] and s9["zoom"] == 1

        real = [e for e in errs if "404" not in e and "Failed to load resource" not in e]
        print("8) 页面报错:", real[:5] or "none")
        assert not real, real[:5]

        await p.locator("#panelBody input").nth(target).fill(want[0])
        await p.wait_for_timeout(1600)
        back = await p.evaluate(FIRST_NAME)
        print("9) 已还原第一行名字:", back)
        assert back == want[0], "还原失败：%s" % back

        await p.locator(".stage").screenshot(path=r"G:/weixin-auto/_pv_in_editor.png")
        print("已截图 _pv_in_editor.png（舞台区域）")
        print("ALL PASS")
        await b.close()


asyncio.run(main())
