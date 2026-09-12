# -*- coding: utf-8 -*-
"""真机画面（不卡版）冒烟：连接 → 点击操作 → 空闲期零请求 → 示意稿切换。

关键断言（性能）：连接完成后静置 6 秒，必须 **0 次** /api/live 请求 —— 证明没有常驻轮询。
"""
import asyncio
import sys
import urllib.request

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"


def _post(path):
    req = urllib.request.Request(BASE + path, data=b"{}",
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode()
    except Exception as exc:                     # noqa: BLE001
        return "ERR %s" % exc


async def main():
    # 前置清场：保证「未连接」是真实初始态（编辑模式可能还在跑）
    print("pre-stop:", _post("/api/editmode/stop"))
    await asyncio.sleep(4)

    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        p = await b.new_page()
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        live_reqs = []
        p.on("request", lambda r: live_reqs.append(r.url) if "/api/live" in r.url else None)

        await p.goto(BASE + "/scene.html", wait_until="networkidle")
        await p.wait_for_timeout(800)

        # 1) 未连接时应显示「连接真机画面」遮罩
        assert await p.locator("#stageLiveEmpty").is_visible(), "未连接遮罩没显示"
        assert await p.locator("#stageLiveImg").is_hidden(), "未连接时不该显示画面"
        assert (await p.locator("#stageLiveState").inner_text()).startswith("真机未连接")
        print("1) 未连接态 OK")

        # 2) 点「连接真机画面」→ 真机进程启动 → 自动接上
        await p.click("#btnStageLiveConnect")
        ok = False
        for _ in range(40):
            await p.wait_for_timeout(1000)
            if await p.locator("#stageLiveImg").is_visible():
                ok = True
                break
        assert ok, "连接超时，真机画面没上来"
        assert await p.locator("#stageLiveBadge").is_visible(), "LIVE 徽标没显示"
        assert "已连接" in (await p.locator("#stageLiveState").inner_text())
        print("2) 连接成功 OK")

        await p.wait_for_timeout(4500)   # 等连接后的补帧 burst 彻底走完
        await p.evaluate("scrollTo(0, 0)")   # Playwright 点按钮时会把页面滚走，复位

        # 3) 空闲期零请求（不卡的核心证据）
        live_reqs.clear()
        await p.wait_for_timeout(6000)
        idle = len(live_reqs)
        assert idle == 0, "空闲时仍在轮询拉帧：%d 次 %s" % (idle, live_reqs[:3])
        print("3) 空闲 6 秒 0 请求 OK")

        # 4) 点击画面 = 点手机 → 应触发一次 tap，且随后补帧
        live_reqs.clear()
        # 用元素内坐标点击（600×1300 的画布内部像素点），Playwright 会自动处理滚动
        await p.locator("#stageLiveImg").click(position={"x": 210, "y": 286})
        await p.wait_for_timeout(2600)
        assert any("/api/live/tap" in u for u in live_reqs), "点击没有转发成 tap"
        frames = [u for u in live_reqs if "/api/live?t=" in u]
        assert len(frames) >= 2, "点击后没有补帧：%d" % len(frames)
        print("4) 点击转发 tap + 补帧 %d 帧 OK" % len(frames))

        # 5) 滚轮 = 滚动真机（Ctrl+滚轮才缩放画布）
        live_reqs.clear()
        await p.locator("#stageLiveImg").hover(position={"x": 300, "y": 585})
        await p.mouse.wheel(0, 400)
        await p.wait_for_timeout(1500)
        assert any("/api/live/scroll" in u for u in live_reqs), "滚轮没有转发成 scroll"
        z0 = await p.evaluate("zoom")
        await p.keyboard.down("Control")
        await p.mouse.wheel(0, -300)
        await p.keyboard.up("Control")
        await p.wait_for_timeout(400)
        z1 = await p.evaluate("zoom")
        assert z1 > z0, "Ctrl+滚轮没缩放画布（%s -> %s）" % (z0, z1)
        print("5) 滚轮滚动真机 / Ctrl+滚轮缩放 OK")

        # 6) ← 返回
        live_reqs.clear()
        await p.click("#btnStageBack")
        await p.wait_for_timeout(1200)
        assert any("/api/live/back" in u for u in live_reqs), "返回没有转发"
        print("6) 返回 OK")

        # 7) 场景变更才会推送：改一个字段 → 应推出 /api/live/scene
        live_reqs.clear()
        await p.evaluate("""() => {
          scene.home[0].messages = [{ dir: 'peer', kind: 'text', text: '真机同步测试', time: '18:22' }];
          renderPhone();
        }""")
        await p.wait_for_timeout(2500)
        assert any("/api/live/scene" in u for u in live_reqs), "场景变更没有推送"
        # 再渲染一次（内容没变）→ 不应重复推
        live_reqs.clear()
        await p.evaluate("renderPhone()")
        await p.wait_for_timeout(2000)
        assert not any("/api/live/scene" in u for u in live_reqs), "场景没变却重复推送了"
        print("7) 场景变更才推送 / 无变化不推送 OK")

        # 8) 切「示意稿」：真机画面隐藏、内置画面显示
        await p.click("#btnViewDraft")
        await p.wait_for_timeout(400)
        assert await p.locator("#stageLiveImg").is_hidden(), "切示意稿后真机画面没隐藏"
        assert await p.locator("#phoneInner .chat-row").first.is_visible(), "示意稿没显示"
        await p.click("#btnViewLive")
        await p.wait_for_timeout(600)
        assert await p.locator("#stageLiveImg").is_visible(), "切回真机画面失败"
        print("8) 真机画面 / 示意稿 切换 OK")

        real = [e for e in errs if "404" not in e]
        assert not real, "页面报错：%s" % real[:3]
        print("SMOKE OK")
        await b.close()


asyncio.run(main())
