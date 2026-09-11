import asyncio, sys
from playwright.async_api import async_playwright

OUT = r"G:\weixin-auto\_phase_{n}.png"
URL = r"file:///G:/weixin-auto/_transfer_phase_test.html"

async def main():
    async with async_playwright() as b:
        br = await b.chromium.launch()
        pg = await br.new_page(viewport={"width": 600, "height": 1280})
        await pg.goto(URL)
        await pg.wait_for_timeout(300)

        # 1) 金额页（右推入 + 键盘）
        await pg.evaluate("window.__wxTransfer.openAmount('学员 D-2026.8', 'Kamk-kamk')")
        await pg.evaluate("window.__wxTransfer.setAmount('1')")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=OUT.format(n=1))

        # 2) 点转账 → toast 阶段
        await pg.evaluate("() => { const k = document.querySelector('#taKeyboard .tkr-ok'); if (k) k.click(); }")
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=OUT.format(n=2))

        # 3) 付款面板滑起
        await pg.wait_for_timeout(1600)
        await pg.screenshot(path=OUT.format(n=3))

        # 4) 输入 3 位密码
        for d in "123":
            await pg.evaluate("(d) => { const k = document.querySelector('#pwKeyboard .tkr-key[data-key=\"' + d + '\"]'); if (k) k.click(); }", d)
            await pg.wait_for_timeout(150)
        await pg.wait_for_timeout(250)
        await pg.screenshot(path=OUT.format(n=4))

        # 5) 输满 → 加载态
        for d in "456":
            await pg.evaluate("(d) => { const k = document.querySelector('#pwKeyboard .tkr-key[data-key=\"' + d + '\"]'); if (k) k.click(); }", d)
            await pg.wait_for_timeout(150)
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=OUT.format(n=5))

        # 6) 成功页
        await pg.wait_for_timeout(1400)
        await pg.screenshot(path=OUT.format(n=6))

        # 7) 完成 → 收起
        await pg.evaluate("() => { const btn = document.querySelector('#payDoneBtn'); if (btn) btn.click(); }")
        await pg.wait_for_timeout(600)
        st = await pg.evaluate("JSON.stringify({sheet:document.querySelector('#wxPaySheet').className, succ:document.querySelector('#wxPaySuccess').className, amt:document.querySelector('#wxTransferAmount').className})")
        print("STATE", st)
        await br.close()

asyncio.run(main())
print("PHASES_DONE")
