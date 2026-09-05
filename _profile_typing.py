# -*- coding: utf-8 -*-
"""打字流畅度探针：定位 40 倍速打字/回删的"卡顿"来源。

P1 (py-paced@40x)：真实 human_type 40 倍速打一段长文本 + delete_chars 回删，
   页内 rAF 采样帧间隔 + longtask 观察，量化掉帧。
P2 (JS 纯同步)：页内直接连续 pressType 字母/backspace（不经 CDP 逐键往返），
   测每键同步耗时 + 候选重绘次数/耗时；再关掉 Rime 引擎(ready=false)对比，
   分离「词库/DOM」与「引擎异步」各自贡献。

用法：python _profile_typing.py [--typing-speed 40]
"""
import argparse
import json
import os

import main as M
import script_translator  # noqa: F401


JS_START = r"""
() => {
  window.__probe = { raf: [], last: 0, on: false, longs: [], tasks: 0 };
  window.__probe.on = true;
  const rec = () => {
    if (!window.__probe.on) return;
    const n = performance.now();
    if (window.__probe.last) window.__probe.raf.push(n - window.__probe.last);
    window.__probe.last = n;
    requestAnimationFrame(rec);
  };
  requestAnimationFrame(rec);
  try {
    const po = new PerformanceObserver((l) => {
      for (const e of l.getEntries()) {
        if (e.entryType === 'longtask') {
          window.__probe.longs.push(e.duration);
          window.__probe.tasks += 1;
        }
      }
    });
    po.observe({ entryTypes: ['longtask'] });
    window.__probe.po = po;
  } catch (e) { window.__probe.poErr = String(e); }
}
"""

JS_STOP = r"""
() => {
  if (!window.__probe) return {};
  window.__probe.on = false;
  if (window.__probe.po) { try { window.__probe.po.disconnect(); } catch (e) {} }
  const p = window.__probe;
  const raf = p.raf;
  const n = raf.length;
  const sum = raf.reduce((a, b) => a + b, 0);
  const sorted = raf.slice().sort((a, b) => a - b);
  const pct = (q) => { if (!n) return 0; return sorted[Math.min(n - 1, Math.floor(n * q))]; };
  const cnt = (lo, hi) => raf.filter((d) => d >= lo && d < hi).length;
  return {
    n, avg: +(sum / Math.max(1, n)).toFixed(2),
    p50: +pct(0.5).toFixed(2), p95: +pct(0.95).toFixed(2), max: +(pct(1)).toFixed(2),
    ge_33: cnt(33, 1e9), ge_50: cnt(50, 1e9), ge_100: cnt(100, 1e9),
    longs: p.longs, longTasks: p.tasks,
  };
}
"""


def reset_input(bot):
    """清空输入框并保留焦点，避免上次残留影响。"""
    bot.page.evaluate(
        "() => { const el = document.activeElement;"
        " if (el && (el.tagName==='INPUT'||el.tagName==='TEXTAREA')) { el.value='';"
        " el.dispatchEvent(new Event('input',{bubbles:true})); } }")


def p1_typed_run(bot, text):
    """真实 40 倍速打字(不发) + 回删全程，返回页内帧间隔统计。"""
    bot.page.evaluate(JS_START)
    bot.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.show()")
    M.TYPE_SPEED = 40.0
    bot.human_type(".chat-txt", text, send=False)
    M._pump_wait(0.3)
    bot.delete_chars(-1)          # 回删全程
    M._pump_wait(0.4)
    return bot.page.evaluate(JS_STOP)


