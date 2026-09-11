# -*- coding: utf-8 -*-
"""打印「发现」页真实 DOM 结构。"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
import main as M

DUMP = """() => {
    const out = { rows: [], html: '' };
    const root = document.querySelector('#explore') || document.body;
    out.html = root.outerHTML.slice(0, 6000);
    // 所有可见文字块的层级路径
    const walk = (el, path) => {
        const b = el.getBoundingClientRect();
        if (b.width <= 0 || b.height <= 0) return;
        const own = Array.from(el.childNodes)
            .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('').trim();
        if (own) out.rows.push([path, el.tagName.toLowerCase(),
                                (el.className || '').toString().slice(0, 40),
                                own.slice(0, 20), Math.round(b.x), Math.round(b.y),
                                Math.round(b.width), Math.round(b.height)]);
        Array.from(el.children).forEach((c, i) => walk(c, path + '/' + i));
    };
    walk(root, 'explore');
    return out;
}"""

bot = M.WeChatAuto(headless=True)
try:
    bot.start()
    M.execute_step(bot, "切换Tab", {"Tab": "发现"})
    bot._wait(1.2)
    info = bot.page.evaluate(DUMP)
    print("=== 可见文字块 ===")
    for r in info["rows"]:
        print("  %-32s %-8s %-40s %-20s x=%-5s y=%-5s w=%-5s h=%-5s" % tuple(r))
    print()
    print("=== DOM 片段 ===")
    print(info["html"])
finally:
    try:
        bot.stop()
    except Exception as e:                                  # noqa: BLE001
        print("stop err", e)
