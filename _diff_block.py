# -*- coding: utf-8 -*-
"""对比参考视频帧与复刻截图的几何/颜色差异（拉黑设置页）。"""
import cv2
import numpy as np

REF = cv2.imread('_block_frames/ref_settings.png')     # 592x1280
MINE = cv2.imread('_block_verify/02_settings.png')     # 1200x2600 (scale=2)

def analyze(img, tag, scale=1.0):
    h, w = img.shape[:2]
    print(f'== {tag} size {w}x{h}')
    # 亮度图：找文字行（左侧 20~300px 区域内的亮像素）
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    roi = gray[:, int(w*0.04):int(w*0.5)]
    rowbright = (roi > 120).sum(axis=1)
    rows = rowbright > 8
    # 聚类成行段
    segs = []
    start = None
    for y, v in enumerate(rows):
        if v and start is None: start = y
        elif not v and start is not None:
            if y - start > 8: segs.append((start, y))
            start = None
    for (a, b) in segs:
        print(f'  text row y {int(a/scale)}..{int(b/scale)}  h={int((b-a)/scale)}')
    # 颜色采样
    def px(x, y):
        b, g, r = img[int(y*scale), int(x*scale)]
        return f'#{r:02x}{g:02x}{b:02x}'
    # 参考坐标（592 宽系）：页面底 / 单元格底 / 文字色 / 开关
    return segs

analyze(REF, 'REF(592x1280, 坐标已换算到600宽)', scale=600/592)
analyze(MINE, 'MINE(1200x2600, 坐标已换算到600宽)', scale=2.0)

# 开关几何：REF 加入黑名单行开关在右侧 (x 400..500, y 420..470)
def toggle_box(img, x0, x1, y0, y1, scale, tag):
    sub = img[int(y0*scale):int(y1*scale), int(x0*scale):int(x1*scale)]
    g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    mask = g > 90
    ys, xs = np.where(mask)
    if len(xs) == 0:
        print(f'  {tag}: no bright toggle found'); return
    print(f'  {tag} toggle bbox x {x0+xs.min()/scale:.0f}..{x0+xs.max()/scale:.0f} '
          f'y {y0+ys.min()/scale:.0f}..{y0+ys.max()/scale:.0f} '
          f'w={(xs.max()-xs.min())/scale:.0f} h={(ys.max()-ys.min())/scale:.0f}')
    # 采样开关中心色
    cx, cy = (xs.min()+xs.max())//2, (ys.min()+ys.max())//2
    b, gg, r = sub[cy, cx]
    print(f'    center color #{r:02x}{gg:02x}{b:02x}')

print('-- toggle (加入黑名单行, off) --')
toggle_box(REF, 395, 505, 430, 480, 600/592, 'REF')
toggle_box(MINE, 395, 505, 430, 480, 2.0, 'MINE')

# 底色采样
def c(img, x, y, scale, tag, label):
    b, g, r = img[int(y*scale), int(x*scale)]
    print(f'  {tag} {label}: #{r:02x}{g:02x}{b:02x}')
print('-- colors --')
c(REF, 300, 700, 600/592, 'REF', 'page bottom bg')
c(MINE, 300, 700, 2.0, 'MINE', 'page bottom bg')
c(REF, 300, 165, 600/592, 'REF', 'cell bg (编辑备注行)')
c(MINE, 300, 165, 2.0, 'MINE', 'cell bg (编辑备注行)')
c(REF, 300, 152, 600/592, 'REF', 'gap?')
# 文字颜色：取编辑备注行最亮像素
def textcolor(img, x0, x1, y0, y1, scale, tag):
    sub = img[int(y0*scale):int(y1*scale), int(x0*scale):int(x1*scale)]
    g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    idx = np.unravel_index(np.argmax(g), g.shape)
    b, gg, r = sub[idx]
    print(f'  {tag} text peak: #{r:02x}{gg:02x}{b:02x} (brightness {g.max()})')
textcolor(REF, 20, 180, 145, 185, 600/592, 'REF')
textcolor(MINE, 20, 180, 145, 185, 2.0, 'MINE')
