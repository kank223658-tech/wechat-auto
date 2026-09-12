# -*- coding: utf-8 -*-
"""kb_body.png 底行「空格/发送」二字放大重绘 —— 对齐参考视频「发送按键的变化规律.mp4」实测。

实测依据（脚本 _snd/_probe_tex2.py）：
- 视频(592宽)内「空格」「发送」「选定」「确认」四词字形高均 ≈21-22px，四态一致，切换才不跳变。
- 贴图现字(msyh 40)「空格」字形高 34 tex(17.3 canvas)，比视频小 23%。
- 新字号 = 40 x 42/34 ≈ 49（msyh 49 -> 「空格」字形高 ≈42 tex ≈ 21.4 canvas ≈ 视频实测）。
- 只重绘两个键自身（含 3px 底阴影），键面/圆角/颜色全部沿用原实测值：
  空格键面 rgb(112,112,112)、发送键 rgb(52,120,245)、阴影 rgb(30,30,30)、圆角 R=12。
"""
from PIL import Image, ImageDraw, ImageFont

P = 'vue-WeChat/public/images/chatbar/kb_body.png'
img = Image.open(P).convert('RGB')
d = ImageDraw.Draw(img)
W, H = img.size

BG = (50, 50, 50)
KEY = (112, 112, 112)
SHADOW = (30, 30, 30)
BLUE = (52, 120, 245)          # 贴图原实测蓝（勿用生成脚本里的 55,122,252）
R = 12
MSYH = r'C:\Windows\Fonts\msyh.ttc'
f = ImageFont.truetype(MSYH, 45)   # 视频字形/键高比 22/64=0.344 -> 44 tex

def redraw_key(x0, y0, x1, y1, fill, text):
    # 清区域到键盘底色
    d.rectangle([x0 - 5, y0 - 5, x1 + 5, y1 + 6], fill=BG)
    # 阴影(键下 3px) + 键帽
    d.rounded_rectangle([x0, y0 + 3, x1, y1 + 3], R, fill=SHADOW)
    d.rounded_rectangle([x0, y0, x1, y1], R, fill=fill)
    # 屏中白字
    l, t, r_, b = d.textbbox((0, 0), text, font=f)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d.text((cx - (r_ - l) / 2 - l, cy - (b - t) / 2 - t), text, font=f, fill=(255, 255, 255))

redraw_key(305, 645, 873, 773, KEY, '空格')
redraw_key(892, 645, 1166, 773, BLUE, '发送')
img.save(P)
print('saved', P, img.size)

# 自验：新字形 bbox
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
b2 = txt_bbox(img2, 907, 1151, 653, 765)
print('fasong glyph h=%d w=%d' % (b2[3]-b2[1]+1, b2[2]-b2[0]+1))
