# -*- coding: utf-8 -*-
"""流式定位成品视频的『孤立异常帧』（放大到左上角等一闪而过的错位帧）。

直接用 ffmpeg 输出 40x87 灰度缩略帧（rawvideo），从 stdout 逐帧读取，
不落盘、速度快。对每帧算低维特征，找「与前后帧都差异大、但前后两帧彼此相近」
的孤立异常帧。
"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe

ff = get_ffmpeg_exe()
video = sys.argv[1] if len(sys.argv) > 1 else r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
FPS = 15
TW, TH = 40, 87
frame_bytes = TW * TH

proc = subprocess.Popen(
    [ff, "-v", "error", "-i", video, "-vf", f"fps={FPS},scale={TW}:{TH}",
     "-f", "rawvideo", "-pix_fmt", "gray", "-"],
    stdout=subprocess.PIPE,
)
feats = []
while True:
    buf = proc.stdout.read(frame_bytes)
    if len(buf) < frame_bytes:
        break
    a = np.frombuffer(buf, dtype=np.uint8).astype(np.float32) / 255.0
    feats.append(a)
N = len(feats)
print("frames(15fps):", N, " dur ~ %.1fs" % (N / FPS))
feats = np.vstack(feats)

def diff(i, j):
    return float(np.mean(np.abs(feats[i] - feats[j])))

anom = []
for i in range(1, N - 1):
    dp = diff(i, i - 1)
    dn = diff(i, i + 1)
    dnn = diff(i - 1, i + 1)
    if dp > 0.04 and dn > 0.04 and dnn < 0.018:
        anom.append((i, dp, dn, dnn))
anom.sort(key=lambda t: -(t[1] + t[2]))
print("=== 孤立异常帧 TOP 50（idx, t秒, d_prev, d_next, d_nn 基线） ===")
for i, dp, dn, dnn in anom[:50]:
    bar = "#" * int(min(40, (dp + dn) * 60))
    print(f"  idx {i:4d}  t={i/FPS:7.2f}s  dp={dp:.3f} dn={dn:.3f} base={dnn:.3f} {bar}")
print("总数:", len(anom))
