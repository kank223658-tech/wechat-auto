# -*- coding: utf-8 -*-
"""核对提示词里的换行 vs 字面反斜杠-n。"""
import sys
sys.path.insert(0, ".")
import script_generator as sg

skills = sg.load_enabled_skills()
p = sg.build_generation_prompt(actions=None, people_block="【人物库】香儿、susu",
                               preferences="", reference_text="", category="美女", skills=skills)

print("字符数:", len(p))
print("真实换行(\\n 字符):", p.count("\n"))
print("字面反斜杠+n(两字符):", p.count("\\n"))
print("字面反斜杠+n(四字符):", p.count("\\\\" + "n"))
print()
pos = p.find("\\" + "n")
print("首个字面反斜杠+n 位置:", pos)
if pos >= 0:
    print("   上下文:", repr(p[max(0, pos - 40):pos + 20]))
print()
print("---- 最后 20 行 ----")
for ln in p.splitlines()[-20:]:
    print("   ", ln[:110])
