# -*- coding: utf-8 -*-
import sys
import numpy as np
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def load(p, size=(112, 112)):
    return np.asarray(Image.open(p).convert("RGB").resize(size)).astype(np.int16)

cover = load(r"G:/weixin-auto/_fs/true_cover.png")
video_pre = load(r"G:/weixin-auto/_fs/t_video_preopen.png")
video_post = load(r"G:/weixin-auto/_fs/t_video_post.png")
minimg = load(r"G:/weixin-auto/_fs/min_dsf3.png")
# 从 min 截图裁 m1（第一个盒子）：DSF3, 盒子在 (8,8)+112*3
m1 = np.asarray(Image.open(r"G:/weixin-auto/_fs/min_dsf3.png").convert("RGB").crop((24, 24, 24+336, 24+336)).resize((112,112))).astype(np.int16)

pairs = [("video_pre vs true_cover", video_pre, cover),
         ("video_post vs true_cover", video_post, cover),
         ("video_pre vs video_post", video_pre, video_post),
         ("min_m1 vs true_cover", m1, cover),
         ("min_m1 vs video_pre", m1, video_pre),
         ("min_m1 vs video_post", m1, video_post)]
for name, a, b in pairs:
    d = np.abs(a - b).mean()
    print("%-28s 平均差 %6.1f" % (name, d))
