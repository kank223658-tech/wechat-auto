# -*- coding: utf-8 -*-
"""验证视频状态扫描：每 0.1s 输出关键 UI 信号，定位点赞/评论动画序列。
用法：py _state_scan.py <video> [t0 t1]
"""
import os
import struct
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


def grab(vid, tsec, tag):
    png = os.path.join(OUT, "st_%s.png" % tag)
    if os.path.exists(png):
        os.remove(png)
    subprocess.run([FF, "-ss", "%.3f" % tsec, "-i", vid, "-frames:v", "1", png],
                   capture_output=True)
    cmd2 = [FF, "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd2, capture_output=True).stdout
    if len(raw) < 100:
        return None
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def sig(f):
    r = f.astype(np.int32)
    R, G, B = r[:, :, 0], r[:, :, 1], r[:, :, 2]
    green = ((G > R + 60) & (G > B + 30) & (G > 140)).mean()
    blue = ((B > R + 25) & (B > G + 8) & (B > 100) & (R > 60)).mean()
    H = f.shape[0]
    kb = f[int(H * 0.66):int(H * 0.92)].mean(axis=2)   # 键盘区
    kb_mean = kb.mean()
    # 键盘行纹理：亮字在暗键帽上 -> 行内方差较大
    kb_std = kb.std()
    # 页面顶部指纹：前 12% 行均值（用于识别页面位置）
    top = f[: int(H * 0.12)].mean()
    return green, blue, kb_mean, kb_std, top


def main():
    vid = sys.argv[1]
    t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    t1 = float(sys.argv[3]) if len(sys.argv) > 3 else 999.0
    t = t0
    prev = None
    while True:
        f = grab(vid, t, "cur")
        if f is None:
            break
        g, b, km, ks, top = sig(f)
        state = (round(g, 4), round(b, 4), round(km), round(ks), round(top))
        if state != prev:
            print("t=%5.2fs 绿=%.4f 蓝=%.4f 键盘亮度=%3d 键盘std=%3d 顶部亮度=%3d"
                  % (t, g, b, km, ks, top))
            prev = state
        t = round(t + 0.1, 2)
        if t > t1:
            break


if __name__ == "__main__":
    main()
