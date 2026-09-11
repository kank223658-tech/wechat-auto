# -*- coding: utf-8 -*-
"""验证视频故事板：按给定时间点抽帧输出粗 ASCII，确认点赞/评论动画序列。
用法：py _probe_likecmt.py <video> t1 t2 t3 ...
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
    png = os.path.join(OUT, "sb_%s.png" % tag)
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


def ascii_full(f, sx=12, sy=16):
    g = f.mean(axis=2)
    H, W = g.shape
    lines = []
    for y in range(0, H - sy + 1, sy):
        line = ""
        for x in range(0, W - sx + 1, sx):
            v = g[y:y + sy, x:x + sx].mean()
            line += " .:-=+*#%@"[min(9, int(v / 26))]
        lines.append(line)
    return "\n".join(lines)


def main():
    vid = sys.argv[1]
    for i, t in enumerate(sys.argv[2:]):
        f = grab(vid, float(t), str(i))
        print("===== t=%ss =====" % t)
        if f is None:
            print("(抽帧失败)")
            continue
        print(ascii_full(f))


if __name__ == "__main__":
    main()
