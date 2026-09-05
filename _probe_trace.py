# -*- coding: utf-8 -*-
"""调用级 tracing：对首次「打字不发」期间所有 _sleep_with_capture / _pump_wait / page.evaluate
计时，找出 1.17s 静默段花在哪个调用上。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
target = steps[1]["params"]["联系人"]
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()

    # 调用级 trace：包一层计时
    trace = []
    _orig_sleep = bot._sleep_with_capture
    def wrap_sleep(seconds):
        t0 = time.perf_counter()
        r = _orig_sleep(seconds)
        dt = (time.perf_counter() - t0) * 1000
        if dt >= 30:
            trace.append(("sleep", round(seconds, 3), round(dt, 1)))
        return r
    bot._sleep_with_capture = wrap_sleep

    _orig_ev = bot.page.evaluate
    def wrap_ev(expr, *a, **k):
        t0 = time.perf_counter()
        r = _orig_ev(expr, *a, **k)
        dt = (time.perf_counter() - t0) * 1000
        if dt >= 30:
            s = (expr if isinstance(expr, str) else str(expr))
            trace.append(("eval", s[:40], round(dt, 1)))
        return r
    bot.page.evaluate = wrap_ev

    bot.set_home_list(home_data)
    M._pump_wait(0.5)
    bot.open_chat(target)
    M._pump_wait(0.3)

    print("开始首次 打字不发 ...")
    t0 = time.perf_counter()
    M.execute_step(bot, "打字不发", {"内容": "身材不错呀 先试探一下", "停留": 0.5})
    wall = time.perf_counter() - t0
    print(f"墙钟 {wall:.3f}s, 慢调用({len(trace)})：")
    for kind, val, ms in trace:
        print(f"   [{kind}] {val:<45} 耗时 {ms}ms")
finally:
    try: bot.stop()
    except Exception: pass
