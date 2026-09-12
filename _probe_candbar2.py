# -*- coding: utf-8 -*-
"""复现用户截图的乱间距候选行：真实按键流程敲出 he，等引擎回填后 dump 候选条 DOM。"""
import json
import time
import main

bot = main.WeChatAuto(headless=True)
bot._live_enabled = False
bot.start()

name = bot.page.evaluate(
    """() => {
        const vm = document.getElementById('app').__vue__;
        const bm = (vm.$store.state.msgList && vm.$store.state.msgList.baseMsg) || [];
        for (const b of bm) {
            if (b.type === 'group' && b.group_name) return b.group_name;
            if (b.user && b.user[0] && b.user[0].remark) return b.user[0].remark;
        }
        return '';
    }""")
assert name, "主页没有可见联系人"
bot.open_chat(name)
bot.page.evaluate("() => window.__wxKeyboard && window.__wxKeyboard.show({instant:true})")
time.sleep(0.8)   # 等引擎就绪

def dump(tag):
    r = bot.page.evaluate(
        """() => {
            const list = document.getElementById('kbCandList');
            const kids = [...list.children];
            return kids.map(el => {
                const r = el.getBoundingClientRect();
                const img = el.querySelector('img');
                return {
                    cls: el.className,
                    text: (el.textContent || '').trim().slice(0, 12),
                    hasImg: !!img, imgOk: img ? img.naturalWidth > 0 : null,
                    x: Math.round(r.x), w: Math.round(r.width),
                };
            });
        }""")
    print(tag, json.dumps(r, ensure_ascii=False))

bot.page.evaluate(
    """() => {
        const vis = [...document.querySelectorAll('.chat-txt')].find(e => e.offsetParent);
        vis.focus();
        return !!document.activeElement;
    }""")
time.sleep(0.2)
# 生产同款驱动：pressRun 逐键推进（main.py _type_run 就是调它）
bot.page.evaluate("() => window.__wxKeyboard.pressRun(['h'], 60, 40, '', '')")
time.sleep(0.7)
time.sleep(0.6)
st = bot.page.evaluate(
    """() => ({ val: (document.querySelector('.chat-txt')||{}).value,
                visVal: ([...document.querySelectorAll('.chat-txt')].find(e => e.offsetParent)||{}).value,
                engineReady: !!(window.__rimeEngine && window.__rimeEngine.ready) })""")
print("state_h", json.dumps(st, ensure_ascii=False))
dump("after_h")
bot.page.evaluate("() => window.__wxKeyboard.pressRun(['e'], 60, 40, '', '')")
time.sleep(1.0)
st2 = bot.page.evaluate(
    """() => ({ val: (document.querySelector('.chat-txt')||{}).value,
                composing: document.getElementById('wxkb').className })""")
print("state_he", json.dumps(st2, ensure_ascii=False))
dump("after_he")
bot.page.screenshot(path="_candbar_he.png")

bot.browser.close() if bot.browser else bot.context.close()
bot._release_profile_lock()
bot._pw.stop()
print("PROBE2_OK")
