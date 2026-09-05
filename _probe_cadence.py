# -*- coding: utf-8 -*-
"""验证「_pump_wait 分片粒度限制 screencast 采集节奏」：
打开聊天(页面滑入动画)期间，用不同 piece(20ms vs 8ms)泵帧，
统计采集帧间隔分布。piece 由环境变量 PIECE 指定（秒）。
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
    gs = [ts[i]-ts[i-1] for i in range(1, len(ts))]
    if not gs:
        print(f"[{tag}] 无帧"); return
    gs.sort()
    n = len(gs)
    avg = sum(gs)/n
    mid = gs[n//2] if n % 2 else (gs[n//2-1]+gs[n//2])/2
    p90 = gs[min(n-1, int(n*0.90))]
    over17 = sum(1 for g in gs if g > 0.017)
    over33 = sum(1 for g in gs if g > 0.033)
    print(f"[{tag}] 帧={n} 平均间隔={avg*1000:.1f}ms 中位={mid*1000:.1f}ms "
          f"p90={p90*1000:.1f}ms max={gs[-1]*1000:.0f}ms "
          f">17ms:{over17} >33ms:{over33} => 等效采集≈{n/max(gs[-1],1e-9):.0f}fps(最大跨度)")

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()
    bot.warmup(texts="身材不错呀", urls=[])
    # 默认首页
    M._pump_wait(0.5)
    bot.reset_frames()
    bot.trim_head_sec = 0.0
    orig = M._pump_wait
    M._pump_wait = make_pump(PIECE)

    # 打开聊天 = 子页 slide 滑入动画（约 .34s），期间 pump
    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot.open_chat("陆香儿")
    dt_wall = time.perf_counter() - t0
    M._pump_wait(0.3)
    ts = [t for t, _j in M._FRAMES[c0:]]
    gaps_report(f"open_chat(piece={PIECE*1000:.0f}ms wall={dt_wall*1000:.0f}ms)", ts)

    # 键盘弹出动画 + 打字
    bot.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.setImeMode('pinyin')")
    c0 = len(M._FRAMES)
    bot._kb_show()
    M._pump_wait(0.1)
    ts = [t for t, _j in M._FRAMES[c0:]]
    gaps_report(f"kb_show(piece={PIECE*1000:.0f}ms)", ts)

    # 首句打字（含 pressRun）
    c0 = len(M._FRAMES)
    t_wall0 = time.perf_counter()
    bot.human_type(".chat-txt", "身材不错呀", send=False, show_keyboard=False)
    t_type = time.perf_counter() - t_wall0
    M._pump_wait(0.2)
    ts = [t for t, _j in M._FRAMES[c0:]]
    gaps_report(f"打字(piece={PIECE*1000:.0f}ms wall={t_type*1000:.0f}ms)", ts)
    print("   打字帧间隔明细(ms):", [round((ts[i]-ts[i-1])*1000) for i in range(1, len(ts))])
    print("   打字帧时间戳(idx: 相对ms):", [f"{i}:{round((t-ts[0])*1000)}" for i, t in enumerate(ts)])
finally:
    try: bot.stop()
    except Exception: pass