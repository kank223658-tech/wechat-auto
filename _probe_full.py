# -*- coding: utf-8 -*-
"""完整跑一遍剧本（含 warmup+prewarm，对齐 main.py），逐步计时 + 注入 longtask 观察者，
定位「执行过程中卡住」的真实位置。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
steps = wf["steps"]
print("总步骤数:", len(steps))

M.SPEED = 1.0
M.TYPE_SPEED = 40.0
M.OUT_TAG = "repro2sfull"

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()

    # 注入 longtask 观察者
    bot.page.evaluate("""
        () => {
            window.__longTasks = [];
            window.__ltMark = 0;
            const log = (e) => window.__longTasks.push({start: Math.round(e.startTime), dur: Math.round(e.duration)});
            try { new PerformanceObserver((l)=>l.getEntries().forEach(log)).observe({entryTypes:['longtask']}); } catch(e){}
        }
    """)

    # ---- warmup（对齐 main.py）----
    _warm_texts = bot.collect_step_texts(steps)
    _warm_urls = []
    for _s in steps:
        for _v in (_s.get("params") or {}).values():
            if isinstance(_v, str):
                _warm_urls += M._ASSET_URL_RE.findall(_v)
    bot.warmup(texts=_warm_texts, urls=list(dict.fromkeys(_warm_urls)))
    try:
        _fp = (steps[0].get("params") or {})
        if steps[0].get("action") == "编辑主页":
            bot.set_home_list(_fp.get("数据", _fp.get("data")))
    except Exception as e:
        print("[预热] 首屏主页预应用失败(忽略):", e)
    bot._prewarm_input(steps)
    bot.reset_frames()
    print("[预热] 完成，进入真实步骤执行……")

    # ---- 逐步执行 + 计时 + 长任务 ----
    M._RUN_CLOCK = 0.0
    total = len(steps)
    slow_steps = []
    lt_per_step = []
    for idx, step in enumerate(steps, start=1):
        action = step["action"]
        params = step.get("params", {}) or {}
        # 记录本步之前已产生的 longtask 数，用于归因
        before_lt = bot.page.evaluate("window.__longTasks.length")
        t0 = time.perf_counter()
        M.execute_step(bot, action, params)
        dt = time.perf_counter() - t0
        bot.live_snapshot()
        lt = bot.page.evaluate("window.__longTasks.slice(%d)" % before_lt)
        lt_per_step.append((idx, action, dt, lt))
        # 只打印打开聊天 / 明显慢的步骤
        if action == "打开聊天" or dt >= 0.8:
            mark = f"  << 慢" if dt >= 0.8 else ""
            print(f"[{idx:>3}/{total}] {action:<8} {json.dumps(params, ensure_ascii=False)[:40]:<42} 耗时 {dt:.3f}s 长任务[{len(lt)}]{mark}")
            if dt >= 0.8:
                slow_steps.append((idx, action, dt))
        if dt >= 0.8:
            for e in lt:
                print(f"        longtask +{e['start']}ms 时长 {e['dur']}ms")

    print("\n========== 汇总 ==========")
    print("慢步骤(>=0.8s):")
    for idx, action, dt in slow_steps:
        print(f"  第{idx}步 [{action}] {dt:.3f}s")
    # 全流程里所有 >=200ms 的长任务 top10
    all_lt = bot.page.evaluate("window.__longTasks")
    big = [e for e in all_lt if e['dur'] >= 200]
    big.sort(key=lambda e: -e['dur'])
    print(f"全程长任务(>=200ms)共 {len(big)} 条，最长 10 条:")
    for e in big[:10]:
        print(f"   +{e['start']}ms  时长 {e['dur']}ms")

finally:
    try:
        bot.stop()
    except Exception:
        pass
