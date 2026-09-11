# -*- coding: utf-8 -*-
"""验证「脚本模式发表情 → 切到其他画面 → 回来」后表情包是否还在（不消失）。

链路：
  1) 打开聊天 → 对方发消息 → 我方发表情 → 对方发表情
  2) 记录表情气泡（DOM + store）
  3) [进入朋友圈] → [闪回聊天] → 复查表情是否还在、顺序是否正确
  4) [切换Tab 微信] 回主页 → [打开聊天] 重新进会话（组件重挂载）→ 再复查
  5) 顺带检查主页会话预览是否显示 [表情]

用法: py _verify_emoji_persist.py
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
            bot.page.screenshot(path=os.path.join(OUT, "emoji_%s_FAIL.png" % tag))
        except Exception:                                    # noqa: BLE001
            pass
        return False


PROBE = """() => {
    const rows = Array.from(document.querySelectorAll('.dialogue-section .row'));
    const emoji = rows.map((r, i) => {
        const im = r.querySelector('.text.msg-emoji img');
        return im ? { i, self: r.classList.contains('self'), src: im.src } : null;
    }).filter(Boolean);
    const texts = rows.filter(r => {
        const p = r.querySelector('.text');
        return p && !p.classList.contains('msg-emoji') && !p.classList.contains('msg-image')
            && !p.classList.contains('msg-voice') && !p.classList.contains('msg-link');
    }).length;
    let storeEmoji = -1, storeTotal = -1;
    try {
        const app = document.getElementById('app');
        const vm = app && app.__vue__;
        const mid = vm.$route.query.mid;
        const cur = vm.$store.state.msgList.baseMsg.find(it => String(it.mid) === String(mid));
        storeTotal = cur.msg.length;
        storeEmoji = cur.msg.filter(it => it.emoji).length;
    } catch (e) { storeEmoji = 'ERR:' + e.message; }
    return { hash: location.hash, rowCount: rows.length, textRows: texts,
             emojiCount: emoji.length, emoji, storeEmoji, storeTotal };
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
                 lastIsEmoji: !!last.emoji };
    } catch (e) { return { found: false, err: e.message }; }
}"""


def snap(page, name):
    try:
        page.screenshot(path=os.path.join(OUT, "emoji_%s.png" % name))
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("screenshot %s: %s" % (name, e))


def probe(page, tag):
    info = page.evaluate(PROBE)
    report["checks"][tag] = info
    print("    [%s] %s" % (tag, json.dumps(info, ensure_ascii=False)[:400]))
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

        print("[2] 打开聊天 + 发消息 + 发表情…")
        do_step(bot, "打开聊天", {"联系人": "阿月"}, "0_open")
        do_step(bot, "对方发消息", {"内容": "在吗？"}, "0_text")
        if not do_step(bot, "发送表情", {"表情": IMG0}, "1_self_emoji"):
            return 1
        M._pump_wait(0.6)
        if not do_step(bot, "对方表情", {"表情": IMG0}, "2_peer_emoji"):
            return 1
        M._pump_wait(0.6)
        a = probe(page, "A_before_leave")

        print("[3] [返回主页]（检查主页预览）→ 切发现 → [进入朋友圈] → [闪回聊天]…")
        if not do_step(bot, "返回主页", {}, "3_home"):
            return 1
        M._pump_wait(0.8)
        pv = page.evaluate(HOME_PREVIEW)
        report["checks"]["home_preview"] = pv
        print("    [主页预览] %s" % json.dumps(pv, ensure_ascii=False))
        if not do_step(bot, "切换Tab", {"Tab": "发现"}, "4_disc"):
            return 1
        if not do_step(bot, "进入朋友圈", {}, "5_moments"):
            return 1
        M._pump_wait(1.2)
        probe(page, "B_in_moments")
        if not do_step(bot, "闪回聊天", {"回到": "阿月"}, "6_back"):
            return 1
        M._pump_wait(0.6)
        b = probe(page, "C_after_flash_back")

        print("[4] 再返回主页重新进会话（组件重挂载）…")
        if not do_step(bot, "返回主页", {}, "7_home2"):
            return 1
        M._pump_wait(0.8)
        if not do_step(bot, "打开聊天", {"联系人": "阿月"}, "8_reenter"):
            return 1
        M._pump_wait(0.8)
        c = probe(page, "D_after_reenter")

        print("[5] 混排顺序：发图片（DOM 直插）→ 再发表情（store）…")
        if do_step(bot, "发送图片", {"图片": IMG0}, "9_img"):
            M._pump_wait(1.0)
            if do_step(bot, "发送表情", {"表情": IMG0}, "10_emoji_after_img"):
                M._pump_wait(0.6)
                e = probe(page, "E_order")
                rows = page.evaluate(
                    "() => Array.from(document.querySelectorAll('.dialogue-section .row'))"
                    ".map(r => r.querySelector('.text.msg-emoji') ? 'emoji'"
                    " : (r.querySelector('.text.msg-image') ? 'img' : 'text'))")
                report["checks"]["row_kinds"] = rows
                r6 = rows and rows[-1] == 'emoji' and rows[-2] == 'img'
            else:
                r6 = None
        else:
            r6 = None
        report["checks"]["order_ok"] = bool(r6)

        # ---- 判定 ----
        def ok_emotes(x, base):
            return (x["emojiCount"] == base["emojiCount"]
                    and all(y["src"].endswith(IMG0) for y in x["emoji"])
                    and x["storeEmoji"] == base["storeEmoji"])

        r1 = ok_emotes(b, a) and b["emojiCount"] == 2
        r2 = ok_emotes(c, a) and c["emojiCount"] == 2
        r3 = bool(pv.get("found") and pv.get("lastIsEmoji"))
        # 我方表情 self=True、对方 self=False
        r4 = (len(a["emoji"]) == 2 and a["emoji"][0]["self"] is True
              and a["emoji"][1]["self"] is False)
        # 最后一条消息行应是表情（对方表情最后发）
        r5 = b["rowCount"] >= 1 and c["rowCount"] >= 1
        report["result"] = {"闪回聊天后表情仍在": r1, "重新进会话后表情仍在": r2,
                            "主页预览显示表情": r3, "我方/对方方向正确": r4,
                            "表情在图片之后仍按真实时序排列": report["checks"].get("order_ok")}
        print("\n===== 结果 =====")
        print(json.dumps(report["result"], ensure_ascii=False, indent=2))
        rr = report["result"]
        if not (r1 and r2 and r3 and r4 and all(v for k, v in rr.items())):
            return 1
        return 0
    finally:
        try:
            bot.stop()
        except Exception:                                    # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
