# -*- coding: utf-8 -*-
"""验证「闪到对方朋友圈」之后能否正常打开/播放视频（播放中采样版）。

要点：[播放视频] 动作设计上是「播完自动关播放器」（main.py play_video 尾部 close），
所以必须在**播放进行中**采样，不能用动作返回后的状态判定。

链路：
  1) 铺对方人设（posts[0].video = /videos/_test.mp4，H.264）→ 打开聊天
  2) [闪到对方朋友圈] → 视频动态已渲染（videoCount>=1）
  3) JS 直开 playVideo(1)（等同手点视频封面）：readyState>=2 + currentTime 前进 = 真的在播
  4) [播放视频] 动作整链路（后台线程跑，主线程播放中采样 isOpen + currentTime）
  5) 播放器开着时 [闪回聊天]：顺路关干净、无黑幕残留

用法: py _verify_flash_video.py   （退出码 0 = 全部通过）
"""
import os
import sys
import json
import threading

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import main as M

M.FRAME_CAPTURE_ENABLED = False
M.ENABLE_AUDIO = False
M.ENABLE_BGM = False
M.SPEED = 3.0

OUT = os.path.join(BASE, "_shot")
os.makedirs(OUT, exist_ok=True)

IMG0 = "/images/avatar/2_20260831_184618_874.jpg"
VID0 = "/videos/_test.mp4"

SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "阿月", "lastText": "", "unread": 0, "messages": []}],
}

PEER = {
    "name": "陆香儿", "wxid": "luxer", "avatar": IMG0, "cover": IMG0,
    "signature": "保持热爱",
    "posts": [
        {"date": "昨天", "text": "随手拍的一段", "video": {"src": VID0, "cover": IMG0}},
        {"date": "周一", "text": "今天的风很舒服", "images": [IMG0]},
    ],
}

report = {"errors": [], "checks": {}}

VID_STATE = """() => {
    const v = document.querySelector('#wxVideoPlayer video');
    const open = !!(window.__wxVideo && window.__wxVideo.isOpen
        && window.__wxVideo.isOpen());
    return { open,
             readyState: v ? v.readyState : -1,
             t: v ? v.currentTime : -1,
             dur: (window.__wxVideo && window.__wxVideo.duration) ?
                  window.__wxVideo.duration() : 0 };
}"""


def do_step(bot, action, params, tag):
    try:
        M.execute_step(bot, action, params)
        print("    ✓ %s %s" % (action, params))
        return True
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("%s: %s" % (action, e))
        print("    ✗ %s %s -> %s" % (action, params, e))
        try:
            bot.page.screenshot(path=os.path.join(OUT, "flashvideo_%s_FAIL.png" % tag))
        except Exception:                                    # noqa: BLE001
            pass
        return False


def snap(page, name):
    try:
        page.screenshot(path=os.path.join(OUT, "flashvideo_%s.png" % name))
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("screenshot %s: %s" % (name, e))


