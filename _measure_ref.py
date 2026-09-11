# -*- coding: utf-8 -*-
"""参考视频精确测量：各元素 bbox（raw 592x1280 → CSS ×1.0135）。
用法：py _measure_ref.py"""
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
    png = r"G:/weixin-auto/_fs/_mr_tmp.png"
    subprocess.run([FF, "-y", "-ss", "%.3f" % tsec, "-i", VID, "-frames:v", "1", png],
                   capture_output=True)
    raw = subprocess.run([FF, "-y", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def bbox(f, y0, y1, x0, x1, thr=None, darker=None, label="", sx=600.0 / 592.0):
    """区域内满足条件的像素 bbox。thr=亮度下限(亮元素)；darker=亮度上限。"""
    r = f[y0:y1, x0:x1]
    lum = r.astype(np.int32).mean(axis=2)
    if thr is not None:
        m = lum > thr
    elif darker is not None:
        m = lum < darker
    else:
        m = np.ones_like(lum, dtype=bool)
    if not m.any():
        print("  [%s] 无" % label)
        return None
    ys, xs = np.where(m)
    print("  [%s] raw x%d-%d y%d-%d | CSS x%.0f-%.0f y%.0f-%.0f  (w%.0f h%.0f) px=%d" % (
        label, x0 + xs.min(), x0 + xs.max(), y0 + ys.min(), y0 + ys.max(),
        (x0 + xs.min()) * sx, (x0 + xs.max()) * sx, (y0 + ys.min()) * sx, (y0 + ys.max()) * sx,
        (xs.max() - xs.min()) * sx, (ys.max() - ys.min()) * sx, m.sum()))
    return (x0 + xs.min(), x0 + xs.max(), y0 + ys.min(), y0 + ys.max())


def col_runs(f, y0, y1, x0, x1, thr, min_run=20):
    """列均值>thr 的连续列段（找并排图块的横向边界）。"""
    g = f[y0:y1, x0:x1].astype(np.int32).mean(axis=(0, 2))
    on = g > thr
    runs = []
    s = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_run:
                runs.append((x0 + s, x0 + i))
            s = None
    if s is not None and len(on) - s >= min_run:
        runs.append((x0 + s, x0 + len(on)))
    return runs


def row_runs(f, y0, y1, x0, x1, thr, min_run=20):
    g = f[y0:y1, x0:x1].astype(np.int32).mean(axis=(1, 2))
    on = g > thr
    runs = []
    s = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_run:
                runs.append((y0 + s, y0 + i))
            s = None
    if s is not None and len(on) - s >= min_run:
        runs.append((y0 + s, y0 + len(on)))
    return runs


def mean_rgb(f, y0, y1, x0, x1, label):
    r = f[y0:y1, x0:x1].astype(np.int32)
    m = r.mean(axis=(0, 1))
    print("  [%s] 均RGB=(%.0f,%.0f,%.0f)" % (label, m[0], m[1], m[2]))


def main():
    sx = 600.0 / 592.0
    print("========== t=0.5 初始页 ==========")
    f = grab(0.5)
    print("-- 封面底部（头像/昵称）--")
    bbox(f, 480, 640, 250, 592, thr=150, label="封面底部亮元素(昵称/头像)")
    bbox(f, 480, 640, 250, 592, thr=180, label="  其中很亮(纯白昵称)")
    print("-- 帖1 头像 --")
    bbox(f, 620, 740, 15, 130, thr=60, label="帖1头像纹理")
    print("-- 帖1 文本（右侧列）--")
    bbox(f, 620, 730, 130, 400, thr=95, label="帖1文本亮字")
    print("-- 帖1 图片行 --")
    rr = row_runs(f, 700, 900, 120, 400, 45)
    print("  行段:", [("raw%d-%d" % r) for r in rr])
    cr = col_runs(f, 735, 845, 60, 500, 45)
    print("  列段:", [("raw%d-%d" % c) for c in cr])
    print("-- 帖1 时间+胶囊行 --")
    bbox(f, 855, 905, 95, 300, thr=70, label="时间文字")
    bbox(f, 850, 910, 460, 580, thr=28, darker=None, label="胶囊区(>28)")
    mean_rgb(f, 862, 894, 510, 552, "胶囊内部均色")
    print("-- 帖2 头像+文本 --")
    bbox(f, 915, 1015, 15, 130, thr=60, label="帖2头像纹理")
    bbox(f, 915, 1015, 130, 450, thr=95, label="帖2文本亮字")
    print("-- 帖2 大灰图 --")
    rr = row_runs(f, 1000, 1280, 130, 400, 40)
    print("  行段:", [("raw%d-%d" % r) for r in rr])
    cr = col_runs(f, 1060, 1260, 60, 592, 40)
    print("  列段:", [("raw%d-%d" % c) for c in cr])
    mean_rgb(f, 1080, 1250, 140, 340, "大灰图内部均色")

    print("========== t=10.0 键盘+输入条 ==========")
    f = grab(10.0)
    print("-- 输入条（键盘上方）--")
    rr = row_runs(f, 700, 850, 20, 560, 60, min_run=10)
    print("  亮行段(>60):", [("raw%d-%d" % r) for r in rr])
    for (a, b) in rr:
        mean_rgb(f, a, b, 20, 560, "行段%d-%d均色" % (a, b))
    print("-- 键盘键行 --")
    rr = row_runs(f, 830, 1280, 20, 560, 60, min_run=15)
    print("  键行段:", [("raw%d-%d" % r) for r in rr])
    cr = col_runs(f, 870, 1160, 0, 592, 60, min_run=10)
    print("  键列段(前12):", [("raw%d-%d" % c) for c in cr[:12]])
    mean_rgb(f, 1180, 1270, 20, 560, "键盘底部区均色")
    mean_rgb(f, 845, 865, 20, 560, "候选/工具条均色")

    print("========== t=13.8 结尾态（评论已上屏） ==========")
    f = grab(13.8)
    print("-- 深灰条（moment-meta）--")
    rr = row_runs(f, 500, 800, 130, 500, 27, min_run=10)
    print("  >27 行段:", [("raw%d-%d" % r) for r in rr])
    cr = col_runs(f, 505, 760, 60, 592, 27, min_run=30)
    print("  >27 列段:", [("raw%d-%d" % c) for c in cr])
    bbox(f, 500, 800, 130, 500, thr=95, label="条内亮文本")
    bbox(f, 500, 800, 130, 500, thr=100, label="条内蓝名(更严格见下)")

    print("========== 弹窗时刻扫描 ==========")
    for t in [5.0, 5.2, 5.4, 5.6, 5.8, 6.0]:
        f = grab(t)
        # 弹窗: 胶囊左侧一条 RGB~85 的横带
        g = f[840:940, 200:470].astype(np.int32).mean(axis=2)
        m = (g > 70) & (g < 100)
        if m.sum() > 2000:
            ys, xs = np.where(m)
            print("  t=%.1f 弹窗候选 raw x%d-%d y%d-%d px=%d" % (
                t, 200 + xs.min(), 200 + xs.max(), 840 + ys.min(), 840 + ys.max(), m.sum()))
        else:
            print("  t=%.1f 无弹窗 (px=%d)" % (t, m.sum()))


if __name__ == "__main__":
    main()
