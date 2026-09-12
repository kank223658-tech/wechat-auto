# -*- coding: utf-8 -*-
"""生成「参考帧 | 渲染帧」对照图（左=参考视频帧，右=本机渲染），供人工目视验收。"""
import numpy as np
from PIL import Image, ImageDraw

BASE = r"G:\weixin-auto\_ref_tf2"
ROOT = r"G:\weixin-auto"
S = 0.62          # 缩放
GAP = 14
PAIRS = [
    ("转账金额页",   r"B\b_012.png", "_ph_filled.png"),
    ("付款面板",     r"B\b_021.png", "_ph_sheet.png"),
    ("支付成功页",   r"B\b_027.png", "_ph_success.png"),
    ("详情页·待收款", r"A\a_006.png", "_tfd_wait.png"),
    ("详情页·已收款", r"A\a_016.png", "_tfd_done.png"),
]


def load(p):
    im = Image.open(p).convert("RGB")
    if im.size != (600, 1300):
        im = im.resize((600, 1300), Image.LANCZOS)
    return im


sheet = None
tiles = []
for name, rf, nf in PAIRS:
    r = load(BASE + "\\" + rf)
    n = load(ROOT + "\\" + nf)
    w = int(600 * S)
    h = int(1300 * S)
    pair = Image.new("RGB", (w * 2 + GAP, h), (18, 18, 18))
    pair.paste(r.resize((w, h), Image.LANCZOS), (0, 0))
    pair.paste(n.resize((w, h), Image.LANCZOS), (w + GAP, 0))
    d = ImageDraw.Draw(pair)
    d.text((6, 4), "REF", fill=(0, 220, 120))
    d.text((w + GAP + 6, 4), "OURS", fill=(255, 190, 60))
    tiles.append((name, pair))

    pair.save(ROOT + "\\_ver_" + nf.replace("_", "").replace(".png", "") + ".png")

# 总览（横向 5 组）
tw = max(t[1].width for t in tiles)
th = sum(t[1].height for t in tiles) + GAP * (len(tiles) - 1) + 0
sheet = Image.new("RGB", (tw, th), (18, 18, 18))
y = 0
for name, t in tiles:
    sheet.paste(t, (0, y))
    y += t.height + GAP
sheet.save(ROOT + "\\_ver_sheet.png")
print("DONE", sheet.size)
