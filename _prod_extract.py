# -*- coding: utf-8 -*-
"""定位后，把疑似孤立帧区间按 60fps 原生尺寸逐帧抽成全 PNG，并排对比。"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from PIL import Image, ImageDraw
from imageio_ffmpeg import get_ffmpeg_exe

ff = get_ffmpeg_exe()
video = sys.argv[1]
center = float(sys.argv[2])
wd = sys.argv[3]
os.makedirs(wd, exist_ok=True)
for f in os.listdir(wd):
    os.remove(os.path.join(wd, f))
start = center - 0.12
dur = 0.24
subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "%.4f" % start, "-i", video,
                "-t", "%.4f" % dur, "-vf", "fps=60,scale=150:325:flags=lanczos", "-q:v", "3",
                os.path.join(wd, "s%02d.jpg")], check=True)
files = sorted([f for f in os.listdir(wd) if f.startswith("s")])
imgs = [Image.open(os.path.join(wd, f)) for f in files]
print("center", center, "frames:", len(imgs), "start", start)
for k, f in enumerate(files):
    fr = k / 60.0
    print(f"  {f}  t={start+fr:.3f}s")
for i, im in enumerate(imgs):
    im.save(os.path.join(wd, f"orig_{i:02d}.png"))
