# -*- coding: utf-8 -*-
"""把 script_generator.py 里被双重转义的 `\\n` 修回 `\n`。

只动「源码里写了两个反斜杠 + n」的那些行，且逐行确认该行不含
真正的四反斜杠写法（`\\\\\\\\`，正则里的字面反斜杠），避免误伤。
"""
import io
import sys

PATH = "script_generator.py"
DOUBLE_N = "\\" + "\\" + "n"      # 源码里的 \\n（错）
SINGLE_N = "\\" + "n"             # 源码里的 \n（对）
FOUR_BS = "\\" + "\\" + "\\" + "\\"

src = io.open(PATH, encoding="utf-8").read()
lines = src.splitlines(True)

fixed = 0
for i, ln in enumerate(lines):
    if DOUBLE_N not in ln:
        continue
    if FOUR_BS in ln:
        print("跳过（含四反斜杠，可能是正则）第 %d 行" % (i + 1))
        continue
    new = ln.replace(DOUBLE_N, SINGLE_N)
    if new != ln:
        lines[i] = new
        fixed += 1

io.open(PATH, "w", encoding="utf-8", newline="").write("".join(lines))
print("修正 %d 行" % fixed)
