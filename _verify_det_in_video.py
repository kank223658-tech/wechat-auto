# -*- coding: utf-8 -*-
"""最终成片验证：抽帧检查「打开转账详情」转场段是否为确定性重采的平滑帧列。

用 ffmpeg 抽出转场时间窗内所有帧，计算相邻帧差异：确定性重采段应当
逐帧平滑推进（每帧都有变化、无跳变、无长重复）。
"""
import subprocess
import sys
import tempfile
import os

import imageio_ffmpeg
from PIL import Image

MP4 = sys.argv[1]
START, END = float(sys.argv[2]), float(sys.argv[3])   # 转场窗口（输出时间轴秒）

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
tmp = tempfile.mkdtemp(prefix="det_verify_")
subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", str(START),
                "-to", str(END), "-i", MP4,
                "-vf", "fps=60,scale=60:40", os.path.join(tmp, "f%04d.png")],
               check=True)
files = sorted(os.listdir(tmp))
imgs = [Image.open(os.path.join(tmp, f)).convert("L") for f in files]
diffs = []
for a, b in zip(imgs, imgs[1:]):
    pa, pb = a.load(), b.load()
    s = sum(abs(pa[x, y] - pb[x, y]) for x in range(60) for y in range(40))
    diffs.append(s / (60 * 40 * 255.0))
moving = sum(1 for d in diffs if d > 0.002)
static = sum(1 for d in diffs if d <= 0.002)
big = sum(1 for d in diffs if d > 0.05)
print(f"[i] {len(imgs)} 帧, 逐帧差异: 有变化 {moving}, 静止 {static}, 跳变(>0.05) {big}")
print(f"[i] 差异序列(前20): " + " ".join(f"{d:.4f}" for d in diffs[:20]))
moving_idx = [i for i, d in enumerate(diffs) if d > 0.002]
print(f"[i] 有变化帧的索引: {moving_idx}")
print(f"[i] 对应时间: {[round(START + i / 60.0, 2) for i in moving_idx[:50]]}")
print("PASS: 转场段逐帧平滑推进" if moving >= len(diffs) * 0.6 and big <= 2
      else "WARN: 转场段帧列不够平滑，需人工查看视频")
