# -*- coding: utf-8 -*-
"""行带扫描比对：在整屏范围内自动找出所有文字行带（y 范围 + 高度 + 颜色），
参考帧与渲染帧各扫一遍，并排打印，用于确认「位置 + 亮度」两个维度是否对齐。

用法: py _band_cmp.py <ref帧相对_ref_tf2的路径> <渲染图路径> [x0] [x1]
"""
import sys
import numpy as np
from PIL import Image

BASE = r"G:\weixin-auto\_ref_tf2"


def load(path):
    im = Image.open(path).convert("RGB")
    if im.size != (600, 1300):
        im = im.resize((600, 1300), Image.LANCZOS)
    return np.asarray(im).astype(np.int32)


def scan(a, x0, x1, thr=34, lo=60, hi=1290, gap=3, minh=5):
    L = (a[:, :, 0] * .299 + a[:, :, 1] * .587 + a[:, :, 2] * .114)
    sub = L[lo:hi, x0:x1]
    bg = np.median(sub)
    # 用每行 98 分位（而非均值）——面板文字居中且短，行均值会被背景稀释
    rows = np.percentile(sub, 98, axis=1)
    m = rows > bg + thr
    bands = []
    y = 0
    n = len(m)
    while y < n:
        if m[y]:
            y2 = y
            miss = 0
            k = y
            while k < n:
                if m[k]:
                    y2 = k
                    miss = 0
                else:
                    miss += 1
                    if miss > gap:
                        break
                k += 1
            if y2 - y + 1 >= minh:
                ys, ye = y + lo, y2 + lo
                seg = a[ys:ye + 1, x0:x1].reshape(-1, 3)
                Ls = seg[:, 0] * .299 + seg[:, 1] * .587 + seg[:, 2] * .114
                order = np.argsort(Ls)
                nn = max(20, int(len(Ls) * .10))
                col = seg[order[-nn:]].mean(axis=0).astype(int)
                bands.append((ys, ye, ye - ys + 1, tuple(col), float(Ls.max())))
            y = y2 + 1
        else:
            y += 1
    return bands, bg


def show(tag, bands, bg):
    print("  [%s] bg=%.0f  行带数=%d" % (tag, bg, len(bands)))
    for (y0, y1, h, col, mx) in bands:
        Lv = col[0] * .299 + col[1] * .587 + col[2] * .114
        print("      y%4d-%4d h%-3d  #%02x%02x%02x  L=%3.0f  max=%.0f" % (
            y0, y1, h, col[0], col[1], col[2], Lv, mx))


ref = sys.argv[1]
rec = sys.argv[2]
x0 = int(sys.argv[3]) if len(sys.argv) > 3 else 24
x1 = int(sys.argv[4]) if len(sys.argv) > 4 else 576

ra = load(BASE + "\\" + ref)
na = load(rec)
print("=== ref %s ===" % ref)
show("ref", *scan(ra, x0, x1))
print("=== rec %s ===" % rec)
show("rec", *scan(na, x0, x1))
