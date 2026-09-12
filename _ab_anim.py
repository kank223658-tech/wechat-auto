# -*- coding: utf-8 -*-
"""帧精确的「旧节奏 vs 新节奏」动效对照。

Playwright 自带的录屏在快速布局变化时会丢帧（实测 260ms 的推入只录到 1 帧），
没法用来对比动画速度。这里改成：把 CSS 过渡拿到 Web Animations 句柄 → 全部 pause
→ 手动把 currentTime 按 1/60s 步进 → 每步截一张图。这样左右两版都是**引擎真实渲染**的
逐帧画面，时间轴完全对齐。

用法: py _ab_anim.py        # 产物 -> _ab_frames_old/ _ab_frames_new/
"""
import glob
import os
import shutil
import subprocess

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = r"G:\weixin-auto"
ENH = os.path.join(ROOT, "enhance")
OLD = os.path.join(ROOT, "_tf_old")
FF = imageio_ffmpeg.get_ffmpeg_exe()

CSS = ["harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
       "wechat_modern.css", "human_actions.css", "transfer_ui.css"]
JS = ["config.js", "chat_extra.js", "iphone_frame.js", "transfer_ui.js"]
TF = {"transfer_ui.css", "transfer_ui.js"}

STEP_MS = 1000.0 / 60.0     # 60fps
CLIP_MS = 520               # 覆盖最长的动画（旧版 300ms + 余量）
NFRAMES = int(CLIP_MS / STEP_MS) + 1


def rd(path, override_dir):
    base = os.path.basename(path)
    if override_dir and base in TF:
        alt = os.path.join(override_dir, base)
        if os.path.exists(alt):
            return open(alt, encoding="utf-8").read()
    return open(path, encoding="utf-8").read()


SNAP = """(sel, cls) => {
    const el = document.querySelector(sel);
    el.classList.remove(cls);
    return null;
}"""

# 加类并冻结所有过渡，返回各动画的 时长/延迟
ARM = """([sel, cls]) => {
    const el = document.querySelector(sel);
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
    void el.offsetWidth;
    const a = document.getAnimations();
    a.forEach(x => x.pause());
    window.__abA = a;
    return a.map(x => {
        const t = x.effect.getTiming();
        return [x.transitionProperty || x.animationName || '?', t.delay, t.duration];
    });
}"""

STEP = "(t) => { (window.__abA || []).forEach(x => { try { x.currentTime = t; } catch (e) {} }); return (window.__abA||[]).length; }"


def capture(pg, name, sel, cls, outdir):
    pg.evaluate("([s,c])=>{const e=document.querySelector(s); e.classList.remove(c);}", [sel, cls])
    pg.wait_for_timeout(700)                    # 等复位到位
    info = pg.evaluate(ARM, [sel, cls])
    print("   ", name, "动画:", info)
    os.makedirs(outdir, exist_ok=True)
    for i in range(NFRAMES):
        t = i * STEP_MS
        pg.evaluate(STEP, t)
        pg.screenshot(path=os.path.join(outdir, "%s_%03d.png" % (name, i)))
    # 收尾：恢复播放并清类
    pg.evaluate("()=>{(window.__abA||[]).forEach(x=>{try{x.finish()}catch(e){}}); window.__abA=[];}")
    pg.wait_for_timeout(200)


def run(variant, override_dir, outroot):
    if os.path.isdir(outroot):
        shutil.rmtree(outroot, ignore_errors=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 600, "height": 1300})
        pg.goto("http://localhost:8080/#/", wait_until="domcontentloaded")
        pg.wait_for_timeout(1200)
        pg.add_style_tag(content=".welcome { display: none !important; }")
        for f in CSS:
            pg.add_style_tag(content=rd(os.path.join(ENH, f), override_dir))
        for f in JS:
            pg.evaluate(rd(os.path.join(ENH, f), override_dir))
        pg.evaluate(rd(os.path.join(ENH, "keyboard.js"), override_dir))
        pg.wait_for_timeout(600)

        print("[%s] 键盘升起" % variant)
        pg.evaluate("window.__wxTransfer.openAmount('小星')")
        pg.wait_for_timeout(1400)               # 让页面推入 + 键盘升起全部落定
        capture(pg, "kb", "#taKeyboard", "kb-up", outroot)

        print("[%s] 付款面板滑起" % variant)
        pg.evaluate("window.__wxTransfer.openPassword('1.00', '')")
        pg.wait_for_timeout(2200)               # 等 toast 走完、面板滑起完成
        capture(pg, "sheet", "#wxPaySheet", "open", outroot)

        b.close()
    print("   ->", outroot)


run("旧", OLD, os.path.join(ROOT, "_ab_frames_old"))
run("新", "", os.path.join(ROOT, "_ab_frames_new"))

# ---------- 拼图：左右各半 + 顶部标签 ----------
from PIL import Image, ImageDraw, ImageFont

tmp = os.path.join(ROOT, "_ab_tmp")
os.makedirs(tmp, exist_ok=True)
for tag, d in [("old", "_ab_frames_old"), ("new", "_ab_frames_new")]:
    src = os.path.join(ROOT, d)
    for n in ["kb", "sheet"]:
        subprocess.run([FF, "-y", "-framerate", "60", "-i", os.path.join(src, n + "_%03d.png"),
                        "-vf", "scale=600:1300:flags=neighbor", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "18", os.path.join(tmp, "%s_%s.mp4" % (tag, n))], capture_output=True, check=True)
print("frames -> mp4 done")
