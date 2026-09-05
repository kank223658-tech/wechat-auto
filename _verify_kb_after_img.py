# -*- coding: utf-8 -*-
"""验收：修复「关闭图片查看器后马上打开键盘仍卡顿」。

新增 display:none 强制回收合成层后，验证「点开大图→捏合放大→关闭→立刻点击输入框弹键盘→打字」，
全程用 CDP screencast 帧时间戳统计掉帧（间隔>33ms 记为掉帧），并照常产出 MP4 视频。

场景复用 _stall_workflow.json 的「编辑主页」首页数据，进入「懒猫不懒」单聊。
运行：  python _verify_kb_after_img.py
输出：  videos/vfy_*_<ts>.mp4  +  stdout 帧间隔统计
"""
import sys, os, json, time
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M

# ---- 场景配置 ----
IMG = "/images/avatar/ComfyUI_00001_cqpki_1788164517_20260831_214430_849.png"
CONTACT = "懒猫不懒"
HOME_DATA = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))["steps"][0]["params"]["数据"]

M.OUT_TAG = "vfy_kbimg"
M.SPEED = 1.0
M.TYPE_SPEED = 40.0


def frames_ts(c0):
    with M._FRAME_LOCK:
        return [t for t, _j in M._FRAMES[c0:]]


def gap_report(tag, fr):
    gaps = []
    for i in range(1, len(fr)):
        gaps.append(fr[i] - fr[i - 1])
    gaps.sort(key=lambda x: -x)
    n = len(gaps)
    over17 = sum(1 for g in gaps if g > 0.017)
    over33 = sum(1 for g in gaps if g > 0.033)
    over50 = sum(1 for g in gaps if g > 0.050)
    top = [round(g * 1000) for g in gaps[:6]]
    print(f"[{tag}] 帧数={len(fr)} 间隙={n}  >17ms:{over17}  >33ms(掉帧):{over33}  >50ms:{over50}  最大间隔(ms):{top}", flush=True)
    return over33


bot = M.WeChatAuto(headless=True)
lt = []
try:
    M.ensure_frontend_running()
    bot.start()
    bot.trim_head_sec = 0.0        # 已 reset_frames，视频从主页面开始，无需再跳过加载期
    bot.set_home_list(HOME_DATA)
    M._pump_wait(0.8)
    M._wusong_words()
    bot.reset_frames()
    bot.open_chat(CONTACT)
    M._pump_wait(0.4)

    # ---- 阶段A：查看图片（全屏打开→放大→关闭）----
    c0 = len(M._FRAMES)
    bot.view_image(IMG, hold_seconds=1.0, zoom=2.0, focus={"x": 0.35, "y": 0.4})
    fr_view = frames_ts(c0)

    # ---- 阶段B：关图后立刻弹键盘（这个动作的动画首帧是我们最关心的）----
    c0 = len(M._FRAMES)
    box = bot.page.locator(".chat-txt")
    box.first.click()
    bot.page.evaluate("(m) => window.__wxKeyboard && window.__wxKeyboard.setImeMode(m)", 'pinyin')
    bot._kb_show()
    M._pump_wait(0.2)
    fr_show = frames_ts(c0)

    # ---- 阶段C：继续打字发出一条消息 ----
    c0 = len(M._FRAMES)
    bot.human_type(".chat-txt", "这个角度拍得真好看", send=True, show_keyboard=False)
    M._pump_wait(0.6)
    fr_type = frames_ts(c0)

    lt = bot.page.evaluate("window.__longTasks || []")
except Exception as exc:                       # noqa: BLE001
    import traceback
    traceback.print_exc()
finally:
    mp4 = None
    try:
        mp4 = bot.stop()
    except Exception:                          # noqa: BLE001
        pass

print("\n== 分阶段帧间隔（掉帧=间隔>33ms）==")
d1 = gap_report("A 查看图片(放大→关闭)", fr_view)
d2 = gap_report("B 关图后弹键盘", fr_show)
d3 = gap_report("C 打字发消息", fr_type)
print("\n[longtask] >=30ms 的长任务:", sum(1 for e in lt if e.get('dur', 0) >= 30), "条")
for e in lt:
    if e.get('dur', 0) >= 30:
        print(f"    +{e['start']:.0f}ms dur={e['dur']:.0f}ms")

print("\n== 结论 ==")
print(f"  B「关图后弹键盘」掉帧帧数 {d2}  (修复前此段动画首帧常出现 >33ms 断帧)")
if d2 == 0:
    print("  => 关图后开键盘未见 >33ms 掉帧，display:none 回收合成层生效。")
else:
    print("  => 关图后开键盘仍出现掉帧，需进一步排查合成层/动画抢占。")
if mp4:
    print(f"\n[视频] {mp4}  ({os.path.getsize(mp4)/1024/1024:.1f} MB)")
