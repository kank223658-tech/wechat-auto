# -*- coding: utf-8 -*-
"""把逐帧对照拼成「左=旧 / 右=新」的循环视频。"""
import os
import subprocess

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = r"G:\weixin-auto"
FF = imageio_ffmpeg.get_ffmpeg_exe()
TMP = os.path.join(ROOT, "_ab_tmp")
os.makedirs(TMP, exist_ok=True)

FONT = None
for c in [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]:
    if os.path.exists(c):
        FONT = c
        break
assert FONT, "no font"


def make_label(path, captions, w=1200, h=88):
    """captions: [(文字, 中心x, 颜色), ...]，最后一行是左右说明。"""
    img = Image.new("RGB", (w, h), (23, 23, 23))
    d = ImageDraw.Draw(img)
    f1 = ImageFont.truetype(FONT, 30)
    f2 = ImageFont.truetype(FONT, 26)
    d.rectangle([0, 0, 599, h], fill=(46, 26, 26))
    d.rectangle([600, 0, 1199, h], fill=(22, 44, 30))
    d.line([597, 0, 597, h], fill=(110, 110, 110), width=5)
    t, cx, col = captions[0]
    bb = d.textbbox((0, 0), t, font=f1)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], 12 - bb[1]), t, font=f1, fill=col)
    s = "左：旧（较慢 · 曲线对称 ≈ 匀速）      右：新（更快 · 先快后缓）"
    bb = d.textbbox((0, 0), s, font=f2)
    d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], 54 - bb[1]), s, font=f2, fill=(215, 215, 215))
    img.save(path)
    return path


CLIPS = [
    ("kb", "输入金额 · 键盘升起   旧 300ms  →  新 220ms"),
    ("sheet", "输入密码 · 付款面板滑起   旧 300ms  →  新 240ms"),
]

parts = []
for name, title in CLIPS:
    lab = make_label(os.path.join(TMP, "lab_%s.png" % name),
                     [(title, 600, (255, 255, 255))])
    o = os.path.join(TMP, "old_%s.mp4" % name)
    n = os.path.join(TMP, "new_%s.mp4" % name)
    out = os.path.join(TMP, "ab_%s.mp4" % name)
    filt = ("[0:v]scale=600:1300[a];[1:v]scale=600:1300[b];"
            "[a][b]hstack=inputs=2[ab];"
            "[ab]drawbox=x=598:y=0:w=4:h=1300:color=0x6a6a6a@1:t=fill[hd];"
            "[hd]pad=1200:1388:0:88:color=0x171717[pad];"
            "[pad][2:v]overlay=0:0[v]")
    r = subprocess.run([FF, "-y", "-i", o, "-i", n, "-i", lab,
                        "-filter_complex", filt, "-map", "[v]",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                        "-r", "60", out], capture_output=True, text=True)
    print(name, "rc=", r.returncode, os.path.getsize(out) if os.path.exists(out) else "-")
    if r.returncode:
        print(r.stderr[-1200:])
    parts.append(out)

# 顺序拼接 + 整体循环 3 遍
lst = os.path.join(TMP, "list.txt")
with open(lst, "w", encoding="utf-8") as f:
    for _ in range(3):                       # 循环 3 遍，方便肉眼比较
        for p in parts:
            f.write("file '%s'\n" % p.replace("\\", "/"))

final = os.path.join(ROOT, "_ab_anim_cmp.mp4")
r = subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-r", "60", "-movflags", "+faststart", final],
                   capture_output=True, text=True)
print("final rc=", r.returncode, os.path.getsize(final) if os.path.exists(final) else "-")
p = subprocess.run([FF, "-i", final], capture_output=True, text=True)
for l in p.stderr.splitlines():
    if "Duration" in l or ("Stream #0" in l and "Video" in l):
        print("   ", l.strip())
