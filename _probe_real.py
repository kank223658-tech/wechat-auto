# -*- coding: utf-8 -*-
"""复刻 main.py 真实顺序并测首个 打字不发 的 键盘->首字 gap。
顺序：warmup(预应用编辑主页) -> _prewarm_input -> reset_frames ->
      step1 编辑主页 -> step2 打开聊天 -> step3 打字不发。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]

M.SPEED = 1.0
M.TYPE_SPEED = 40.0

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()

    # warmup: 预应用 step0 编辑主页 + 预热
    try:
        bot.warmup(texts=bot.collect_step_texts(steps), urls=[])
        _fp = (steps[0].get("params") or {})
        if steps[0].get("action") == "编辑主页":
            bot.set_home_list(_fp.get("数据", _fp.get("data")))
    except Exception as e:
        print("[warmup 跳过]", e)
    bot._prewarm_input(steps)
    bot.reset_frames()

    # step1 编辑主页
    M.execute_step(bot, "编辑主页", steps[0]["params"])
    # step2 打开聊天
    M.execute_step(bot, "打开聊天", steps[1]["params"])
    M._pump_wait(0.3)

    # 采样
    bot.page.evaluate("""
      () => { window.__s=[]; window.__stop=false;
        const r=()=>{const b=document.querySelector('.chat-txt');const k=window.__wxKeyboard||{};
          window.__s.push({t:Math.round(performance.now()),kb:!!k.visible,in:b?b.value:''});
          if(!window.__stop) setTimeout(r,30);}; r(); }
    """)
    t0=time.perf_counter()
    M.execute_step(bot, "打字不发", {"内容":"身材不错呀 先试探一下","停留":0.5})
    wall=time.perf_counter()-t0
    bot.page.evaluate("window.__stop=true")
    M._pump_wait(0.2)
    s=bot.page.evaluate("window.__s")
    kbt=next((x['t'] for x in s if x['kb']),None)
    ct=next((x['t'] for x in s if x.get('in')),None)
    gap=(ct-kbt) if (kbt is not None and ct is not None) else None
    print(f"真实顺序 [step2->step3] 键盘->首字 静默={gap}ms, step3 墙钟={wall:.3f}s")
finally:
    try: bot.stop()
    except Exception: pass
