# -*- coding: utf-8 -*-
"""测「预热后首键」的合成帧停滞：对齐真实录屏流程(set_home_list -> prewarm -> open_chat -> 首键'身')。
用 screencast 帧时间戳(合成器换帧时刻)量化画面停滞，同时读 longtask 与 __wxPerfLog，
区分「主线程 JS 长任务」vs「合成/光栅停滞」vs「无停滞」。
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
M.HEADSET = False

def frames_range(c0):
    with M._FRAME_LOCK:
        return [t for t, _j in M._FRAMES[c0:]]

bot = M.WeChatAuto(headless=os.environ.get("HEADED") != "1")
try:
    M.ensure_frontend_running()
    bot.start()
    bot.set_home_list(home_data)
    M._pump_wait(0.5)
    # 预热输入管线（对齐真实 run：先预热再 reset，随后才真正开始）
    bot._prewarm_input(steps)
    bot.reset_frames()

    # 打开首个会话（真实 step2），随后进入首键
    bot.open_chat(target)
    M._pump_wait(0.3)

    # 安装测量：longtask + __wxPerf，重开键盘前先记 screencast 帧数基线
    bot.page.evaluate("""
        () => {
            window.__wxPerf = true; window.__wxPerfLog = [];
            window.__longTasks = [];
            try {
                new PerformanceObserver((list) => {
                    for (const e of list.getEntries())
                        window.__longTasks.push({start: Math.round(e.startTime), dur: Math.round(e.duration)});
                }).observe({entryTypes: ['longtask']});
            } catch (e) {}
        }
    """)

    box = bot.page.locator(".chat-txt")
    box.first.click()
    bot._kb_show()
    bot.page.evaluate("(m)=>window.__wxKeyboard&&window.__wxKeyboard.setImeMode(m)", 'pinyin')
    bot.page.evaluate("window.__wxKeyboard&&window.__wxKeyboard.setShift('off')")
    M._pump_wait(0.15)

    c0 = len(M._FRAMES)
    t0 = time.perf_counter()
    bot._kb_type("s", 80)            # 身材 的 身 -> 首字母 s
    dt_first = time.perf_counter() - t0
    M._pump_wait(0.35)
    c1 = len(M._FRAMES)
    v = box.first.input_value()
    print(f"\n首键 pressType('s') 墙钟 {dt_first*1000:.1f}ms, 上屏=[{v}]")

    # screencast 帧时间戳间隔（合成器换帧节奏；大间隔=画面停滞）
    fr = frames_range(c0)
    print(f"首键区间 screencast 帧数 {len(fr)}（0.5s 窗口）")
    gaps = []
    for i in range(1, len(fr)):
        g = (fr[i] - fr[i-1])
        gaps.append((fr[i], g))
    gaps.sort(key=lambda x: -x[1])
    print("最大的 8 个帧间隔(s):")
    for t, g in gaps[:8]:
        print(f"   会聚帧在 t={t:.3f}s 前后间隔 {g*1000:.0f}ms")

    # longtask
    lt = bot.page.evaluate("window.__longTasks")
    print(f"\n[longtask] 共 {len(lt)} 条;  >=50ms:")
    for e in lt:
        if e['dur'] >= 50:
            print(f"   +{e['start']}ms  时长 {e['dur']}ms")
    big = [e for e in lt if e['dur'] >= 100]
    print(f"[结论] longtask>=100ms 共 {len(big)} 条")

    # __wxPerfLog（首键内部阶段）
    plog = bot.page.evaluate("window.__wxPerfLog")
    print(f"\n[__wxPerfLog] {len(plog)} 项（仅首键若干）:")
    lab_big = [p for p in plog if p.get('dt', 0) >= 30]
    for p in plog[:14]:
        print(f"   {p['label']:38s} dt={p['dt']:>4}ms total={p['total']:>4}ms")
    print(f"[__wxPerfLog] dt>=30ms 项: {len(lab_big)}")
finally:
    try:
        bot.stop()
    except Exception:
        pass
