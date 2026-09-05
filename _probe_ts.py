# -*- coding: utf-8 -*-
"""首句期间 DOM 状态时间线：键盘/输入值/候选/组合区每 ~40ms 采样。
判断各"静止间隔"里是「正在打字但画面没变(卡)」还是「本就空闲(非卡)」。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_ts"
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

bot = M.WeChatAuto(headless=True)
try:
    M.ensure_frontend_running()
    bot.start()
    _warm_texts = bot.collect_step_texts(steps)
    _warm_urls = []
    for _s in steps:
        for _v in (_s.get("params") or {}).values():
            if isinstance(_v, str):
                _warm_urls += M._ASSET_URL_RE.findall(_v)
    bot.warmup(texts=_warm_texts, urls=list(dict.fromkeys(_warm_urls)))
    fp = steps[0].get("params") or {}
    if steps[0].get("action") == "编辑主页":
        bot.set_home_list(fp.get("数据", fp.get("data")))
    bot._prewarm_input(steps)
    bot.reset_frames()
    bot.trim_head_sec = 0.0

    # 页面侧采样器
    bot.page.evaluate("""
        () => {
            window.__samp=[]; window.__sampStop=false;
            const rec=()=>{
                const kb = window.__wxKeyboard||{};
                const cnt = (sel)=>{ const el=document.querySelector(sel); return el?el.childElementCount:0; };
                const cand = document.querySelector('#kb-cand-list, .kb-cand-list, .cand-list');
                const box = document.querySelector('.chat-txt');
                window.__samp.push({
                    t: Math.round(performance.now()),
                    kb: !!kb.visible,
                    in: box? box.value : '',
                    candN: cand? cand.childElementCount : -1,
                    cand: cand? (cand.textContent||'').slice(0,8) : '',
                });
                if(!window.__sampStop) setTimeout(rec, 40);
            };
            rec();
        }
    """)

    # 跑步骤 1..3，同时记 screencast 帧时间戳
    c0 = len(M._FRAMES)
    t_wall0 = time.perf_counter()
    for idx, step in enumerate(steps[:3], start=1):
        print(f"  [执行 {idx}] {step['action']} {str(step.get('params') or {})[:70]}", flush=True)
        M.execute_step(bot, step["action"], step.get("params") or {})
    c1 = len(M._FRAMES)
    bot.page.evaluate("window.__sampStop=true")
    M._pump_wait(0.2)
    with M._FRAME_LOCK:
        fts = [t for t,_j in M._FRAMES[c0:c1]]

    samp = bot.page.evaluate("window.__samp")
    print(f"\n采样 {len(samp)} 点; screencast 帧 {len(fts)}")
    # 帧时间戳起点对齐 0
    t0 = fts[0] if fts else 0
    # 打印状态时间线 + 标出大间隔(帧)与状态
    # 先打印每帧的间隔>90ms 及对应的采样状态
    print("\n帧间隔>=90ms 附近 => 键盘/输入/候选 状态:")
    for i in range(1, len(fts)):
        dt = fts[i]-fts[i-1]
        if dt >= 0.09:
            ms = (fts[i]-t0)*1000
            # 找时间最接近的采样点
            best=None; bd=1e9
            for s in samp:
                d=abs(s['t']-ms); 
                if d<bd: bd=d; best=s
            print(f"   间隙 {dt*1000:>4.0f}ms @ {ms:>6.0f}ms  | kb={int(best['kb'])} in=[{best['in']!r}] cand({best['candN']})={best['cand']!r}")
    # 打印输入值变化轨迹（看打字过程）
    print("\n输入值随时间(采样) 简表 (只在变化时分隔):")
    prev_in='\x00'
    for s in samp:
        if s['in'] != prev_in:
            print(f"   {s['t']}ms  in=[{s['in']!r}] kb={int(s['kb'])} cand({s['candN']})={s['cand']!r}")
            prev_in=s['in']
finally:
    try:
        bot.stop()
    except Exception:
        pass
