# -*- coding: utf-8 -*-
"""忠实复刻真实脚本的前几条消息(setup + 步骤1..3)，全段测 screencast 帧间隔与 longtask。
对比我在探针里"只测单键"测不到的点：完整 warmup / 重应用主页 / 打完整第一句。
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_firstmsg"
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

bot = M.WeChatAuto(headless=os.environ.get("HEADED") != "1")
try:
    M.ensure_frontend_running()
    bot.start()

    # ---- 对齐真实 run 的 setup ----
    _warm_texts = bot.collect_step_texts(steps)
    _warm_urls = []
    for _s in steps:
        for _v in (_s.get("params") or {}).values():
            if isinstance(_v, str):
                _warm_urls += M._ASSET_URL_RE.findall(_v)
    bot.warmup(texts=_warm_texts, urls=list(dict.fromkeys(_warm_urls)))

    # 【假设验证】额外强制光栅化全部字形：字体子集加载≠字形位图就绪，首次绘制某字才光栅化。
    bot.page.evaluate("""
        (t) => {
            const cv = document.createElement('canvas');
            const ctx = cv.getContext('2d', { willReadFrequently: true });
            ctx.font = '16px "HarmonyOS Sans SC"';
            // 分块draw：避免超长字符串撑爆canvas；一次draw触发该字形光栅化缓存
            const lines = String(t).match(/[\\s\\S]{1,40}/g) || [];
            for (const ln of lines) { ctx.fillText(ln, 0, 8); ctx.translate(0, 0); ctx.fillText(ln, 0, 8); }
            try { ctx.getImageData(0, 0, 1, 1); } catch (e) {}
            return lines.length;
        }
    """, _warm_texts)
    M._pump_wait(0.2)

    fp = steps[0].get("params") or {}
    if steps[0].get("action") == "编辑主页":
        bot.set_home_list(fp.get("数据", fp.get("data")))
    bot._prewarm_input(steps)
    bot.reset_frames()
    bot.trim_head_sec = 0.0

    # ---- 装测量 ----
    bot.page.evaluate("""
        () => {
            window.__wxPerf = true; window.__wxPerfLog = [];
            window.__longTasks = [];
            window.__lt0 = performance.now();
            try {
                new PerformanceObserver((list) => {
                    for (const e of list.getEntries())
                        window.__longTasks.push({start: Math.round(e.startTime - window.__lt0), dur: Math.round(e.duration)});
                }).observe({entryTypes: ['longtask']});
            } catch (e) {}
            window.__res = [];
            try {
                new PerformanceObserver((list) => {
                    for (const e of list.getEntries()) {
                        if (e.initiatorType === 'img' || e.initiatorType === 'css' || e.name.indexOf('/images/') >= 0)
                            window.__res.push({name: e.name.split('/').pop(), dur: Math.round(e.duration), size: (e.decodedBodySize||e.transferSize||0)});
                    }
                }).observe({entryTypes: ['resource']});
            } catch (e) {}
        }
    """)

    # ---- 执行步骤 1..3，记录帧数边界 ----
    marks = []   # (step, action, frame_count_before, wall_sec_after)
    def frame_count():
        with M._FRAME_LOCK:
            return len(M._FRAMES)

    for idx, step in enumerate(steps[:3], start=1):
        action = step["action"]; params = step.get("params", {}) or {}
        c0 = frame_count()
        t0 = time.perf_counter()
        print(f"  [执行 {idx}] {action} {str(params)[:80]}", flush=True)
        M.execute_step(bot, action, params)
        dt = time.perf_counter() - t0
        c1 = frame_count()
        marks.append((idx, action, c0, c1, dt))
        print(f"      -> {dt*1000:.0f}ms, 帧 {c0}->{c1}, perf={bot.page.evaluate('window.__wxPerfLog.length')}", flush=True)

    # ---- 分析 screencast 帧间隔 ----
    with M._FRAME_LOCK:
        ts = [t for t, _j in M._FRAMES]
    print(f"\n总帧数 {len(ts)}")
    gaps = []
    for i in range(1, len(ts)):
        g = ts[i] - ts[i-1]
        if g >= 0.12:   # >=120ms 才视为异常停滞
            gaps.append((g, ts[i], i))
    gaps.sort(key=lambda x: -x[0])
    print(f"[异常帧间隔 >=120ms] 共 {len(gaps)} 个:")
    for g, t, idx in gaps[:20]:
        print(f"   #{idx}  t={t:.3f}  gap={g*1000:.0f}ms")

    # 步骤边界映射到帧号，判断停滞落在哪一步
    print("\n步骤边界(帧号/墙钟ms):")
    for idx, action, c0, c1, dt in marks:
        print(f"   step{idx} {action}: 帧[{c0}..{c1}] 墙钟 {dt*1000:.0f}ms")

    # longtask
    lt = bot.page.evaluate("window.__longTasks")
    print(f"\n[longtask] 共 {len(lt)} 条:")
    for e in lt:
        if e['dur'] >= 50:
            print(f"   +{e['start']}ms  dur={e['dur']}ms")

    # 资源加载：慢资源 / 大资源
    res = bot.page.evaluate("window.__res")
    print(f"\n[资源加载] 共 {len(res)} 条:")
    rs = sorted(res, key=lambda r: -(r.get('dur') or 0))
    for r in rs[:15]:
        print(f"   {r['name']:50s} dur={r['dur']}ms size={r['size']}")
finally:
    try:
        bot.stop()
    except Exception:
        pass