def p2_js_probe(bot, pinyin_chars, engine_on=True, with_backspace=True):
    """页内纯 JS：连敲 pinyin_chars（真实按键链路），测每键同步耗时与候选重绘。

    engine_on=False 时把 __rimeEngine.ready 置假再测（分离 Rime 异步刷新贡献）。
    """
    script = r"""
    (args) => {
      const [letters, engineOn, withBs] = args;
      const kb = window.__wxKeyboard;
      if (!kb) return { err: 'no kb' };
      const E = window.__rimeEngine;
      const enginePrev = E ? E.ready : false;
      if (!engineOn && E) { try { E.ready = false; } catch (e) {} }
      // 包裹候选渲染统计
      const scPrev = kb.showCandidates;
      const renders = [];
      kb.showCandidates = function () {
        const t0 = performance.now();
        const r = scPrev.apply(this, arguments);
        renders.push(performance.now() - t0);
        return r;
      };
      // 包 input 事件统计
      const durs = [];
      const raws = { pt: [], bs: [], ev: [], q: [] };
      const el = document.activeElement;
      const typeOne = (l, kind) => {
        const t0 = performance.now();
        kb.pressType(l, 4);
        raws[kind].push(performance.now() - t0);
      };
      for (const l of letters) typeOne(l, 'pt');
      if (withBs) {
        // 逐字母回退到清空，模拟真实回删链路
        for (let i = 0; i < letters.length; i++) typeOne('backspace', 'bs');
      }
      const raw = (a) => {
        if (!a.length) return 0;
        const s = a.slice().sort((x, y) => x - y);
        const sum = a.reduce((x, y) => x + y, 0);
        return { n: a.length, avg: +(sum / a.length).toFixed(3),
                 p50: +s[Math.floor(s.length * 0.5)].toFixed(3),
                 p95: +s[Math.min(s.length - 1, Math.floor(s.length * 0.95))].toFixed(3),
                 max: +s[s.length - 1].toFixed(3) };
      };
      kb.showCandidates = scPrev;   // 还原
      if (!engineOn && E) { try { E.ready = enginePrev; } catch (e) {} }
      return { pt: raw(raws.pt), bs: raw(raws.bs),
               render: raw(renders), rendersN: renders.length,
               keysN: letters.length + (withBs ? letters.length : 0) };
    }
    """
    return bot.page.evaluate(script, [list(pinyin_chars), bool(engine_on),
                                      bool(with_backspace)])


def run(typing_speed):
    M.SPEED = 1.0
    M.TYPE_SPEED = float(typing_speed)
    M.FRAME_CAPTURE_ENABLED = False   # 关闭采集干扰，专注测时间
    M.ENABLE_AUDIO = False
    M.ENABLE_BGM = False

    bot = M.WeChatAuto(headless=True)
    M._LIVE_BOT["bot"] = bot
    bot._live_enabled = False
    text = "今晚我请你吃饭然后我们一起去楼下的新店尝尝好不好"
    pinyin = "jinwanwoqingnichifanranhouwomenyiqiqulouxia"
    try:
        M.ensure_frontend_running()
        bot.start()
        bot.open_chat("陆香儿")
        M._pump_wait(0.8)
        # 聚焦输入框 + 键盘就位 + 模式拼音
        box = bot.page.locator(".chat-txt")
        box.first.click()
        bot._kb_show()
        bot.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.setImeMode('pinyin')")
        M._pump_wait(0.5)

        # 预热输入管线（对齐 main 预热逻辑，避免首个字符渲染慢）
        try:
            bot.warmup_typing_pipeline("陆香儿") if hasattr(bot, 'warmup_typing_pipeline') else None
        except Exception:
            pass
        reset_input(bot)

        print("== P1 真实 40x 打字+回删（rAF 帧间隔统计）==")
        r1 = p1_typed_run(bot, text)
        print(json.dumps(r1, ensure_ascii=False))

        print("\n== P2 JS 纯同步每键耗时（引擎开启）==")
        r2 = p2_js_probe(bot, pinyin, engine_on=True, with_backspace=True)
        print(json.dumps(r2, ensure_ascii=False))
        reset_input(bot)

        print("\n== P2' JS 纯同步每键耗时（引擎关闭 ready=false）==")
        r3 = p2_js_probe(bot, pinyin, engine_on=False, with_backspace=True)
        print(json.dumps(r3, ensure_ascii=False))
        reset_input(bot)
        return r1, r2, r3
    finally:
        try:
            bot.stop()
        except Exception:
            pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--typing-speed", type=float, default=40.0)
    args = ap.parse_args()
    run(args.typing_speed)
