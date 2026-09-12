# 精测贴图底行两键 bbox/圆角/文字 + 参考视频确认态
from PIL import Image

tex = Image.open('vue-WeChat/public/images/chatbar/kb_body.png').convert('RGB')
W, H = tex.size

def key_bbox(im, x0, x1, y0, y1, is_key):
    # 在区域内找键面像素(非背景)的 bbox
    minx, miny, maxx, maxy = 10**9, 10**9, -1, -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            if is_key(im.getpixel((x, y))):
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
    return minx, miny, maxx, maxy

# 空格键: 键面≈112灰 (排除背景50与文字白)
def is_sp(p): return 95 <= p[0] <= 130 and abs(p[0]-p[1]) < 6 and abs(p[1]-p[2]) < 6
def is_blue(p): return p[2] > 180 and p[2]-p[0] > 100
def is_white(p): return p[0] > 180 and p[1] > 180 and p[2] > 180

sb = key_bbox(tex, 300, 890, 620, 800, is_sp)
print('space key bbox tex:', sb, 'w=%d h=%d' % (sb[2]-sb[0]+1, sb[3]-sb[1]+1))
bb = key_bbox(tex, 890, W, 620, 800, is_blue)
print('send key bbox tex:', bb, 'w=%d h=%d' % (bb[2]-bb[0]+1, bb[3]-bb[1]+1))
# 文字 bbox（键内白字）
spt = key_bbox(tex, sb[0]+40, sb[2]-40, sb[1]+8, sb[3]-8, is_white)
print('space text bbox:', spt, 'w=%d h=%d' % (spt[2]-spt[0]+1, spt[3]-spt[1]+1))
sdt = key_bbox(tex, bb[0]+15, bb[2]-15, bb[1]+8, bb[3]-8, is_white)
print('send text bbox:', sdt, 'w=%d h=%d' % (sdt[2]-sdt[0]+1, sdt[3]-sdt[1]+1))
# 圆角: 键顶行宽度 vs 中行宽度
ymid = (sb[1]+sb[3])//2
for dy in [0, 3, 6, 10, 14]:
    y = sb[1]+dy
    row = [x for x in range(sb[0]-5, sb[0]+40) if is_sp(tex.getpixel((x, y)))]
    print('space top row y+%d left edge:' % dy, row[0]-sb[0] if row else None)

print()
# ---- 参考视频 CONFIRM 帧 f30_050: 确认键颜色/文字, 选定文字 ----
ref = Image.open('_snd/f30_050.png').convert('RGB')
# 视频坐标: send 键区域 x 422-540, y 1095-1152
rb = key_bbox(ref, 400, 592, 1085, 1165, lambda p: 60 <= p[0] <= 90 and abs(p[0]-p[1])<8 and abs(p[1]-p[2])<8)
print('confirm key bbox video:', rb, 'w=%d h=%d' % (rb[2]-rb[0]+1, rb[3]-rb[1]+1))
# 键面颜色采样(中心偏上避开文字)
cx = (rb[0]+rb[2])//2
print('confirm key color:', ref.getpixel((cx, rb[1]+8)), ref.getpixel((rb[0]+10, (rb[1]+rb[3])//2)))
ct = key_bbox(ref, rb[0]+5, rb[2]-5, rb[1]+3, rb[3]-3, is_white)
print('confirm text bbox:', ct, 'w=%d h=%d' % (ct[2]-ct[0]+1, ct[3]-ct[1]+1))
# 视频里确认键文字「确认」颜色
# 空格键「选定」文字
spb = key_bbox(ref, 140, 415, 1085, 1165, is_sp)
print('video space key bbox:', spb, 'w=%d h=%d' % (spb[2]-spb[0]+1, spb[3]-spb[1]+1))
stt = key_bbox(ref, spb[0]+40, spb[2]-40, spb[1]+8, spb[3]-8, is_white)
print('video xuangding text bbox:', stt, 'w=%d h=%d' % (stt[2]-stt[0]+1, stt[3]-stt[1]+1))
print('video space key color:', ref.getpixel((spb[0]+15, spb[1]+8)))
# SEND 帧 f30_020 发送键颜色
ref2 = Image.open('_snd/f30_020.png').convert('RGB')
sb2 = key_bbox(ref2, 400, 592, 1085, 1165, is_blue)
print('video send key bbox:', sb2, 'w=%d h=%d' % (sb2[2]-sb2[0]+1, sb2[3]-sb2[1]+1))
print('video send key color:', ref2.getpixel(((sb2[0]+sb2[2])//2, sb2[1]+6)))
# 视频「空格」文字高度 (SEND帧)
spb2 = key_bbox(ref2, 140, 415, 1085, 1165, is_sp)
stt2 = key_bbox(ref2, spb2[0]+40, spb2[2]-40, spb2[1]+8, spb2[3]-8, is_white)
print('video kongge text bbox:', stt2, 'w=%d h=%d' % (stt2[2]-stt2[0]+1, stt2[3]-stt2[1]+1))
