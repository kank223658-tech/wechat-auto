# -*- coding: utf-8 -*-
"""
preview_ui.py —— 一键预览当前微信皮肤各界面
====================================================
复刻 main.py 的完整注入流程（含 weui_tokens.css / wx_icons.css），
用移动端视口渲染微信暗色皮肤的各个界面，输出截图到 preview/，
并拼成一张总览图 preview/grid.png，方便快速查看当前手机画面。

用法：
    py preview_ui.py            # 自动使用已运行的 localhost:8080；未运行会自动启动
    py preview_ui.py --open     # 预览完成后用系统默认看图程序打开 preview 目录

前置：
    依赖 playwright、PIL、imageio；需本地 vue dev server（vue-WeChat）在 8080。
    若 8080 未启动，脚本会用项目自带 node 自动 `vue-cli-service serve` 拉起。
"""
import os
import sys
import json
import time
import subprocess
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ENHANCE = os.path.join(BASE, "enhance")
PREVIEW = os.path.join(BASE, "preview")
VIEWPORT_W, VIEWPORT_H = 390, 844
SCALE = 3  # 与真机 device pixel ratio 一致，截图更清晰
BASE_URL = "http://localhost:8080/"

CSS_ORDER = (
    "harmony_font.css", "keyboard.css", "iphone_frame.css",
    "weui_tokens.css", "wechat_modern.css", "human_actions.css",
    "transfer_ui.css", "homepage_exact.css", "chat_exact.css", "wx_icons.css",
    "moments_exact.css", "discover_exact.css",
    # 底部三面板「直接切换」联动层：必须晚于 chat_exact.css / transfer_ui.css /
    # keyboard.css，用更高特异性压过各面板自己的稳态规则（与 main.py 注入顺序一致）。
    "panel_switch.css",
)
JS_ORDER = (
    "config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
    "wxemoji_map.js", "pinyin_data.js", "keyboard.js", "transfer_ui.js",
    "human_actions.js", "homepage.js",
    # 需在 keyboard.js / chat_extra.js / transfer_ui.js 之后：它调用
    # __wxKeyboard / __wxEmojiPanel / __wxTransfer 做三面板直切。
    "panel_switch.js",
)


def read_enhance(name):
    with open(os.path.join(ENHANCE, name), "r", encoding="utf-8") as fh:
        return fh.read()


def ensure_frontend_running(timeout=120):
    """本地 8080 未启动时，用项目自带 node 拉起 vue dev server。"""
    import urllib.request
    try:
        urllib.request.urlopen(BASE_URL, timeout=3)
        return
    except Exception:
        pass
    vue = os.path.join(BASE, "vue-WeChat")
    node = os.path.join(BASE, "tools", "node-v20.19.4-win-x64", "node.exe")
    cli = os.path.join(vue, "node_modules", "@vue", "cli-service", "bin", "vue-cli-service.js")
    print("前端未运行，正在启动 vue dev server ...")
    subprocess.Popen(
        [node, cli, "serve", "--port", "8080", "--open", "false"],
        cwd=vue,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(BASE_URL, timeout=3)
            print("前端已就绪。")
            return
        except Exception:
            time.sleep(2)
    raise SystemExit("前端启动超时，请手动运行 vue dev server。")


def build_page(browser, context=None):
    """创建页面并注入完整皮肤。

    context 可选：传入已有的 context（例如带 record_video_dir / 自定义视口的录制上下文）
    则使用它；否则按默认移动端视口新建。
    """
    if context is None:
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=SCALE,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
            is_mobile=True, has_touch=True, locale="zh-CN",
        )
    page = context.new_page()
    page.goto(BASE_URL + "#/", wait_until="domcontentloaded")
    page.add_style_tag(content=".welcome { display: none !important; }")
    for name in CSS_ORDER:
        page.add_style_tag(content=read_enhance(name))
    for name in JS_ORDER:
        page.evaluate(read_enhance(name))
    page.wait_for_timeout(1200)
    # 应用个人资料 / 会话 / 朋友圈数据
    try:
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(300)
        scene = os.path.join(BASE, "scene.json")
        if os.path.isfile(scene):
            with open(scene, "r", encoding="utf-8") as fh:
                scene_data = json.load(fh)
            page.evaluate("(s) => window.__wxConfig && window.__wxConfig.applyScene(s)", scene_data)
            page.wait_for_timeout(300)
    except Exception as e:  # noqa: BLE001
        print("应用场景失败（忽略）：", e)
    return context, page


def scroll_chat_to_bottom(page):
    page.evaluate("""() => {
        const s = document.querySelector('.dialogue-section');
        if (s) s.scrollTop = s.scrollHeight;
    }""")
    page.wait_for_timeout(300)


