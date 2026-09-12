# -*- coding: utf-8 -*-
"""参考 vs 渲染：行带扫描 + 放大裁剪并排图。"""
import os
import numpy as np
from PIL import Image

BASE = r"G:\weixin-auto\_cmp_ref_home"
REF = os.path.join(BASE, "ref.png")
OURS = os.path.join(BASE, "ours.png")

# 1) 参考图统一缩到 600x1300
src = Image.open(r"G:\weixin-auto\参考图片\对方的个人主页.png").convert("RGB")
src.resize((600, 1300), Image.LANCZOS).save(REF)
print("ref resized:", src.size, "-> (600,1300)")


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int32)


def bands(a, x0=14, x1=586, y0=90, y1=900, thr=None):
    """在整屏范围找文字行带：每行有墨(>thr)像素数，聚成带。"""
    seg = a[y0:y1, x0:x1]
    L = seg[:, :, 0] * .299 + seg[:, :, 1] * .587 + seg[:, :, 2] * .114
    if thr is None:
        thr = 60
    ink = (L > thr).sum(axis=1)
    out = []
    y = 0
    H = len(ink)
    while y < H:
        if ink[y] > 2:
            s = y
            while y < H and ink[y] > 0:
                y += 1
            rows = L[s:y]
            bright = rows[rows > thr]
            out.append((y0 + s, y0 + y, int(bright.mean()) if len(bright) else 0))
        else:
            y += 1
    return out


ra, na = load(REF), load(OURS)
print("\n=== 行带扫描 (y起, y止, 带内亮度均值) ===")
rb = bands(ra)
nb = bands(na)
print("REF:")
for b in rb:
    print("   ", b)
print("OURS:")
for b in nb:
    print("   ", b)

# 2) 放大裁剪并排图
CROPS = [
    ("nav",      0, 90, 600, 150),     # 导航栏
    ("head",     0, 150, 600, 320),    # 头像+名字+昵称/微信号
    ("friend",   0, 355, 600, 480),    # 朋友资料
    ("moments",  0, 490, 600, 620),    # 朋友圈
    ("actions",  0, 620, 600, 820),    # 发消息/音视频通话
]
Z = 2
for name, x0, y0, x1, y1 in CROPS:
    rc = Image.open(REF).crop((x0, y0, x1, y1))
    nc = Image.open(OURS).crop((x0, y0, x1, y1))
    w, h = rc.size
    sheet = Image.new("RGB", (w * Z, h * 2 * Z + 8), (255, 0, 0))
    sheet.paste(rc.resize((w * Z, h * Z), Image.LANCZOS), (0, 0))
    sheet.paste(nc.resize((w * Z, h * Z), Image.LANCZOS), (0, h * Z + 8))
    sheet.save(os.path.join(BASE, "cmp_%s.png" % name))
print("\ncrops saved")
