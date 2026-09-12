# -*- coding: utf-8 -*-
"""kb_body_num.png 底行「空格/发送」二字与字母页统一（msyh 45，字面高 44tex）。

_gen_num_kb.py 原用 f_cjk=msyh40（字面高 34tex），比已定版的字母页
kb_body.png（msyh45，对齐参考视频「发送按键的变化规律.mp4」实测）小 23%。
两页在打字过程中会来回切换，字必须同大，否则切页时文字跳变。
键面/圆角/颜色/几何全部沿用本贴图原实测值（KEY(112) FN 蓝(55,122,252) R=12）。
"""
from PIL import Image, ImageDraw, ImageFont

P = 'vue-WeChat/public/images/chatbar/kb_body_num.png'
img = Image.open(P).convert('RGB')
d = ImageDraw.Draw(img)

BG = (50, 50, 50)
KEY = (112, 112, 112)
SHADOW = (30, 30, 30)
BLUE = (52, 120, 245)          # 与 kb_body.png 定版蓝统一（两页切来切去必须同色）
R = 12
MSYH = r'C:\Windows\Fonts\msyh.ttc'
f = ImageFont.truetype(MSYH, 45)   # 与 kb_body.png 定版一致

def redraw_key(x0, y0, x1, y1, fill, text):
    d.rectangle([x0 - 5, y0 - 5, x1 + 5, y1 + 6], fill=BG)
    d.rounded_rectangle([x0, y0 + 3, x1, y1 + 3], R, fill=SHADOW)
    d.rounded_rectangle([x0, y0, x1, y1], R, fill=fill)
    l, t, r_, b = d.textbbox((0, 0), text, font=f)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d.text((cx - (r_ - l) / 2 - l, cy - (b - t) / 2 - t), text, font=f, fill=(255, 255, 255))

redraw_key(305, 645, 873, 773, KEY, '空格')
redraw_key(892, 645, 1167, 773, BLUE, '发送')
img.save(P)
print('saved', P, img.size)

# 自验：字形 bbox（应与字母页一致 h≈44）
img2 = Image.open(P).convert('RGB')
def is_white(p): return p[0] > 180 and p[1] > 180 and p[2] > 180
def txt_bbox(im, x0, x1, y0, y1):
    minx, miny, maxx, maxy = 10**9, 10**9, -1, -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            if is_white(im.getpixel((x, y))):
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
    return minx, miny, maxx, maxy
b1 = txt_bbox(img2, 345, 833, 653, 765)
print('kongge glyph h=%d w=%d' % (b1[3]-b1[1]+1, b1[2]-b1[0]+1))
b2 = txt_bbox(img2, 907, 1152, 653, 765)
print('fasong glyph h=%d w=%d' % (b2[3]-b2[1]+1, b2[2]-b2[0]+1))
