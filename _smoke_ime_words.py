# -*- coding: utf-8 -*-
"""打字冒烟：新词库（视频号/快递柜/开黑吗）经真实键盘管线逐段上屏验证。"""
import json
import main

bot = main.WeChatAuto(headless=True)
bot._live_enabled = False
bot.start()

info = bot.page.evaluate(
    """() => {
        const vm = document.getElementById('app').__vue__;
        const st = vm.$store.state;
        const bm = (st.msgList && st.msgList.baseMsg) || [];
        return {
            baseN: bm.length,
            sample: bm.slice(0, 2).map(b => ({keys: Object.keys(b), user: b.user})),
            allContacts: (st.allContacts || []).slice(0, 3).map(
                c => ({name: c.name, nickname: c.nickname, username: c.username})),
        };
    }""")
print(json.dumps(info, ensure_ascii=False)[:800])

# 从主页可见会话里取一个名字（群用 group_name，单聊用 user[0].remark）
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
text = "视频号今天更新了去快递柜取件咱们开黑吗"
bot.human_type(".chat-txt", text, send=False, show_keyboard=True)
val = bot.page.evaluate('() => (document.querySelector(".chat-txt")||{}).value || ""')
print("committed_ok =", val == text, "| input:", val)

if bot.browser:
    bot.browser.close()
else:
    bot.context.close()
bot._release_profile_lock()
bot._pw.stop()
print("TYPE_SMOKE_OK")
