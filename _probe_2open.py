# -*- coding: utf-8 -*-
"""连续打开两次聊天：判断 open_chat 冻结是「首次挂载」还是「每次挂载都冷」。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_2open"
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

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

    def open_and_gaps(tag):
        c0 = len(M._FRAMES)
        t0 = time.perf_counter()
        bot.open_chat("懒猫不懒")
        dt = time.perf_counter() - t0
        M._pump_wait(0.25)
        c1 = len(M._FRAMES)
        with M._FRAME_LOCK:
            ts = [t for t, _j in M._FRAMES[c0:c1]]
        gaps = sorted([(ts[i]-ts[i-1], ts[i]) for i in range(1, len(ts))], key=lambda x: -x[0])
        print(f"[{tag}] 墙钟 {dt*1000:.0f}ms 帧{len(ts)} 最大间隙={gaps[0][0]*1000:.0f}ms" if gaps else f"[{tag}] 墙钟 {dt*1000:.0f}ms 无帧")
        return gaps[0][0]*1000 if gaps else 0

    open_and_gaps("第1次 open_chat")
    bot.go_back_home()
    M._pump_wait(0.3)
    open_and_gaps("第2次 open_chat")
    bot.go_back_home()
    M._pump_wait(0.3)
    open_and_gaps("第3次 open_chat")
finally:
    try:
        bot.stop()
    except Exception:
        pass
