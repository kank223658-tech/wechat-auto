# -*- coding: utf-8 -*-
"""验证「脚本模式」下所有聊天消息类型在切画面后都持久化（不消失）。

覆盖类型：文字 / 图片(我方+对方) / 语音(我方+对方) / 表情(我方+对方) /
链接卡片 / 转账卡(我方+对方) / 转发 / 撤回系统提示。

链路：
  1) 聊天页铺满 11 条各类消息 → 记录 DOM 行类型序列 + store 条目类型序列
  2) [返回主页] → 切发现 → [进入朋友圈] → [闪回聊天 回到=阿月] → 复查序列一致
  3) [返回主页] → [打开聊天]（组件重挂载）→ 复查序列一致
  4) [撤回我的消息] → 最后一条消失 + 「你撤回了一条消息」出现
  5) 再切走再回来 → 撤回状态不回退

用法: py _verify_chat_persist.py   （退出码 0 = 全部通过）
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
            bot.page.screenshot(path=os.path.join(OUT, "persist_%s_FAIL.png" % tag))
        except Exception:                                    # noqa: BLE001
            pass
        return False


PROBE = """() => {
    const kind = (r) => {
        if (r.querySelector('.text.msg-image')) return 'image';
        if (r.querySelector('.text.msg-emoji')) return 'emoji';
        if (r.querySelector('.text.msg-voice')) return 'voice';
        if (r.querySelector('.text.msg-transfer')) return 'transfer';
        if (r.querySelector('.text.msg-link')) return 'link';
        return 'text';
    };
    const rows = Array.from(document.querySelectorAll('.dialogue-section .row'));
    let storeKinds = null;
    try {
        const vm = document.getElementById('app').__vue__;
        const mid = vm.$route.query.mid;
        const cur = vm.$store.state.msgList.baseMsg.find(it => String(it.mid) === String(mid));
        storeKinds = cur.msg.map(it => it.system ? 'system'
            : it.image ? 'image' : it.emoji ? 'emoji' : it.voice ? 'voice'
            : it.transfer ? 'transfer' : it.link ? 'link' : 'text');
    } catch (e) { storeKinds = 'ERR:' + e.message; }
    const sys = Array.from(document.querySelectorAll('.dialogue-section .msg-system'))
        .map(e => e.textContent);
    return { hash: location.hash, domKinds: rows.map(kind), storeKinds, systemTips: sys };
}"""

HOME_PREVIEW = """() => {
    try {
        const vm = document.getElementById('app').__vue__;
        const it = vm.$store.state.msgList.baseMsg.find(x => {
            const u = x.user && x.user[0];
            return u && (u.nickname === '阿月' || u.remark === '阿月');
        });
        if (!it) return { found: false };
        const last = it.msg[it.msg.length - 1] || {};
        return { found: true, lastText: it.lastText, lastMsgText: last.text,
                 lastIsTransfer: !!last.transfer };
    } catch (e) { return { found: false, err: e.message }; }
}"""


def snap(page, name):
    try:
        page.screenshot(path=os.path.join(OUT, "persist_%s.png" % name))
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("screenshot %s: %s" % (name, e))


def probe(page, tag):
    info = page.evaluate(PROBE)
    report["checks"][tag] = info
    print("    [%s] dom=%s store=%s sys=%s" % (
        tag, info["domKinds"], info["storeKinds"], info["systemTips"]))
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

        print("[2] 铺满 11 条各类消息…")
        do_step(bot, "打开聊天", {"联系人": "阿月"}, "0_open")
        do_step(bot, "对方发消息", {"内容": "在吗？"}, "s1")
        if not do_step(bot, "发送图片", {"图片": IMG0}, "s2"):
            return 1
        M._pump_wait(1.6)
        if not do_step(bot, "对方发图片", {"图片": IMG0}, "s3"):
            return 1
        M._pump_wait(0.8)
        do_step(bot, "发送语音", {"秒数": 3}, "s4")
        M._pump_wait(0.5)
        do_step(bot, "对方语音", {"秒数": 2}, "s5")
        M._pump_wait(0.5)
        if not do_step(bot, "发送表情", {"表情": IMG0}, "s6"):
            return 1
        M._pump_wait(1.2)
        do_step(bot, "对方表情", {"表情": IMG0}, "s7")
        M._pump_wait(0.5)
        if not do_step(bot, "我方发链接", {"标题": "今晚吃什么？好文分享", "来源": "恋爱技巧"}, "s8"):
            return 1
        M._pump_wait(0.5)
        if not do_step(bot, "转账上屏", {"金额": "1.00", "备注": "吃饭"}, "s9"):
            return 1
        M._pump_wait(0.5)
        if not do_step(bot, "对方转账", {"金额": "520.00"}, "s10"):
            return 1
        M._pump_wait(0.5)
        if not do_step(bot, "转发消息", {"内容": "看看这个"}, "s11"):
            return 1
        M._pump_wait(0.6)
        a = probe(page, "A_before_leave")
        if "ERR" in str(a["storeKinds"]):
            report["errors"].append("store 读取失败: %s" % a["storeKinds"])
            return 1

        print("[3] 返回主页（查预览）→ 切发现 → 进朋友圈 → 闪回聊天…")
        if not do_step(bot, "返回主页", {}, "1_home"):
            return 1
        M._pump_wait(0.8)
        pv = page.evaluate(HOME_PREVIEW)
        report["checks"]["home_preview"] = pv
        print("    [主页预览] %s" % json.dumps(pv, ensure_ascii=False))
        if not do_step(bot, "切换Tab", {"Tab": "发现"}, "2_disc"):
            return 1
        if not do_step(bot, "进入朋友圈", {}, "3_moments"):
            return 1
        M._pump_wait(1.2)
        if not do_step(bot, "闪回聊天", {"回到": "阿月"}, "4_back"):
            return 1
        M._pump_wait(0.8)
        c = probe(page, "C_after_flash_back")

        print("[4] 再返回主页重进会话（组件重挂载）…")
        if not do_step(bot, "返回主页", {}, "5_home2"):
            return 1
        M._pump_wait(0.8)
        if not do_step(bot, "打开聊天", {"联系人": "阿月"}, "6_reenter"):
            return 1
        M._pump_wait(0.8)
        d = probe(page, "D_after_reenter")

        print("[5] [撤回我的消息] → 检查提示与持久…")
        if not do_step(bot, "撤回我的消息", {}, "7_withdraw"):
            return 1
        M._pump_wait(0.6)
        e = probe(page, "E_after_withdraw")
        if not do_step(bot, "返回主页", {}, "8_home3"):
            return 1
        M._pump_wait(0.8)
        if not do_step(bot, "打开聊天", {"联系人": "阿月"}, "9_reenter2"):
            return 1
        M._pump_wait(0.8)
        f = probe(page, "F_withdraw_persist")

        # ---- 判定 ----
        r1 = (a["domKinds"] == c["domKinds"] == d["domKinds"])
        r2 = (a["storeKinds"] == c["storeKinds"] == d["storeKinds"])
        r3 = (len(e["domKinds"]) == len(a["domKinds"]) - 1
              and e["domKinds"][-1] == "transfer"
              and any("撤回" in s for s in e["systemTips"]))
        r4 = (e["domKinds"] == f["domKinds"]
              and any("撤回" in s for s in f["systemTips"]))
        r5 = (len(a["domKinds"]) >= 11
              and {"image", "emoji", "voice", "transfer", "link"} <= set(a["domKinds"]))
        r6 = bool(pv.get("found") and pv.get("lastMsgText") == "转发：看看这个")
        report["result"] = {
            "11类消息铺满": r5,
            "闪回聊天后全部还在": r1,
            "重新进会话后全部还在(store)": r2,
            "撤回后消息消失+提示出现": r3,
            "撤回状态切画面后不回退": r4,
            "主页预览跟随最后一条消息": r6,
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
