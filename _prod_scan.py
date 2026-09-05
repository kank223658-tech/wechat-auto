# -*- coding: utf-8 -*-
"""成品视频 wx_20260902_205201.mp4：抽帧生成缩略拼图 + 逐帧异常度评分。

1) 从 60fps 视频每 0.5s 抽 1 帧，拼成 montage_*.jpg（可一次看到全片概览）。
2) 对每 0.5s 帧算「放大分」：把帧缩到统一 300x650，与「同页邻域」对比细节能量。
   放大帧＝内容比正常大很多，表现为高对比/边缘密集/大面积对象。这里用简化版：
   取帧的 Sobel 梯度能量 + 前景比例，作为异常度；异常度突增的帧被抓出来。
"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
from PIL import Image, ImageOps
from imageio_ffmpeg import get_ffmpeg_exe

ff = get_ffmpeg_exe()
video = r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
wd = r"F:\weixin-auto\_prod_frames"
os.makedirs(wd, exist_ok=True)

# --- 按 0.5s 间隔抽帧（fps=2） ---
frames_dir = os.path.join(wd, "all")
os.makedirs(frames_dir, exist_ok=True)
for f in os.listdir(frames_dir):
    os.remove(os.path.join(frames_dir, f))
subprocess.run([ff, "-y", "-loglevel", "error", "-i", video, "-vf", "fps=2",
                os.path.join(frames_dir, "f_%03d.png")], check=True)
files = sorted(os.listdir(frames_dir))
files = [f for f in files if f.endswith(".png")]
print("sampled frames(0.5s each):", len(files))

# --- 逐帧异常度（梯度能量 + 前景占比） ---
scores = []
for i, fn in enumerate(files):
    im = Image.open(os.path.join(frames_dir, fn)).convert("L").resize((300, 650))
    a = np.asarray(im, dtype=np.float32)
    gx = np.abs(np.diff(a, axis=1))
    gy = np.abs(np.diff(a, axis=0))
    grad = gx.sum() + gy.sum()
    fore = (a > 22).mean()
    scores.append((i, grad, fore))
norm = max(s[1] for s in scores) or 1.0
# 异常度 = 梯度能量（归一化） + 前景占比偏离 0.5 的惩罚（满屏内容/空屏都异常）
anom = []
for i, grad, fore in scores:
    a1 = grad / norm
    a2 = abs(fore - 0.5) * 2.0
    anom.append((i, a1, a2, a1 + a2))
print("=== 异常度 TOP 12 帧（索引, 梯度项, 前景项, 总） ===")
top = sorted(anom, key=lambda t: -t[3])[:12]
for i, a1, a2, tot in sorted(top):
    ts = i * 0.5
    print(f"  idx {i:3d}  t={ts:.1f}s   grad={a1:.3f} fore={a2:.3f} total={tot:.3f}")

# --- 生成概览拼图（每 2s 取一帧，12 列） ---
sub = files[::4]   # 每 2 秒一帧（0.5s*4）
cols = 12
thumb_w, thumb_h = 100, 216
rows = (len(sub) + cols - 1) // cols
sheet = Image.new("RGB", (cols * thumb_w, rows * thumb_h), (40, 40, 40))
from PIL import ImageDraw
d = ImageDraw.Draw(sheet)
for k, fn in enumerate(sub):
    im = Image.open(os.path.join(frames_dir, fn)).convert("RGB")
    im.thumbnail((thumb_w, thumb_h))
    x = (k % cols) * thumb_w
    y = (k // cols) * thumb_h
    sheet.paste(im, (x, y))
    d.text((x + 2, y + 2), f"{k*2}s", fill=(255, 255, 0))
sheet.save(os.path.join(wd, "montage.jpg"), quality=80)
print("montage saved:", os.path.join(wd, "montage.jpg"))
print("index->time: idx*0.5s ; montage cell k -> k*2s")
