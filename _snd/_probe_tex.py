# 采样 kb_body.png 底行 空格/发送键 与参考视频 确认态 的精确颜色几何
from PIL import Image
import collections

# ---- 1. 贴图 kb_body.png (1179x1008) ----
tex = Image.open('vue-WeChat/public/images/chatbar/kb_body.png').convert('RGB')
W, H = tex.size
print('tex size', tex.size)
# 底行在贴图坐标: canvas y 252.2+76=328.2..393.8 -> tex y 645..774
# space: canvas x155.2-444.8 -> tex 305-874 ; send: canvas 453.9-593.8 -> tex 892-1167
# 逐列扫底行找键边界(键面 vs 背景色)
row_y = 700
cols = []
prev = None
for x in range(0, W):
    p = tex.getpixel((x, row_y))
    cols.append(p)
# 输出底行横剖面: 每10px 报颜色
for x in range(280, 1179, 20):
    print(x, tex.getpixel((x, 700)), tex.getpixel((x, 660)))
