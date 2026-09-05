# -*- coding: utf-8 -*-
"""成品视频 60fps 全帧孤立异常检测。

与 _prod_stream 相同思路，但按 60fps 逐帧读，捕捉「单帧一闪」的放大闪帧。
判别：第 i 帧与前后帧都差异大，而前后两帧彼此相近（base 很小）。
用低维 30x66 灰度特征，逐帧从 stdout 读，不落盘。
"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe

ff = get_ffmpeg_exe()
video = sys.argv[1] if len(sys.argv) > 1 else r"F:\weixin-auto\videos\wx_20260902_220240.mp4"
FPS = 60
TW, TH = 30, 66
fb = TW * TH
proc = subprocess.Popen(
    [ff, "-v", "error", "-i", video, "-vf", f"fps={FPS},scale={TW}:{TH}",
     "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
feats = []
while True:
    buf = proc.stdout.read(fb)
    if len(buf) < fb:
        break
    a = np.frombuffer(buf, dtype=np.uint8).astype(np.float32) / 255.0
    feats.append(a)
N = len(feats)
print("frames(60fps):", N, " dur ~ %.2fs" % (N / FPS))
if not feats:
    sys.exit(0)
F = np.vstack(feats)

def diff(i, j):
    return float(np.mean(np.abs(F[i] - F[j])))

anom = []
for i in range(1, N - 1):
    dp = diff(i, i - 1)
    dn = diff(i, i + 1)
    dnn = diff(i - 1, i + 1)
    # 帧本身异常：与两侧都差异明显，而两侧彼此接近（真实孤立帧）
    if dp > 0.05 and dn > 0.05 and dnn < 0.02:
        anom.append((i, dp, dn, dnn))
anom.sort(key=lambda t: -(t[1] + t[2]))
print("=== 孤立异常帧 TOP 40 (t秒, d_prev, d_next, d_base) ===")
for i, dp, dn, dnn in anom[:40]:
    print(f"  t={i/FPS:7.3f}s  dp={dp:.3f} dn={dn:.3f} base={dnn:.3f}")
print("总数:", len(anom))
