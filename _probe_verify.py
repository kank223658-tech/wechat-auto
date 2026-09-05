# -*- coding: utf-8 -*-
"""验证 pressRun 批量打字修复：复刻真实首条消息(打字不发)流程，40 倍速下记录
每操作往返耗时、screencast 帧间隔、__wxPerfLog、longtask。
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
target = steps[1]["params"]["联系人"]
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

def frames_ts(c0):
    with M._FRAME_LOCK:
        return [t for t, _j in M._FRAMES[c0:]]

def classify(js):
    s = js if isinstance(js, str) else str(js)
    if 'pressRun' in s: return 'pressRun(批)'
    if 'pressType' in s: return 'pressType'
    if 'commitByPhrase' in s: return 'commit'
    if 'setTopHint' in s: return 'setTopHint'
    if 'setShift' in s: return 'setShift'
    if 'setImeMode' in s: return 'setImeMode'
    return 'other'

def summ(v):
    v = sorted(v); n = len(v)
    if not n: return "n=0"
    avg = sum(v)/n; p95 = v[min(n-1, int(n*0.95))]; mx = v[n-1]
    return f"n={n:2d} avg={avg:5.1f} p95={p95:5.1f} max={mx:5.1f}"

bot = M.WeChatAuto(headless=os.environ.get("HEADED") != "1")
stats = {}
fr = []
lt = []
plog = []
dt_total = c1 = c0 = 0
try:
    M.ensure_frontend_running()
    bot.start()
    bot.set_home_list(home_data)
    M._pump_wait(0.6)
    bot._prewarm_input(steps)
    M._wusong_words()
    bot.reset_frames()
    bot.open_chat(target)
    M._pump_wait(0.25)

    bot.page.evaluate("window.__wxPerf = true; window.__wxPerfLog = []; window.__longTasks = [];")
    bot.page.evaluate("""
        () => {
            window.__longTasks = [];
            try {
                new PerformanceObserver((list) => {
                    for (const e of list.getEntries())
                        window.__longTasks.push({start: Math.round(e.startTime), dur: Math.round(e.duration)});
                }).observe({entryTypes: ['longtask']});
            } catch (e) {}
        }
    """)

    orig_eval = bot.page.evaluate
    def ev_wrap(js, *a, **k):
        t0 = time.perf_counter()
        try:
            return orig_eval(js, *a, **k)
        finally:
            dt = (time.perf_counter()-t0)*1000
            k_ = classify(js)
            stats.setdefault(k_, []).append(round(dt, 1))
    bot.page.evaluate = ev_wrap

    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot.human_type(".chat-txt", "身材不错呀", send=False, show_keyboard=True)
    dt_total = time.perf_counter() - t0
    M._pump_wait(0.3)
    c1 = len(M._FRAMES)
    fr = frames_ts(c0)
    lt = bot.page.evaluate("window.__longTasks")
    plog = bot.page.evaluate("window.__wxPerfLog")
finally:
    try:
        bot.stop()
    except Exception:
        pass

print(f"\n== human_type(身材不错呀) 墙钟 {dt_total*1000:.0f}ms, 帧 {c1-c0} ==")
print("== 每操作往返耗时(ms) ==")
for k_ in sorted(stats, key=lambda x: -sum(stats[x])):
    print(f"  {k_:14s} {summ(stats[k_])}")
slow = [(k_, v) for k_ in stats for v in stats[k_] if v >= 20]
print("\n慢操作(>=20ms):", slow if slow else "无")

gaps = []
for i in range(1, len(fr)):
    gaps.append(fr[i]-fr[i-1])
gaps.sort(key=lambda x: -x)
over16 = sum(1 for g in gaps if g > 0.017)
over24 = sum(1 for g in gaps if g > 0.024)
print(f"\n[screencast] 打字区间帧数 {len(fr)}; 间隔>17ms:{over16} >24ms:{over24}")
print("最大帧间隔(ms):", [round(g*1000) for g in gaps[:8]])

big = [e for e in lt if e['dur'] >= 40]
print(f"\n[longtask] 共 {len(lt)} 条; >=40ms: {len(big)}")
bigp = [p for p in plog if p.get('dt',0) >= 25]
print(f"[__wxPerfLog] 共 {len(plog)} 项; dt>=25ms: {len(bigp)}")
for p in bigp[:10]:
    print(f"    {p['label']:42s} dt={p['dt']:>4}ms total={p['total']:>4}ms")