def main():
    print("[1] 确保前端在跑…")
    M.ensure_frontend_running()
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        M._pump_wait(1.0)
        page = bot.page
        bot.apply_scene(SCENE)
        M._pump_wait(0.8)

        print("[2] 铺人设 + 进聊天…")
        do_step(bot, "打开聊天", {"联系人": "阿月"}, "0_open")
        do_step(bot, "编辑对方资料", {"数据": PEER}, "1_peer")
        do_step(bot, "对方发消息", {"内容": "给你看段视频"}, "2_msg")
        M._pump_wait(0.6)

        print("[3] [闪到对方朋友圈] → 视频动态应已渲染…")
        if not do_step(bot, "闪到对方朋友圈", {}, "3_flash"):
            return 1
        M._pump_wait(0.4)
        cnt = page.evaluate(
            "() => (window.__wxPeer && window.__wxPeer.videoCount) ?"
            " window.__wxPeer.videoCount() : -1")
        st = page.evaluate(
            "() => (window.__wxPeer && window.__wxPeer.isOpen()) || {}")
        print("    [状态] moments=%s videoCount=%s" % (st.get("moments"), cnt))
        r1 = bool(st.get("moments") and cnt >= 1)
        snap(page, "A_peer_moments")

        print("[4] JS 直开视频（等同手点封面）→ 播放中采样…")
        ok = page.evaluate(
            "() => !!(window.__wxPeer && window.__wxPeer.playVideo(1))")
        if not ok:
            report["errors"].append("playVideo(1) 返回 false")
            return 1
        try:
            page.wait_for_function(
                "() => { const v = document.querySelector('#wxVideoPlayer video');"
                " return !!(v && v.readyState >= 2); }", timeout=4000)
        except Exception:                                # noqa: BLE001
            pass
        s1 = page.evaluate(VID_STATE)
        M._pump_wait(0.9)
        s2 = page.evaluate(VID_STATE)
        print("    [采样1] open=%s ready=%s t=%.2f" % (s1["open"], s1["readyState"], s1["t"]))
        print("    [采样2] open=%s ready=%s t=%.2f dur=%.2f" % (
            s2["open"], s2["readyState"], s2["t"], s2["dur"]))
        snap(page, "B_playing")
        r2 = bool(s1["open"] and s2["open"] and s2["readyState"] >= 2 and s2["t"] > s1["t"])
        page.evaluate("window.__wxVideo && window.__wxVideo.close()")
        M._pump_wait(0.3)

        print("[5] [播放视频] 动作整链路（页面内 JS 采样器记录播放轨迹）…")
        # playwright sync API 线程不安全：不能用后台线程采样，改在页面里装采样器
        page.evaluate(
            """() => {
                window.__vv = [];
                window.__vvTimer = setInterval(() => {
                    const v = document.querySelector('#wxVideoPlayer video');
                    window.__vv.push({
                        open: !!(window.__wxVideo && window.__wxVideo.isOpen()),
                        ready: v ? v.readyState : -1,
                        t: v ? v.currentTime : -1,
                    });
                }, 100);
            }""")
        err = []
        try:
            M.execute_step(bot, "播放视频", {"序号": "1"})
            print("    ✓ 播放视频 {'序号': '1'}")
        except Exception as e:                           # noqa: BLE001
            err.append(str(e))
            print("    ✗ 播放视频 -> %s" % e)
        samples = page.evaluate(
            """() => { clearInterval(window.__vvTimer);
                       const s = window.__vv || []; window.__vv = []; return s; }""")
        opened_any = any(s["open"] for s in samples)
        ready_peak = max([s["ready"] for s in samples], default=0)
        t_peak = max([s["t"] for s in samples if s["t"] >= 0], default=0.0)
        print("    [采样] %d 帧 | 出现过open=%s ready峰值=%s currentTime峰值=%.2f" % (
            len(samples), opened_any, ready_peak, t_peak))
        r3 = (not err) and opened_any and ready_peak >= 2 and t_peak > 0.1

        print("[6] 播放器开着时 [闪回聊天]（顺路关干净）…")
        # 先手动开着一个视频，再闪回
        page.evaluate(
            "(o) => !!(window.__wxVideo && window.__wxVideo.open(o.src, {cover: o.cover}))",
            {"src": VID0, "cover": ""})
        M._pump_wait(0.5)
        if not do_step(bot, "闪回聊天", {"回到": "阿月"}, "6_back"):
            return 1
        M._pump_wait(0.4)
        blk = page.evaluate(
            "() => { const f = document.getElementById('wxCutBlack');"
            " return f ? getComputedStyle(f).opacity : null; }")
        vopen = page.evaluate(
            "() => !!(window.__wxVideo && window.__wxVideo.isOpen"
            " && window.__wxVideo.isOpen())")
        pm = page.evaluate(
            "() => (window.__wxPeer && window.__wxPeer.isOpen()) || {}")
        print("    [闪回后] 播放器=%s 朋友圈=%s 黑幕opacity=%s" % (
            vopen, pm.get("moments"), blk))
        snap(page, "C_back_chat")
        r4 = bool(not vopen and not pm.get("moments") and float(blk) == 0.0)

        report["result"] = {
            "闪进后视频动态已渲染": r1,
            "JS直开视频真的在播(readyState>=2且时间前进)": r2,
            "[播放视频]动作整链路播放中确在播": r3,
            "视频开着闪回能干净收场": r4,
        }
        if err:
            report["errors"].append("播放视频: %s" % err[0])
        print("\n===== 结果 =====")
        print(json.dumps(report["result"], ensure_ascii=False, indent=2))
        if report["errors"]:
            print("错误:", report["errors"])
        return 0 if all(report["result"].values()) else 1
    finally:
        try:
            bot.stop()
        except Exception:                                    # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
