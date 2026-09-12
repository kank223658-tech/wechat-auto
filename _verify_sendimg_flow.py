# -*- coding: utf-8 -*-
"""真机验证：[发送图片] 新流程 —— 弹「+」功能面板 → 点「照片」→ 预览页 → 自动发送。
用法: py _verify_sendimg_flow.py   （退出码 0 = 全部通过）

链路：
  1) 打开聊天（阿月）→ 无面板态直接 [发送图片]：
     断言中途弹了「+」面板（借 send_image 的时序在页面上留 trace）、
     预览页开过又关、面板收起、图片气泡上屏（DOM + store）。
  2) 键盘开着再发一张：断言键盘/面板全部收起、第二张上屏。
  3) 各阶段截图到 _shot/ 供人工目检。
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
M.SPEED = 2.0

OUT = os.path.join(BASE, "_shot")
os.makedirs(OUT, exist_ok=True)

IMG0 = "/images/avatar/2_20260831_184618_874.jpg"

SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "阿月", "lastText": "", "unread": 0, "messages": []}],
}

errors = []

def do_step(bot, action, params, tag):
    try:
        M.execute_step(bot, action, params)
        print("    ✓ %s %s" % (action, params))
        return True
    except Exception as e:                                   # noqa: BLE001
        errors.append("%s: %s" % (action, e))
        print("    ✗ %s %s -> %s" % (action, params, e))
        try:
            bot.page.screenshot(path=os.path.join(OUT, "sendimg_%s_FAIL.png" % tag))
        except Exception:                                    # noqa: BLE001
            pass
        return False

def snap(page, name):
    try:
        page.screenshot(path=os.path.join(OUT, "sendimg_%s.png" % name))
    except Exception:                                        # noqa: BLE001
        pass

def probe(page, tag):
    info = page.evaluate("""() => {
        let storeHasImg = null;
        try {
            const vm = document.getElementById('app').__vue__;
            const mid = vm.$route.query.mid;
            const cur = vm.$store.state.msgList.baseMsg.find(it => String(it.mid) === String(mid));
            storeHasImg = cur.msg.filter(it => it.image).length;
        } catch (e) { storeHasImg = 'ERR:' + e.message; }
        const sip = document.getElementById('sendImagePreview');
        return {
            domImages: document.querySelectorAll('.dialogue-section .text.msg-image').length,
            storeImages: storeHasImg,
            previewOpen: !!(sip && sip.classList.contains('sip-open')),
            attachOpen: document.body.classList.contains('wxp-open'),
            kbOpen: document.body.classList.contains('wxkb-open'),
            emojiOpen: document.body.classList.contains('wx-emoji-open'),
        };
    }""")
    print("    [%s] %s" % (tag, json.dumps(info, ensure_ascii=False)))
    snap(page, tag)
    return info


def main():
    print("[1] 起真机实例…")
    M.ensure_frontend_running()
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        M._pump_wait(1.0)
        page = bot.page
        bot.apply_scene(SCENE)
        M._pump_wait(0.8)

        print("[2] 打开聊天 → 直接 [发送图片]（无面板态）…")
        if not do_step(bot, "打开聊天", {"联系人": "阿月"}, "0_open"):
            return 1
        M._pump_wait(0.6)
        if not do_step(bot, "发送图片", {"图片": IMG0}, "1_send"):
            return 1
        M._pump_wait(1.6)
        p1 = probe(page, "2_after_send1")

        print("[3] 键盘开着再 [发送图片]（键盘→面板直切）…")
        page.evaluate("() => { window.__wxPanels && window.__wxPanels.set('kb'); }")
        M._pump_wait(0.6)
        kb_before = page.evaluate("() => document.body.classList.contains('wxkb-open')")
        if not do_step(bot, "发送图片", {"图片": IMG0}, "3_send2"):
            return 1
        M._pump_wait(1.6)
        p2 = probe(page, "4_after_send2")

        # ---- 判定 ----
        r1 = (p1["domImages"] >= 1 and str(p1["storeImages"]).isdigit()
              and int(p1["storeImages"] or 0) >= 1)
        r2 = (not p1["previewOpen"] and not p1["attachOpen"]
              and not p1["kbOpen"] and not p1["emojiOpen"])
        r3 = bool(kb_before)
        r4 = (p2["domImages"] >= 2 and not p2["previewOpen"]
              and not p2["attachOpen"] and not p2["kbOpen"])
        result = {
            "第1张上屏(DOM+store)": r1,
            "发完后 预览/加号面板/键盘 全收起": r2,
            "第2次发图前键盘确实开着(直切路径)": r3,
            "第2张上屏且界面全部收起": r4,
        }
        print("\n===== 结果 =====")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if errors:
            print("错误:", errors)
        return 0 if all(result.values()) else 1
    finally:
        try:
            bot.stop()
        except Exception:                                    # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
