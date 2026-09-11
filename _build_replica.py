# -*- coding: utf-8 -*-
"""微信「通讯录」「我」界面像素级复刻：从参考图裁切图标 + 生成 HTML"""
from PIL import Image
import numpy as np, os

SRC = r"G:/weixin-auto/参考图片"
OUT = r"G:/weixin-auto/复刻_界面"
ASSETS = os.path.join(OUT, "assets")
os.makedirs(ASSETS, exist_ok=True)

# 预扫描「我」页行分隔线位置（裁切前需要）
_a2 = np.asarray(Image.open(os.path.join(SRC, "我界面.jpg")).convert("RGB")).astype(int)
sep_ys = []
for _y in range(1060, 1780):
    _v = _a2[_y, 600]
    if abs(_v[0]-49) < 12 and abs(_v[1]-49) < 12 and abs(_v[2]-49) < 12:
        if not sep_ys or _y - sep_ys[-1] > 20:
            sep_ys.append(_y)

im1 = Image.open(os.path.join(SRC, "通讯录界面.jpg")).convert("RGB")
im2 = Image.open(os.path.join(SRC, "我界面.jpg")).convert("RGB")
S = 3.0  # 3x 截图 -> CSS px

# sRGB ICC 配置文件（防止浏览器按 Display P3 解码导致颜色偏移）
ICC = open(r"C:\Windows\System32\spool\drivers\color\sRGB Color Space Profile.icm", "rb").read()

def crop(im, name, box):
    im.crop(box).save(os.path.join(ASSETS, name), icc_profile=ICC)
    x0, y0, x1, y1 = box
    return dict(name=name, l=x0/S, t=y0/S, w=(x1-x0)/S, h=(y1-y0)/S)

# ---------------- 通讯录 ----------------
c = {}
c['statusbar'] = crop(im1, 'c_statusbar.png', (0, 0, 1179, 180))
c['person_add'] = crop(im1, 'c_person_add.png', (1056, 198, 1131, 258))
c['search'] = crop(im1, 'c_search.png', (0, 306, 1179, 414))
fn_rows = [('新的朋友', 477, 606), ('群聊', 645, 774), ('标签', 813, 942),
           ('公众号', 979, 1108), ('服务号', 1149, 1278), ('企业微信联系人', 1317, 1446)]
for name, y0, y1 in fn_rows:
    key = 'fn_' + name
    c[key] = crop(im1, 'c_fn_%d.png' % fn_rows.index((name, y0, y1)), (39, y0, 180, y1))
c['alphabet'] = crop(im1, 'c_alphabet.png', (1134, 798, 1170, 1614))
c['avatar1'] = crop(im1, 'c_avatar1.png', (42, 1626, 177, 1761))
c['avatar2'] = crop(im1, 'c_avatar2.png', (42, 1938, 177, 2073))
c['bottom'] = crop(im1, 'c_bottom.png', (0, 2148, 1179, 2556))
c['sep_full'] = []
for i, y in enumerate([1465, 1777, 2089]):
    c['sep_full'].append(crop(im1, 'c_sepf%d.png' % i, (45, y-1, 1179, y+2)))

# ---------------- 我 ----------------
m = {}
m['statusbar'] = crop(im2, 'm_statusbar.png', (0, 0, 1179, 180))
m['avatar'] = crop(im2, 'm_avatar.png', (81, 351, 279, 549))
m['scan'] = crop(im2, 'm_scan.png', (1068, 351, 1131, 441))
m['pills'] = crop(im2, 'm_pills.png', (327, 549, 621, 633))
m['chevron'] = crop(im2, 'm_chevron.png', (1098, 810, 1131, 843))
me_rows = [('服务', 804, 861), ('收藏', 993, 1056), ('朋友圈', 1167, 1221),
           ('作品', 1326, 1392), ('卡包', 1503, 1557), ('表情', 1662, 1731), ('设置', 1857, 1920)]
for i, (name, y0, y1) in enumerate(me_rows):
    m['row_' + name] = crop(im2, 'm_row%d.png' % i, (42, y0, 129, y1))
m['reddot'] = crop(im2, 'm_reddot.png', (1044, 1344, 1080, 1380))
m['bottom'] = crop(im2, 'm_bottom.png', (0, 2241, 1179, 2556))
m['seps'] = [crop(im2, 'm_sep%d.png' % i, (165, y-1, 1179, y+2)) for i, y in enumerate(sep_ys)]
m['gaps'] = [crop(im2, 'm_gap%d.png' % i, (0, y-3, 1179, y+36)) for i, y in enumerate([912, 1776])]


def img(name): return '<img class="a" src="assets/%s">' % name[name] if False else '<img class="a" src="assets/{0}" style="left:{1:.1f}px;top:{2:.1f}px;width:{3:.1f}px;height:{4:.1f}px;">'

