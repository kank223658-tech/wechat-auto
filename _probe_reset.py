# -*- coding: utf-8 -*-
"""验证：prewarm 之后是否因再次 set_home_list(编辑主页) 把引擎刷冷，导致首打字又回到冷 gap。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
home_data = wf["steps"][0]["params"]["数据"]
target = wf["steps"][1]["params"]["联系人"]
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

def gap_after_kb(bot):
    bot.page.evaluate("""
        () => { window.__s=[]; window.__stop=false;
            const r=()=>{const b=document.querySelector('.chat-txt');const k=window.__wxKeyboard||{};
                window.__s.push({t:Math.round(performance.now()),kb:!!k.visible,in:b?b.value:''});
                if(!window.__stop) setTimeout(r,30);}; r(); }
    """)
    t0=time.perf_counter()
    M.execute_step(bot,"打字不发",{"内容":"身材不错呀 先试探一下","停留":0.5})
    wall=time.perf_counter()-t0
    bot.page.evaluate("window.__stop=true")
    M._pump_wait(0.2)
    s=bot.page.evaluate("window.__s")
    kbt=next((x['t'] for x in s if x['kb']),None)
    ct=next((x['t'] for x in s if x.get('in')),None)
    gap=(ct-kbt) if (kbt is not None and ct is not None) else None
    return wall,gap

def run(label, reapply):
    bot=M.WeChatAuto(headless=True)
    try:
        M.ensure_frontend_running(); bot.start()
        bot.set_home_list(home_data); M._pump_wait(0.5); bot.open_chat(target); M._pump_wait(0.3)
        # prewarm
        bot._mute_sound=True
        try:
            box=bot.page.locator(".chat-txt")
            if box.count():
                box.first.click(); bot._kb_show()
                for l in "nihao": bot._kb_type(l,30)
                bot.page.evaluate("([w])=>window.__wxKeyboard&&window.__wxKeyboard.commitByPhrase(w)",["你好"])
                bot._set_input_value(box,"")
            bot.go_back_home(); M._pump_wait(0.3)
            if reapply:
                bot.set_home_list(home_data); M._pump_wait(0.3)  # 模拟 step1 编辑主页重复应用
            bot.open_chat(target); M._pump_wait(0.3)
        finally:
            bot._mute_sound=False
        wall,gap=gap_after_kb(bot)
        print(f"{label:<28} 墙钟={wall:.3f}s  键盘->首字 静默={gap}ms")
    finally:
        try: bot.stop()
        except Exception: pass

run("cold(无prewarm)", False)
run("prewarm(不重应用编辑主页)", False)
run("prewarm+重复set_home_list", True)
