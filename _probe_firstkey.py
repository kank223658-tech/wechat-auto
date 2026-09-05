# -*- coding: utf-8 -*-
"""测首次 pressType('s') 的延迟 vs 后续键，区分「首键引擎懒加载」和「Python 等待」。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
home_data = wf["steps"][0]["params"]["数据"]
target = wf["steps"][1]["params"]["联系人"]
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()
    bot.set_home_list(home_data)
    M._pump_wait(0.5)
    bot.open_chat(target)
    M._pump_wait(0.3)

    box = bot.page.locator(".chat-txt")
    box.first.click()
    bot._kb_show()
    # 切到拼音、复位 shift（这是首键前必做的）
    bot.page.evaluate("(m)=>window.__wxKeyboard&&window.__wxKeyboard.setImeMode(m)", 'pinyin')
    bot.page.evaluate("window.__wxKeyboard&&window.__wxKeyboard.setShift('off')")

    # 测首键
    t0 = time.perf_counter()
    bot._kb_type("s", 80)
    dt_first = time.perf_counter() - t0
    v1 = box.first.input_value()
    print(f"首键 pressType('s') 耗时 {dt_first*1000:.1f}ms, 上屏=[{v1}]")

    # 测第二/三键（应更快）
    for ch in ["h", "e"]:
        t0 = time.perf_counter()
        bot._kb_type(ch, 80)
        dt = time.perf_counter() - t0
        print(f"后续键 pressType('{ch}') 耗时 {dt*1000:.1f}ms, 上屏=[{box.first.input_value()}]")

    # 若首键显著慢于后续键 => 引擎首次懒加载 schema
finally:
    try: bot.stop()
    except Exception: pass
