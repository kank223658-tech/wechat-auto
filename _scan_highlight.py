# -*- coding: utf-8 -*-
"""检测每帧「被按下的键」：键帽按下后瞬间到位 #8e8e93(亮度~142)，空闲键 #636366(~99)。
按灰度落在 [130,155] 且成团的大量像素来识别被按下的键（键框/阴影多为中低灰，不会误入）。
裁剪只覆盖字母/数字键行，避开发送键(蓝)与候选条。
"""
import glob
import sys
import numpy as np
from PIL import Image

Y0, Y1, X0, X1 = 880, 1075, 8, 592
LO, HI = 130, 155
MIN_PIX = 800   # 一个键帽被完整点亮通常 >2000 像素


def count(path):
    im = Image.open(path).convert("L")
    a = np.asarray(im, dtype=np.int16)[Y0:Y1, X0:X1]
    return int(((a >= LO) & (a <= HI)).sum())


def main(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        print("未找到帧文件：", pattern)
        return
    on = []
    for i, f in enumerate(files):
        n = count(f)
        if n >= MIN_PIX:
            on.append(i)
    tot = len(files)
    print(f"共 {tot} 帧，检测到「按下的键」的帧：{len(on)}（{len(on)/tot:.0%}）")
    if on:
        # 输出连续段，方便定位打字窗口
        segs = []
        s = p = on[0]
        for x in on[1:]:
            if x == p + 1:
                p = x
            else:
                segs.append((s, p)); s = p = x
        segs.append((s, p))
        print("亮键帧连续段(帧号区间)：", segs[:20])
        print("亮键像素 max/avg:", max(count(files[i]) for i in on),
              round(float(np.mean([count(files[i]) for i in on])), 1))
    else:
        print("没有任何一帧捕捉到按下的键 —— 打字动画仍未出现。")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else r"F:\weixin-auto\_video_frames\vf_*.jpg")
