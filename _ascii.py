# -*- coding: utf-8 -*-
"""任意区域 ASCII 灰度图 + 列剖面。用法：py _ascii.py <video> <t> <y0> <y1> [x0] [x1] [ystep] [xstep]"""
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


def grab(vid, tsec):
    png = r"G:/weixin-auto/_fs/_ascii_tmp.png"
    subprocess.run([FF, "-y", "-ss", "%.3f" % tsec, "-i", vid, "-frames:v", "1", png],
                   capture_output=True)
    raw = subprocess.run([FF, "-y", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def main():
    vid, t = sys.argv[1], float(sys.argv[2])
    y0, y1 = int(sys.argv[3]), int(sys.argv[4])
    x0 = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    x1 = int(sys.argv[6]) if len(sys.argv) > 6 else None
    ys = int(sys.argv[7]) if len(sys.argv) > 7 else 6
    xs = int(sys.argv[8]) if len(sys.argv) > 8 else 6
    f = grab(vid, t)
    H, W = f.shape[:2]
    x1 = x1 or W
    g = f[y0:y1, x0:x1].mean(axis=2)
    print("帧 %dx%d，区域 y%d-%d x%d-%d" % (W, H, y0, y1, x0, x1))
    hdr = "     " + "".join(str((x0 + x) // 100 % 10) if (x0 + x) % 50 < xs else " " for x in range(0, x1 - x0, xs))
    print(hdr)
    for y in range(0, y1 - y0, ys):
        line = ""
        for x in range(0, x1 - x0, xs):
            v = g[y:y + ys, x:x + xs].mean()
            line += " .:-=+*#%@"[min(9, int(v / 26))]
        print("%4d %s" % (y0 + y, line))


if __name__ == "__main__":
    main()
