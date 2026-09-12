# -*- coding: utf-8 -*-
"""UX 二轮冒烟：问号弹层 / hint 折叠 / 等高布局"""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
errors = []

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        pg = await b.new_page()
        pg.on("pageerror", lambda e: errors.append("index: " + str(e)))
        pg.on("console", lambda m: errors.append("index: " + m.text) if m.type == "error" else None)
        await pg.goto(BASE + "/index.html", wait_until="networkidle")

        # --- 工作流视图仍在，切到脚本模式 ---
        await pg.locator(".view-btn").nth(1).click()
        await pg.wait_for_timeout(300)
        # 使用说明大卡片应已不在文档流中
        assert await pg.locator(".script-card.hint-card").count() == 0, "hint-card still present"
        # 问号按钮存在且点击弹出说明
        q = pg.locator('.hq[data-help="#scriptHelpSrc"]')
        assert await q.count() == 1, "script hq missing"
        await q.click()
        assert await pg.locator(".hq-pop").count() == 1, "popover not opened"
        tips = await pg.locator(".hq-pop li").count()
        assert tips >= 8, "popover items missing: %d" % tips
        # 点别处关闭
        await pg.locator("#scriptInput").click()
        await pg.wait_for_timeout(150)
        assert await pg.locator(".hq-pop").count() == 0, "popover not closed"

        # --- 创作模式 ---
        await pg.locator(".view-btn").nth(2).click()
        await pg.wait_for_timeout(300)
        q2 = pg.locator('.hq[data-help="#createHelpSrc"]')
        assert await q2.count() == 1, "create hq missing"
        await q2.click()
        assert await pg.locator(".hq-pop").count() == 1, "create popover not opened"
        # 等高：脚本模式左右两栏卡片高度一致
        await pg.locator(".view-btn").nth(1).click()
        await pg.wait_for_timeout(200)
        h = await pg.evaluate("""() => {
          const l = document.querySelector('.script-input-col > .script-card').getBoundingClientRect();
          const r = document.querySelector('.script-result-col > .script-card').getBoundingClientRect();
          return [l.height, r.height];
        }""")
        assert abs(h[0] - h[1]) < 4, "columns not equal: %s" % h
        print("INDEX OK  col-heights=%s" % h)

        # --- scene.html ---
        ps = await b.new_page()
        ps.on("pageerror", lambda e: errors.append("scene: " + str(e)))
        ps.on("console", lambda m: errors.append("scene: " + m.text) if m.type == "error" else None)
        await ps.goto(BASE + "/scene.html", wait_until="networkidle")
        await ps.wait_for_timeout(400)
        # 顶部介绍说明被折叠（在文档级）
        assert await ps.locator('.hint.compacted').count() >= 1, "intro hint not compacted"
        # 切到「朋友圈」tab：该 tab 有多条说明性 hint
        await ps.click('[data-tab="moments"]')
        await ps.wait_for_timeout(400)
        compacted = await ps.locator("#panelBody .hint.compacted").count()
        assert compacted >= 2, "scene hints not compacted: %d" % compacted
        # 含 checkbox 的 hint 未被折叠
        withcb = await ps.locator('.hint:has(input)').count()
        foldedcb = await ps.locator('.hint:has(input).compacted').count()
        assert withcb == foldedcb, "hint with checkbox wrongly compacted"
        # 点开一个
        await ps.locator("#panelBody .hint-q").first.click()
        assert await ps.locator("#panelBody .hint.compacted.open").count() == 1, "hint not opened"
        print("SCENE OK  compacted=%d" % compacted)

        # --- concurrent.html ---
        pc = await b.new_page()
        pc.on("pageerror", lambda e: errors.append("concurrent: " + str(e)))
        pc.on("console", lambda m: errors.append("concurrent: " + m.text) if m.type == "error" else None)
        await pc.goto(BASE + "/concurrent.html", wait_until="networkidle")
        await pc.wait_for_timeout(400)
        assert await pc.locator('.hint.compacted').count() >= 1, "concurrent intro not compacted"
        print("CONCURRENT OK")

        await b.close()

    real = [e for e in errors if "favicon" not in e and "404" not in e]
    if real:
        print("ERRORS:", json.dumps(real[:6], ensure_ascii=False))
        raise SystemExit(1)
    print("SMOKE PASS")

asyncio.run(main())
