# -*- coding: utf-8 -*-
"""分离「活文件」中的悬空引用，排除文档/已废弃演示文件/_backup。只读。"""
import os, re, collections

ROOT = r"G:\weixin-auto"
STATIC = {
    "/images/": os.path.join(ROOT, "vue-WeChat", "public", "images"),
    "/videos/": os.path.join(ROOT, "vue-WeChat", "public", "videos"),
}
LIVE = ("main.py", "editor_server.py", "preview_ui.py", "enhance/", "editor/",
        "vue-WeChat/src/", "scene.json", "reference_workflow.json", "workflow.json",
        "people.json", "peer_presets.json", "reference_scripts.json")
NOISE = ("enhance/_backup/", "editor/_redesign/", "README.md", "清理扫描报告.md",
         ".workbuddy/", "vue-WeChat/public/_", "vue-WeChat/README.md")
SKIP = {"node_modules", "dist", ".git", "engine", "_archive_dev_20260909"}

found = collections.defaultdict(lambda: collections.defaultdict(int))
allfiles = collections.defaultdict(lambda: collections.defaultdict(int))

for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in SKIP and not d.startswith("_archive")]
    rel = os.path.relpath(dp, ROOT)
    if rel.count(os.sep) > 3:
        dns[:] = []
        continue
    for fn in fns:
        if os.path.splitext(fn)[1].lower() not in (".py", ".js", ".vue", ".html", ".css", ".less", ".json", ".md"):
            continue
        fp = os.path.join(dp, fn)
        r = os.path.relpath(fp, ROOT).replace("\\", "/")
        try:
            if os.path.getsize(fp) > 20 * 1024 * 1024:
                continue
            txt = open(fp, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in re.finditer(r'["\'`(](/(?:images|videos)/[^"\'`)\s,;]+)', txt):
            p = m.group(1)
            pre = next((k for k in STATIC if p.startswith(k)), None)
            if not pre or p.endswith("/"):
                continue
            if os.path.isfile(os.path.join(STATIC[pre], p[len(pre):].replace("/", os.sep))):
                continue
            allfiles[p][r] += 1
            if any(r.startswith(x) for x in LIVE) and not any(r.startswith(x) for x in NOISE):
                found[p][r] += 1

print("=" * 76)
print(f"【A】活文件中的悬空引用：{len(found)} 个路径")
print("=" * 76)
for p in sorted(found, key=lambda x: -sum(found[x].values())):
    tot = sum(found[p].values())
    fs = sorted(found[p])
    print(f"  {p:50s} {tot:3d} 处 / {len(fs)} 文件   {fs[0] if len(fs)==1 else ''}")

print()
print("=" * 76)
print("【B】涉及的活文件")
print("=" * 76)
byf = collections.Counter()
for p, v in found.items():
    for r, c in v.items():
        byf[r] += c
for r, c in byf.most_common():
    print(f"  {r:56s} {c} 处")

print()
print("=" * 76)
print(f"【C】噪声（文档 / _backup / _redesign / 测试页）：{len(allfiles) - len(found)} 个路径只在这些地方出现")
print("=" * 76)
for p in sorted(allfiles):
    if p in found:
        continue
    fs = sorted(allfiles[p])
    print(f"  {p:50s} {len(fs)} 文件   {', '.join(fs[:2])}")
