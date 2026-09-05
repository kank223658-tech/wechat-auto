# -*- coding: utf-8 -*-
"""用 Performance.getMetrics 增量定位 open_chat / 首键的耗时归属(布局 vs 样式 vs 脚本)。"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
steps = wf["steps"]
M.OUT_TAG = "prb_metrics"
M.SPEED = 1.0
M.TYPE_SPEED = 40.0

FIELDS = ["TotalLayoutDuration","LayoutDuration","RecalcStyleDuration","ScriptDuration",
          "TaskDuration","StyleRecalcCount","LayoutCount","JSHeapUsedSize","BodyTextNodeCount"]

bot = M.WeChatAuto(headless=os.environ.get("HEADED") != "1")
try:
    M.ensure_frontend_running()
    bot.start()
    cdp = bot.context.new_cdp_session(bot.page)
    cdp.send("Performance.enable")

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

    def metrics():
        m = cdp.send("Performance.getMetrics")
        return {x["name"]: x["value"] for x in m["metrics"]}

    def report(tag, before, after):
        print(f"\n[{tag}]")
        for k in FIELDS:
            b = before.get(k, 0); a = after.get(k, 0)
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                print(f"   {k:26s} before={int(b):>9}  after={int(a):>9}  delta={int(a-b):>9}")

    for idx, step in enumerate(steps[:3], start=1):
        action = step["action"]; params = step.get("params", {}) or {}
        m0 = metrics()
        t0 = time.perf_counter()
        M.execute_step(bot, action, params)
        dt = time.perf_counter() - t0
        m1 = metrics()
        if idx == 1:
            report("编辑主页", m0, m1)
        elif idx == 2:
            report("打开聊天", m0, m1)
        else:
            report("打字不发(首句)", m0, m1)
        print(f"   墙钟 {dt*1000:.0f}ms")

    # 打字不发内部多次：再单独测一次从 show 到首键
finally:
    try:
        bot.stop()
    except Exception:
        pass
