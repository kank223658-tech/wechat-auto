# -*- coding: utf-8 -*-
"""全量悬空引用扫描：抽出所有 /images/... 与 /videos/... 路径，逐个查文件是否存在。只读。"""
import os, re, collections

ROOT = r"G:\weixin-auto"
STATIC = {
    "/images/": os.path.join(ROOT, "vue-WeChat", "public", "images"),
    "/videos/": os.path.join(ROOT, "vue-WeChat", "public", "videos"),
}
SKIP_DIRS = {"node_modules", "dist", ".git", "engine", "_archive_dev_20260909"}

files = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith("_archive")]
    rel = os.path.relpath(dp, ROOT)
    if rel.count(os.sep) > 3:
        dns[:] = []
        continue
    for fn in fns:
        if os.path.splitext(fn)[1].lower() in (".py", ".js", ".vue", ".html", ".css", ".less", ".json", ".md"):
            files.append(os.path.join(dp, fn))

hits = collections.defaultdict(list)   # 缺失路径 -> [(文件, 行号, 行内容)]
for fp in files:
    try:
        if os.path.getsize(fp) > 20 * 1024 * 1024:
            continue
        lines = open(fp, "r", encoding="utf-8", errors="ignore").read().splitlines()
    except Exception:
        continue
    for i, line in enumerate(lines, 1):
        for m in re.finditer(r'["\'`(](/(?:images|videos)/[^"\'`)\s,;]+)', line):
            path = m.group(1)
            prefix = next((p for p in STATIC if path.startswith(p)), None)
            if not prefix:
                continue
            f = os.path.join(STATIC[prefix], path[len(prefix):].replace("/", os.sep))
            if not os.path.isfile(f):
                hits[path].append((os.path.relpath(fp, ROOT).replace("\\", "/"), i))

print("=" * 74)
print(f"悬空引用共 {len(hits)} 个路径")
print("=" * 74)
for path in sorted(hits, key=lambda p: -len(hits[p])):
    locs = hits[path]
    print(f"\n{path}   （{len(locs)} 处）")
    for fn, ln in locs[:8]:
        print(f"    {fn}:{ln}")
    if len(locs) > 8:
        print(f"    …… 另有 {len(locs)-8} 处")

# 按文件聚合，便于修复
print()
print("=" * 74)
print("按文件聚合（需要修的文件）")
print("=" * 74)
byfile = collections.defaultdict(set)
for path, locs in hits.items():
    for fn, ln in locs:
        byfile[fn].add(path)
for fn in sorted(byfile, key=lambda f: -len(byfile[f])):
    print(f"  {fn}  ->  {len(byfile[fn])} 个悬空路径")
