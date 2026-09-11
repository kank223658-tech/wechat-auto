# -*- coding: utf-8 -*-
"""区域 ASCII：只看画面下半部（帖子工具条/点赞条/弹窗/键盘/输入条所在）。
用法：py _probe_regions.py <video> t1 t2 ...
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
    png = os.path.join(OUT, "rg_%s.png" % tag)
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


def main():
    vid = sys.argv[1]
    for i, t in enumerate(sys.argv[2:]):
        f = grab(vid, float(t), str(i))
        print("===== t=%ss =====" % t)
        if f is None:
            print("(抽帧失败)")
            continue
        H, W = f.shape[:2]
        y0 = int(H * 0.50)          # 下半部
        g = f[y0:, :].mean(axis=2)
        hh, ww = g.shape
        sx, sy = 16, 26
        for y in range(0, hh - sy + 1, sy):
            line = ""
            for x in range(0, ww - sx + 1, sx):
                v = g[y:y + sy, x:x + sx].mean()
                line += " .:-=+*#%@"[min(9, int(v / 26))]
            print(line)


if __name__ == "__main__":
    main()
