# -*- coding: utf-8 -*-
"""中间帧检查：闪黑过程里黑幕是否真的全黑（opacity → 1）。

  _black_in(慢速0.5s) → 截图 + 读 opacity → 截图应接近全黑 → _black_out
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import main as M

M.FRAME_CAPTURE_ENABLED = False
M.ENABLE_AUDIO = False
M.ENABLE_BGM = False
M.SPEED = 3.0

IMG0 = "/images/avatar/2_20260831_184618_874.jpg"
SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "阿月", "lastText": "", "unread": 0, "messages": []}],
}


def main():
    M.ensure_frontend_running()
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        M._pump_wait(1.0)
        bot.apply_scene(SCENE)
        M._pump_wait(0.6)
        M.execute_step(bot, "打开聊天", {"联系人": "阿月"})
        M._pump_wait(0.6)

        # 慢速淡入便于抓中间帧：淡入到 0.35s 时画面应已接近全黑
        bot._black_in(0.5)
        op = bot.page.evaluate(
            "() => { const f = document.getElementById('wxCutBlack');"
            " return f ? getComputedStyle(f).opacity : null; }")
        bot.page.screenshot(path=os.path.join(BASE, "_shot", "flashblack_mid.png"))
        print("黑幕中间帧 opacity =", op)
        bot._black_out(0.3)
        M._pump_wait(0.5)
        op2 = bot.page.evaluate(
            "() => { const f = document.getElementById('wxCutBlack');"
            " return f ? getComputedStyle(f).opacity : null; }")
        print("淡出后 opacity =", op2)
        ok = op is not None and float(op) > 0.9 and (op2 is None or float(op2) == 0.0)
        print("结论:", "✓ 闪黑中间帧确实全黑" if ok else "✗ 黑幕没有生效")
        return 0 if ok else 1
    finally:
        try:
            bot.stop()
        except Exception:                                    # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
