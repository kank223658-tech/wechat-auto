# -*- coding: utf-8 -*-
"""候选条探针：敲一个拼音后数一行候选个数 + 量相邻候选间距（只读，不改页面状态）。"""
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
print("target:", repr(name))
assert name, "主页没有可见联系人"

bot.open_chat(name)
# 打开键盘（不敲字，避免打字管线干扰探针）
bot.page.evaluate("() => window.__wxKeyboard && window.__wxKeyboard.show({instant:true})")
time.sleep(0.4)
# 喂一个单音节拼音 + 10 个候选（引擎页大小），观察实际渲染几个、间距多少
r = bot.page.evaluate(
    """() => {
        const kb = window.__wxKeyboard;
        const cands = ['好','号','浩','豪','壕','毫','郝','耗','嚎','貉'];
        const shown = kb.showCandidates('hao', cands);
        const items = [...document.querySelectorAll('#kbCandList .kb-cand-item')];
        const rects = items.map(el => el.getBoundingClientRect());
        const gaps = [];
        for (let i = 1; i < rects.length; i++)
            gaps.push(Math.round(rects[i].left - rects[i-1].right));
        return {
            requested: cands.length, shown,
            texts: items.map(el => (el.querySelector('b')||{}).textContent || ''),
            gaps, listW: document.getElementById('kbCandList').clientWidth,
        };
    }""")
print(json.dumps(r, ensure_ascii=False))
assert r["shown"] == 8, "期望一行 8 个，实际 %d" % r["shown"]

# 用例2：两个拼音的词候选（多字词）——同样应出满 8 个且间距更紧
r2 = bot.page.evaluate(
    """() => {
        const kb = window.__wxKeyboard;
        const cands = ['好的','号的','豪的','壕的','毫的','郝的','耗的','嚎的','貉的','浩的'];
        const shown = kb.showCandidates('haode', cands);
        const items = [...document.querySelectorAll('#kbCandList .kb-cand-item')];
        const rects = items.map(el => el.getBoundingClientRect());
        const gaps = [];
        for (let i = 1; i < rects.length; i++)
            gaps.push(Math.round(rects[i].left - rects[i-1].right));
        const multiN = items.filter(el => el.classList.contains('kb-cand-multi')).length;
        return { requested: cands.length, shown, multiN, gaps,
                 widths: rects.map(r => Math.round(r.width)),
                 scrollW: document.getElementById('kbCandList').scrollWidth,
                 clientW: document.getElementById('kbCandList').clientWidth,
                 lastRight: Math.round(rects[rects.length-1].right) };
    }""")
print(json.dumps(r2, ensure_ascii=False))
assert r2["shown"] == 7, "词候选期望自然放 7 个，实际 %d" % r2["shown"]
assert r2["multiN"] == 7, "多字类未生效: %d" % r2["multiN"]

# 用例3/4：三字词、四字词行——个数与间距是否均衡
def word_row_case(pinyin, cands):
    return bot.page.evaluate(
        """(args) => {
            const kb = window.__wxKeyboard;
            const shown = kb.showCandidates(args[0], args[1]);
            const items = [...document.querySelectorAll('#kbCandList .kb-cand-item')];
            const rects = items.map(el => el.getBoundingClientRect());
            const gaps = [];
            for (let i = 1; i < rects.length; i++)
                gaps.push(Math.round(rects[i].left - rects[i-1].right));
            return { py: args[0], shown, texts: items.map(el => (el.querySelector('b')||{}).textContent || ''),
                     gaps, lastRight: Math.round(rects[rects.length-1].right) };
        }""", [pinyin, cands])

r3 = word_row_case('haodeya', ['好的呀','号的呀','豪的呀','壕的呀','毫的呀','郝的呀','耗的呀','嚎的呀'])
print(json.dumps(r3, ensure_ascii=False))
r4 = word_row_case('bukeyisi', ['不可思议','不好意思','不客气啊','不肯意思','不克意思','不可示意','不可四忆'])
print(json.dumps(r4, ensure_ascii=False))
bot.page.screenshot(path="_candbar_8up.png")
print("CAND_PROBE_OK")

bot.browser.close() if bot.browser else bot.context.close()
bot._release_profile_lock()
bot._pw.stop()
