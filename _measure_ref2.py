# -*- coding: utf-8 -*-
"""参考视频第二轮精确测量：头像/文本列/图块/深灰条/输入条/候选栏/弹窗。"""
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
VID = r"G:/weixin-auto/参考图片/朋友圈点赞后评论.mp4"


def grab(tsec):
    png = r"G:/weixin-auto/_fs/_mr2_tmp.png"
    subprocess.run([FF, "-y", "-ss", "%.3f" % tsec, "-i", VID, "-frames:v", "1", png],
                   capture_output=True)
    raw = subprocess.run([FF, "-y", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


SX = 600.0 / 592.0


def css(v):
    return v * SX


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


def col_profile_edges(f, y0, y1, x0, x1, thr, label):
    """列最大亮度 > thr 的列段（抗图片内容暗区干扰）。"""
    g = f[y0:y1, x0:x1].astype(np.int32).mean(axis=2)
    colmax = g.max(axis=0)
    on = colmax > thr
    runs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= 12:
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


def main():
    print("========== t=0.5 帖子版面 ==========")
    f = grab(0.5)
    mask_bbox(f, 640, 726, 0, 105, 45, 255, "帖1头像(只到x105避文字)")
    row_profile_edges(f, 636, 730, 8, 100, 45, "头像行边界")
    # 文本列左缘：每行最左亮像素
    r = f[650:726, 85:400].astype(np.int32).mean(axis=2)
    mins = []
    for i in range(r.shape[0]):
        xs = np.where(r[i] > 95)[0]
        if len(xs):
            mins.append(85 + xs.min())
    if mins:
        import collections
        cnt = collections.Counter(mins)
        common = cnt.most_common(6)
        print("  文本行最左x(raw)众数:", common, "-> CSS %.0f" % css(common[0][0]))
    col_profile_edges(f, 736, 850, 60, 480, 55, "图块列边界")
    row_profile_edges(f, 700, 880, 130, 220, 55, "图块行边界")
    mask_bbox(f, 855, 905, 490, 580, 28, 60, "胶囊(28-60)")
    rgb_at(f, 866, 892, 515, 550, "胶囊内部")

    print("========== t=13.8 深灰条 ==========")
    f = grab(13.8)
    mask_bbox(f, 540, 730, 40, 592, 26, 42, "面板(26-42)")
    row_profile_edges(f, 545, 725, 130, 500, 60, "面板内文字行")
    # 蓝名行
    r = f[540:730, 100:592].astype(np.int32)
    b, g, rr = r[:, :, 2], r[:, :, 1], r[:, :, 0]
    blue = (b > rr + 20) & (b > 85)
    ys, xs = np.where(blue)
    if len(ys):
        print("  蓝字 raw x%d-%d y%d-%d | CSS x%.0f-%.0f y%.0f-%.0f px=%d" % (
            100 + xs.min(), 100 + xs.max(), 540 + ys.min(), 540 + ys.max(),
            css(100 + xs.min()), css(100 + xs.max()), css(540 + ys.min()), css(540 + ys.max()), len(ys)))
    rgb_at(f, 600, 640, 200, 500, "面板中段均色")

    print("========== t=10.0 输入条+键盘 ==========")
    f = grab(10.0)
    # 输入条区精确行边界（内容与键盘之间）
    row_profile_edges(f, 760, 860, 90, 560, 55, "输入条/候选栏行")
    rgb_at(f, 786, 842, 92, 550, "条区整体均色")
    rgb_at(f, 786, 842, 4, 80, "条区左侧块")
    rgb_at(f, 786, 842, 556, 588, "条区右端")
    rgb_at(f, 848, 878, 92, 550, "键上方过渡带")
    # 键盘行
    row_profile_edges(f, 845, 1280, 90, 560, 60, "键盘行")
    rgb_at(f, 860, 910, 30, 80, "键帽采样")
    rgb_at(f, 925, 945, 92, 550, "键行间隙")
    rgb_at(f, 1180, 1260, 92, 550, "键盘底部")

    print("========== t=6.05 弹窗 ==========")
    f = grab(6.05)
    mask_bbox(f, 840, 920, 150, 520, 70, 105, "弹窗面板(70-105)")
    row_profile_edges(f, 855, 900, 230, 480, 110, "弹窗内容行")
    col_profile_edges(f, 860, 892, 230, 500, 110, "弹窗内容列")
    rgb_at(f, 852, 902, 240, 480, "弹窗内部均色")


if __name__ == "__main__":
    main()
