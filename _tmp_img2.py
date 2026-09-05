# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import json
from main import parse_script_text, _strip_trailing_time

print("==== 实时动作（图片 + 时间）====")
for t in [
    "[发送图片] /images/avatar/01.jpg | 00:10",
    "[对方发图片] /images/avatar/02.jpg | 昨天 23:52",
    "[我方发送图片] /images/avatar/03.jpg | 18:22",
    "[发送图片] /images/avatar/04.jpg",
    "[我方打字] 我下班了 | 18:22",
    "[发送语音] 5 | 00:10",   # 语音不在 TIMEABLE，秒数回退默认（不崩溃）
]:
    print(repr(t), "->", parse_script_text(t))

print("\n==== _strip_trailing_time 图片路径 ====")
for s in ["/images/avatar/01.jpg | 00:10", "/images/a|b.jpg | 18:22"]:
    print(repr(s), "->", _strip_trailing_time(s))