def main():
    ap = argparse.ArgumentParser(description="预览微信暗色皮肤各界面")
    ap.add_argument("--open", action="store_true", help="预览完成后打开 preview 目录")
    ap.add_argument("--out", default=PREVIEW, help="输出目录")
    args = ap.parse_args()
    outdir = args.out
    os.makedirs(outdir, exist_ok=True)

    ensure_frontend_running()

    from playwright.sync_api import sync_playwright
    from PIL import Image

    shots = []

    def snap(page, name, full=False):
        path = os.path.join(outdir, name + ".png")
        page.screenshot(path=path, full_page=full)
        shots.append((name, path))
        print("  +", name)

    with sync_playwright() as pw:
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        browser = pw.chromium.launch(
            headless=True,
            executable_path=chrome if os.path.isfile(chrome) else None,
        )
        context, page = build_page(browser)
        page.wait_for_timeout(600)

        # 1 首页 · 聊天列表
        print("渲染 1/9 首页聊天列表")
        snap(page, "01_chat_list")

        # 2 聊天详情
        print("渲染 2/9 聊天详情")
        page.locator('.wechat-list li:has(.desc-author:text-is("陆香儿")) .list-info').first.click()
        page.wait_for_timeout(1000)
        scroll_chat_to_bottom(page)
        snap(page, "02_chat_detail")

        # 3 「+」功能面板
        print("渲染 3/9 「+」功能面板")
        page.evaluate("window.__wxTransfer && window.__wxTransfer.openPanel()")
        page.wait_for_timeout(600)
        snap(page, "03_plus_panel")
        page.evaluate("window.__wxTransfer && window.__wxTransfer.reset()")
        page.wait_for_timeout(200)

        # 4 转账金额页
        print("渲染 4/9 转账金额页")
        page.evaluate("window.__wxTransfer && window.__wxTransfer.openAmount('d', 'AAi201')")
        page.evaluate("window.__wxTransfer && window.__wxTransfer.setAmount('50')")
        page.wait_for_timeout(500)
        snap(page, "04_transfer_amount")
        page.evaluate("window.__wxTransfer && window.__wxTransfer.reset()")
        page.wait_for_timeout(200)

        # 5 转账消息卡片（聊天内上屏）
        print("渲染 5/9 转账消息卡片")
        page.evaluate("window.__wxChatExt && window.__wxChatExt.selfTransfer('d', '50.00', '聚餐AA')")
        page.wait_for_timeout(400)
        scroll_chat_to_bottom(page)
        snap(page, "05_transfer_card")

        # 6 朋友圈
        print("渲染 6/9 朋友圈")
        page.goto(BASE_URL + "#/explore/moments", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        snap(page, "06_moments")

        # 7 发现页
        print("渲染 7/9 发现页")
        page.goto(BASE_URL + "#/explore", wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        snap(page, "07_discover")

        # 8 我 · 个人主页
        print("渲染 8/9 我 · 个人主页")
        page.goto(BASE_URL + "#/self", wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        snap(page, "08_self")

        # 9 联系人详细资料
        print("渲染 9/9 联系人详细资料")
        page.goto(BASE_URL + "#/contact", wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        # 进入第一个联系人详情
        try:
            page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
            page.locator('.contact-list .weui-cell, #contact .weui-cell').first.click()
            page.wait_for_timeout(800)
            snap(page, "09_contact_detail")
        except Exception:  # noqa: BLE001
            snap(page, "09_contact_detail")

        browser.close()

    # 拼总览图（两列网格 + 文件名标注）
    print("正在拼接总览图 grid.png ...")
    if shots:
        thumbs = []
        from PIL import ImageDraw, ImageFont
        for name, path in shots:
            im = Image.open(path).convert("RGB")
            im.thumbnail((220, 476))  # 每帧缩到首屏比例
            thumbs.append((name, im))
        pad = 12
        cols = 3
        rows = (len(thumbs) + cols - 1) // cols
        tw = max(i.width for _, i in thumbs)
        th = max(i.height for _, i in thumbs)
        grid = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad + 20) + pad), (28, 28, 30))
        draw = ImageDraw.Draw(grid)
        for idx, (name, im) in enumerate(thumbs):
            r, c = divmod(idx, cols)
            x = pad + c * (tw + pad)
            y = pad + r * (th + pad + 20)
            grid.paste(im, (x, y))
            draw.text((x, y + th + 2), name, fill=(220, 220, 220))
        grid_path = os.path.join(outdir, "grid.png")
        grid.save(grid_path)
        print("总览图:", grid_path)

    print("完成：截图已输出到", outdir)
    if args.open:
        os.startfile(outdir)  # noqa: S606 (Windows 打开目录)


if __name__ == "__main__":
    main()