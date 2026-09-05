# -*- coding: utf-8 -*-
"""记录首个「打字不发」期间的帧级时间线：键盘可见性 / 候选词 / 输入栏字符 / 组合区。
找出画面“静止不动”的静默段（真实感上的卡顿），并对比浏览器 perf（应远超 Python 计时）。
采样在浏览器侧每 ~50ms 打点，同时用 wall 时钟标记 Python 各子阶段。
"""
import sys, os, json, time, threading
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
target = steps[1]["params"]["联系人"]
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()
    bot.page.evaluate("window.__wxPerf = true; window.__wxPerfLog = [];")
    bot.set_home_list(home_data)
    M._pump_wait(0.5)
    bot.open_chat(target)
    M._pump_wait(0.3)

    # 页面侧采样器：每 ~40ms 记一帧状态
    bot.page.evaluate("""
        () => {
            window.__samp = [];
            window.__sampStop = false;
            const rec = () => {
                const kb = window.__wxKeyboard || {};
                const cand = (kb.candText || kb.getCandText || (()=>''))();
                const box = document.querySelector('.chat-txt');
                const v = box ? box.value : '';
                const comp = document.querySelector('.comp, .composition, .wx-comp') ;
                window.__samp.push({
                    t: Math.round(performance.now()),
                    kb: !!kb.visible,
                    cand: String(cand || '').slice(0,6),
                    in: v,
                    comp: comp ? (comp.textContent||'').slice(0,6) : ''
                });
                if (!window.__sampStop) setTimeout(rec, 40);
            };
            rec();
        }
    """)

    # 标记开始（记录 wall 起点，采样用 performance.now 相对即可）
    t0 = time.perf_counter()
    M.execute_step(bot, "打字不发", {"内容": "身材不错呀 先试探一下", "停留": 0.5})
    wall = time.perf_counter() - t0
    bot.page.evaluate("window.__sampStop = true")
    M._pump_wait(0.3)

    samp = bot.page.evaluate("window.__samp")
    print(f"首个打字不发 墙钟 {wall:.3f}s, 采样 {len(samp)} 帧")

    # 找出变化点与静默段（相邻两帧状态相同则累计）
    def sig(s):
        return (s["kb"], s["cand"], s["in"], s["comp"])
    prev = None
    last_change = samp[0]["t"] if samp else 0
    print("\n时间线（t/键盘/候选/输入栏/组合区）：")
    for s in samp:
        print(f"   {s['t']:>5}ms  kb={int(s['kb'])}  cand=[{s['cand']}]  in=[{s['in']}]  comp=[{s['comp']}]")
    # 静默段统计
    print("\n静默段（状态不变 >=300ms）：")
    start = None
    for i in range(len(samp)):
        if i == 0:
            start = samp[i]["t"]; continue
        if sig(samp[i]) == sig(samp[i-1]):
            continue
        gap = samp[i]["t"] - start
        if gap >= 300:
            print(f"   静默 {gap}ms  ({start}->{samp[i]['t']})  状态=kb={int(samp[i-1]['kb'])} in=[{samp[i-1]['in']}] cand=[{samp[i-1]['cand']}]")
        start = samp[i]["t"]
    # 从最后一次变化到结尾
    if samp:
        gap = samp[-1]["t"] - start
        if gap >= 300:
            print(f"   静默 {gap}ms  (结尾)  状态=kb={int(samp[-1]['kb'])} in=[{samp[-1]['in']}]")
finally:
    try: bot.stop()
    except Exception: pass
