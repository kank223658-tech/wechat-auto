# -*- coding: utf-8 -*-
"""数值化定位：给定时刻输出绿键/蓝名/输入条/键盘的像素级证据。
用法：py _probe_num.py <video> t1 t2 ...
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
    png = os.path.join(OUT, "nm_%s.png" % tag)
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


def bbox(mask, label, off=0):
    ys, xs = np.where(mask)
    if len(ys) < 20:
        print("  %s: 无" % label)
        return
    print("  %s: %d px, y%d-%d x%d-%d" % (label, len(ys),
          ys.min() + off, ys.max() + off, xs.min(), xs.max()))


def main():
    vid = sys.argv[1]
    for i, t in enumerate(sys.argv[2:]):
        f = grab(vid, float(t), str(i))
        if f is None:
            print("===== t=%s 抽帧失败 =====" % t)
            continue
        H, W = f.shape[:2]
        print("===== t=%ss  (%dx%d) =====" % (t, W, H))
        r = f.astype(np.int32)
        R, G, B = r[:, :, 0], r[:, :, 1], r[:, :, 2]
        green = (G > R + 60) & (G > B + 30) & (G > 140)
        bbox(green, "绿色(发送键)")
        blue = (B > R + 25) & (B > G + 8) & (B > 100) & (R > 60)
        bbox(blue, "蓝色(名字/心)")
        # 输入条：整行 55%+ 像素亮度在 60-100（#4f4f4f）
        g = f.mean(axis=2)
        band = ((g > 55) & (g < 105)).mean(axis=1)
        rows = np.where(band > 0.55)[0]
        if len(rows):
            print("  输入条候选行: y%d-%d (共%d行)" % (rows.min(), rows.max(), len(rows)))
        else:
            print("  输入条候选行: 无")
        # 键盘：底部 40% 中，行内亮度 std>25（键帽纹理）的行
        kb_zone = g[int(H * 0.6):, :]
        kstd = kb_zone.std(axis=1)
        krows = np.where(kstd > 30)[0]
        if len(krows):
            print("  键盘纹理行: y%d-%d (共%d行, 相对y60%%)" % (
                krows.min(), krows.max(), len(krows)))
        else:
            print("  键盘纹理行: 无")
        # 底部 15% 平均亮度（键盘区应明显不同于纯页面）
        print("  底部15%%均亮: %.0f | y60-95%%均亮: %.0f" % (
            g[int(H * 0.85):].mean(), g[int(H * 0.6):int(H * 0.95)].mean()))


if __name__ == "__main__":
    main()
