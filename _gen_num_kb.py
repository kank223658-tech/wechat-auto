# -*- coding: utf-8 -*-
"""生成数字/符号键盘贴图 kb_body_num.png（1179x1008，与 kb_body.png 同几何）。

几何来源：
- kb_body.png 实测：四行键帽 tex y = 159/321/483/645，键高 128.9（取 129），
  键下 3px 深色阴影 #1E1E1E，键帽 #707070、功能键 #4E4E4E、底 #323232、发送蓝 ≈ (55,122,252)。
- 参考视频（参考图片/打数字功能.mp4 f_020）实测键位 x 区段 x1.9916 映射到贴图：
  行1/行2 = 10 键全宽（与字母行1同位）；行3 = #+=(宽) + 。,\\?!. + 退格(宽)；
  行4 = 拼音(宽) + 笑脸 + 空格 + 发送(蓝)。
- 候选条带(0..159) / 底部 dict 带(778..1008) / 笑脸键 / 退格键 直接从 kb_body.png 整块拷贝。
"""
from PIL import Image, ImageDraw, ImageFont

SRC = Image.open('vue-WeChat/public/images/chatbar/kb_body.png').convert('RGB')
W, H = SRC.size
BG = (50, 50, 50)
KEY = (112, 112, 112)
FN = (78, 78, 78)
SHADOW = (30, 30, 30)
BLUE = (55, 122, 252)
R = 12                      # 键帽圆角
ROW_Y = [159, 321, 483, 645]
KEY_H = 129

INTER = '_numref/inter-latin.ttf'
MSYH = r'C:\Windows\Fonts\msyh.ttc'
# 字号/偏移均按参考视频 f_020 实测标定（600 尺度 px x1.965 = tex px）：
# 数字 cap 高 24.3px(600)=48tex -> Inter 64pt；SF Pro 笔画粗于 Inter Regular，加 stroke 1 补偿
f_big = ImageFont.truetype(INTER, 62)      # 数字/符号主字形
f_cjk = ImageFont.truetype(MSYH, 40)       # 空格/发送
f_small = ImageFont.truetype(MSYH, 34)     # 拼音
f_hash = ImageFont.truetype(INTER, 36)     # #+=
f_at = ImageFont.truetype(INTER, 58)       # @（实测已吻合，不随 f_big 放大）
f_quote = ImageFont.truetype('C:/Windows/Fonts/georgia.ttf', 70)  # “”（Segoe UI 弯引号，SF 同形）
f_yuan = ImageFont.truetype(MSYH, 60)      # ￥（实测 h24.3px(600)，雅黑更接近 SF 粗细）
f_yuan = ImageFont.truetype(MSYH, 64)

img = SRC.copy()
d = ImageDraw.Draw(img)
# 清空键区带，重画
d.rectangle([0, ROW_Y[0] - 6, W, ROW_Y[3] + KEY_H + 6], fill=BG)

def draw_key(x0, x1, y0, color=KEY, shadow=True):
    y1 = y0 + KEY_H
    if shadow:
        d.rounded_rectangle([x0, y0 + 3, x1, y1 + 3], R, fill=SHADOW)
    d.rounded_rectangle([x0, y0, x1, y1], R, fill=color)

def center_text(cx, cy, text, font, fill=(255, 255, 255), dy=0, stroke=0):
    l, t, r_, b = d.textbbox((0, 0), text, font=font, stroke_width=stroke)
    d.text((cx - (r_ - l) / 2 - l, cy - (b - t) / 2 - t + dy), text,
           font=font, fill=fill, stroke_width=stroke, stroke_fill=fill)

WHITE = (255, 255, 255)

# --- 行1：1 2 3 4 5 6 7 8 9 0（与字母行1同位） ---
R1 = [(13, 109), (130, 227), (248, 344), (365, 461), (482, 579),
      (600, 696), (717, 813), (834, 930), (951, 1048), (1069, 1165)]
