# -*- coding: utf-8 -*-
"""_frame_health 单元自检：直接调用 main.py 真函数（不依赖浏览器，合成 JPEG 帧）。

跑法：py _test_quality_gate.py
覆盖：动态断流（该报）/ 静止长间隔（不该报）/ 硬切窗内（不该报）/ trim 裁头 /
空帧边界 / 多处断流计数。帧数据用 bytes（与采集缓存 base64 str 同样兼容）。
"""
import io
import sys

import main
from PIL import Image

FH = main.WeChatAuto._frame_health
GAP_MAX = main.QUALITY_GAP_MAX_SEC
DIFF_EPS = main.QUALITY_DYNAMIC_DIFF
assert GAP_MAX == 0.15 and DIFF_EPS == 0.05, "常量被改动，测试阈值需同步"


def jpeg(im):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def solid(color):
    return Image.new("RGB", (60, 130), color)


def grad(p):
    """渐变图（两张不同 p 差异明显，模拟断流期间画面在动）。"""
    im = Image.new("RGB", (60, 130))
    px = im.load()
    for x in range(60):
        for y in range(130):
            v = (x * 4 + y * 2 + p) % 256
            px[x, y] = (v, v, v)
    return im


def seq60(n, t0=0.0, color=(20, 20, 20)):
    """60fps 连续静止帧。"""
    return [(t0 + i / 60.0, jpeg(solid(color))) for i in range(n)]


failures = []

# 1) 正常录制：纯静止 60fps×90 帧 → 通过
r = FH(seq60(90))
if not r["ok"] or r["frames"] != 90:
    failures.append(f"case1 应通过却报断流: {r}")

# 2) 动态断流：静止 30 帧 + 0.3s 空窗 + 画面变了 → 必须报 1 处
frames = seq60(30)
t_gap = 29 / 60.0
frames += [(t_gap + 0.30, jpeg(grad(100)))] + seq60(20, t0=t_gap + 0.30 + 1 / 60.0)
r = FH(frames)
if r["ok"] or r["suspect_count"] != 1 or not (0.28 < r["suspects"][0]["gap"] < 0.32):
    failures.append(f"case2 应报 1 处动态断流: {r}")

# 3) 静止长间隔：同样的 0.3s 空窗，前后画面一样 → 不报
frames = seq60(30)
frames += [(t_gap + 0.30, jpeg(solid((20, 20, 20))))] + seq60(20, t0=t_gap + 0.30 + 1 / 60.0)
r = FH(frames)
if not r["ok"]:
    failures.append(f"case3 静止等待不应报: {r}")

# 4) 硬切窗内断流：0.3s 空窗 + 画面变了，但落在 hard_cut_spans → 不报
frames = seq60(30)
frames += [(t_gap + 0.30, jpeg(grad(100)))] + seq60(20, t0=t_gap + 0.30 + 1 / 60.0)
r = FH(frames, hard_cut_spans=[(t_gap - 0.01, t_gap + 0.31)])
if not r["ok"]:
    failures.append(f"case4 硬切窗内不应报: {r}")

# 5) trim：加载期内的断流被裁掉 → 通过
frames = [(0.0, jpeg(solid((0, 0, 0)))), (0.10, jpeg(grad(50)))] + seq60(30, t0=0.25)
r = FH(frames, trim_sec=0.2)
if not r["ok"]:
    failures.append(f"case5 trim 后应通过: {r}")

# 6) 边界：空帧 ok=False；单帧 ok=True
if FH([]).get("ok") is not False:
    failures.append(f"case6a 空帧应 ok=False: {FH([])}")
if not FH([(1.0, jpeg(solid((0, 0, 0))))])["ok"]:
    failures.append("case6b 单帧应 ok=True")

# 7) 两个独立断流 → 计数 2
frames = seq60(30)
t1 = 29 / 60.0
frames += [(t1 + 0.3, jpeg(grad(100)))] + seq60(10, t0=t1 + 0.3 + 1 / 60.0)
t2 = t1 + 0.3 + 11 / 60.0
frames += [(t2 + 0.25, jpeg(grad(200)))] + seq60(10, t0=t2 + 0.25 + 1 / 60.0)
r = FH(frames)
if r["suspect_count"] != 2:
    failures.append(f"case7 应报 2 处: {r}")

# 8) base64 字符串帧（与 _FRAMES 实际存储格式一致）→ 结果与 bytes 一致
import base64
r_b = FH(frames)
r_s = FH([(ts, base64.b64encode(d).decode()) for ts, d in frames])
if r_b != r_s:
    failures.append(f"case8 base64 与 bytes 结果应一致: {r_b} vs {r_s}")

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print(f"PASS 8/8  (真函数 main.WeChatAuto._frame_health, 阈值 gap={GAP_MAX}s diff={DIFF_EPS})")
