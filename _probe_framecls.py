# -*- coding: utf-8 -*-
"""区分「真卡顿(画面该动却不动)」vs「静止停顿(画面没变化=正常)」。
抓首句期间 screencast 帧，按内容相似度分类每个大间隔：
  - 前后帧内容差异大却隔了很久  => 真卡(运动中断)
  - 帧内容相同 => 静止(自然停顿，非卡)
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M
from PIL import Image
import io

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_framecls"
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

def down(png_or_jpeg):
    im = Image.open(io.BytesIO(png_or_jpeg)).convert("L").resize((40, 80))
    return list(im.getdata())

def diff(a, b):
    if not a or not b: return 1.0
    s = 0
    for x, y in zip(a, b):
        s += abs(x - y)
    return s / (len(a) * 255)

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()
    _warm_texts = bot.collect_step_texts(steps)
    _warm_urls = []
    for _s in steps:
        for _v in (_s.get("params") or {}).values():
            if isinstance(_v, str):
                _warm_urls += M._ASSET_URL_RE.findall(_v)
    bot.warmup(texts=_warm_texts, urls=list(dict.fromkeys(_warm_urls)))
    fp = steps[0].get("params") or {}
    if steps[0].get("action") == "编辑主页":
        bot.set_home_list(fp.get("数据", fp.get("data")))
    bot._prewarm_input(steps)
    bot.reset_frames()
    bot.trim_head_sec = 0.0

    # 抓首句期间的原帧字节
    c0 = len(M._FRAMES)
    for idx, step in enumerate(steps[:3], start=1):
        M.execute_step(bot, step["action"], step.get("params") or {})
    c1 = len(M._FRAMES)
    with M._FRAME_LOCK:
        frames = M._FRAMES[c0:c1]

    print(f"抓取帧 {len(frames)}")
    # 解析时间戳+像素
    parsed = []
    for t, jpeg in frames:
        parsed.append((t, down(jpeg)))
    print("帧时间戳(秒)与相邻间隔分类:")
    for i in range(1, len(parsed)):
        t0, px0 = parsed[i-1]
        t1, px1 = parsed[i]
        dt = t1 - t0
        d = diff(px0, px1)
        if dt >= 0.09:   # >=90ms 的间隔才关注
            kind = "真卡(画面变化%%)" if d > 0.01 else "静止(无变化)"
            print(f"   #{i}  gap={dt*1000:>4.0f}ms  内容差异={d:.3f}  -> {kind}")
    # 汇总
    big_changed = []
    big_same = 0
    for i in range(1, len(parsed)):
        t0, px0 = parsed[i-1]; t1, px1 = parsed[i]
        dt = t1 - t0
        if dt >= 0.12:
            if diff(px0, px1) > 0.01:
                big_changed.append((dt, t1))
            else:
                big_same += 1
    print(f"\n[>=120ms] 画面变化(真卡) {len(big_changed)} 个;  画面相同(静止) {big_same} 个")
finally:
    try:
        bot.stop()
    except Exception:
        pass
