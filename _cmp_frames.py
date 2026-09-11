# -*- coding: utf-8 -*-
"""全分辨率对比两个时间点的帧：整体 dy、残差、分段差异带。
用法：py _cmp_frames.py video t1 t2 [t3 ...]  （两两对比相邻时间点）
"""
import os
import re
import subprocess
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FF = (r"C:/Users/mik/AppData/Local/Programs/Python/Python314"
      r"/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe")
OUT = r"G:/weixin-auto/_fs"
os.makedirs(OUT, exist_ok=True)
TAG = "cmpf"


def grab_frame(vid, tsec, tag_idx):
    """按时间抽一帧原尺寸，返回 HxWx3 uint8。"""
    png = os.path.join(OUT, "%s_%d.png" % (TAG, tag_idx))
    if os.path.exists(png):
        os.remove(png)
    cmd = [FF, "-ss", "%.3f" % tsec, "-i", vid, "-frames:v", "1", png]
    subprocess.run(cmd, capture_output=True)
    cmd2 = [FF, "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd2, capture_output=True).stdout
    if len(raw) < 100:
        return None
    import struct
    # 从 png 头取宽高
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def best_dy(a, b, search=200):
    """b 相对 a 的纵向位移（内容上移为正），灰度下采样 x2 加速。"""
    ga = a[::2, ::2].mean(axis=2).astype(np.int16)
    gb = b[::2, ::2].mean(axis=2).astype(np.int16)
    H, W = ga.shape
    best = (0, 1e18)
    for dy in range(-search, search + 1, 1):
        if dy >= 0:
            aa, bb = ga[dy:, :], gb[: H - dy, :]
        else:
            aa, bb = ga[: H + dy, :], gb[-dy:, :]
        d = int(np.abs(aa - bb).sum())
        if d < best[1]:
            best = (dy, d)
    dy0, s0 = best
    return dy0, s0 / aa.size / 255.0


def band_diff(a, b, bands=13):
    """水平分带的平均差（0-255），看变化集中在哪些行。"""
    ga = a.mean(axis=2).astype(np.int16)
    gb = b.mean(axis=2).astype(np.int16)
    H = ga.shape[0]
    out = []
    for k in range(bands):
        y0, y1 = H * k // bands, H * (k + 1) // bands
        out.append(float(np.abs(ga[y0:y1] - gb[y0:y1]).mean()))
    return out


def main():
    vid = sys.argv[1]
    ts = [float(x) for x in sys.argv[2:]]
    frames = []
    for i, t in enumerate(ts):
        f = grab_frame(vid, t, i)
        frames.append(f)
        print("帧%d t=%.2fs  %s" % (i, t, "OK %dx%d" % (f.shape[1], f.shape[0]) if f is not None else "FAIL"))
    for i in range(len(frames) - 1):
        a, b = frames[i], frames[i + 1]
        if a is None or b is None:
            continue
        dy, res = best_dy(a, b)
        print("\n[%.2fs -> %.2fs]  最优dy=%+d(视频px)  残差=%.4f" % (ts[i], ts[i + 1], dy * 2, res))
        bd = band_diff(a, b)
        print("  分带差异(13带, 0-255):", " ".join("%4.1f" % v for v in bd))
        h = a.shape[0]
        hot = [(k, round(v, 1)) for k, v in enumerate(bd) if v > 3.0]
        if hot:
            print("  热带(>3):", ["带%d(y%d-%d)=%.1f" % (k, h * k // 13, h * (k + 1) // 13, v) for k, v in hot])


if __name__ == "__main__":
    main()
