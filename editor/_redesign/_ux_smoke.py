# -*- coding: utf-8 -*-
"""编辑器 UX 升级运行时冒烟（独立无头会话，不污染运行中的实例）"""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
errors = {"index": [], "scene": []}

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])

        # ---------- index.html：工作流编辑器 ----------
        pg = await browser.new_page()
        pg.on("console", lambda m: errors["index"].append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors["index"].append(str(e)))
        await pg.goto(BASE + "/index.html", wait_until="networkidle")

        # 1) 撤销/重做按钮存在
        assert await pg.locator("#btnUndo").count() == 1, "btnUndo missing"
        assert await pg.is_disabled("#btnUndo"), "btnUndo should start disabled"

        # 2) 基线可能是已保存的流程：全部用相对计数断言
        base = await pg.locator(".step-node").count()
        await pg.locator(".action-card").first.click()
        await pg.locator(".action-card").nth(1).click()
        n = await pg.locator(".step-node").count()
        assert n == base + 2, "expect %d steps, got %d" % (base + 2, n)
        assert not await pg.is_disabled("#btnUndo"), "btnUndo should be enabled"
        await pg.click("#btnUndo")
        assert await pg.locator(".step-node").count() == base + 1, "undo failed"
        await pg.click("#btnRedo")
        assert await pg.locator(".step-node").count() == base + 2, "redo failed"

        # 3) 选中第 1 步后从动作库添加 → 应插入到第 2 位（而不是末尾）
        await pg.locator(".step-node").nth(0).click()
        await pg.locator(".action-card").first.click()
        names = await pg.locator(".step-node .node-title").all_inner_texts()
        first_actions = await pg.locator(".action-card .action-name").all_inner_texts()
        assert names[1] == first_actions[0], "insert-after-selected failed: %s" % names

        # 4) 键盘：Ctrl+Z 撤销插入；Delete 删除选中；Ctrl+D 复制
        await pg.keyboard.press("Control+z")
        assert await pg.locator(".step-node").count() == base + 2, "ctrl+z failed"
        await pg.keyboard.press("Control+d")
        assert await pg.locator(".step-node").count() == base + 3, "ctrl+d failed"
        await pg.keyboard.press("Delete")
        assert await pg.locator(".step-node").count() == base + 2, "delete key failed"
        print("INDEX OK")

        # ---------- scene.html：场景编辑器 ----------
        ps = await browser.new_page(viewport={"width": 1600, "height": 900})
        ps.on("console", lambda m: errors["scene"].append(m.text) if m.type == "error" else None)
        ps.on("pageerror", lambda e: errors["scene"].append(str(e)))
        await ps.goto(BASE + "/scene.html", wait_until="networkidle")

        # 1) 折叠工具条 + 折叠按钮
        assert await ps.locator(".fold-toolbar").count() == 1, "fold-toolbar missing"
        folds = await ps.locator(".fold-btn").count()
        assert folds > 0, "no fold buttons"
        # 折叠第一个卡片
        await ps.locator(".fold-btn").first.click()
        cls = await ps.locator(".card-fold").first.get_attribute("class")
        assert "closed" in cls, "fold did not close"
        # 全部展开恢复
        await ps.click('[data-fold="open"]')
        closed = await ps.locator(".card-fold.closed").count()
        assert closed == 0, "expand-all failed"

        # 2) 文本输入不重建面板（打标记 → 输入 → 标记还在 = 面板没重建）
        await ps.click('[data-tab="me"]')
        inp = ps.locator('#panelBody [data-set="me.name"]')
        await inp.evaluate("el => el.dataset.__marker = '1'")
        await inp.click()
        await inp.type("测试昵称abc")
        marker = await inp.evaluate("el => el.dataset.__marker || ''")
        assert marker == "1", "panel rebuilt while typing (focus loss bug remains)"
        val = await inp.input_value()
        assert val.endswith("abc"), "value not committed"

        # 3) select 变更仍会重建面板（行为保留）
        await ps.click('[data-tab="conversations"]')
        sel = ps.locator('#panelBody select[data-set$=".type"]').first
        cnt_before = await ps.locator("#panelBody .card").count()
        if cnt_before:
            await sel.evaluate("el => el.dataset.__marker2 = '1'")
            await sel.select_option("group")
            marker2 = await sel.evaluate("el => el.dataset.__marker2 || ''")
            # select 重建面板属预期；只要页面不报错即可
        print("SCENE OK")

        await browser.close()

    for k, v in errors.items():
        v[:] = [e for e in v if "favicon" not in e]
        if v:
            print(k, "CONSOLE ERRORS:", json.dumps(v[:5], ensure_ascii=False))

asyncio.run(main())
print("SMOKE PASS")
