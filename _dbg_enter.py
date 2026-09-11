# -*- coding: utf-8 -*-
"""临时排查：为什么 [进入朋友圈] 偶尔找不到入口。"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))

import main as M

DUMP = """() => {
    const vis = (el) => { const b = el.getBoundingClientRect();
        return b.width > 0 && b.height > 0; };
    const txt = (el) => (el.textContent || '').trim().slice(0, 16);
    const cells = Array.from(document.querySelectorAll('.weui-cell')).filter(vis);
    return {
        body: document.body.className,
        navTabs: Array.from(document.querySelectorAll('#wx-nav nav dl')).map(txt),
        cells: cells.map(txt).slice(0, 20),
        hasMoments: cells.some(c => (c.textContent || '').indexOf('朋友圈') >= 0),
        pages: Array.from(document.querySelectorAll('#app > *')).map(
            e => e.id + '.' + (e.className || '').split(' ').join('.')).slice(0, 12),
        exploreIds: Array.from(document.querySelectorAll('#explore *[id], .explore *[id]'))
            .map(e => e.id).slice(0, 12),
    };
}"""


def dump(bot, tag):
    try:
        info = bot.page.evaluate(DUMP)
    except Exception as e:                                  # noqa: BLE001
        print("[%s] evaluate err %s" % (tag, e))
        return
    print("[%s] %s" % (tag, json.dumps(info, ensure_ascii=False)))


wf = json.load(open(os.path.join(BASE, "_demo_grid_wf.json"), encoding="utf-8"))
scene_edit = wf["steps"][1]["params"]["数据"]

bot = M.WeChatAuto(headless=True)
try:
    bot.start()
    dump(bot, "启动后")
    M.execute_step(bot, "编辑主页", wf["steps"][0]["params"])
    dump(bot, "编辑主页后")
    M.execute_step(bot, "编辑朋友圈", {"数据": scene_edit})
    dump(bot, "编辑朋友圈后")
    M.execute_step(bot, "切换Tab", {"Tab": "发现"})
    bot._wait(0.6)
    dump(bot, "切换Tab 发现 后")
    bot._wait(1.5)
    dump(bot, "再等 1.5s")
    loc = bot.page.locator('.weui-cell:has-text("朋友圈"):visible')
    print("朋友圈入口 count =", loc.count())
finally:
    try:
        bot.stop()
    except Exception as e:                                  # noqa: BLE001
        print("stop err", e)
