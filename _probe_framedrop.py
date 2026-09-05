# -*- coding: utf-8 -*-
"""定位「打字/键盘收起掉帧、首次打开键盘打字尤其明显」：复刻首条消息流程，
分阶段记录 screencast 帧间隔（掉帧=间隔>~33ms）、__wxPerfLog 重阶段、longtask。
阶段：open(首次弹键盘) -> type(打字不发) -> hide(收起键盘)。
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

def gap_report(tag, fr):
    gaps = []
    for i in range(1, len(fr)):
        gaps.append(fr[i]-fr[i-1])
    gaps.sort(key=lambda x: -x)
    n = len(gaps)
    over17 = sum(1 for g in gaps if g > 0.017)
    over33 = sum(1 for g in gaps if g > 0.033)
    over50 = sum(1 for g in gaps if g > 0.050)
    top = [round(g*1000) for g in gaps[:6]]
    print(f"[{tag}] 帧数={len(fr)} 间隙{n}  >17ms:{over17} >33ms(掉帧):{over33} >50ms:{over50}  最大:{top}")

bot = M.WeChatAuto(headless=os.environ.get("HEADED") != "1")
lt = []
plog = []
try:
    M.ensure_frontend_running()
    bot.start()
    bot.set_home_list(home_data)
    M._pump_wait(0.6)
    bot._prewarm_input(steps)
    M._wusong_words()
    bot.reset_frames()
    bot.open_chat(target)
    M._pump_wait(0.2)

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

    box = bot.page.locator(".chat-txt")
    box.first.click()
    bot.page.evaluate("(m)=>window.__wxKeyboard&&window.__wxKeyboard.setImeMode(m)", 'pinyin')
    bot.page.evaluate("window.__wxKeyboard&&window.__wxKeyboard.setShift('off')")

    # ---- 阶段1：首次弹键盘 ----
    c0 = len(M._FRAMES)
    bot._kb_show()
    M._pump_wait(0.1)
    fr_open = frames_ts(c0)

    # ---- 阶段2：打字不发 ----
    c0 = len(M._FRAMES)
    bot.human_type(".chat-txt", "身材不错呀", send=False, show_keyboard=False)
    M._pump_wait(0.1)
    fr_type = frames_ts(c0)

    # ---- 阶段3：收起键盘 ----
    c0 = len(M._FRAMES)
    bot._kb_hide()
    M._pump_wait(0.1)
    fr_hide = frames_ts(c0)

    lt = bot.page.evaluate("window.__longTasks")
    plog = bot.page.evaluate("window.__wxPerfLog")
finally:
    try:
        bot.stop()
    except Exception:
        pass

print("\n== 分阶段帧间隔 ==")
gap_report("首次弹键盘", fr_open)
gap_report("打字不发", fr_type)
gap_report("收起键盘", fr_hide)

bg = [e for e in lt if e['dur'] >= 30]
print(f"\n[longtask] 共 {len(lt)} 条; >=30ms: {len(bg)}")
for e in bg[:10]:
    print(f"    +{e['start']}ms dur={e['dur']}ms")

bp = [p for p in plog if p.get('dt',0) >= 25]
print(f"\n[__wxPerfLog] 共 {len(plog)} 项; dt>=25ms: {len(bp)}")
for p in bp[:12]:
    print(f"    {p['label']:40s} dt={p['dt']:>4}ms total={p['total']:>4}ms")
