# -*- coding: utf-8 -*-
"""参考视频结尾态探针：确认评论发送后的呈现形式 + 输入条配色。
用法：py _probe_end.py <video>
"""
import os
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
    png = os.path.join(OUT, "probe_%s.png" % tag)
    if os.path.exists(png):
        os.remove(png)
    subprocess.run([FF, "-ss", "%.3f" % tsec, "-i", vid, "-frames:v", "1", png],
                   capture_output=True)
    cmd2 = [FF, "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd2, capture_output=True).stdout
    import struct
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def region_stats(f, x0, y0, x1, y1, label):
    r = f[y0:y1, x0:x1].astype(np.int32)
    mean = r.mean(axis=(0, 1))
    # 蓝色文字像素（WeChat 蓝 #576b95 / 深色模式蓝名）
    b, g, rr = r[:, :, 2], r[:, :, 1], r[:, :, 0]
    blue = (b > rr + 25) & (b > g + 10) & (b > 90)
    green = (g > rr + 40) & (g > b + 20) & (g > 110)
    bright = r.mean(axis=2) > 170
    print("  [%s] 均值RGB=(%.0f,%.0f,%.0f) 蓝px=%.1f%% 绿px=%.1f%% 亮px=%.1f%%" % (
        label, mean[0], mean[1], mean[2],
        100.0 * blue.mean(), 100.0 * green.mean(), 100.0 * bright.mean()))
    if blue.mean() > 0.001:
        ys, xs = np.where(blue)
        print("      蓝像素范围 y%d-%d x%d-%d" % (ys.min() + y0, ys.max() + y0,
                                                  xs.min() + x0, xs.max() + x0))
    if green.mean() > 0.005:
        ys, xs = np.where(green)
        # 绿色区域的平均色
        sel = r[green]
        print("      绿像素范围 y%d-%d x%d-%d 均色RGB=(%.0f,%.0f,%.0f)" % (
            ys.min() + y0, ys.max() + y0, xs.min() + x0, xs.max() + x0,
            sel[:, 0].mean(), sel[:, 1].mean(), sel[:, 2].mean()))
    return mean


def row_profile(f, y0, y1, x0=0, x1=None):
    g = f[y0:y1, x0:(x1 or f.shape[1])].mean(axis=2)
    prof = g.mean(axis=1)
    lines = []
    prev = None
    for i, v in enumerate(prof):
        b = int(v // 24)
        if b != prev:
            lines.append("y%d:%d" % (y0 + i, int(v)))
            prev = b
    return " ".join(lines)


def main():
    vid = sys.argv[1]
    # t=10.0 键盘+输入条稳定态：输入条配色
    f = grab(vid, 10.0, "t10")
    print("== t=10.0 输入条区 ==")
    region_stats(f, 0, 1090, 592, 1170, "输入条整条")
    region_stats(f, 8, 1098, 148, 1160, "左侧图标区")
    region_stats(f, 156, 1098, 440, 1160, "输入框")
    region_stats(f, 444, 1098, 580, 1160, "发送按钮")
    # t=13.8 结束态：点赞/评论区
    f2 = grab(vid, 13.8, "t138")
    print("\n== t=13.8 结束态 ==")
    for (x0, y0, x1, y1, lb) in [
            (0, 0, 592, 130, "顶部导航"),
            (0, 280, 592, 560, "帖内容区"),
            (0, 560, 592, 700, "点赞/评论区"),
            (0, 700, 592, 1080, "中部大区(疑似图/滚动内容)"),
            (0, 1080, 592, 1280, "底部区")]:
        region_stats(f2, x0, y0, x1, y1, lb)
    print("  行剖面 y560-700:", row_profile(f2, 560, 700))
    print("  行剖面 y700-1100:", row_profile(f2, 700, 1100))
    # t=6.0 对照：点赞条刚出现
    f3 = grab(vid, 6.0, "t60")
    print("\n== t=6.0 对照（点赞后键盘前） ==")
    region_stats(f3, 0, 560, 592, 700, "点赞/评论区")
    print("  行剖面 y560-700:", row_profile(f3, 560, 700))
    # t=13.8 点赞条区域放大 ASCII（每3x6px一格）看评论行
    g = f2[560:700, :, :].mean(axis=2)
    print("\n== t=13.8 y560-700 高分辨率ASCII (x步6,y步3) ==")
    for y in range(0, 140, 3):
        line = ""
        for x in range(0, 592, 6):
            v = g[y:y + 3, x:x + 6].mean()
            line += " .:-=+*#%@"[min(9, int(v / 26))]
        print(line)
    # t=13.8 中部大区低分辨率 ASCII 确认是否为图片网格
    g2 = f2[700:1100, :, :].mean(axis=2)
    print("\n== t=13.8 y700-1100 ASCII (x步12,y步8) ==")
    for y in range(0, 400, 8):
        line = ""
        for x in range(0, 592, 12):
            v = g2[y:y + 8, x:x + 12].mean()
            line += " .:-=+*#%@"[min(9, int(v / 26))]
        print(line)


if __name__ == "__main__":
    main()
