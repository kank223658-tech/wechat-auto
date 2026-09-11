# -*- coding: utf-8 -*-
"""验证 Tab 切换是否为硬切：解码视频为小尺寸灰度帧序列，计算相邻帧差异。

判定：
  硬切 = 某一帧对差异突然变大，且前后相邻差异都接近 0（单帧跳变）；
  混合（GAP_BLEND 残留）= 切换点附近出现一连串中等差异（渐变坡道）。
"""
import subprocess
import sys

import numpy as np

VID = sys.argv[1] if len(sys.argv) > 1 else r"g:\weixin-auto\videos\wx_20260911_005559_732.mp4"
W, H = 60, 130

cmd = [
    r"C:\Users\mik\AppData\Local\Programs\Python\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe",
    "-loglevel", "error", "-i", VID,
    "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-",
]
raw = subprocess.run(cmd, capture_output=True).stdout
n_expected = len(raw) // (W * H)
frames = np.frombuffer(raw[: n_expected * W * H], dtype=np.uint8).reshape(n_expected, H, W).astype(np.int16)
print(f"帧数: {n_expected}  (60fps => {n_expected/60:.2f}s)")

d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))  # d[i] = 帧 i -> i+1 的差异
print(f"差异统计: mean={d.mean():.4f}  p95={np.percentile(d, 95):.4f}  max={d.max():.4f}")

# 找出所有显著跳变（阈值取 p95 与绝对值的较大者）
thr = max(0.012, float(np.percentile(d, 95)) * 0.8)
idx = np.where(d > thr)[0]
# 聚类相邻索引成事件
events = []
for i in idx:
    if events and i - events[-1][-1] <= 3:
        events[-1].append(i)
    else:
        events.append([i])

print(f"\n跳变事件 {len(events)} 个（阈值 {thr:.4f}）：")
for ev in events:
    a, b = ev[0], ev[-1]
    span_s = (a / 60.0)
    width = b - a + 1
    kind = "硬切(单帧)" if width <= 2 else f"渐变坡({width}帧, 可疑残留混合)"
    lo = max(0, a - 5)
    hi = min(len(d), b + 6)
    ctx = " ".join(f"{v:.3f}" for v in d[lo:hi])
    print(f"  t≈{span_s:6.2f}s  帧{a}~{b}  -> {kind}\n     附近差异: {ctx}")
