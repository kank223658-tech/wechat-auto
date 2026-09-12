# -*- coding: utf-8 -*-
"""全场景剧本离线解析校验：
1) main.parse_script_text（脚本模式运行用的解析）与
   script_translator.translate_offline（编辑器离线解析）双路对比，步骤是否一模一样；
2) 校验剧本里引用的 /images /videos 资源是否真实存在；
3) 汇总离线解析 warning / 未知指令；
4) 覆盖率：与 action_registry 全量动作对比，列出没覆盖的动作。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import main as M
import script_translator as T
import action_registry as R

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_fullcover_script.txt")
PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "public")
SCENE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene.json")

text = open(SCRIPT, encoding="utf-8").read()

# ---- 1. 双路解析对比 ----
steps_a = M.parse_script_text(text)
steps_b, warnings = T.translate_offline(text)

# 公平对比：把脚本模式的结果也过一遍 validate_steps（编辑器离线解析的统一规范化层）。
# validate_steps 只做「剔除空参数 + 补缺省值 + 时长转 float」，语义无副作用。
steps_a_norm, extra_a = T.validate_steps(
    {"action": s["action"], "params": s.get("params", {})} for s in steps_a)

def canon(steps):
    return json.dumps(steps, ensure_ascii=False, sort_keys=True)

same = canon(steps_a_norm) == canon(steps_b)
print(f"[解析] 脚本模式 parse_script_text 步数 = {len(steps_a)}")
print(f"[解析] 离线 translate_offline   步数 = {len(steps_b)}")
print(f"[解析] 规范化后两路解析结果{'完全一致（一模一样）' if same else '存在差异！'}")

if not same:
    n = max(len(steps_a_norm), len(steps_b))
    for i in range(n):
        sa = steps_a_norm[i] if i < len(steps_a_norm) else None
        sb = steps_b[i] if i < len(steps_b) else None
        if canon([sa]) != canon([sb]):
            print(f"  差异 @ 步骤{i}:")
            print(f"    脚本模式: {json.dumps(sa, ensure_ascii=False)}")
            print(f"    离线解析: {json.dumps(sb, ensure_ascii=False)}")

# ---- 2. warning / 未知指令 ----
if warnings:
    print(f"[离线解析] {len(warnings)} 条 warning：")
    for w in warnings:
        print("  -", w)
else:
    print("[离线解析] 无 warning")

# parse_script_text 的未知行/告警是直接 print 的，这里重新静默扫一遍统计
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    M.parse_script_text(text)
script_mode_warns = [l for l in buf.getvalue().splitlines() if "警告" in l or "警告" in l]
if script_mode_warns:
    print(f"[脚本模式] {len(script_mode_warns)} 条解析警告：")
    for l in script_mode_warns:
        print("  ", l)
else:
    print("[脚本模式] 无解析警告")

# ---- 3. 资源存在性 ----
import re
ASSET_RE = re.compile(r"/(?:images|videos)/[\w\-.%𝙒𝙚𝘾𝙝𝙖𝙩___]+?\.(?:png|jpg|jpeg|webp|mp4|gif)", re.I)
missing = []
for m in sorted(set(ASSET_RE.findall(text))):
    p = os.path.join(PUBLIC, m.lstrip("/"))
    if not os.path.isfile(p):
        missing.append(m)
if missing:
    print(f"[资源] 缺失 {len(missing)} 个：")
    for m in missing:
        print("  -", m)
else:
    print("[资源] 剧本引用的全部 /images /videos 资源都存在")

# emoji 图（3D emoji 名字解析）
for s in steps_a:
    if s["action"] in ("发送emoji", "对方emoji"):
        print(f"[emoji] {s['action']} -> {s['params'].get('表情')}")

# ---- 4. 覆盖率 ----
reg = {a["action"] for a in R.ACTIONS}
used = [s["action"] for s in steps_a]
uncovered = sorted(reg - set(used))
unknown_used = sorted(set(used) - reg)
print(f"[覆盖率] 剧本用到 {len(set(used))}/{len(reg)} 个动作")
if uncovered:
    print("[覆盖率] 未覆盖动作：", "、".join(uncovered))
else:
    print("[覆盖率] 已覆盖全部注册动作")
if unknown_used:
    print("[覆盖率] 用到但不在注册表的动作：", "、".join(unknown_used))

# ---- 5. 联系人核对（scene.json 主页名字） ----
scene = json.load(open(SCENE, encoding="utf-8"))
names = {h.get("name") for h in scene.get("home", [])}
bad = []
for s in steps_a:
    p = s.get("params") or {}
    for key in ("联系人", "接收人"):
        v = p.get(key)
        if v and v not in names:
            bad.append((s["action"], key, v))
print(f"[联系人] scene.json 主页共 {len(names)} 个：{sorted(n for n in names if n)}")
if bad:
    print("[联系人] 剧本里引用但场景中不存在的：", bad)
else:
    print("[联系人] 剧本引用的联系人在场景里都能找到")
