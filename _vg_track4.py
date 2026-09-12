# -*- coding: utf-8 -*-
"""成品视频输入栏位移追踪 v4（自校准）：
   1) 先用「从底向上找连续亮面」粗定位一帧「收起态」（输入栏在最底部）作为模板帧；
   2) 再用该帧的输入栏横带做全宽 SSD 模板匹配，逐帧求输入栏顶边 y。
   这样不依赖任何人工给定的帧号，可对任意一段成品视频直接跑。

用法：py _vg_track4.py
"""
import os, sys, glob
import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = r"G:\weixin-auto\_vg"
fs = sorted(glob.glob(os.path.join(OUT, "f_*.png")))
N = len(fs)
arrs = [np.asarray(Image.open(f).convert("L"), dtype=np.float32) for f in fs]
H, W = arrs[0].shape
print("帧数 %d (%d fps)  尺寸 %dx%d  时长≈%.2fs" % (N, 30, W, H, N / 30.0))

X0, X1 = int(0.02 * W), int(0.99 * W)
MID0, MID1 = int(0.14 * W), int(0.84 * W)


def block_top(a):
    """从画面底部向上走，找连续亮面（输入栏+当前面板）的顶边；收起态即输入栏顶边"""
    m = np.convolve(a[:, MID0:MID1].mean(axis=1), np.ones(5) / 5.0, mode="same")
    y = H - 6
    lim = int(0.40 * H)
    while y > lim:
        if m[y - 1] > 19:
            y -= 1
        elif m[max(0, y - 6):y].mean() > 19:
            y -= 6
        else:
            break
    return y


tos = [block_top(a) for a in arrs]
vals = [t for t in tos if t]
print("block_top 分布: min=%d max=%d" % (min(vals), max(vals)))
# 模板帧：必须是「稳定平台」里的帧（相邻 ±4 帧同值），且亮面本身够高（≥45px，
# 排除「首页输入栏+底部 Tab 栏」那种贴底的短亮块），取其中 block_top 最大者
# （输入栏最低 = 聊天页收起态，整块亮面从输入栏顶一直延到画面底部，模板最完整）。
def stable(i):
    return 8 <= i < N - 8 and tos[i] == tos[i - 8] == tos[i + 8]
# 只在「后半段」找模板帧：视频开头往往还在路由转场/上滑入页，帧内容带运动，
# 拿它当模板会让整条轨迹系统性偏移一个模板高。后半段一定是稳定的聊天页。
cands = [i for i in range(N // 3, N) if stable(i) and tos[i] and tos[i] <= H - 45]
if not cands:
    cands = [i for i in range(N) if tos[i] and tos[i] <= H - 45]
if not cands:
    cands = [i for i in range(N) if tos[i]]
# 同为最大时取最靠后的那帧（最稳）
tmpl_i = max(cands, key=lambda i: (tos[i], i))
ty = tos[tmpl_i]
print("模板帧 = %d  block_top=%d (%.3fH, canvas %.0f)" % (tmpl_i, ty, ty / H, ty / 1.8))

TY0, TY1 = ty, ty + 29
tpl = arrs[tmpl_i][TY0:TY1, X0:X1].copy()
th = TY1 - TY0
print("模板 %d 行 x %d 列（原图 y %d-%d）" % (th, tpl.shape[1], TY0, TY1))

YS = np.arange(int(0.20 * H), H - th)
pbuf = [a[:, X0:X1] for a in arrs]
trace = np.zeros(N, dtype=np.float32)
err = np.zeros(N, dtype=np.float32)
for i in range(N):
    best, by = 1e18, -1
    for y in YS:
        d = pbuf[i][y:y + th] - tpl
        v = (d * d).mean()
        if v < best:
            best, by = v, y
    trace[i], err[i] = by, best
np.save(os.path.join(OUT, "trace4.npy"), trace)
print("平均匹配残差 %.1f" % err.mean())

CANVAS = 1 / 0.45
print("\n--- 位置轨迹（每 0.1s，strip y / canvas y） ---")
line = []
for i in range(0, N, 3):
    line.append("%.1f:%d/%.0f" % (i / 30.0, trace[i], trace[i] * CANVAS))
    if len(line) == 6:
        print("  " + "  ".join(line)); line = []
if line:
    print("  " + "  ".join(line))

THR = 6.0
plateaus, cur = [], [0]
for i in range(1, N):
    if abs(trace[i] - trace[cur[-1]]) > THR:
        if i - cur[0] >= 8:
            plateaus.append((cur[0], i - 1, float(np.median(trace[cur[0]:i]))))
        cur = [i]
if N - cur[0] >= 8:
    plateaus.append((cur[0], N - 1, float(np.median(trace[cur[0]:N]))))

LUT = [(1171, "收起"), (702, "键盘"), (629, "表情"), (793, "更多")]
print("\n--- 平台（稳态） ---")
named = []
for k, (a, b, y) in enumerate(plateaus):
    cv = y * CANVAS
    nm, dd = min(((n, abs(cv - v)) for v, n in LUT), key=lambda z: z[1])
    nm = nm if dd < 60 else "?"
    named.append((a, b, y, nm))
    print("  平台%2d frames %4d-%4d  t=%5.2f~%5.2f  canvas=%4.0f  -> %s (偏差%.0f)"
          % (k, a, b, a / 30.0, b / 30.0, cv, nm, dd))

print("\n--- 各段切换 ---")
for k in range(len(named) - 1):
    a, b, y0, n0 = named[k]
    b2, c, y1, n1 = named[k + 1]
    seg = trace[a:c + 1]
    mv = np.where(np.abs(seg - seg[0]) > 4)[0]
    if not len(mv):
        continue
    i0, i1 = mv[0], mv[-1]
    d = np.diff(seg)
    sg = np.sign(d[np.abs(d) > 1.0])
    mono = "单调✓" if (len(sg) == 0 or np.all(sg == sg[0])) else "★非单调!"
    print("  %-9s y %3.0f→%3.0f (canvas %+5.0f)  帧%d~%d  行程%4.0fms  %s"
          % ("%s→%s" % (n0, n1), seg[0], seg[-1], (seg[-1] - seg[0]) * CANVAS,
             a + i0, a + i1, (i1 - i0) / 30.0 * 1000, mono))
    print("      逐帧: " + " ".join("%.0f" % v for v in seg))

print("\n--- 相邻稳态之间的间隔（切换起点到下一个切换起点） ---")
for k in range(len(named) - 1):
    a, b, y0, n0 = named[k]
    c, d2, y1, n1 = named[k + 1]
    print("  %-9s  %.2fs" % ("%s→%s" % (n0, n1), (c - a) / 30.0))
