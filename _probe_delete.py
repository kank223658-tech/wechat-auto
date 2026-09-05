# -*- coding: utf-8 -*-
"""删除流畅度探针：回删期间逐 rAF 帧采样输入框长度，量化每帧删字数量抖动。

用法：python _probe_delete.py [--typing-speed 40]
"""
import argparse
import json
import statistics

import main as M
import script_translator  # noqa: F401

SAMPLE_START = r"""
() => {
  const el = document.querySelector('.chat-txt');
  if (!el) return 'no-input';
  window.__delProbe = { samples: [], on: true, start: performance.now() };
  const tick = () => {
    if (!window.__delProbe.on) return;
    window.__delProbe.samples.push([performance.now() - window.__delProbe.start,
                                    el.value.length]);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return 'started';
}
"""

SAMPLE_STOP = r"""
() => {
  if (!window.__delProbe) return {};
  const p = window.__delProbe;
  p.on = false;
  return p.samples;
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--typing-speed", type=float, default=40.0)
    ap.add_argument("--text", type=str, default="今晚我请你吃饭然后我们一起去楼下的新店尝尝")
    args = ap.parse_args()

    M.SPEED = 1.0
    M.TYPE_SPEED = float(args.typing_speed)
    M.FRAME_CAPTURE_ENABLED = False
    M.ENABLE_AUDIO = False
    M.ENABLE_BGM = False

    bot = M.WeChatAuto(headless=True)
    M._LIVE_BOT["bot"] = bot
    bot._live_enabled = False
    text = args.text
    try:
        M.ensure_frontend_running()
        bot.start()
        bot.open_chat("陆香儿")
        M._pump_wait(0.8)
        bot.human_type(".chat-txt", text, send=False)
        M._pump_wait(0.3)

        cur = bot.page.evaluate("() => document.querySelector('.chat-txt').value.length")
        print(f"[就绪] 输入框长度={cur}")
        bot.page.evaluate(SAMPLE_START)
        t0_del = None
        bot.delete_chars(-1)
        M._pump_wait(0.2)
        rows = bot.page.evaluate(SAMPLE_STOP)
        print("[采样帧数]", len(rows))

        # 每帧删除字数 = 本帧长度 - 上帧长度（负值表示删字）
        dels = []                     # 帧级删除量（负数）
        for (t, ln) in rows:
            if not dels or True:
                pass
        changes = []                  # 连续每帧变化量
        prev = None
        for (t, ln) in rows:
            changes.append(prev - ln if prev is not None else 0)
            prev = ln

        del_changes = [c for c in changes if c > 0]
        total_del = sum(del_changes)
        del_frames = len(del_changes)
        if total_del <= 0:
            print("[警告] 未采到长度变化")
            return
        from collections import Counter
        cnt = Counter(del_changes)
        print("[删除帧分布] 发生删除的帧=%d 总删字=%d" % (del_frames, total_del))
        for k in sorted(cnt):
            print("  单帧删 %d 字: %d 帧 (%.1f%%)" % (k, cnt[k], 100.0 * cnt[k] / del_frames))
        # 活动区间：第一次删字帧 .. 最后一次删字帧 之间的"本帧没删字"空窗（真正的节奏空洞）
        del_idx = [i for i, c in enumerate(changes) if c > 0]
        if del_idx:
            lo, hi = del_idx[0], del_idx[-1]
            s = 0
            streaks = []
            for i in range(lo + 1, hi + 1):
                if changes[i] <= 0:
                    s += 1
                else:
                    if s:
                        streaks.append(s)
                    s = 0
            if s:
                streaks.append(s)
            if streaks:
                print("[删字区间空窗] 次数=%d 最大=%d 帧 平均=%.2f 帧（区间 %d→%d 帧）"
                      % (len(streaks), max(streaks), statistics.mean(streaks), lo, hi))
            else:
                print("[删字区间空窗] 无：删字逐帧连续，无空洞")
    finally:
        try:
            bot.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
