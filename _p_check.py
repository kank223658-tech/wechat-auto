# -*- coding: utf-8 -*-
import sys, io, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import script_translator as st
import editor_server as es
text = io.open("_p.txt", encoding="utf-8").read()
steps, warnings, source = es._parse_script_to_steps(text, offline=True)
print("source:", source)
print("warnings:", len(warnings))
for w in warnings:
    print("  -", w)
print("总步数:", len(steps))
# 找出 后台消息队列 与 对方后台发消息
print("\n== 后台消息队列 步骤 ==")
for i, s in enumerate(steps):
    if s["action"] == "后台消息队列":
        print("  step", i+1, json.dumps(s["params"], ensure_ascii=False))
print("\n== 对方后台发消息 步骤 ==")
for i, s in enumerate(steps):
    if s["action"] == "对方后台发消息":
        print("  step", i+1, json.dumps(s["params"], ensure_ascii=False))
