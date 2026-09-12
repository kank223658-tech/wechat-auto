# -*- coding: utf-8 -*-
"""对方主页逐元素数值审计：颜色(前3%均值) + 墨迹bbox高度(字号) + 位置。"""
import os
import numpy as np
from PIL import Image

BASE = r"G:\weixin-auto\_cmp_ref_home"
REF = os.path.join(BASE, "ref.png")
OURS = os.path.join(BASE, "ours.png")


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int32)


def win(a, x0, y0, x1, y1):
    return a[y0:y1, x0:x1]


def color3(a, x0, y0, x1, y1, frac=.03):
    seg = win(a, x0, y0, x1, y1).reshape(-1, 3)
    L = seg[:, 0] * .299 + seg[:, 1] * .587 + seg[:, 2] * .114
    # 贴合：只取有墨的列范围
    o = np.argsort(L)
    n = max(12, int(len(L) * frac))
    c = seg[o[-n:]].mean(axis=0)
    return [int(round(v)) for v in c]


def ink(a, x0, y0, x1, y1, thr=70):
    seg = win(a, x0, y0, x1, y1)
    L = seg[:, :, 0] * .299 + seg[:, :, 1] * .587 + seg[:, :, 2] * .114
    mask = L > thr
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    return (x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max(),
            int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1))


ra, na = load(REF), load(OURS)

# 窗口: (名称, x0,y0,x1,y1, 是文字色窗口还是bbox窗口)
ITEMS = [
    ("返回箭头",   20, 96, 60, 134),
    ("更多点",    540, 100, 590, 130),
    ("名字 月亮",  138, 186, 300, 230),
    ("昵称行",    138, 232, 420, 266),
    ("微信号行",   138, 266, 420, 300),
    ("朋友资料",   16, 370, 130, 400),
    ("desc行1",   16, 410, 575, 436),
    ("朋友圈title", 16, 520, 130, 570),
    ("发消息",    280, 658, 370, 692),
    ("音视频通话", 260, 744, 430, 778),
]

print("=== 颜色（亮度前3%均值） ===")
for name, x0, y0, x1, y1 in ITEMS:
    rc = color3(ra, x0, y0, x1, y1)
    nc = color3(na, x0, y0, x1, y1)
    rl = rc[0] * .299 + rc[1] * .587 + rc[2] * .114
    nl = nc[0] * .299 + nc[1] * .587 + nc[2] * .114
    d = nl - rl
    flag = "OK  " if abs(d) <= 10 else ("偏白" if d > 0 else "偏暗")
    print("%s %-9s ref #%02x%02x%02x L=%3.0f | ours #%02x%02x%02x L=%3.0f | dL=%+3.0f" % (
        flag, name, rc[0], rc[1], rc[2], rl, nc[0], nc[1], nc[2], nl, d))

print("\n=== 墨迹bbox (x0,y0,x1,y1,h,w) ===")
for name, x0, y0, x1, y1 in ITEMS:
    r = ink(ra, x0, y0, x1, y1)
    n = ink(na, x0, y0, x1, y1)
    def fmt(b):
        return ("none" if b is None else
                "(%d,%d)-(%d,%d) h=%d w=%d" % (b[0], b[1], b[2], b[3], b[4], b[5]))
    print("%-9s REF %s\n          OURS %s" % (name, fmt(r), fmt(n)))

print("\n=== 底色定点采样 ===")
PTS = [
    ("页面顶部bg", 300, 160),
    ("head区bg", 450, 240),
    ("朋友资料cell bg", 450, 385),
    ("朋友圈cell bg", 300, 530),
    ("actions区bg", 300, 700),
    ("页面底部bg", 300, 1000),
    ("cell间分隔", 300, 470),
]
for name, x, y in PTS:
    r = ra[y, x]
    n = na[y, x]
    print("%-12s y=%4d ref #%02x%02x%02x | ours #%02x%02x%02x" % (
        name, y, r[0], r[1], r[2], n[0], n[1], n[2]))

print("\n=== 头像bbox（亮区） ===")
print("REF ", ink(ra, 10, 170, 140, 320, thr=45))
print("OURS", ink(na, 10, 170, 140, 320, thr=45))
print("\n=== 朋友圈缩略图行bbox ===")
print("REF ", ink(ra, 120, 500, 560, 620, thr=45))
print("OURS", ink(na, 120, 500, 560, 620, thr=45))
