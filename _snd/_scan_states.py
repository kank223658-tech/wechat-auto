# 扫描参考视频每一帧的空格键/右下角键状态
import glob, re
from PIL import Image

frames = sorted(glob.glob('f_*.png'))
# 原图 592x1280，crop offset y=1080。裁切图2x: 空格键 x 285-820 y 30-145 -> 原图 x 143-410, y 1095-1152
SPACE = (143, 1095, 410, 1152)
SEND  = (422, 1095, 540, 1152)

def analyze(path):
    im = Image.open(path).convert('RGB')
    sx0, sy0, sx1, sy1 = SPACE
    sp = im.crop((sx0, sy0, sx1, sy1))
    bx0, by0, bx1, by1 = SEND
    snd = im.crop((bx0, by0, bx1, by1))
    # 右键: 统计蓝色像素 (b明显大于r) 与白色文字像素
    px = list(snd.getdata())
    n = len(px)
    blue = sum(1 for r,g,b in px if b > 150 and b - r > 40)
    white = sum(1 for r,g,b in px if r>200 and g>200 and b>200)
    # 空格键: 白色文字像素（「空格」/「选定」都有字；空白键则少）
    spx = list(sp.getdata())
    swhite = sum(1 for r,g,b in spx if r>190 and g>190 and b>190)
    # 空格键是否高亮（按下/选定态键面更浅灰）
    savg = tuple(sum(p[i] for p in spx)//len(spx) for i in range(3))
    is_blue = blue > n*0.15
    return is_blue, blue, swhite, savg

print("frame\tstate\tblue\tspaceWhite\tspaceAvg")
for f in frames:
    idx = int(re.search(r'f_(\d+)', f).group(1))
    is_blue, blue, swhite, savg = analyze(f)
    state = 'SEND(蓝)' if is_blue else 'CONFIRM(灰)'
    mark = ''
    print(f"{idx:03d}\t{state}\t{blue:5d}\t{swhite:5d}\t{savg}")
