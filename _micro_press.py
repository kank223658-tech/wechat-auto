# -*- coding: utf-8 -*-
"""微诊断：单次 pressType 是否真的给键加 kb-press 且背景变 #8e8e93。
隔离"class 未生效" vs "高倍速太快抓不到"两种可能。"""
import os
import subprocess
import tempfile
import time

import main as M


def snapshot(bot, name):
    bot.page.screenshot(path=os.path.join(r"F:\weixin-auto\_repro_out", name + ".png"))


def main():
    M.FRAME_CAPTURE_ENABLED = True
    M.ENABLE_AUDIO = False
    M.ENABLE_BGM = False
    out = r"F:\weixin-auto\_repro_out"
    bot = M.WeChatAuto(headless=True)
    M._LIVE_BOT["bot"] = bot
    bot._live_enabled = False
    try:
        M.ensure_frontend_running()
        bot.start()
        bot.open_chat("陆香儿")
        M._pump_wait(0.6)
        bot._kb_show()
        M._pump_wait(0.4)

        # 1) 空闲基线：z 键的 class 与 computed background
        r0 = bot.page.evaluate("""() => {
            const el = document.querySelector('#wxkb .kb-key[data-key="z"]');
            return { cls: el.className, bg: getComputedStyle(el).backgroundColor };
        }""")
        print("[空闲] z 键:", r0)

        # 2) 长按 300ms（应肯定能被采到）
        bot.page.evaluate("window.__wxKeyboard.pressType('z', 300)")
        M._pump_wait(0.06)
        r1 = bot.page.evaluate("""() => {
            const el = document.querySelector('#wxkb .kb-key[data-key="z"]');
            return { cls: el.className, bg: getComputedStyle(el).backgroundColor };
        }""")
        print("[按下300ms] z 键:", r1)
        snapshot(bot, "press_z_300")
        M._pump_wait(0.5)

        # 3) 模拟高倍速：连按 n,i 各 40ms，中间间隔 4ms
        bot.page.evaluate("window.__wxKeyboard.pressType('n', 40)")
        M._pump_wait(0.004)
        bot.page.evaluate("window.__wxKeyboard.pressType('i', 40)")
        M._pump_wait(0.004)
        r2 = bot.page.evaluate("""() => {
            const out = {};
            document.querySelectorAll('#wxkb .kb-key[data-key]').forEach(el => {
                if (el.classList.contains('kb-press')) out[el.dataset.key] = getComputedStyle(el).backgroundColor;
            });
            const pop = document.querySelector('.kb-pop');
            out.__pop = pop ? { show: pop.classList.contains('kb-pop-show'),
                                text: pop.textContent } : null;
            return out;
        }""")
        print("[快速连按 n,i] 处于 kb-press 的键及其背景:", r2)
        snapshot(bot, "press_rapid")
    finally:
        try:
            bot.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
