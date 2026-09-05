# -*- coding: utf-8 -*-
"""定位「首条消息打字期间 ~0.5-0.75s 无帧」的精确归属：
预热后，给 page 每次 CDP 往返计时 + 每操作后记录帧数，
按操作打印耗时与「该操作区间内是否有长帧间隙」。
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

M.SPEED = 1.0
M.TYPE_SPEED = 40.0

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
target = steps[1]["params"]["联系人"]

bot = M.WeChatAuto(headless=True)
ops = []
try:
    M.ensure_frontend_running()
    bot.start()
    bot.warmup(texts=bot.collect_step_texts(steps), urls=[])
    bot.set_home_list(home_data)
    bot._prewarm_workflow(steps)
    M._wusong_words()
    bot.reset_frames()
    bot.trim_head_sec = 0.0

    def nf():
        with M._FRAME_LOCK:
            return len(M._FRAMES)

    # 记录每操作时间 + 操作前后帧数
    def log(label, t0, f0):
        ops.append((label, (time.perf_counter()-t0)*1000, nf()-f0))

    t = time.perf_counter(); f = nf()
    bot.open_chat(target)
    log("open_chat", t, f)

    box = bot.page.locator(".chat-txt")
    t = time.perf_counter(); f = nf()
    box.first.click()
    log("box.click 聚焦", t, f)

    t = time.perf_counter(); f = nf()
    M._pump_wait(0.2)
    log("聚焦后等待200ms", t, f)

    t = time.perf_counter(); f = nf()
    bot.human_type(".chat-txt", "身材不错呀", send=False, show_keyboard=True)
    log("human_type(身材不错呀)", t, f)
    M._pump_wait(0.2)

    # 再打第二句看是否还有冻结
    box2 = bot.page.locator(".chat-txt")
    bot._set_input_value(box2, "")
    t = time.perf_counter(); f = nf()
    bot.human_type(".chat-txt", "我去拿搓澡巾", send=False, show_keyboard=False)
    log("human_type(第2句 键盘已开)", t, f)
    M._pump_wait(0.2)

finally:
    try: bot.stop()
    except Exception: pass

print("\n== 操作计时 ==")
for label, dt, df in ops:
    print(f"   {label:30s} {dt:7.1f}ms   帧增量={df}")

# 帧间隙归属：某间隙落在哪个操作区间内
with M._FRAME_LOCK:
    frames = list(M._FRAMES)
if frames:
    ts = [x[0] for x in frames]
    print(f"\n== 全流程帧间隙 >60ms ==")
    for i in range(1, len(ts)):
        g = (ts[i]-ts[i-1])*1000
        if g > 60:
            print(f"   gap {g:.0f}ms @ 帧#{i} ts={ts[i]:.3f}")