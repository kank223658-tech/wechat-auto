# -*- coding: utf-8 -*-
"""两视频版面对齐测量：任一视频任一时刻，输出
  1) 实际分辨率
  2) 全页行带结构（亮度带 + 均色，找导航/封面/帖子/深灰条/输入条/键盘分界）
  3) 关键色 bbox（微信绿 / 蓝系文字 / 深灰面板 #1d1d1d 档 / 中灰面板 #4f4f4f~#555 档）
  4) 参考视频坐标自动换算到 600 宽 CSS 空间（×600/W）
用法：py _cmp_layout.py <video> t1 t2 t3 ...
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

_seq = [0]


def grab(vid, tsec):
    _seq[0] += 1
    png = os.path.join(OUT, "cmp_%03d.png" % _seq[0])
    subprocess.run([FF, "-y", "-ss", "%.3f" % tsec, "-i", vid, "-frames:v", "1", png],
                   capture_output=True)
    raw = subprocess.run([FF, "-y", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    with open(png, "rb") as f:
        head = f.read(33)
    w, h = struct.unpack(">II", head[16:24])
    arr = np.frombuffer(raw[: w * h * 3], dtype=np.uint8)
    return arr.reshape(h, w, 3)


def row_bands(f, min_h=6):
    """把整页按行均色切成亮度带，输出 (y0,y1,均RGB)。"""
    g = f.astype(np.int32)
    rm = g[:, :, 0].mean(axis=1)
    gm = g[:, :, 1].mean(axis=1)
    bm = g[:, :, 2].mean(axis=1)
    lum = (rm * 299 + gm * 587 + bm * 114) // 1000
    bands = []
    y0 = 0
    for y in range(1, f.shape[0]):
        if abs(int(lum[y]) - int(lum[y - 1])) > 14:
            if y - y0 >= min_h:
                bands.append((y0, y, rm[y0:y].mean(), gm[y0:y].mean(), bm[y0:y].mean()))
            y0 = y
    if f.shape[0] - y0 >= min_h:
        y = f.shape[0]
        bands.append((y0, y, rm[y0:y].mean(), gm[y0:y].mean(), bm[y0:y].mean()))
    # 合并均色相近的相邻带（<10 亮度差）
    merged = []
    for b in bands:
        if merged and abs(b[2] * 299 + b[3] * 587 + b[4] * 114
                          - (merged[-1][2] * 299 + merged[-1][3] * 587 + merged[-1][4] * 114)) / 1000 < 10:
            p = merged[-1]
            merged[-1] = (p[0], b[1],
                          (p[2] + b[2]) / 2, (p[3] + b[3]) / 2, (p[4] + b[4]) / 2)
        else:
            merged.append(b)
    return merged


def masks(f):
    r = f[:, :, 0].astype(np.int32)
    g = f[:, :, 1].astype(np.int32)
    b = f[:, :, 2].astype(np.int32)
    lum = (r * 299 + g * 587 + b * 114) // 1000
    sat = np.max(f, axis=2).astype(np.int32) - np.min(f, axis=2).astype(np.int32)
    out = {}
    out["green"] = (g > r + 40) & (g > b + 20) & (g > 110)
    out["blue"] = (b > r + 22) & (b > 80) & (lum < 200)
    out["darkpanel"] = (lum >= 20) & (lum <= 40) & (sat < 14)
    out["midpanel"] = (lum >= 60) & (lum <= 100) & (sat < 14)
    return out


def bbox_rows(mask):
    """mask 按行统计，返回覆盖率>2% 的行区间列表。"""
    rowcov = mask.mean(axis=1)
    ys = np.where(rowcov > 0.02)[0]
    if len(ys) == 0:
        return "无"
    segs = []
    y0 = ys[0]
    prev = ys[0]
    for y in ys[1:]:
        if y - prev > 8:
            segs.append((y0, prev))
            y0 = y
        prev = y
    segs.append((y0, prev))
    return segs


def seg_str(segs, sx):
    if segs == "无":
        return "无"
    return " ".join("%d-%d" % (int(a * sx), int(b * sx)) for a, b in segs)


def main():
    vid = sys.argv[1]
    ts = [float(x) for x in sys.argv[2:]]
    for t in ts:
        f = grab(vid, t)
        H, W = f.shape[:2]
        sx = 600.0 / W
        print("=" * 72)
        print("t=%.2f  实际 %dx%d  (CSS=×%.4f → %dx%d)" % (t, W, H, sx, int(W * sx), int(H * sx)))
        print("-- 行带结构 (CSS y: 均RGB) --")
        for (y0, y1, r, g, b) in row_bands(f):
            print("  %4d-%4d  RGB(%3.0f,%3.0f,%3.0f)" % (y0 * sx, y1 * sx, r, g, b))
        mk = masks(f)
        print("-- 关键色行区间 (CSS y) --")
        print("  微信绿  :", seg_str(bbox_rows(mk["green"]), sx))
        print("  蓝系文字:", seg_str(bbox_rows(mk["blue"]), sx))
        print("  深灰面板:", seg_str(bbox_rows(mk["darkpanel"]), sx))
        print("  中灰面板:", seg_str(bbox_rows(mk["midpanel"]), sx))
        for name in ("green", "blue", "darkpanel", "midpanel"):
            m = mk[name]
            if m.any():
                ys, xs = np.where(m)
                print("    %s bbox CSS: x %d-%d  y %d-%d  px=%d" % (
                    name, xs.min() * sx, xs.max() * sx, ys.min() * sx, ys.max() * sx, m.sum()))


if __name__ == "__main__":
    main()
