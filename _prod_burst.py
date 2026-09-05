# -*- coding: utf-8 -*-
"""抽取指定时间点附近的 60fps 原帧，存成「前正常｜闪光帧｜后正常」三联图，便于肉眼核对。"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
from PIL import Image, ImageDraw
from imageio_ffmpeg import get_ffmpeg_exe

ff = get_ffmpeg_exe()
video = r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
wd = r"F:\weixin-auto\_prod_burst"
os.makedirs(wd, exist_ok=True)

# 目标时间点（已在 15fps 检测里定位到的孤立异常帧中心）
times = [54.67, 100.40, 15.67, 29.80, 25.80, 69.33]
tw = int(60 * 0.34)   # 每个窗口抽 60fps，0.34s 两侧
for t in times:
    start = max(0, t - 0.34)
    dur = 0.68
    tag = str(t).replace(".", "_")
    out = os.path.join(wd, f"win_{tag}.jpg")
    # 抽 60fps 一段
    subprocess.run(
        [ff, "-y", "-loglevel", "error", "-ss", "%.3f" % start, "-i", video,
         "-t", "%.3f" % dur, "-vf", f"fps=60,scale=120:260", "-q:v", "4",
         os.path.join(wd, f"seq_{tag}_%03d.jpg")], check=True)
    files = sorted([f for f in os.listdir(wd) if f.startswith(f"seq_{tag}_")])
    imgs = [Image.open(os.path.join(wd, f)) for f in files]
    n = len(imgs)
    cols = 2
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 122, rows * 262), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for k, im in enumerate(imgs):
        x = (k % cols) * 122
        y = (k // cols) * 262
        sheet.paste(im, (x, y))
        d.text((x + 2, y + 2), f"{k}", fill=(255, 255, 0))
    sheet.save(out, quality=82)
    print(f"t={t}s -> {n} frames, sheet: {out}")
    for f in files:
        os.remove(os.path.join(wd, f))
