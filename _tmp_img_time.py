# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import json
from script_translator import _line_to_message, split_history_block
from main import parse_script_text

print("==== 历史块 _line_to_message（图片/语音 + 时间）====")
for t in [
    "懒猫不懒：[图片] 草地自拍照 | 00:10",
    "我：[图片] 健身房自拍 | 昨天 23:52",
    "香儿：[语音] 5秒 | 18:22",
    "香儿：[语音] 5秒",
    "王心乐：正常文字 | 20:00",
]:
    print(json.dumps(_line_to_message(t), ensure_ascii=False))

print("\n==== 完整历史块 split_history_block ====")
src = """[历史会话]
[会话] 陆香儿
陆香儿：[图片] 草地自拍照 | 00:10
我：好看 | 00:12
[历史会话结束]
[打开聊天] 陆香儿
"""
hs, cleaned, warns, rmap = split_history_block(src)
for s in hs:
    print(json.dumps(s, ensure_ascii=False))

print("\n==== 实时动作（图片类当前是否带时间？）====")
for t in [
    "[发送图片] /images/avatar/01.jpg | 00:10",
    "[对方发图片] /images/avatar/02.jpg | 00:10",
    "[我方打字] 我下班了 | 18:22",
]:
    print(repr(t), "->", parse_script_text(t))
