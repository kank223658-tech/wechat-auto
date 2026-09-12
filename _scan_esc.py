# -*- coding: utf-8 -*-
"""扫描 script_generator.py 里的「双重转义」残留。

起因：用 heredoc 往文件里写补丁时，`\n` 会被多转义一层，
落到源码里就成了字面量 `\\n`（两个字符：反斜杠 + n），
运行时字符串里就真的出现「\n」两个可见字符，而不是换行。
"""
import sys

DOUBLE = "\\" + "\\"          # 两个反斜杠
NEEDLE = DOUBLE + "n"          # 字面量 \\n（源码里写了两条反斜杠）

path = sys.argv[1] if len(sys.argv) > 1 else "script_generator.py"
src = open(path, encoding="utf-8").read()
lines = src.splitlines()

hits = []
for i, ln in enumerate(lines, 1):
    if NEEDLE in ln:
        hits.append((i, ln))

print("文件: %s  总行数: %d" % (path, len(lines)))
print("含字面 \\\\n 的行数: %d" % len(hits))
print("-" * 70)
for i, ln in hits:
    print("%5d| %s" % (i, ln))
