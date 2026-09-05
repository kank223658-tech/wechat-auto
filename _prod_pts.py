# -*- coding: utf-8 -*-
"""抽取指定 60fps 时间点的原尺寸帧，便于看清放大闪帧。"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from imageio_ffmpeg import get_ffmpeg_exe
ff = get_ffmpeg_exe()
video = r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
wd = r"F:\weixin-auto\_prod_burst\full"
os.makedirs(wd, exist_ok=True)
# (标签, 提取时间点秒) —— 前帧/闪光帧/后帧
pts = [("54_647", 54.647), ("54_663", 54.663), ("54_680", 54.680),
       ("54_697", 54.697), ("100_383", 100.383), ("100_400", 100.400),
       ("100_417", 100.417), ("15_650", 15.650), ("15_667", 15.667),
       ("29_783", 29.783), ("29_800", 29.800)]
for tag, t in pts:
    out = os.path.join(wd, f"f_{tag}.png")
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "%.4f" % t,
                    "-i", video, "-frames:v", "1", out], check=True)
    print("saved", out)
