# -*- coding: utf-8 -*-
"""验证新视频的「关图幽灵」修复效果。

检查项：
1) 每次「点开图片」循环：开图前稳定帧 vs 关图后稳定帧，全画幅(1080x2340)逐像素
   对比 —— 修复前 tile3 区域 12,090 个 >30 差异像素（幽灵残留），修复后应≈0。
2) 静止期突发跳变（幽灵中途弹现/重绘）：所有 d>2.0 的帧簇按时间列出，
   出现在「关图稳态后～下一动作前」这类静止窗口里的就是闪帧。
3) Tab 切换 / 闪回：硬切应仍为单帧簇。
"""
import os
import re
import subprocess
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VID_DIR = r"G:/weixin-auto/videos"
FF = (r"C:/Users/mik/AppData/Local/Programs/Python/Python314"
      r"/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe")
OUT = r"G:/weixin-auto/_fs"
os.makedirs(OUT, exist_ok=True)

SW, SH = 96, 208          # 缩略灰度尺寸（保持 1080x2340 比例）
FPS = 60.0                # 合流后的 CFR 帧率


def newest_video():
    vids = [os.path.join(VID_DIR, f) for f in os.listdir(VID_DIR)
            if f.endswith(".mp4")]
    vids.sort(key=os.path.getmtime)
    return vids[-1]


