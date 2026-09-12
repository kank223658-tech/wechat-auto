# -*- coding: utf-8 -*-
"""转账全链路回归录制（提速后版本）。

与旧版的差别：
  1) 用 Playwright locator.click()（真实鼠标事件，会走 pointerdown 分支），
     顺带把新加的「落指」微动效录进去；
  2) 按键节奏改成「基础 75~175ms + 22% 概率迟疑 170~320ms」的非匀速人手节奏，
     不再是每键固定 190~200ms 的等距敲击；
  3) 各段等待按新动画时长重算。

用法: py _rec_tf.py
"""
import os
import random
import shutil
from playwright.sync_api import sync_playwright

ROOT = r"G:\weixin-auto"
ENH = os.path.join(ROOT, "enhance")
OUT = os.path.join(ROOT, "_rec_out" + os.environ.get("TF_TAG", ""))
if os.path.isdir(OUT):
    shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

random.seed(20260911)


# 若设置 TF_OVERRIDE=<目录>，则这四个转账相关文件从该目录读（用于 A/B 对比旧版本）
TF_OVERRIDE = os.environ.get("TF_OVERRIDE")
TF_FILES = {"transfer_ui.css", "transfer_ui.js", "transfer_detail.css", "transfer_detail.js"}
OUT_TAG = os.environ.get("TF_TAG", "")


def rd(p):
    base = os.path.basename(p)
    if TF_OVERRIDE and base in TF_FILES:
        alt = os.path.join(TF_OVERRIDE, base)
        if os.path.exists(alt):
            return open(alt, encoding="utf-8").read()
    return open(p, encoding="utf-8").read()


CSS_MAIN = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
            "wechat_modern.css", "human_actions.css", "transfer_ui.css", "send_image_ui.css",
            "peer_pages.css", "block_ui.css", "video_player.css", "homepage_exact.css"]
JS_MAIN = ["config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
           "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
           "video_player.js", "peer_pages.js", "block_ui.js"]
CSS_TFD = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
           "wechat_modern.css", "human_actions.css", "transfer_ui.css", "transfer_detail.css"]
JS_TFD = ["config.js", "chat_extra.js", "iphone_frame.js", "transfer_ui.js", "transfer_detail.js"]


def boot(pg, css, js, keyboard=False):
    pg.goto("http://localhost:8080/#/", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    pg.add_style_tag(content=".welcome { display: none !important; }")
    for f in css:
        pg.add_style_tag(content=rd(os.path.join(ENH, f)))
    for f in js:
        pg.evaluate(rd(os.path.join(ENH, f)))
    if keyboard:
        pg.evaluate(rd(os.path.join(ENH, "keyboard.js")))
    pg.wait_for_timeout(500)


def key(pg, grid, d):
    """真人鼠标点击键位 + 非匀速节奏（基础快、偶尔迟疑）。"""
    pg.locator('%s .tkr-key[data-key="%s"]' % (grid, d)).click(timeout=4000)
    if random.random() < 0.22:
        pg.wait_for_timeout(random.randint(170, 320))     # 迟疑
    else:
        pg.wait_for_timeout(random.randint(75, 175))      # 顺手连打


with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)

    # ---------- 片段1：金额页 → 成功页 ----------
    ctx = b.new_context(viewport={"width": 600, "height": 1300},
                        record_video_dir=os.path.join(OUT, "v1"),
                        record_video_size={"width": 600, "height": 1300})
    pg = ctx.new_page()
    boot(pg, CSS_MAIN, JS_MAIN, keyboard=True)

    pg.evaluate("window.__wxTransfer.openAmount('小星')")
    pg.wait_for_timeout(1050)                             # 键盘 0.30s 起 + 0.22s 升完 =0.52s；900ms 仍差 3px 未落定
    pg.screenshot(path=os.path.join(ROOT, "_rec" + OUT_TAG + "_p01_amount.png"))

    for k in ["1", ".", "0", "0"]:
        key(pg, "#taKeyboard", k)
    pg.wait_for_timeout(500)
    pg.screenshot(path=os.path.join(ROOT, "_rec_p02_filled.png"))

    pg.locator("#taKeyboard .tkr-ok").click(timeout=4000)  # 绿键「转账」
    pg.wait_for_timeout(500)
    pg.screenshot(path=os.path.join(ROOT, "_rec_p03_toast.png"))

    pg.wait_for_timeout(1200)                             # 面板 1.20s 起 + 0.24s 滑入
    pg.screenshot(path=os.path.join(ROOT, "_rec_p04_sheet.png"))

    for d in "123456":
        key(pg, "#pwKeyboard", d)
    pg.wait_for_timeout(420)                              # 输满 0.20s 后进加载态
    pg.screenshot(path=os.path.join(ROOT, "_rec_p05_loading.png"))

    pg.wait_for_timeout(1400)                             # 加载 0.68s + 成功页 0.24s 滑入
    pg.screenshot(path=os.path.join(ROOT, "_rec_p06_success.png"))
    pg.wait_for_timeout(1200)

    print("V1 ->", pg.video.path())
    ctx.close()

    # ---------- 片段2：详情页 待收款 → 已收款 ----------
    ctx2 = b.new_context(viewport={"width": 600, "height": 1300},
                         record_video_dir=os.path.join(OUT, "v2"),
                         record_video_size={"width": 600, "height": 1300})
    pg2 = ctx2.new_page()
    boot(pg2, CSS_TFD, JS_TFD)

    pg2.evaluate("window.__wxTransferDetail.open()")
    pg2.wait_for_timeout(1500)          # 推入 0.28s + 加载 toast 0.70s
    pg2.screenshot(path=os.path.join(ROOT, "_rec_p07_tfd_wait.png"))
    pg2.wait_for_timeout(700)
    pg2.evaluate("window.__wxTransferDetail.accept()")
    pg2.wait_for_timeout(1200)          # 加载 0.70s → 单帧切到已收款
    pg2.screenshot(path=os.path.join(ROOT, "_rec_p08_tfd_done.png"))
    pg2.wait_for_timeout(900)

    print("V2 ->", pg2.video.path())
    ctx2.close()
    b.close()

print("DONE")
