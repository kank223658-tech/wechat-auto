# -*- coding: utf-8 -*-
"""验证 _assemble_vfr_mp4 的逐帧归一化分支逻辑。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from PIL import Image

VIEWPORT_W, VIEWPORT_H = 600, 1300
def norm_size(w, h):
    """返回该尺寸会被归一化到哪种结果：'as-is' / 'scale_full' / 'crop_left'"""
    if (w, h) == (VIEWPORT_W, VIEWPORT_H):
        return "as-is (600x1300)"
    app_ar = VIEWPORT_W / float(VIEWPORT_H)
    ar = w / float(h)
    if abs(ar - app_ar) <= 0.06:
        return "scale_full -> 600x1300 (整页缩放，消除放大左上角)"
    return "crop_left 600x1300 (并排/非等比转场)"

cases = [
    (600, 1300),   # 正常
    (1200, 2600),  # 等比放大 2x（闪帧）-> scale_full
    (1800, 3900),  # 等比放大 3x -> scale_full
    (368, 800),    # 等比缩小 -> scale_full
    (1380, 1300),  # 底页+滑入页并排撑宽（转场）-> crop_left
    (2600, 1300),  # 更宽的转场 -> crop_left
    (600, 2400),   # 高度被撑大（键盘顶出）-> crop_left
    (1170, 2532),  # 接近 600:1300(0.4615) 的 1170:2532=0.4624 -> scale_full（其实这是设备像素比）
]
for w, h in cases:
    print(f"  {w:5d}x{h:5d}  ar={w/h:.4f}  -> {norm_size(w, h)}")
