# -*- coding: utf-8 -*-
"""扫描视频中的「渐变段」（fade 特征：连续 >=8 帧微小变化），用于验证 GAP_BLEND 修复。
用法: py _scan_fades.py <video1> [video2 ...]
"""
import subprocess
import imageio_ffmpeg
import os
import re
import sys
import json
import numpy as np
from PIL import Image

ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()


def scan(vid):
    os.makedirs("_fadechk", exist_ok=True)
    for f in os.listdir("_fadechk"):
        os.remove(os.path.join("_fadechk", f))
    # 一遍拿到帧图 + showinfo 的 pts_time
    proc = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "info", "-i", vid,
         "-vf", "showinfo", "_fadechk/f%04d.jpg"],
        capture_output=True, text=True)
    times = [float(m) for m in
             re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
    files = sorted(f for f in os.listdir("_fadechk") if f.endswith(".jpg"))
    n = min(len(times), len(files))
    prev = None
    rows = []
    for i in range(n):
        im = Image.open(f"_fadechk/{files[i]}").convert("L").resize((40, 86))
        a = np.asarray(im, dtype=np.float32)
        if prev is not None:
            rows.append((times[i], float(np.abs(a - prev).mean()) / 255.0))
        prev = a
    runs = []
    cur = []
    for t, d in rows:
        if 0.0003 < d < 0.05:
            cur.append((t, d))
        else:
            if len(cur) >= 8:
                runs.append(cur)
            cur = []
    if len(cur) >= 8:
        runs.append(cur)
    print(f"{vid}  ({len(files)}帧, 末帧 {times[-1] if times else -1:.2f}s)")
    if not runs:
        print("  无渐变段")
    for r in runs:
        print(f"  fade? {r[0][0]:.2f}s -> {r[-1][0]:.2f}s "
              f"({len(r)}帧, 峰值diff={max(d for _, d in r):.4f})")


if __name__ == "__main__":
    for v in sys.argv[1:]:
        scan(v)
