# -*- coding: utf-8 -*-
"""临时诊断：复现 editor /api/translate 离线路径，看 [编辑主页] 数据最终形态。写入 out.txt。"""
import json
import script_translator as st

TXT = """[历史会话]
[会话] luna-富婆
luna-富婆：[图片] 穿着酒红色真丝吊带睡裙的对镜自拍照
luna-富婆：夏天快到了，刚买的，会不会有点太露了呀？[纠结的emoji]
[会话] 学员-小康
学员-小康：[图片] 早安未回的聊天截图
学员-小康：诺哥，她半天没回我了，我是不是该打个语音过去问问？
[会话] 香儿
香儿：[图片] 落地窗旁小吧台上的半杯红酒
香儿：又失眠了，烦。
[会话] 安雅
安雅：你太小了
[会话] 妍妍
妍妍：来姨妈了
[会话] 熙熙（酒吧）
熙熙（酒吧）：来喝吗
[会话] 苏苏
苏苏：拍得好看吗
[会话] 乌云乌云
乌云乌云：那你今晚不过来？
[会话] 萝卜快跑
萝卜快跑：到了联系
[历史会话结束]
[打开聊天] luna-富婆
[等待] 0.5
[我方打字] xyz
[对方发消息] 什么意思？那对谁危险？
[返回主页]
[等待] 0.5
[打开聊天] 香儿
[等待] 0.5
[对方发消息] 没人跟我碰杯呀
[返回主页]
[等待] 0.5
[打开聊天] 学员-小康
[等待] 0.5
[返回主页]
[等待] 0.5
"""

lines = []
# 1) split_history_block
history_steps, cleaned, hist_warnings, repl_map = st.split_history_block(TXT)
# 2) translate_offline(cleaned) -> steps
steps, warn = st.translate_offline(cleaned)
# 3) 剔除 AI 补的编辑主页
translated = [s for s in steps if s.get("action") != "编辑主页"]
# 4) 合并
result = history_steps + translated
# 5) 人物归一
st.normalize_step_people(result, pre_mapping=repl_map)

lines.append("==== 合并后 steps 动作序列 ====")
for idx, s in enumerate(result):
    params = s.get("params") or {}
    brief = {k: (v if not isinstance(v, list) else f"<list[{len(v)}]>") for k, v in params.items()}
    lines.append(f"  [{idx}] {s.get('action')} {json.dumps(brief, ensure_ascii=False)}")

# 6) 看 [编辑主页] data 里香儿 / 萝卜快跑 的 messages + unread 计算
lines.append("\n==== [编辑主页] 里香儿 / 萝卜快跑 的最终数据 ====")
home = result[0]["params"]["数据"] if result and result[0].get("action") == "编辑主页" else []
for it in home:
    if it.get("name") in ("香儿", "萝卜快跑"):
        lines.append(f"\n--- {it['name']} ---")
        lines.append(json.dumps(it, ensure_ascii=False, indent=2))
        msgs = it.get("messages") or []
        lastMe = -1
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("dir") == "me":
                lastMe = i
                break
        unread = sum(1 for i in range(lastMe + 1, len(msgs)) if msgs[i].get("dir") != "me")
        lines.append(f"  -> messages={len(msgs)} lastMe={lastMe} unreadCount={unread} "
                     f"read={unread<=0} newMsgCount={unread}")

with open("_tmp_fix_unread_out.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("done")