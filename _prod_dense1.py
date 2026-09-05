# -*- coding: utf-8 -*-
"""密集抽取某一小段时间的 60fps 原尺寸帧，逐帧命名保存。"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from imageio_ffmpeg import get_ffmpeg_exe
ff = get_ffmpeg_exe()
video = r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
wd = r"F:\weixin-auto\_prod_dense\100"
os.makedirs(wd, exist_ok=True)
for f in os.listdir(wd):
    os.remove(os.path.join(wd, f))
# 从 100.30s 起，取 0.20s = 12 帧
subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "100.300", "-i", video,
                "-t", "0.20", "-vf", "fps=60", os.path.join(wd, "d%02d.png")], check=True)
for f in sorted(os.listdir(wd)):
    print(f, end="  ")
print()
