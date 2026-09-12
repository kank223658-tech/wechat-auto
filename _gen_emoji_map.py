# -*- coding: utf-8 -*-
"""从 names.json 生成 vue 前端内嵌 emoji 静态映射（wxemoji3d_map.js）。

为什么生成静态文件而不是前端 fetch names.json：对话气泡渲染是同步的，
fetch 有竞态（首屏消息可能先于 JSON 返回渲染出裸 [微笑] 文字），生成期固化最稳。
names.json 仍是唯一数据源；改了 emoji 表后重跑本脚本即可。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "vue-WeChat", "public", "images", "wxemoji3d", "names.json")
DST = os.path.join(ROOT, "vue-WeChat", "src", "assets", "wxemoji3d_map.js")

with open(SRC, encoding="utf-8") as fh:
    data = json.load(fh)
items = data.get("emoji", []) if isinstance(data, dict) else []

mapping = {}
for e in items:
    if not isinstance(e, dict) or not e.get("file"):
        continue
    name = str(e.get("name", "")).strip()
    if name:
        mapping[name] = e["file"]
    for a in e.get("aliases") or []:
        a = str(a).strip()
        if a and a not in mapping:
            mapping[a] = e["file"]

lines = [
    "/* AUTO-GENERATED from public/images/wxemoji3d/names.json —— 请勿手改。",
    " * 重新生成：py _gen_emoji_map.py",
    " * 用途：聊天文本气泡内嵌 [名称] 3D emoji（dialogue.vue richText）。",
    " */",
    "export const WXEMOJI3D_MAP = {",
]
for k, v in mapping.items():
    lines.append('  "%s": "%s",' % (k, v))
lines.append("};")
lines.append("")
lines.append("export default WXEMOJI3D_MAP;")
lines.append("")

with open(DST, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines))
print("OK %d entries -> %s" % (len(mapping), DST))

# —— 同步 chat_extra.js：面板格子 title 标签（文件 -> 名称） ——
CEX = os.path.join(ROOT, "enhance", "chat_extra.js")
file2name = {}
for e in items:
    if isinstance(e, dict) and e.get("file"):
        nm = str(e.get("name", "")).strip()
        if nm:
            file2name[str(e["file"])] = nm
_nbegin = "/* [GEN:EMOJI3D_NAMES] 由 py _gen_emoji_map.py 维护，勿手改 */"
_nend = "/* [/GEN:EMOJI3D_NAMES] */"
_nblock = (_nbegin + "\n    const EMOJI3D_NAMES = "
           + json.dumps(file2name, ensure_ascii=False, separators=(",", ":"))
           + ";\n    " + _nend)
with open(CEX, encoding="utf-8") as fh:
    _src = fh.read()
_pat = re.compile(re.escape(_nbegin) + r"[\s\S]*?" + re.escape(_nend))
if _pat.search(_src):
    _src = _pat.sub(lambda m: _nblock, _src, count=1)
else:
    _anchor = "/* [/GEN:EMOJI3D_ORDER] */"
    assert _anchor in _src, "chat_extra.js ORDER 块缺失"
    _src = _src.replace(_anchor, _anchor + "\n" + _nblock, 1)
with open(CEX, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(_src)
print("OK EMOJI3D_NAMES %d entries -> %s" % (len(file2name), CEX))
