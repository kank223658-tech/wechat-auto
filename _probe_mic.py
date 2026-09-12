# -*- coding: utf-8 -*-
"""输入栏麦克风颜色校验：打开聊天 + 键盘，截输入栏，量麦克风屏上亮度 vs 参考图（149~159）。"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = r"G:\weixin-auto\_mic"
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as pw:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    br = pw.chromium.launch(headless=True, executable_path=chrome if os.path.isfile(chrome) else None)
    ctx = br.new_context(viewport={"width": main.VIEWPORT_W, "height": main.VIEWPORT_H},
                         device_scale_factor=main.DEVICE_SCALE_FACTOR,
                         user_agent=main.MOBILE_UA, is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
    main.inject_overlays(page)
    page.wait_for_timeout(900)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.evaluate("() => document.querySelector('.wechat-list li .list-info').click()")
    page.wait_for_timeout(1000)
    page.evaluate("window.__wxKeyboard && window.__wxKeyboard.show()")
    page.wait_for_timeout(800)

    # 输入栏截图（footer 区域）
    box = page.evaluate("""() => {
        const f = document.querySelector('.dialogue-footer').getBoundingClientRect();
        return {x: f.x, y: f.y, w: f.width, h: f.height};
    }""")
    page.screenshot(path=os.path.join(OUT, "bar.png"),
                    clip={"x": box["x"], "y": box["y"] + box["h"] - 140, "width": box["w"], "height": 140})
    br.close()

a = np.asarray(Image.open(os.path.join(OUT, "bar.png")).convert("L"), dtype=np.float32)
H, W = a.shape
print("输入栏截图 %dx%d" % (W, H))
# 找 .chat-mic 的位置：右侧 1/4 区域内、非背景亮像素
# 麦克风在输入框右端（约 x 0.78W），笑脸/加号在栏最右
right = a[:, int(0.70 * W):]
# 逐列扫描找亮像素簇
mask = right > 80
print("右侧亮像素列分布（每 20 列计数）:")
for x in range(0, right.shape[1], 20):
    c = mask[:, x:x + 20].sum()
    if c:
        print("  x=%4d  %d" % (int(0.70 * W) + x, c))
# 麦克风亮度：取右侧 70%~85% 区域的亮像素（避开笑脸/加号）
mic_zone = a[:, int(0.70 * W):int(0.86 * W)]
ys, xs = np.where(mic_zone > 80)
if len(ys):
    vals = mic_zone[ys, xs]
    print("麦克风亮像素 %d 个: p50=%.0f p90=%.0f max=%.0f" %
          (len(ys), np.percentile(vals, 50), np.percentile(vals, 90), vals.max()))
    print("参考目标: p50≈149 p90≈152 max≈159  （笑脸/加号≈208 不用动）")
else:
    print("★ 未找到麦克风亮像素，检查位置")