for (x0, x1), ch in zip(R1, '1234567890'):
    draw_key(x0, x1, ROW_Y[0])
    center_text((x0 + x1) // 2, ROW_Y[0] + KEY_H // 2, ch, f_big)

# --- 行2：- / : ; ( ) ￥ @ “ ”（与行1同位，参考视频实测） ---
# dy(向下为正, tex px) 按参考视频 cy 偏差修正（iOS 按基线排版，非 bbox 居中）
sym2 = ['-', '/', ':', ';', '(', ')', '￥', '@', '“', '”']
dy2 = {'-': 9, ':': 4, ';': 9}
for (x0, x1), ch in zip(R1, sym2):
    draw_key(x0, x1, ROW_Y[1])
    cx, cy = (x0 + x1) // 2, ROW_Y[1] + KEY_H // 2
    if ch == '-':
        # 实测：粗短横线 cy+0.5px(600)，h≈6tex w≈20tex（Inter 字形偏细偏高，手绘）
        d.rounded_rectangle([cx - 10, cy - 2, cx + 10, cy + 4], 2, fill=WHITE)
    elif ch == '￥':
        center_text(cx, cy, ch, f_yuan)
    elif ch == '@':
        center_text(cx, cy, ch, f_at)
    elif ch in '“”':
        center_text(cx, cy, ch, f_quote, dy=5)
    else:
        center_text(cx, cy, ch, f_big, dy=dy2.get(ch, 0))

# --- 行3：#+=(宽) 。 , \ ? ! . 退格(宽) —— x 区段取自参考视频 x1.9916 ---
R3 = [(12, 145, '#+=', FN), (175, 297, '。', KEY), (317, 438, ',', KEY),
      (456, 578, '\\', KEY), (598, 717, '?', KEY), (739, 859, '!', KEY),
      (880, 998, '.', KEY), (1032, 1166, 'BS', FN)]
for x0, x1, ch, color in R3:
    draw_key(x0, x1, ROW_Y[2], color)
    cx, cy = (x0 + x1) // 2, ROW_Y[2] + KEY_H // 2
    if ch == 'BS':
        # 退格键整块从字母贴图拷贝（图标+底色一致）
        cell = SRC.crop((x0, ROW_Y[2], x1 + 1, ROW_Y[2] + KEY_H))
        img.paste(cell, (x0, ROW_Y[2]))
    elif ch == '#+=':
        center_text(cx, cy, ch, f_hash)
    elif ch == '。':
        # iOS 中文句号 = 空心圆环，中心在键中心下方 +17tex（实测 cy+8.6px(600)），
        # 外半径 9tex、内半径 5tex（实测 h9.1 w10.1px(600)，环厚视觉 ~4tex）
        ey = cy + 17
        d.ellipse([cx - 9, ey - 9, cx + 9, ey + 9], fill=WHITE)
        d.ellipse([cx - 5, ey - 5, cx + 5, ey + 5], fill=KEY)
    elif ch == '\\':
        # 小斜线：位于基线处，中心 cy+18tex，半宽 8tex，线宽 5tex（实测 h8.1px(600)）
        ly = cy + 18
        d.line([cx - 7, ly - 8, cx + 7, ly + 8], fill=WHITE, width=5)
    elif ch == ',':
        center_text(cx, cy, ch, f_big, dy=26)
    elif ch == '.':
        center_text(cx, cy, ch, f_big, dy=22)
    else:
        center_text(cx, cy, ch, f_big)

# --- 行4：拼音(宽,fn) 笑脸 空格 发送(蓝) ---
# 笑脸键整块拷贝字母贴图
cell = SRC.crop((159, ROW_Y[3], 287, ROW_Y[3] + KEY_H))
draw_key(159, 286, ROW_Y[3], FN, shadow=True)
img.paste(cell, (159, ROW_Y[3]))
draw_key(12, 140, ROW_Y[3], FN)
center_text(76, ROW_Y[3] + KEY_H // 2, '拼音', f_small)
draw_key(305, 873, ROW_Y[3], KEY)
center_text(589, ROW_Y[3] + KEY_H // 2, '空格', f_cjk)
draw_key(892, 1167, ROW_Y[3], BLUE)
center_text(1029, ROW_Y[3] + KEY_H // 2, '发送', f_cjk)

img.save('vue-WeChat/public/images/chatbar/kb_body_num.png')
print('saved kb_body_num.png', img.size)
# 输出小图供人工比对
img.resize((590, 504), Image.LANCZOS).save('_numref/_kb_num_small.png')
