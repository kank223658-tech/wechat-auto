# -*- coding: utf-8 -*-
"""测量「第一次打开键盘准备打字」前 2 秒的精确分解。

对比三种路径：
  A) 冷启动：全新页面 -> apply 编辑主页 -> open_chat -> 首次 kb_show + 首个 打字不发
  B) 带 prewarm（对齐 main.py）：prewarm 后再走首个打字不发
同时 WX_PERF=1 dump __wxPerfLog（show/首键/引擎回填 各段 ms）。
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
os.environ["WX_PERF"] = "1"
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
target = steps[1]["params"]["联系人"]

M.SPEED = 1.0
M.TYPE_SPEED = 40.0

def measure_first_typing(mode):
    bot = M.WeChatAuto(headless=True)
    try:
        M.ensure_frontend_running()
        bot.start()
        bot.page.evaluate("window.__wxPerf = true; window.__wxPerfLog = [];")
        # apply 编辑主页
        bot.set_home_list(home_data)
        M._pump_wait(0.5)
        # 打开首个会话
        bot.open_chat(target)
        M._pump_wait(0.3)
        if mode == "prewarm":
            # 模拟 prewarm_input：开键盘打几个拼音清空再返回主页，再重新打开会话
            bot._mute_sound = True
            try:
                box = bot.page.locator(".chat-txt")
                if box.count():
                    box.first.click()
                    bot._kb_show()
                    for letter in "nihao":
                        bot._kb_type(letter, 30)
                    bot.page.evaluate("([w]) => window.__wxKeyboard && window.__wxKeyboard.commitByPhrase(w)", ["你好"])
                    bot._set_input_value(box, "")
                bot.go_back_home()
                M._pump_wait(0.3)
                bot.open_chat(target)
            except Exception as e:
                print("prewarm 异常(忽略):", e)
            finally:
                bot._mute_sound = False
            M._pump_wait(0.3)
        # 清空 perf log，只留首次真实打字的记录
        bot.page.evaluate("window.__wxPerfLog = []; window.__lt = [];")
        # 注入 longtask
        bot.page.evaluate("""
            () => {
                window.__lt = [];
                try { new PerformanceObserver((l)=>l.getEntries().forEach(e=>window.__lt.push({start:Math.round(e.startTime),dur:Math.round(e.duration)})))
                  .observe({entryTypes:['longtask']}); } catch(e){}
            }
        """)
        # 首次打字（首个 打字不发 "身材不错呀 先试探一下"）
        t0 = time.perf_counter()
        M.execute_step(bot, "打字不发", {"内容": "身材不错呀 先试探一下", "停留": 0.5})
        wall = time.perf_counter() - t0
        plog = bot.page.evaluate("window.__wxPerfLog || []")
        lt = bot.page.evaluate("window.__lt || []")
        print(f"\n===== 模式: {mode} | 首次打字不发 墙钟 {wall:.3f}s =====")
        for e in plog:
            print(f"   [perf] {e.get('label','?'):<26} dt={e.get('dt','?'):>6}ms  total={e.get('total','?'):>7}ms  detail={e.get('detail','')}")
        big = [e for e in lt if e['dur'] >= 150]
        print(f"   长任务(>=150ms) {len(big)} 条:", big[:6])
    finally:
        try: bot.stop()
        except Exception: pass

measure_first_typing("cold")
measure_first_typing("prewarm")
