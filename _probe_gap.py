# -*- coding: utf-8 -*-
"""量化「键盘弹出 -> 首字符出现」的静默间隙。对比 cold / prewarm 两种模式。"""
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

def run(mode):
    bot = M.WeChatAuto(headless=True)
    try:
        M.ensure_frontend_running()
        bot.start()
        bot.set_home_list(home_data)
        M._pump_wait(0.5)
        bot.open_chat(target)
        M._pump_wait(0.3)
        if mode == "prewarm":
            bot._mute_sound = True
            try:
                box = bot.page.locator(".chat-txt")
                if box.count():
                    box.first.click(); bot._kb_show()
                    for l in "nihao": bot._kb_type(l, 30)
                    bot.page.evaluate("([w])=>window.__wxKeyboard&&window.__wxKeyboard.commitByPhrase(w)", ["你好"])
                    bot._set_input_value(box, "")
                bot.go_back_home(); M._pump_wait(0.3); bot.open_chat(target)
            except Exception as e:
                print("prewarm 异常:", e)
            finally:
                bot._mute_sound = False
            M._pump_wait(0.3)
        # 采样
        bot.page.evaluate("""
            () => {
                window.__samp = []; window.__sampStop = false;
                const rec = () => {
                    const box = document.querySelector('.chat-txt');
                    const kb = window.__wxKeyboard || {};
                    window.__samp.push({t: Math.round(performance.now()), kb: !!kb.visible,
                        in: box ? box.value : ''});
                    if (!window.__sampStop) setTimeout(rec, 30);
                }; rec();
            }
        """)
        t0 = time.perf_counter()
        M.execute_step(bot, "打字不发", {"内容": "身材不错呀 先试探一下", "停留": 0.5})
        wall = time.perf_counter() - t0
        bot.page.evaluate("window.__sampStop = true")
        M._pump_wait(0.2)
        samp = bot.page.evaluate("window.__samp")
        # 找键盘出现时刻 与 首字符出现时刻
        kb_t = next((s["t"] for s in samp if s["kb"]), None)
        ch_t = next((s["t"] for s in samp if s.get("in")), None)
        gap = (ch_t - kb_t) if (kb_t is not None and ch_t is not None) else None
        print(f"模式={mode:<8} 墙钟={wall:.3f}s  键盘出现={kb_t}ms  首字符={ch_t}ms  静默间隙={gap}ms" if gap is not None
              else f"模式={mode:<8} 墙钟={wall:.3f}s  未检出键盘/字符")
    finally:
        try: bot.stop()
        except Exception: pass

run("cold")
run("prewarm")
