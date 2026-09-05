# -*- coding: utf-8 -*-
"""定位成品视频里的『孤立异常帧』（一闪而过的错位/放大帧）。

思路：抽 30fps 帧，对每帧算一个低维特征（下采样缩略图）。
若某帧与【前帧】和【后帧】的差异同时都很大，而它的前后两帧彼此相近，
则该帧是孤立异常帧 —— 正是『放大到左上角』等一闪而过的错位帧的签名。
"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe

ff = get_ffmpeg_exe()
video = r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
wd = r"F:\weixin-auto\_prod_30fps"
os.makedirs(wd, exist_ok=True)
for f in os.listdir(wd):
    os.remove(os.path.join(wd, f))
FPS = 30
subprocess.run([ff, "-y", "-loglevel", "error", "-i", video, "-vf", f"fps={FPS}",
                os.path.join(wd, "%05d.png")], check=True)
files = sorted(os.listdir(wd))
files = [f for f in files if f.endswith(".png")]
N = len(files)
print("frames(30fps):", N, " dur ~", N / FPS, "s")

# 特征：下采样到 40x87 的灰度
TW, TH = 40, 87
feats = np.zeros((N, TW * TH), dtype=np.float32)
for i, fn in enumerate(files):
    im = Image.open(os.path.join(wd, fn)).convert("L").resize((TW, TH))
    feats[i] = np.asarray(im, dtype=np.float32).ravel() / 255.0

def diff(a, b):
    return float(np.mean(np.abs(feats[a] - feats[b])))

# 孤立异常帧：与前后都差异大
anom = []
for i in range(1, N - 1):
    d_prev = diff(i, i - 1)
    d_next = diff(i, i + 1)
    d_nn = diff(i - 1, i + 1)      # 前后两帧彼此的差异（正常基线）
    # 若前后两帧本身相近(d_nn 小)但当前帧同时偏离前后(d_prev,d_next 都大) => 孤立异常
    if d_prev > 0.05 and d_next > 0.05 and d_nn < 0.02:
        anom.append((i, d_prev, d_next, d_nn))
print("=== 孤立异常帧（idx, d_prev, d_next, d_nn）top 40 ===")
anom.sort(key=lambda t: -(t[1] + t[2]))
for i, dp, dn, dnn in anom[:40]:
    print(f"  idx {i:5d}  t={i/FPS:6.2f}s  d_prev={dp:.3f} d_next={dn:.3f} d_nn={dnn:.3f}")
print("总数:", len(anom))
