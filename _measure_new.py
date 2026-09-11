# -*- coding: utf-8 -*-
"""输出视频修复后复测：图块/单图/胶囊/深灰条/心形/弹窗/细条/键盘行距。"""
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
VID = r"G:/weixin-auto/videos/wx_likecmt_20260911_061813_976.mp4"

SX = 600.0 / 1080.0


def css(v):
    return v * SX


def grab(tsec):
    png = r"G:/weixin-auto/_fs/_mn_tmp.png"
    subprocess.run([FF, "-y", "-ss", "%.3f" % tsec, "-i", VID, "-frames:v", "1", png],
                   capture_output=True)
    raw = subprocess.run([FF, "-y", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def mask_bbox(f, y0, y1, x0, x1, lo, hi, label):
    r = f[y0:y1, x0:x1].astype(np.int32).mean(axis=2)
    m = (r >= lo) & (r <= hi)
    if not m.any():
        print("  [%s] 无" % label)
        return
    ys, xs = np.where(m)
    print("  [%s] raw x%d-%d y%d-%d | CSS x%.0f-%.0f y%.0f-%.0f (w%.0f h%.0f) px=%d" % (
        label, x0 + xs.min(), x0 + xs.max(), y0 + ys.min(), y0 + ys.max(),
        css(x0 + xs.min()), css(x0 + xs.max()), css(y0 + ys.min()), css(y0 + ys.max()),
        css(xs.max() - xs.min()), css(ys.max() - ys.min()), m.sum()))


def col_profile_edges(f, y0, y1, x0, x1, thr, label, min_run=10):
    g = f[y0:y1, x0:x1].astype(np.int32).mean(axis=2)
    colmax = g.max(axis=0)
    on = colmax > thr
    runs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_run:
                runs.append((x0 + s, x0 + i))
            s = None
    if s is not None:
        runs.append((x0 + s, x0 + len(on)))
    print("  [%s] 列段: %s" % (label, [("raw%d-%d CSS%.0f-%.0f" % (a, b, css(a), css(b))) for a, b in runs]))


def row_profile_edges(f, y0, y1, x0, x1, thr, label, min_run=8):
    g = f[y0:y1, x0:x1].astype(np.int32).mean(axis=2)
    rowmax = g.max(axis=1)
    on = rowmax > thr
    runs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_run:
                runs.append((y0 + s, y0 + i))
            s = None
    if s is not None:
        runs.append((y0 + s, y0 + len(on)))
    print("  [%s] 行段: %s" % (label, [("raw%d-%d CSS%.0f-%.0f" % (a, b, css(a), css(b))) for a, b in runs]))


def rgb_at(f, y0, y1, x0, x1, label):
    r = f[y0:y1, x0:x1].astype(np.int32)
    m = r.mean(axis=(0, 1))
    print("  [%s] 均RGB=(%.0f,%.0f,%.0f)" % (label, m[0], m[1], m[2]))


def blue_bbox(f, y0, y1, x0, x1, label):
    r = f[y0:y1, x0:x1].astype(np.int32)
    b, g, rr = r[:, :, 2], r[:, :, 1], r[:, :, 0]
    m = (b > rr + 20) & (b > 85)
    if not m.any():
        print("  [%s] 无" % label)
        return
    ys, xs = np.where(m)
    print("  [%s] raw x%d-%d y%d-%d | CSS x%.0f-%.0f y%.0f-%.0f (w%.0f h%.0f) px=%d" % (
        label, x0 + xs.min(), x0 + xs.max(), y0 + ys.min(), y0 + ys.max(),
        css(x0 + xs.min()), css(x0 + xs.max()), css(y0 + ys.min()), css(y0 + ys.max()),
        css(xs.max() - xs.min()), css(ys.max() - ys.min()), m.sum()))


def main():
    print("========== t=9.0 帖1 图块/胶囊/深灰条/心形 ==========")
    f = grab(9.0)
    col_profile_edges(f, 560, 830, 100, 700, 55, "帖1图块列边界", min_run=14)
    row_profile_edges(f, 540, 900, 220, 380, 55, "帖1图块行边界(取图1列)")
    mask_bbox(f, 820, 900, 860, 1060, 28, 60, "胶囊(28-60)")
    rgb_at(f, 850, 880, 940, 990, "胶囊内部")
    mask_bbox(f, 930, 1400, 50, 1040, 26, 42, "深灰面板(26-42)")
    rgb_at(f, 1100, 1200, 400, 900, "面板中段均色")
    blue_bbox(f, 1000, 1200, 60, 300, "心形+蓝名(蓝mask)")
    row_profile_edges(f, 1000, 1200, 60, 220, 60, "点赞行内容行")

    print("========== t=11.0 滚动后 竖图 ==========")
    f = grab(11.0)
    col_profile_edges(f, 300, 1300, 60, 500, 70, "帖区列边界", min_run=20)
    row_profile_edges(f, 300, 1300, 240, 400, 70, "帖区行边界(取竖图列)")

    print("========== t=15.0 细条+键盘 ==========")
    f = grab(15.0)
    row_profile_edges(f, 1240, 1500, 100, 1000, 52, "细条区行段")
    rgb_at(f, 1340, 1410, 60, 800, "细条均色")
    rgb_at(f, 1340, 1410, 40, 90, "细条左端")
    col_profile_edges(f, 1330, 1420, 700, 1070, 50, "细条区列段", min_run=14)
    mask_bbox(f, 1330, 1420, 850, 1060, 55, 95, "发送按钮(55-95)")
    row_profile_edges(f, 1420, 1700, 100, 1000, 60, "键盘顶部行")
    row_profile_edges(f, 1500, 2350, 100, 1000, 60, "键盘键行")


if __name__ == "__main__":
    main()
