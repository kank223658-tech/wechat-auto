# -*- coding: utf-8 -*-
"""确定性转场重采引擎自检：真 Chrome + 真实 CSS transition。

跑法：py _test_det_transition.py
流程：Playwright 起 headless Chrome → 打开含 0.5s 线性 transition 的页面 →
evaluate 触发 → 立即调 WeChatAuto._det_transition（用 FakeBot 承载实例状态，
不走完整 WeChatAuto 初始化）→ 断言：
  1) 产出 ~30 帧（0.5s × 60fps）；
  2) 帧列首尾差异大（确实从起点推到终点）；
  3) 相邻帧差异小且均匀（没有跳变/重复）；
  4) _apply_det_spans 把窗口内实时帧替换为精确 1/60s 间隔的合成帧；
  5) 窗口外时间戳原样保留。
"""
import io
import sys
import time

from playwright.sync_api import sync_playwright
from PIL import Image

from main import WeChatAuto, FRAME_CAPTURE_FPS

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PAGE = """data:text/html,<html><body style="margin:0">
<div id="box" style="width:100px;height:100px;background:red;
     transition:transform 0.5s linear"></div>
<script>
function go(){ document.getElementById('box').style.transform = 'translateX(200px)'; }
function pos(){ const t = getComputedStyle(document.getElementById('box')).transform;
  return t; }
</script></body></html>"""


class FakeBot:
    """只承载 _det_transition/_apply_det_spans 所需的实例状态。"""


def diff01(ja, jb):
    ia = Image.open(io.BytesIO(ja)).convert("L").resize((32, 32)).load()
    ib = Image.open(io.BytesIO(jb)).convert("L").resize((32, 32)).load()
    s = 0.0
    for x in range(32):
        for y in range(32):
            s += abs(ia[x, y] - ib[x, y])
    return s / (32 * 32 * 255.0)


def main():
    bot = WeChatAuto.__new__(WeChatAuto)     # 跳过 __init__，只手工备齐所需状态
    bot._pump = None
    bot._cdp = None
    bot._audio_offset = 0.0
    bot._det_spans = []
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = browser.new_page(viewport={"width": 400, "height": 300})
        bot.page = page
        page.goto(PAGE)
        page.wait_for_timeout(500)
        page.evaluate("go()")
        t0 = time.time()
        ok = WeChatAuto._det_transition(bot, "测试转场")
        wall = time.time() - t0
        browser.close()

    if not ok:
        print("FAIL: _det_transition 返回 False")
        return 1
    spans = bot._det_spans
    if len(spans) != 1:
        print(f"FAIL: 应登记 1 个窗口，实际 {len(spans)}")
        return 1
    sp = spans[0]
    n = len(sp["frames"])
    print(f"[i] 重采 {n} 帧（{n/60:.2f}s），墙钟 {wall:.2f}s，"
          f"窗口 {sp['t1']-sp['t0']:.3f}s")
    if not (24 <= n <= 36):
        failures.append(f"帧数 {n} 偏离 30（0.5s×60fps）")
    d_first_last = diff01(sp["frames"][0], sp["frames"][-1])
    if d_first_last < 0.02:
        failures.append(f"首尾帧差异过小({d_first_last:.4f})，动画没推进")
    d_step = [diff01(sp["frames"][i], sp["frames"][i + 1]) for i in range(n - 1)]
    big = sum(1 for d in d_step if d > 0.02)
    dup = sum(1 for d in d_step if d < 0.0005)
    if big > 2:
        failures.append(f"相邻帧出现 {big} 处跳变（>0.02），步进不均匀")
    if dup > n // 3:
        failures.append(f"{dup} 帧完全重复，currentTime 推进可能失效")
    print(f"[i] 首尾差异 {d_first_last:.4f}，相邻帧差异中位 "
          f"{sorted(d_step)[len(d_step)//2]:.4f}，跳变 {big}，重复 {dup}")

    # _apply_det_spans 替换验证：构造实时帧列（窗口前正常 / 窗口内失真 / 窗口后正常）
    t0c = sp["t0"]
    real = [(t0c - 0.5 + i / 60.0, b"pre") for i in range(30)]          # 窗口前
    real += [(t0c + i * (0.5 / 20.0), b"bad") for i in range(20)]       # 窗口内失真帧
    real += [(sp["t1"] + 0.3 + i / 60.0, b"post") for i in range(30)]   # 窗口后
    out = WeChatAuto._apply_det_spans(bot, real)
    bad_left = sum(1 for ts, d in out if d == b"bad")
    det_left = sum(1 for ts, d in out if d not in (b"pre", b"post"))
    pre_ts = [ts for ts, d in out if d == b"pre"]
    post_ts = [ts for ts, d in out if d == b"post"]
    if bad_left:
        failures.append(f"窗口内还有 {bad_left} 帧未替换")
    if det_left != n:
        failures.append(f"合成帧应 {n} 帧，实际 {det_left}")
    if len(pre_ts) != 30 or len(post_ts) != 30:
        failures.append("窗口外帧数量不对")
    gaps = sorted({round(post_ts[i+1]-post_ts[i], 6) for i in range(len(post_ts)-1)})
    if gaps and abs(gaps[0] - 1/60.0) > 1e-6:
        failures.append(f"窗口外帧间隔被改动: {gaps[:3]}")
    step = sorted({round(out[i+1][0]-out[i][0], 6)
                   for i in range(len(out)-1) if out[i][1] not in (b"pre", b"post")})
    if step and abs(min(step) - 1/60.0) > 1e-6:
        failures.append(f"合成帧间隔不是 1/60: {step[:3]}")
    print(f"[i] 替换后 {len(out)} 帧（pre 30 + det {det_left} + post 30），"
          f"窗口外时间戳未动")

    if failures:
        print("FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS  确定性重采引擎全部断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