def load_small(path):
    cmd = [FF, "-i", path, "-f", "rawvideo", "-pix_fmt", "gray",
           "-vf", "scale=%d:%d" % (SW, SH), "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (SW * SH)
    return np.frombuffer(raw[: n * SW * SH], dtype=np.uint8).reshape(n, SH, SW)


def load_full_frames(path, idxs, tag):
    """按帧号精确抽取原尺寸帧，返回 {idx: array}"""
    idxs = sorted(set(int(i) for i in idxs))
    expr = "+".join("eq(n,%d)" % i for i in idxs)
    pat = os.path.join(OUT, "g2_%s_%%d.png" % tag)
    for f in os.listdir(OUT):
        if f.startswith("g2_%s_" % tag):
            os.remove(os.path.join(OUT, f))
    cmd = [FF, "-i", path, "-vf", "select='%s'" % expr, "-vsync", "0", pat]
    subprocess.run(cmd, capture_output=True)
    files = sorted([f for f in os.listdir(OUT) if f.startswith("g2_%s_" % tag)],
                   key=lambda s: int(re.search(r"_(\d+)\.png$", s).group(1)))
    frames = {}
    for i, f in zip(idxs, files):
        cmd2 = [FF, "-i", os.path.join(OUT, f), "-f", "rawvideo", "-pix_fmt",
                "rgb24", "-"]
        raw = subprocess.run(cmd2, capture_output=True).stdout
        frames[i] = np.frombuffer(raw, dtype=np.uint8).reshape(2340, 1080, 3)
    return frames


def diff_report(a, b, label):
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    n30 = int((d > 30).sum())
    n15 = int((d > 15).sum())
    print("  [%s] >30:%d  >15:%d  max:%d" % (label, n30, n15, int(d.max())))
    try:
        from scipy import ndimage
        mask = d > 30
        if mask.any():
            lab, num = ndimage.label(mask)
            sizes = ndimage.sum(mask, lab, range(1, num + 1))
            order = np.argsort(sizes)[::-1][:3]
            for k in order:
                ys, xs = np.where(lab == k + 1)
                print("    区块 %dx%d @ x %d-%d, y %d-%d" % (
                    sizes[k], len(xs), xs.min(), xs.max(), ys.min(), ys.max()))
    except ImportError:
        pass
    return n30


def main():
    vid = newest_video()
    print("视频:", os.path.basename(vid))
    frames = load_small(vid)
    n = len(frames)
    print("缩略帧数: %d  (%.2fs)" % (n, n / FPS))

    d = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16)
               ).mean(axis=(1, 2))

    # ---- 帧簇划分：连续 d>1.0 归为一簇 ----
    active = d > 1.0
    groups = []
    i = 0
    while i < len(active):
        if active[i]:
            j = i
            while j + 1 < len(active) and active[j + 1]:
                j += 1
            groups.append((i, j, float(d[i:j + 1].max())))
            i = j + 1
        else:
            i += 1

    print("\n== 事件簇（>2.0）==")
    for g0, g1, gmax in groups:
        if gmax < 2.0:
            continue
        dur = (g1 - g0 + 1)
        kind = "切换?" if dur <= 3 else ("动作" if gmax < 20 else "大切换")
        print("  帧 %4d-%4d  t=%.2f-%.2fs  簇宽%2d  峰值%5.1f  %s" % (
            g0, g1, g0 / FPS, g1 / FPS, dur, gmax, kind))

    # ---- 配对「点开图片」循环：大切换峰（淡出摊帧后峰值 15-25），间隔 1.2~2.2s，中间静止 ----
    big = [(g0, g1) for g0, g1, m in groups if m >= 12]
    pairs = []
    for a, b in zip(big, big[1:]):
        gap = (b[0] - a[0]) / FPS
        if not (1.2 <= gap <= 2.2):
            continue
        quiet = d[a[1] + 1: b[0]]
        if len(quiet) and quiet.max() < 1.0:   # 停留期间画面完全静止
            pairs.append((a[0], a[1], b[0], b[1]))
    print("\n== 点开图片循环配对 ==  %s" %
          [("帧%d→%d" % (p[0], p[2])) for p in pairs])

    need = []
    for k, (o0, o1, c0, c1) in enumerate(pairs):
        # 开图前帧：开图峰起始前 0.12s
        pre = max(0, o0 - 8)
        # 关图后稳态帧：从关图峰尾+3 起向后找连续静止段的最后一帧
        j = c1 + 3
        while j + 1 < n - 1 and d[j] < 1.2 and d[j + 1] < 1.2:
            j += 1
        post = j
        need += [pre, post]
        print("  循环%d: 开图帧%d(%.2fs)  关图帧%d-%d  "
              "对比帧: 开前%d vs 关后%d(关图尾后%.2fs)" % (
                  k + 1, o0, o0 / FPS, c0, c1, pre, post,
                  (post - c1) / FPS))

    if pairs:
        fmap = load_full_frames(vid, need, "cmp")
        print("\n== 开图前 vs 关图后（全画幅 1080x2340）==")
        for k, (o0, o1, c0, c1) in enumerate(pairs):
            pre = max(0, o0 - 8)
            j = c1 + 3
            while j + 1 < n - 1 and d[j] < 1.2 and d[j + 1] < 1.2:
                j += 1
            diff_report(fmap[pre], fmap[j], "循环%d" % (k + 1))
        # 出对比图
        from PIL import Image
        for k, (o0, o1, c0, c1) in enumerate(pairs):
            pre = max(0, o0 - 8)
            j = c1 + 3
            while j + 1 < n - 1 and d[j] < 1.2 and d[j + 1] < 1.2:
                j += 1
            a = Image.fromarray(fmap[pre]).resize((270, 585))
            b = Image.fromarray(fmap[j]).resize((270, 585))
            canvas = Image.new("RGB", (552, 585), "#222")
            canvas.paste(a, (0, 0))
            canvas.paste(b, (282, 0))
            canvas.save(os.path.join(OUT, "g2_pair%d.png" % (k + 1)))

    # ---- 关图瞬间的胶片条（目检幽灵）----
    try:
        from PIL import Image
        for k, (o0, o1, c0, c1) in enumerate(pairs):
            sel = list(range(max(0, c0 - 6), min(n - 1, c1 + 34), 3))
            fmap2 = load_full_frames(vid, sel, "strip%d" % (k + 1))
            tiles = [Image.fromarray(fmap2[i]).resize((180, 390))
                     for i in sel if i in fmap2]
            if tiles:
                canvas = Image.new("RGB", (186 * len(tiles), 396), "#111")
                for t, tx in zip(tiles, tiles.__iter__()):
                    pass
                x = 0
                for t in tiles:
                    canvas.paste(t, (x, 3))
                    x += 186
                canvas.save(os.path.join(OUT, "g2_closestrip%d.png" % (k + 1)))
    except ImportError:
        pass

    print("\n完成。对比图/胶片条在 _fs/g2_*.png")


if __name__ == "__main__":
    main()
