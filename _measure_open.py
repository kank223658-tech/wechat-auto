# -*- coding: utf-8 -*-
"""精测开图动画：逐帧检测全屏白卡片包围盒，对比缩略图真实位置。
判定 zoom 起点是否落在被点缩略图上，还是「凭空淡入」。
"""
import subprocess

import numpy as np
from PIL import Image

VID = r"videos/wx_20260911_005559_732.mp4"
FF = r"C:\Users\mik\AppData\Local\Programs\Python\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"

def grab_frame(idx):
    ts = idx / 60.0
    out = f"_fs/f{idx}.png"
    subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{ts:.4f}", "-i", VID,
                    "-frames:v", "1", out], capture_output=True)
    return np.asarray(Image.open(out).convert("L"), dtype=np.uint8)

def bright_bbox(arr, x0, x1, y0, y1, thr=150):
    """区域内的亮像素包围盒（视频 600x1300 坐标）。"""
    reg = arr[y0:y1, x0:x1]
    ys, xs = np.where(reg > thr)
    if len(xs) < 30:
        return None
    return [x0 + int(xs.min()), y0 + int(ys.min()),
            x0 + int(xs.max()), y0 + int(ys.max())]

# 帧 375 = 静止列表：定位九宫格第三张（亮块）真实位置
base = grab_frame(375)
print("帧375 静止列表，各亮块包围盒（找缩略图3）:")
# 九宫格大概在 x 150-510, y 520-720（先粗扫，找 112px 方块）
boxes = []
arr = base
th = arr > 150
# 连通亮块按行扫描简化：在网格区域内逐列投影
from scipy import ndimage as ndi  # noqa: E402
lab, n = ndi.label(th[400:900, 100:600])
for i in range(1, n + 1):
    ys, xs = np.where(lab == i)
    if len(xs) > 2000:  # 大块（封面大图等）跳过
        continue
    w = xs.max() - xs.min(); h = ys.max() - ys.min()
    if 60 < w < 160 and 60 < h < 160:
        boxes.append([100 + int(xs.min()), 400 + int(ys.min()),
                      100 + int(xs.max()), 400 + int(ys.max())])
for b in sorted(boxes, key=lambda z: (z[1], z[0])):
    print("   亮块:", b)

# 动画帧序列：跟踪中央区域最大亮块
print("\n动画帧白卡片包围盒跟踪:")
for f in [376, 378, 379, 380, 381, 382, 384, 386]:
    a = grab_frame(f)
    bb = bright_bbox(a, 0, 600, 250, 1000)
    print(f"   帧{f} (t={f/60:.2f}s): {bb}")
