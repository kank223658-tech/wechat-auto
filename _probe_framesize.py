# -*- coding: utf-8 -*-
"""统计 screencast 推送帧的字节数/解码尺寸分布：验证「超宽大帧」是否是偶发卡顿源。
复刻首条消息阶段，在 _on_screencast_frame 中顺带记录 jpeg 字节数；
帧 > 300KB 的再做 PIL 解码量尺寸（只对样本）。
"""
import sys, os, json, time, io
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M
from PIL import Image

M.SPEED = 1.0
M.TYPE_SPEED = 40.0

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
target = steps[1]["params"]["联系人"]

sizes = []          # (nbytes, wall_dt_of_decode) 采样
big_samples = []    # 大帧的尺寸

_orig = M.WeChatAuto._on_screencast_frame
def patched(self, params):
    L = self.page
    try:
        jpeg = __import__("base64").b64decode(params["data"])
    except Exception:
        jpeg = b""
    if jpeg:
        sizes.append(len(jpeg))
    _orig(self, params)
M.WeChatAuto._on_screencast_frame = patched

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()
    bot.warmup(texts=bot.collect_step_texts(steps), urls=[])
    bot.set_home_list(home_data)
    bot._prewarm_workflow(steps)
    M._wusong_words()
    bot.reset_frames()
    bot.trim_head_sec = 0.0

    # 首条消息 + 键盘
    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot.open_chat(target)
    bot.human_type(".chat-txt", "身材不错呀 先试探一下", send=False, show_keyboard=True)
    dt = time.perf_counter() - t0
    M._pump_wait(0.2)
    with M._FRAME_LOCK:
        frames = M._FRAMES[c0:]
finally:
    try: bot.stop()
    except Exception: pass

# 统计
import statistics
if sizes:
    s = sorted(sizes)
    print(f"帧字节数: n={len(s)} 最小={s[0]} 中位={s[len(s)//2]} 平均={int(sum(s)/len(s))} "
          f"p95={s[min(len(s)-1,int(len(s)*0.95))]} 最大={s[-1]}")
    big = sum(1 for x in s if x > 400_000)
    print(f"  >400KB: {big} 个 (>200KB: {sum(1 for x in s if x>200_000)})")
# 从 _FRAMES 中抽查最大帧的尺寸
if frames:
    biggest = sorted(frames, key=lambda f: -len(f[1]))[:3]
    for ts, jpeg in biggest:
        try:
            im = Image.open(io.BytesIO(jpeg))
            print(f"  最大帧 ts={ts:.3f} 尺寸={im.size} 字节={len(jpeg)}")
        except Exception as e:
            print(f"  最大帧解码失败: {e}")
print(f"首条消息墙钟 {dt*1000:.0f}ms")