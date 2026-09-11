# -*- coding: utf-8 -*-
"""弹窗 / Toast 对比 + 生成左右拼图。"""
import cv2
import numpy as np

REF_S = cv2.imread('_block_frames/ref_sheet.png')      # 592x1280
MINE_S = cv2.imread('_block_verify/04_sheet.png')      # 1200x2600
REF_T = cv2.imread('_block_frames/ref_toast.png')
MINE_T = cv2.imread('_block_verify/06_loading.png')

def px(img, x, y, scale=1.0):
    b, g, r = img[int(y*scale), int(x*scale)]
    return f'#{r:02x}{g:02x}{b:02x}'

S = 600/592
print('== 弹窗 (sheet) ==')
# REF 弹窗：从底部往上找非纯黑区域。先采样已知位置：
# REF f0100: 弹窗 msg 两行在 y~800-830, 确定按钮 y~890, 取消 y~968
for y in (760, 790, 830, 860, 890, 930, 968, 1010):
    print(f'  REF y{y}: {px(REF_S, 296, y, S)}')
print()
# MINE (scale=2): 弹窗 msg y~830*2, 确定 y~940*2, 取消 y~1010*2
for y in (780, 820, 850, 900, 940, 990, 1010, 1060):
    print(f'  MINE y{y}: {px(MINE_S, 300, y, 2.0)}')

print()
print('== 弹窗上沿位置（亮度扫描，从下往上找 sheet 顶） ==')
def sheet_top(img, scale, x):
    col = img[:, int(x*scale)]
    g = cv2.cvtColor(col.reshape(1, -1, 3), cv2.COLOR_BGR2GRAY).ravel()
    # 从底部 100px 往上，找亮度明显升高处（sheet bg 比页面亮）
    ys = None
    for y in range(len(g)-40, len(g)//2, -1):
        if g[y] > 45:
            ys = y
    return int(ys/scale) if ys else None
print('  REF sheet top y =', sheet_top(REF_S, S, 296))
print('  MINE sheet top y =', sheet_top(MINE_S, 2.0, 300))

print()
print('== Toast ==')
def toast_box(img, scale, tag):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 中央区域找 toast（比页面亮的灰块）
    h, w = g.shape
    cy0, cy1 = int(h*0.35), int(h*0.68)
    sub = g[cy0:cy1, int(w*0.25):int(w*0.75)]
    mask = sub > 70
    ys, xs = np.where(mask)
    if len(xs) < 100:
        print(f'  {tag}: toast not found'); return
    x0, x1 = int(w*0.25)+xs.min()/scale, int(w*0.25)+xs.max()/scale
    y0, y1 = cy0/scale+ys.min()/scale, cy0/scale+ys.max()/scale
    print(f'  {tag} toast bbox x {x0:.0f}..{x1:.0f} y {y0:.0f}..{y1:.0f} '
          f'w={x1-x0:.0f} h={y1-y0:.0f}')
    cx, cy = int((xs.min()+xs.max())/2), int((ys.min()+ys.max())/2)
    b, gg, r = sub[cy, 10]
    print(f'    left-edge color #{r:02x}{gg:02x}{b:02x}')
toast_box(REF_T, S, 'REF')
toast_box(MINE_T, 2.0, 'MINE')

print()
print('== 拼图 ==')
def side(ref, mine, out, y0r, y1r, y0m, y1m):
    # ref 592 宽、mine 1200 宽 → 都缩到 500 宽拼接
    rc = ref[y0r:y1r]
    mc = mine[y0m:y1m]
    rc = cv2.resize(rc, (500, int(rc.shape[0]*500/rc.shape[1])))
    mc = cv2.resize(mc, (500, int(mc.shape[0]*500/mc.shape[1])))
    hh = max(rc.shape[0], mc.shape[0])
    canvas = np.zeros((hh, 1010, 3), np.uint8)
    canvas[:rc.shape[0], :500] = rc
    canvas[:mc.shape[0], 510:] = mc
    cv2.imwrite(out, canvas)
    print('  saved', out)

side(REF_S, MINE_S, '_block_frames/cmp_settings.png', 0, 900, 0, 1800)
side(REF_T, MINE_T, '_block_frames/cmp_toast.png', 380, 900, 760, 1800)
