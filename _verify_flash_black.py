# -*- coding: utf-8 -*-
"""验证「闪到对方朋友圈」新动作 + 「闪回聊天」默认自动闪黑。

链路：
  1) 聊天页 → [闪到对方朋友圈]（默认闪黑）→ __wxPeer.moments 应为 open
  2) [闪回聊天]（默认闪黑）→ __wxPeer 全关、仍在聊天页、消息仍在
  3) [闪到对方朋友圈] 闪黑=否（裸硬切回归验证）
  4) 探针检查 #wxCutBlack 幕布存在 + 淡出后 opacity 归零
  5) 走一遍 dispatch（execute_step）别名：「闪进对方朋友圈」

用法: py _verify_flash_black.py   （退出码 0 = 全部通过）
"""
import os
import sys
import json

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

SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "阿月", "lastText": "", "unread": 0, "messages": []}],
}

PEER = {
    "name": "陆香儿", "wxid": "luxer", "avatar": IMG0, "cover": IMG0,
    "signature": "保持热爱",
    "posts": [{"date": "昨天", "text": "今天的风很舒服", "images": [IMG0]}],
}

report = {"errors": [], "checks": {}}


def do_step(bot, action, params, tag):
    try:
        M.execute_step(bot, action, params)
        print("    ✓ %s %s" % (action, params))
        return True
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("%s: %s" % (action, e))
        print("    ✗ %s %s -> %s" % (action, params, e))
        try:
            bot.page.screenshot(path=os.path.join(OUT, "flashblack_%s_FAIL.png" % tag))
        except Exception:                                    # noqa: BLE001
            pass
        return False


STATE = """() => {
    const st = (window.__wxPeer && window.__wxPeer.isOpen)
        ? window.__wxPeer.isOpen() : { profile: false, moments: false };
    const blk = document.getElementById('wxCutBlack');
    let inChat = false, lastText = null;
    try {
        const vm = document.getElementById('app').__vue__;
        inChat = String(vm.$route.path).indexOf('dialogue') >= 0;
        const mid = vm.$route.query.mid;
        const cur = vm.$store.state.msgList.baseMsg.find(
            it => String(it.mid) === String(mid));
        lastText = cur && cur.msg.length ? cur.msg[cur.msg.length - 1].text : null;
    } catch (e) {}
    return {
        profile: !!st.profile, moments: !!st.moments,
        inChat, lastText,
        blackCurtain: !!blk,
        blackOpacity: blk ? getComputedStyle(blk).opacity : null,
    };
}"""


def snap(page, name):
    try:
        page.screenshot(path=os.path.join(OUT, "flashblack_%s.png" % name))
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("screenshot %s: %s" % (name, e))


def probe(page, tag):
    info = page.evaluate(STATE)
    report["checks"][tag] = info
    print("    [%s] %s" % (tag, json.dumps(info, ensure_ascii=False)))
    snap(page, tag)
    return info


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

        print("[2] 进入聊天 + 铺对方人设…")
        do_step(bot, "打开聊天", {"联系人": "阿月"}, "0_open")
        do_step(bot, "编辑对方资料", {"数据": PEER}, "1_peer")
        do_step(bot, "对方发消息", {"内容": "晚上一起吃饭吗"}, "2_msg")
        M._pump_wait(0.6)
        a = probe(page, "A_in_chat")
        if not a["inChat"]:
            report["errors"].append("起始状态不在聊天页")
            return 1

        print("[3] [闪到对方朋友圈]（默认闪黑）…")
        if not do_step(bot, "闪到对方朋友圈", {}, "3_to_peer"):
            return 1
        M._pump_wait(0.4)
        b = probe(page, "B_peer_moments")
        # 注意：对方朋友圈是覆盖层，路由仍停在 dialogue（inChat=true 是正常的）
        r1 = bool(b["moments"] and b["profile"] and b["blackCurtain"]
                  and float(b["blackOpacity"]) == 0.0)

        print("[4] [闪回聊天] 回到=阿月（默认闪黑）…")
        if not do_step(bot, "闪回聊天", {"回到": "阿月"}, "4_back"):
            return 1
        M._pump_wait(0.4)
        c = probe(page, "C_back_chat")
        r2 = bool(c["inChat"] and not c["profile"] and not c["moments"]
                  and c["lastText"] == "晚上一起吃饭吗")

        print("[5] [闪到对方朋友圈] 闪黑=否（裸硬切回归）…")
        if not do_step(bot, "闪到对方朋友圈", {"闪黑": "否"}, "5_noblack"):
            return 1
        M._pump_wait(0.4)
        d = probe(page, "D_peer_noblack")
        r3 = bool(d["moments"] and d["profile"])

        print("[6] 别名「闪进对方朋友圈」+ [闪回聊天] 闪白=是（旧版回归）…")
        if not do_step(bot, "闪回聊天", {}, "6_back2"):
            return 1
        M._pump_wait(0.4)
        if not do_step(bot, "闪进对方朋友圈", {}, "7_alias"):
            return 1
        M._pump_wait(0.4)
        e = probe(page, "E_alias")
        r4 = bool(e["moments"])
        if not do_step(bot, "闪回聊天", {"闪白": "是"}, "8_flashwhite"):
            return 1
        M._pump_wait(0.4)
        f = probe(page, "F_flashwhite")
        r5 = bool(f["inChat"] and not f["moments"])

        report["result"] = {
            "闪到对方朋友圈(闪黑)打开成功且幕布归零": r1,
            "闪回聊天(闪黑)回到聊天且消息还在": r2,
            "闪黑=否裸硬切仍可用": r3,
            "别名「闪进对方朋友圈」可用": r4,
            "旧版闪白回归可用": r5,
        }
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