def place(o):
    return '<img class="a" src="assets/%s" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;">' % (o['name'], o['l'], o['t'], o['w'], o['h'])

def text(l, t, w, size, color, weight, content, align='left', lh=None, ls=None):
    return ('<div class="t" style="left:%.2fpx;top:%.2fpx;width:%.1fpx;font-size:%.0fpx;color:%s;font-weight:%d;text-align:%s;line-height:%s;%s">%s</div>'
            % (l, t, w, size, color, weight, align, lh or str(size+6)+'px',
               ('letter-spacing:%.2fpx;' % ls) if ls else '', content))

FONT = '"PingFang SC","DengXian","Microsoft YaHei UI","Microsoft YaHei",sans-serif'
BASE = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>html,body{margin:0;padding:0;background:#191919;}'
        '.phone{position:relative;width:393px;height:852px;background:#191919;overflow:hidden;'
        'font-family:%s;-webkit-font-smoothing:antialiased;}'
        '.a{position:absolute;display:block;image-rendering:pixelated;}'
        '.t{position:absolute;margin:0;white-space:nowrap;}</style></head>'
        '<body><div class="phone">' % FONT)

# ================= 通讯录页 =================
p = [BASE]
p.append('<div style="position:absolute;left:0;top:0;width:393px;height:154px;background:#111111;"></div>')
p.append(place(c['statusbar']))
p.append(text(0, 65, 393, 17, '#ebebeb', 500, '通讯录', 'center'))
p.append(place(c['person_add']))
p.append(place(c['search']))
# 功能行：图标 + 文字
for name, y0, y1 in fn_rows:
    o = c['fn_' + name]
    p.append(place(o))
    p.append(text(68.3, (y0+y1)/2/S - 11.5, 240, 17, '#f0f0f0', 400, name))
# 行分割线（功能行之间，从原图裁切）
for i, y in enumerate([625, 793, 961, 1129, 1297]):
    p.append('<img class="a" src="assets/c_sep%d.png" style="left:68px;top:%dpx;width:325px;height:1px;">' % (i, (y-1)//S))
# 整组分隔线（企业微信联系人/沉默光环/d 行下方）
for i, o in enumerate(c['sep_full']):
    p.append('<img class="a" src="assets/%s" style="left:%.0fpx;top:%.0fpx;width:%.0fpx;height:%.0fpx;">' % (o['name'], o['l'], o['t'], o['w'], o['h']))
# 分组字母 C / D
p.append(text(16.7, 513.4, 40, 14, '#a4a4a4', 700, 'C'))
p.append(text(16.7, 617.4, 40, 14, '#a4a4a4', 700, 'D'))
# 字母索引条
p.append(place(c['alphabet']))
# 联系人行
p.append(place(c['avatar1']))
p.append(text(68.3, 552.8, 240, 17, '#f0f0f0', 400, '沉默光环'))
p.append(place(c['avatar2']))
p.append(text(68.3, 657.3, 240, 17, '#f0f0f0', 400, 'd'))
p.append(place(c['bottom']))
p.append('</div></body></html>')
open(os.path.join(OUT, '通讯录.html'), 'w', encoding='utf-8').write(''.join(p))

# ================= 我 页 =================
p = [BASE]
p.append(place(m['statusbar']))
p.append(place(m['avatar']))
p.append(text(112.3, 121, 200, 22, '#eeeeee', 500, 'd'))
p.append(text(112.3, 155.7, 260, 15, '#adadad', 400, '微信号：AAi201', ls=1))
p.append(place(m['scan']))
p.append(place(m['pills']))
# 行：图标 + 文字 + 箭头
for name, y0, y1 in me_rows:
    o = m['row_' + name]
    p.append(place(o))
    p.append(text(56.5, (y0+y1)/2/S - 11, 200, 17, '#e7e7e7', 400, name))
    cy = round((y0+y1)/2/S) - m['chevron']['h']/2
    p.append('<img class="a" src="assets/%s" style="left:364px;top:%.4fpx;width:%.4fpx;height:%.4fpx;">'
             % (m['chevron']['name'], cy, m['chevron']['w'], m['chevron']['h']))
# 行间细分割线（原图裁切，x55 -> 右边缘）
for o in m['seps']:
    p.append(place(o))
# 分组间隙（原图裁切：细分隔线+浅线+深色带+浅线 完整结构）
for o in m['gaps']:
    p.append(place(o))
# 作品行附加：添加第 1 个作品 + 红点
p.append(text(232, 443.7, 108, 13, '#a0a0a0', 400, '添加第 1 个作品', 'right'))
p.append(place(m['reddot']))
p.append(place(m['bottom']))
p.append('</div></body></html>')
open(os.path.join(OUT, '我.html'), 'w', encoding='utf-8').write(''.join(p))
print('done')
