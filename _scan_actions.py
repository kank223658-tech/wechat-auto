# -*- coding: utf-8 -*-
"""第四轮：动作库一致性。对比 editor_server.py 的 ACTIONS 定义 vs main.py 实际派发。只读。"""
import re, os, json

ROOT = r"G:\weixin-auto"


def read(p):
    with open(os.path.join(ROOT, p), "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


srv = read("editor_server.py")
main = read("main.py")

# 服务端动作定义： {"action": "xxx", "category": ...
srv_actions = re.findall(r'\{"action":\s*"([^"]+)"\s*,\s*"category"', srv)
# 有些定义是多行，补一次宽松匹配
loose = re.findall(r'"action":\s*"([^"]+)"', srv)
seen = []
for a in srv_actions + loose:
    if a not in seen:
        seen.append(a)
srv_actions = seen

# main.py 派发：if action == "xxx" / action in ("a","b") / _do_xxx
dispatch = set()
for m in re.finditer(r'action\s*==\s*"([^"]+)"', main):
    dispatch.add(m.group(1))
for m in re.finditer(r'action\s+in\s*\(([^)]*)\)', main):
    for s in re.findall(r'"([^"]+)"', m.group(1)):
        dispatch.add(s)
for m in re.finditer(r'act\s*==\s*"([^"]+)"', main):
    dispatch.add(m.group(1))
for m in re.finditer(r'ACTIONS\s*=\s*\{([^}]*)\}', main):
    for s in re.findall(r'"([^"]+)"', m.group(1)):
        dispatch.add(s)
# set 常量里的中文动作名
for m in re.finditer(r'(?:ACTIONS|_ACTIONS|TIMEABLE_ACTIONS|MY_EMOJI_ACTIONS|PEER_EMOJI_ACTIONS|BG_PEER_EMOJI_ACTIONS|_TYPING_ACTIONS)\s*=\s*\{([^}]*)\}', main):
    for s in re.findall(r'"([^"]+)"', m.group(1)):
        dispatch.add(s)

print("=" * 70)
print("A. 服务端 UI 定义了、但 main.py 里找不到派发分支的动作：")
print("=" * 70)
missing = [a for a in srv_actions if a not in dispatch]
for a in missing:
    print("  ✗", a)
if not missing:
    print("  （无）")

print()
print("=" * 70)
print("B. main.py 里派发、但服务端 ACTIONS 未定义的动作（可能是隐藏/旧动作）")
print("=" * 70)
for a in sorted(dispatch):
    if a not in srv_actions and a.strip():
        # 只报含中文的，过滤英文标识符噪声
        if re.search(r'[\u4e00-\u9fff]', a):
            print("  ? ", a)

print()
print("动作定义数(服务端):", len(srv_actions))
print("派发名(主程序):", len([d for d in dispatch if re.search(r'[\u4e00-\u9fff]', d)]))

# 手册
man = read("editor/manual.js")
man_names = set(re.findall(r'name:\s*"([^"]+)"', man))
print()
print("=" * 70)
print("C. 服务端定义了但《使用手册》里没有的动作")
print("=" * 70)
for a in srv_actions:
    if a not in man_names:
        print("  ✗", a)

print()
print("=" * 70)
print("D. 手册里有、但服务端 ACTIONS 没有的动作（旧版残留）")
print("=" * 70)
for a in sorted(man_names):
    if re.search(r'[\u4e00-\u9fff]', a) and a not in srv_actions:
        print("  ? ", a)
