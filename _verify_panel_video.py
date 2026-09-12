# -*- coding: utf-8 -*-
"""成品视频校验：自动定位 8 段面板切换，逐段抽 6 帧拼成「过渡逐帧带」，
再与参考视频同状态的帧做并排对照。全部靠像素判读，不依赖肉眼抽象描述。

用法：py _verify_panel_video.py videos\wx_xxx.mp4
"""
import os, sys, glob, shutil, subprocess
import numpy as np
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FF = r"C:\Users\mik\AppData\Local\Programs\Python\Python314\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
REF = r"G:\weixin-auto\参考图片\微信聊天框三个界面切换.mp4"

VID = sys.argv[1] if len(sys.argv) > 1 else None
if not VID or not os.path.isfile(VID):
    cands = sorted(glob.glob(r"G:\weixin-auto\videos\wx_*.mp4"), key=os.path.getmtime)
    VID = cands[-1]
print("视频:", VID)

OUT = r"G:\weixin-auto\_vg"
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

# ---- 1) 全片 30fps 抽帧（宽 270，约 1/4） ----
subprocess.run([FF, "-y", "-i", VID, "-vf", "fps=30,scale=270:-1",
                os.path.join(OUT, "f_%04d.png")], capture_output=True)
fs = sorted(glob.glob(os.path.join(OUT, "f_*.png")))
N = len(fs)
print("帧数:", N, " 时长≈%.2fs" % (N / 30.0))
arrs = [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in fs]
H, W, _ = arrs[0].shape
print("尺寸:", W, "x", H)

# ---- 2) 相邻帧差异 → 找切换窗口 ----
diffs = np.array([0.0] + [np.abs(arrs[i] - arrs[i - 1]).mean() for i in range(1, N)])
hot = diffs > 1.2
windows, i = [], 0
while i < N:
    if hot[i]:
        j = i
        while j + 1 < N and (hot[j + 1] or diffs[j + 1] > 0.5):
            j += 1
        if j - i >= 2:
            windows.append((i, j))
        i = j + 1
    else:
        i += 1
# 合并间隔 < 6 帧的窗口
merged = []
for w in windows:
    if merged and w[0] - merged[-1][1] < 6:
        merged[-1] = (merged[-1][0], w[1])
    else:
        merged.append(w)
print("\n切换窗口（帧号 / 秒）:", len(merged))
for a, b in merged:
    print("  frames %4d-%4d  t=%.2f~%.2f  (%.0fms)  peak=%.1f"
          % (a, b, a / 30.0, b / 30.0, (b - a) / 30.0 * 1000, diffs[a:b + 1].max()))


def strip_of(im):
    """裁底部 46% 作为观察带"""
    w, h = im.size
    return im.crop((0, int(h * 0.54), w, h))


# ---- 3) 每段切换抽 7 帧拼成一行 ----
LBL = 16
rows = []
for k, (a, b) in enumerate(merged):
    idxs = [max(0, a - 3)] + [a + int(round(off * (b - a)))
                              for off in (0, .25, .5, .75, 1.0)] + [min(N - 1, b + 3)]
    ims = [strip_of(Image.open(fs[i]).convert("RGB")) for i in idxs]
    tw, th = ims[0].size
    row = Image.new("RGB", (len(ims) * (tw + 4) + 4, th + LBL + 4), (250, 250, 250))
    d = ImageDraw.Draw(row)
    d.text((4, 2), "过渡#%d  帧%s  t=%.2f~%.2fs" % (k + 1, idxs, a / 30.0, b / 30.0), fill=(0, 0, 0))
    for n, im in enumerate(ims):
        row.paste(im, (4 + n * (tw + 4), LBL + 2))
    rows.append(row)

if rows:
    CW = max(r.size[0] for r in rows)
    sheet = Image.new("RGB", (CW, sum(r.size[1] + 6 for r in rows) + 6), (235, 235, 235))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y)); y += r.size[1] + 6
    p1 = os.path.join(OUT, "trans_all.png")
    sheet.save(p1); print("\n过渡总览:", p1, sheet.size)

# ---- 4) 与参考视频同状态并排对照 ----
# 参考关键状态帧（已抽好）：t1.0 收起 / t2.8 键盘 / t4.5 表情 / t5.6 更多
ref_map = [("收起", r"G:\weixin-auto\_ref3\fs_1.0.png"),
           ("键盘", r"G:\weixin-auto\_ref3\fs_2.8.png"),
           ("表情", r"G:\weixin-auto\_ref3\fs_4.5.png"),
           ("更多", r"G:\weixin-auto\_ref3\fs_5.6.png")]
# 成品：取各稳态段中间帧 —— 用窗口之间的平台中点
bounds = [0] + [x for w in merged for x in w] + [N - 1]
plats = [(bounds[i] + bounds[i + 1]) // 2 for i in range(0, len(bounds) - 1, 2)]
pairs = []
for (name, rp), mi in zip(ref_map, plats[:4]):
    if not os.path.exists(rp):
        continue
    r = Image.open(rp).convert("RGB")
    r = r.resize((270, int(r.size[1] * 270 / r.size[0])), Image.LANCZOS)
    m = Image.open(fs[mi]).convert("RGB")
    pairs.append((name, r, m, mi))
if pairs:
    th = max(p[1].size[1] for p in pairs)
    sheet = Image.new("RGB", (len(pairs) * (270 * 2 + 12) + 8, th + LBL + 8), (250, 250, 250))
    d = ImageDraw.Draw(sheet)
    for n, (name, r, m, mi) in enumerate(pairs):
        x = 4 + n * (270 * 2 + 12)
        d.text((x + 4, 2), "%s   参考 | 复刻(帧%d)" % (name, mi), fill=(0, 0, 0))
        sheet.paste(r, (x, LBL + 2)); sheet.paste(m, (x + 270 + 4, LBL + 2))
    p2 = os.path.join(OUT, "cmp_ref.png")
    sheet.save(p2); print("参考对照:", p2, sheet.size)
