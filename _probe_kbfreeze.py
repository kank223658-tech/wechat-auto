# -*- coding: utf-8 -*-
"""找「打开键盘后、首字前」冻结窗口：页面内 setTimeout 采样 kb+输入值，分析 kb=1 且 in='' 的持续时长。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_kb"
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
    M._wusong_words()   # 模拟 run() 修复后的预热

    bot.page.evaluate("""
        () => {
            window.__samp=[]; window.__sampStop=false;
            let last=performance.now();
            const rec=()=>{
                const kb=!!(window.__wxKeyboard&&window.__wxKeyboard.visible);
                const box=document.querySelector('.chat-txt');
                const iv=box?box.value:'';
                const now=performance.now();
                window.__samp.push({t:Math.round(now), dt:Math.round(now-last), kb:kb?1:0, in:iv});
                last=now;
                if(!window.__sampStop) setTimeout(rec, 25);
            };
            rec();
        }
    """)

    for idx, step in enumerate(steps[:3], start=1):
        print(f"  [执行 {idx}] {step['action']} {str(step.get('params') or {})[:60]}", flush=True)
        M.execute_step(bot, step["action"], step.get("params") or {})
    bot.page.evaluate("window.__sampStop=true")
    M._pump_wait(0.2)

    samp = bot.page.evaluate("window.__samp")
    print(f"采样 {len(samp)} 条")
    # 段：kb=1 且 in 空
    segs=[]; cur=None
    for s in samp:
        e = (s['kb']==1 and s['in'].strip()=='')
        if e:
            if cur is None: cur=[s['t'],s['t']]
            else: cur[1]=s['t']
        else:
            if cur is not None: segs.append(cur); cur=None
    if cur is not None: segs.append(cur)
    segs=[x for x in segs if x[1]-x[0]>=120]
    print("\n[kb=1 输入为空] >=120ms 的窗口(开键盘后还没出字):")
    for a,b in segs:
        print(f"   持续 {b-a:>4}ms @ 相对 {a}ms")
    print(f"   共 {len(segs)} 段")

    # 键盘开启时刻 与 首字时刻 的差
    first_kb=None; first_text=None
    prev_kb=0
    for s in samp:
        if s['kb']==1 and first_kb is None: first_kb=s['t']
        if s['in'].strip() and first_text is None: first_text=s['t']
        # 第一段 kb=1 in 有值
    print(f"\n首开键盘 @ {first_kb}ms ; 首字 @ {first_text}ms ; 差 {first_text-first_kb}ms")
finally:
    try: bot.stop()
    except Exception: pass
