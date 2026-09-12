"""验证：同源嵌入的真实前端 + 浏览器内 enhance 注入，能否渲染出与真机一致的画面。"""
import asyncio
import io
import json

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8002/vue-wechat/#/"


async def main():
    scene = json.load(io.open(r"G:\weixin-auto\scene.json", encoding="utf-8"))
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        p = await b.new_page(viewport={"width": 600, "height": 1300},
                             device_scale_factor=1)
        errs = []
        p.on("pageerror", lambda e: errs.append("PAGEERR " + str(e)))
        p.on("console", lambda m: errs.append("CONSOLE " + m.text) if m.type == "error" else None)
        await p.goto(URL, wait_until="domcontentloaded")
        try:
            await p.wait_for_function("() => window.__wxEmbedReady === true", timeout=45000)
            print("embed ready: OK")
        except Exception as e:  # noqa: BLE001
            print("embed ready: TIMEOUT", e)
        print("url now:", p.url)
        print("embed errors:", await p.evaluate("window.__wxEmbedErrors"))

        # 套用场景（与 main.py 同法）
        r = await p.evaluate(
            "(s) => { window.__wxConfig && window.__wxConfig.apply();"
            " return window.__wxConfig ? window.__wxConfig.applyScene(s) : 'no-config'; }",
            scene)
        print("applyScene ->", r)
        await p.wait_for_timeout(1500)
        # 等所有图片真的加载完（头像/表情等异步图）
        try:
            await p.wait_for_function(
                "() => [...document.images].every(i => i.complete && i.naturalWidth > 0)",
                timeout=15000)
            print("images loaded: OK")
        except Exception:  # noqa: BLE001
            broken = await p.evaluate(
                "() => [...document.images].filter(i => !i.complete || !i.naturalWidth)"
                ".map(i => i.getAttribute('src')).slice(0, 6)")
            print("images NOT all loaded, broken:", broken)
        await p.wait_for_timeout(400)

        info = await p.evaluate("""() => {
          const app = document.getElementById('app');
          const rows = document.querySelectorAll('.msg-list .msg-item, .msg-item, .home-item');
          const txt = [];
          document.querySelectorAll('*').forEach(() => {});
          const names = [...document.querySelectorAll('.msg-item .title, .msg-item .name')]
              .slice(0, 8).map(e => e.textContent.trim());
          return { appChildren: app ? app.children.length : -1,
                   appRect: app ? JSON.stringify(app.getBoundingClientRect()) : null,
                   rowCount: rows.length, names,
                   bodyBg: getComputedStyle(document.body).backgroundColor,
                   font: getComputedStyle(document.body).fontFamily.slice(0, 60) };
        }""")
        print("page info:", json.dumps(info, ensure_ascii=False))
        await p.screenshot(path=r"G:\weixin-auto\_embed_home.png")
        print("screenshot saved")
        print("errors:", errs[:8] or "none")
        await b.close()


asyncio.run(main())
