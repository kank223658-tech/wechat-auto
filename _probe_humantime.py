# -*- coding: utf-8 -*-
"""逐步计时 human_type 首键链路的各段 evaluate，定位「kb=1 后 ~780ms 才出首字」的瓶颈。"""
import sys, os, json, time, random
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_humantime"
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

    # 【模拟 run() 修复后的预热】先调 _wusong_words() 加载词表
    tw = time.perf_counter(); n = len(M._wusong_words()); print(f"   [预热] _wusong_words() 首载 {n} 词 耗时 {time.perf_counter()-tw:.3f}s", flush=True)

    M.execute_step(bot, "打开聊天", {"联系人": "懒猫不懒"})
    M._pump_wait(0.3)

    box = bot.page.locator(".chat-txt")
    def T(label, t0):
        print(f"   {label:34s} {time.perf_counter()-t0:.3f}s", flush=True)

    t=time.perf_counter(); box.first.click(); T("box.click()", t)
    t=time.perf_counter(); M._pump_wait(random.uniform(0.15,0.35)/M.SPEED/max(0.05,M.TYPE_SPEED)); T("点击后自然反应等待", t)
    t=time.perf_counter(); bot.page.evaluate("(m)=>window.__wxKeyboard&&window.__wxKeyboard.setImeMode(m)",'pinyin'); T("setImeMode(弹键盘前)", t)
    t=time.perf_counter(); bot._kb_show(); T("_kb_show() 含0.26s动画等待", t)
    t=time.perf_counter(); bot.page.evaluate("window.__wxKeyboard&&window.__wxKeyboard.setShift('off')"); T("setShift('off')", t)
    # _wusong_word_len(身, 0)
    t=time.perf_counter(); wlen = M._wusong_word_len("身材不错呀 先试探一下", 0, max_len=5); T(f"_wusong_word_len 身 -> {wlen}", t)
    # setTopHint 身/shen
    chunk="身"; chunk_py="shen"
    t=time.perf_counter(); bot.page.evaluate("((w,p)=>window.__wxKeyboard&&window.__wxKeyboard.setTopHint&&window.__wxKeyboard.setTopHint(w,p))",[chunk,chunk_py]); T("setTopHint(身,shen)", t)
    t=time.perf_counter(); bot._kb_type("s", 80); T("首个 _kb_type('s')", t)
    v = box.first.input_value()
    print(f"\n首键后输入值=[{v!r}]")
finally:
    try: bot.stop()
    except Exception: pass
