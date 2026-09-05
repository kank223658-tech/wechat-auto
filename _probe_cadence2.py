# -*- coding: utf-8 -*-
"""生产路径复刻（预热+reset）下测采集节奏：
1) 第一条「打字不发」（CJK+空格混合 → pressRun 为主）
2) 含数字/字母的句子（"干搓 50 加盐 10 全身 spa100" → 部分走逐字 Python 往返）
统计每阶段的采集帧间隔分布。piece 由环境变量 PIECE 指定。
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

PIECE = float(os.environ.get("PIECE", "0.02"))
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

def make_pump(piece):
    def pump(seconds):
        if seconds <= 0:
            return
        bot = M._PUMP_BOT
        page = getattr(bot, "page", None) if bot is not None else None
        if page is None or page.is_closed():
            time.sleep(seconds); return
        while seconds > 0:
            wait = min(piece, seconds)
            try:
                page.wait_for_timeout(max(1, int(wait * 1000)))
            except Exception:
                time.sleep(wait)
            seconds -= wait
    return pump

def gaps_report(tag, ts):
    if not ts:
        print(f"[{tag}] 无帧"); return
    gs = sorted(ts[i]-ts[i-1] for i in range(1, len(ts)))
    n = len(gs)
    avg = sum(gs)/n
    p50 = gs[n//2]
    p90 = gs[min(n-1, int(n*0.90))]
    over17 = sum(1 for g in gs if g > 0.017)
    over33 = sum(1 for g in gs if g > 0.033)
    over80 = sum(1 for g in gs if g > 0.080)
    print(f"[{tag}] 帧={n} 平均={avg*1000:.1f}ms 中位={p50*1000:.1f}ms "
          f"p90={p90*1000:.1f}ms max={gs[-1]*1000:.0f}ms "
          f">17ms:{over17} >33ms:{over33} >80ms:{over80}")
    if n <= 40:
        print(f"   明细(ms): {[round(g*1000) for g in gs]}")

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]

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
    orig = M._pump_wait
    M._pump_wait = make_pump(PIECE)

    # 1) 首条打字不发（第一句，键盘从收起→弹出）
    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot.open_chat("懒猫不懒")
    bot.human_type(".chat-txt", "身材不错呀 先试探一下", send=False, show_keyboard=True)
    dtw = time.perf_counter() - t0
    M._pump_wait(0.15)
    ts = [t for t, _j in M._FRAMES[c0:]]
    gaps_report(f"句1 打字不发(piece={PIECE*1000:.0f}ms wall={dtw*1000:.0f}ms)", ts)
    g1 = [(round((ts[i]-ts[i-1])*1000), i) for i in range(1, len(ts))]
    g1.sort(reverse=True)
    print(f"   句1 前8大间隙: idx={[x[1] for x in g1[:8]]} ms={[x[0] for x in g1[:8]]}")

    # 2) 含数字/英文的段（逐字路径）
    bot._set_input_value(bot.page.locator(".chat-txt"), "")
    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot.human_type(".chat-txt", "干搓 50 加盐 10 全身 spa100", send=False, show_keyboard=False)
    dtw = time.perf_counter() - t0
    M._pump_wait(0.15)
    ts = [t for t, _j in M._FRAMES[c0:]]
    gaps_report(f"句2 混合数字(piece={PIECE*1000:.0f}ms wall={dtw*1000:.0f}ms)", ts)

    # 3) 纯数字/标点句
    bot._set_input_value(bot.page.locator(".chat-txt"), "")
    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot.human_type(".chat-txt", "666 ?!", send=False, show_keyboard=False)
    dtw = time.perf_counter() - t0
    M._pump_wait(0.15)
    ts = [t for t, _j in M._FRAMES[c0:]]
    gaps_report(f"句3 纯数字标点(piece={PIECE*1000:.0f}ms wall={dtw*1000:.0f}ms)", ts)
finally:
    try: bot.stop()
    except Exception: pass