# -*- coding: utf-8 -*-
"""从视频帧反推朋友圈滚动的逐帧轨迹，定位「淡入淡出 / 闪回原处」。

方法：
1) 解码为 270x585 灰度帧（半分辨率，1px=真实2px）。
2) 逐对相邻帧估计纵向位移 dy（±80 半分辨率px 搜索），累加得滚动轨迹。
3) 残差 = 最优 dy 下的平均差。真实滚动的帧残差低；交叉混合帧（GAP_BLEND）
   或陈旧闪回帧用任何单一 dy 都解释不好 → 残差高。
4) 输出：每个事件簇的时间、dy、残差；「倒退」= 轨迹反向 >30(半分辨率px)。
用法：py _check_scrollfx.py [video]
"""
import os
import subprocess
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VID = sys.argv[1] if len(sys.argv) > 1 else r"G:/weixin-auto/videos/wx_20260911_023800_683.mp4"
FF = (r"C:/Users/mik/AppData/Local/Programs/Python/Python314"
      r"/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe")
W, H = 270, 585
FPS = 60.0
SEARCH = 80


def load_gray(path):
    cmd = [FF, "-i", path, "-f", "rawvideo", "-pix_fmt", "gray",
           "-vf", "scale=%d:%d" % (W, H), "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[: n * W * H], dtype=np.uint8).reshape(n, H, W)


def best_dy(a, b):
    """b 相对 a 的纵向位移（b 内容下移 dy 表示 view 向上滚）。返回 (dy, diff)。
    在 [-SEARCH, SEARCH] 内整数搜索；比较重叠区平均绝对差。"""
    best = (0, 1e9)
    for dy in range(-SEARCH, SEARCH + 1):
        if dy >= 0:
            aa = a[dy:, :]
            bb = b[: H - dy, :]
        else:
            aa = a[: H + dy, :]
            bb = b[-dy:, :]
        d = float(np.abs(aa.astype(np.int16) - bb.astype(np.int16)).mean())
        if d < best[1]:
            best = (dy, d)
    return best


def main():
    frames = load_gray(VID)
    n = len(frames)
    print("视频:", os.path.basename(VID))
    print("帧数: %d (%.2fs)  半分辨率 %dx%d" % (n, n / FPS, W, H))

    d = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16)
               ).mean(axis=(1, 2))

    i16 = frames.astype(np.int16)
    cum = np.zeros(n, dtype=np.float64)
    resid = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if d[i - 1] < 0.05:          # 完全静止，跳过搜索
            cum[i] = cum[i - 1]
            resid[i] = 0.0
            continue
        dy, dd = best_dy(i16[i - 1], i16[i])
        cum[i] = cum[i - 1] + dy
        resid[i] = dd

    # ---- 事件簇 ----
    active = d > 0.8
    groups = []
    i = 0
    while i < len(active):
        if active[i]:
            j = i
            while j + 1 < len(active) and active[j + 1]:
                j += 1
            groups.append((i, j))
            i = j + 1
        else:
            i += 1

    print("\n== 活动簇（d>0.8）==")
    for g0, g1 in groups:
        dur = g1 - g0 + 1
        dmax = float(d[g0:g1 + 1].max())
        dmed = float(np.median(d[g0:g1 + 1]))
        rmed = float(np.median(resid[g0 + 1:g1 + 1])) if g1 > g0 else 0.0
        dy0, dy1 = float(cum[g0]), float(cum[g1])
        kind = []
        if dur <= 3:
            kind.append("硬切")
        if dmed > 1.0 and dur >= 6:
            kind.append("渐变坡?")
        if rmed > 2.0:
            kind.append("高残差(混合/闪帧?)")
        if dy1 - dy0 < -40:
            kind.append("倒退↑↑")
        elif dy1 - dy0 > 40:
            kind.append("前进↓↓(滚动)")
        print("  帧%4d-%4d t=%6.2f-%6.2fs 宽%3d d峰%5.1f d中%5.1f 残差%5.1f dy %+7.1f→%+7.1f  %s" % (
            g0, g1, g0 / FPS, g1 / FPS, dur, dmax, dmed, rmed, dy0, dy1,
            "+".join(kind) if kind else ""))

    # ---- 轨迹采样（每 0.1s 一行，只在有变化的时段）----
    print("\n== 轨迹（每0.1s，cum_dy=半分辨率px，正值=内容上移/视图下滚）==")
    step = 6
    prev = None
    for i in range(0, n, step):
        cur = (round(float(cum[i])), round(float(d[max(0, i - 1):i + 1].mean()), 2))
        if prev is not None and cur[0] == prev[0] and d[max(0, i - 1):i + 1].max() < 0.8:
            prev = cur
            continue
        print("  t=%6.2fs cum_dy=%+7.1f d=%5.2f resid=%5.2f" % (
            i / FPS, cum[i], d[max(0, i - 1):i + 1].mean(), resid[i]))
        prev = cur


if __name__ == "__main__":
    main()
