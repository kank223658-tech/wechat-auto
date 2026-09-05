# -*- coding: utf-8 -*-
"""验证合成阶段的「孤立放大帧回退」检测：在成品视频 wx_20260902_205201.mp4 上，
用与 _assemble_vfr_mp4 完全一致的算法（30x66 缩略图、DP=0.10、BASE=0.02、<=3帧成段）
找出孤立异常帧段，看是否命中已肉眼确认的放大闪帧时间点。"""
import io, sys, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from imageio_ffmpeg import get_ffmpeg_exe
ff = get_ffmpeg_exe()
video = r"F:\weixin-auto\videos\wx_20260902_205201.mp4"
FPS = 30
TW, TH = 30, 66
fb = TW * TH
proc = subprocess.Popen([ff, "-v", "error", "-i", video, "-vf", f"fps={FPS},scale={TW}:{TH}",
                         "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
feat = []
while True:
    buf = proc.stdout.read(fb)
    if len(buf) < fb:
        break
    feat.append(bytes(buf))
N = len(feat)
print("frames:", N, " dur ~ %.1f s" % (N / FPS))
def fd(i, j):
    a, b = feat[i], feat[j]
    return sum(abs(x - y) for x, y in zip(a, b)) / (255.0 * len(a))
DP, BASE = 0.10, 0.02
flash = [i for i in range(1, N - 1)
         if fd(i, i - 1) > DP and fd(i, i + 1) > DP and fd(i - 1, i + 1) < BASE]
runs = []
if flash:
    s = p = flash[0]
    for x in flash[1:]:
        if x <= p + 3:
            p = x
        else:
            runs.append((s, p)); s = p = x
    runs.append((s, p))
print("检测到孤立异常段:", len(runs))
for a, b in runs:
    print(f"  t={a/FPS:.2f}s .. {b/FPS:.2f}s  ({b-a+1}帧, {(b-a+1)/FPS:.3f}s)")
known = [15.67, 25.80, 29.80, 54.67, 100.40]
print("已知放大闪帧时间点:", known)
