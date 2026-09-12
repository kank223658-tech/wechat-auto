# -*- coding: utf-8 -*-
"""校验「面板滑入过程不再空白」：逐帧统计彩色像素（emoji/图标有颜色，空面板近乎纯黑）。
修复前实测：首次打开面板到位后仍有 ~260ms 彩色像素≈236（空）。
用法：py _check_blank.py [视频路径]   缺省取 videos/ 下最新 mp4
"""
import os, glob, shutil, subprocess, sys
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FF = r"C:\Users\mik\AppData\Local\Programs\Python\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
ROOT = r"G:\weixin-auto"


def newest_video():
    fs = [f for f in glob.glob(os.path.join(ROOT, "videos", "wx_*.mp4"))]
    return max(fs, key=os.path.getmtime)


def main():
    vid = sys.argv[1] if len(sys.argv) > 1 else newest_video()
    print("视频:", vid)
    out = os.path.join(ROOT, "_fix7", "chk")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    subprocess.run([FF, "-y", "-i", vid, "-vf", "fps=30,scale=250:-1",
                    os.path.join(out, "f_%04d.png")], capture_output=True)
    fs = sorted(glob.glob(os.path.join(out, "f_*.png")))
    arrs = [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in fs]
    H, W, _ = arrs[0].shape
    print("共 %d 帧 @30fps（%.1fs）  缩放后 %dx%d" % (len(fs), len(fs) / 30.0, W, H))

    lows = []
    for i, a in enumerate(arrs):
        sub = a[int(0.45 * H):H]
        col = int(((sub.max(axis=2) - sub.min(axis=2)) > 45).sum())
        lows.append(col)

    print("\n彩色像素时间线（只打印变化点）:")
    prev = None
    for i, c in enumerate(lows):
        if prev is None or abs(c - prev) > 300:
            print("  t=%6.2f  彩色=%5d" % (i / 30.0, c))
        prev = c

    # 找「低谷」：连续 >=2 帧彩色 < 600（空面板）且两侧都有高值
    print("\n低谷段（彩色<600，疑似空面板）:")
    i = 0
    found = False
    while i < len(lows):
        if lows[i] < 600:
            j = i
            while j + 1 < len(lows) and lows[j + 1] < 600:
                j += 1
            if j - i + 1 >= 2:
                found = True
                print("  t=%.2f~%.2f  %d 帧 = %.0fms" % (i / 30.0, (j + 1) / 30.0,
                                                        j - i + 1, (j - i + 1) / 30.0 * 1000))
            i = j + 1
        else:
            i += 1
    if not found:
        print("  （无）")


main()
