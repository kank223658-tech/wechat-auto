# -*- coding: utf-8 -*-
"""复现「进入带历史会话的聊天页」是否在前 2 秒卡顿。

流程对齐 main.py 真实跑法：apply 编辑主页(首页数据含消息历史) -> open_chat(懒猫不懒)。
注入 longtask PerformanceObserver 统计浏览器主线程卡顿；同时读数 DOM 规模(消息数/图片数)。
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

# 读 workflow 的第一步「编辑主页」数据
wf = json.load(open(r"F:\weixin-auto\_repro_workflow.json", encoding="utf-8"))
steps = wf["steps"]
home_data = steps[0]["params"]["数据"]
print("首页会话数:", len(home_data))
for s in home_data:
    name = s.get("name")
    msgs = s.get("messages", [])
    imgs = sum(1 for m in msgs if m.get("kind") == "image")
    print(f"  - {name}: {len(msgs)} 条消息, {imgs} 张图")

# 关键全局量对齐真实运行
M.SPEED = 1.0
M.TYPE_SPEED = 40.0
M.OUT_TAG = "repro2sprobe"

import os
bot = M.WeChatAuto(headless=os.environ.get("HEADED") != "1")
try:
    M.ensure_frontend_running()
    bot.start()

    # 注入 longtask 观察者
    bot.page.evaluate("""
        () => {
            window.__longTasks = [];
            const log = (e) => window.__longTasks.push({
                start: Math.round(e.startTime),
                dur: Math.round(e.duration)
            });
            try {
                new PerformanceObserver((list) => list.getEntries().forEach(log))
                    .observe({ entryTypes: ['longtask'] });
            } catch (e) {}
            window.__t0 = performance.now();
        }
    """)

    # 应用历史主页
    t = time.perf_counter()
    bot.set_home_list(home_data)
    M._pump_wait(0.5)
    home_msgs = bot.page.evaluate("document.querySelectorAll('.wechat-list li').length")
    print(f"[set_home_list] 耗时 {time.perf_counter()-t:.3f}s, 首页 li 数={home_msgs}")

    # 明确标记「聊天页渲染起点」，观察者记录 longtask 相对该起点的时间
    bot.page.evaluate("window.__chatEntry = performance.now()")

    t = time.perf_counter()
    bot.open_chat("懒猫不懒")
    wall = time.perf_counter() - t
    print(f"[open_chat 懒猫不懒] 墙钟耗时 {wall:.3f}s")

    # 读数：DOM 规模
    dom = bot.page.evaluate("""
        () => {
            const doc = document;
            const imgs = doc.querySelectorAll('img').length;
            const msgs = doc.querySelectorAll('.msg-content, .dialogue-item, .msg-item').length;
            const text = doc.body.innerText.length;
            return {imgs, msgs, textLen: text};
        }
    """)
    # 读数：longtask（相对 __chatEntry 的时间）
    lt = bot.page.evaluate("(() => { const t0 = window.__chatEntry || 0; return window.__longTasks.map(t=>({start: Math.round(t.start - t0), dur: t.dur})); })()")
    print(f"[DOM] imgs={dom['imgs']} msgs={dom['msgs']} bodyTextLen={dom['textLen']}")
    print(f"[longtask 相对进入聊天页]")
    for e in lt:
        print(f"    +{e['start']}ms  时长 {e['dur']}ms")
    lt_big = [e for e in lt if e['dur'] >= 200]
    print(f"[结论] 长任务(>=200ms) {len(lt)} 条；>=1000ms {len([e for e in lt if e['dur']>=1000])} 条；"
          f"其中 >=200ms 且落在进入聊天页后 2s 内: "
          f"{len([e for e in lt_big if e['start'] <= 2000])} 条")
finally:
    try:
        bot.stop()
    except Exception:
        pass
