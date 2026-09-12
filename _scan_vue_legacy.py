# -*- coding: utf-8 -*-
"""扫描 vue-WeChat 开源底子的遗留视觉资源：图片引用率 / 样式文件引用 / 空目录。只读。"""
import os, re, json

ROOT = r"G:\weixin-auto"
VW = os.path.join(ROOT, "vue-WeChat")

# ---- 1. 建立"消费者"文本索引（所有可能引用图片的代码）----
consumers = {}
for base in [VW, os.path.join(ROOT, "enhance"), os.path.join(ROOT, "editor"),
             os.path.join(ROOT, "vue-WeChat", "public")]:
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in ("node_modules", "dist", ".git", "engine")]
        rel = os.path.relpath(dp, ROOT)
        if rel.count(os.sep) > 4:
            dns[:] = []
            continue
        for fn in fns:
            if os.path.splitext(fn)[1].lower() not in (".vue", ".js", ".html", ".css", ".less", ".json"):
                continue
            fp = os.path.join(dp, fn)
            if os.path.basename(fp) == "_scan_vue_legacy.py":
                continue
            try:
                if os.path.getsize(fp) > 15 * 1024 * 1024:
                    continue
                consumers[os.path.relpath(fp, ROOT).replace("\\", "/")] = \
                    open(fp, "r", encoding="utf-8", errors="ignore").read()
            except Exception:
                pass
# 加上根目录的运行时配置
for f in ["scene.json", "workflow.json", "people.json", "peer_presets.json",
          "reference_workflow.json", "reference_scripts.json", "settings.json"]:
    p = os.path.join(ROOT, f)
    if os.path.isfile(p):
        consumers[f] = open(p, "r", encoding="utf-8", errors="ignore").read()
# 加上动态拼接场景：enhance 里常写 "/images/" + 变量，用目录名兜底判断
dynamic_hints = set()
for relp, txt in consumers.items():
    for m in re.findall(r'["\'`]/images/([A-Za-z0-9_]+)/', txt):
        dynamic_hints.add(m)

print("消费者文件数:", len(consumers))
print("代码里出现的 /images/<目录>/ 名字:", ", ".join(sorted(dynamic_hints)))
print()

IMGDIR = os.path.join(VW, "public", "images")

# ---- 2. 逐图查引用 ----
unused = {}
used = {}
for dp, dns, fns in os.walk(IMGDIR):
    for fn in fns:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            continue
        fp = os.path.join(dp, fn)
        rel = os.path.relpath(fp, IMGDIR).replace("\\", "/")
        sz = os.path.getsize(fp)
        hit = False
        for relp, txt in consumers.items():
            if fn in txt or rel in txt or ("/images/" + rel) in txt:
                hit = True
                break
        (used if hit else unused).setdefault(
            os.path.dirname(rel) or "(根层)", []).append((rel, sz))

print("=" * 72)
print("A. 零引用的图片（按目录分组）")
print("=" * 72)
tot = 0
for d in sorted(unused, key=lambda k: -sum(s for _, s in unused[k])):
    items = unused[d]
    s = sum(x[1] for x in items)
    tot += s
    print(f"\n--- {d}  ({len(items)} 个, {s/1e6:.2f} MB) ---")
    for rel, sz in sorted(items, key=lambda x: -x[1]):
        print(f"    {rel:58s} {sz:9d} B")
print(f"\n零引用合计：{tot/1e6:.2f} MB")

print()
print("=" * 72)
print("B. 被引用的图片（按目录分组，只列数量与体积）")
print("=" * 72)
for d in sorted(used, key=lambda k: -sum(s for _, s in used[k])):
    items = used[d]
    print(f"  {d:26s} {len(items):4d} 个  {sum(x[1] for x in items)/1e6:7.2f} MB")

# ---- 3. 空目录 ----
print()
print("=" * 72)
print("C. 空目录（上游残留）")
print("=" * 72)
for dp, dns, fns in os.walk(IMGDIR):
    if not fns and not dns:
        print("  ", os.path.relpath(dp, IMGDIR))

# ---- 4. 样式文件引用 ----
print()
print("=" * 72)
print("D. src/assets 下的样式/资源文件被引用情况")
print("=" * 72)
for sub in ("css", "less"):
    base = os.path.join(VW, "src", "assets", sub)
    if not os.path.isdir(base):
        continue
    for dp, _, fns in os.walk(base):
        for fn in sorted(fns):
            users = [r for r, t in consumers.items()
                     if r.startswith("vue-WeChat/src") and fn in t]
            print(f"  [{'用到' if users else '没人用'}] {sub}/{fn:34s} {len(users)} 处")
