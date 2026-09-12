# -*- coding: utf-8 -*-
"""扫描根目录文件被谁引用：用于识别旧版遗留。只读，不修改任何文件。"""
import os, re, json, collections

ROOT = r"G:\weixin-auto"

# 1) 待判定清单：根目录下的脚本/配置/资源
candidates = []
for name in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, name)
    if not os.path.isfile(p):
        continue
    ext = os.path.splitext(name)[1].lower()
    if ext in (".py", ".json", ".txt", ".bat", ".db", ".log", ".md", ".mp4", ".gif"):
        candidates.append(name)

# 2) 索引所有源码文件内容（排除巨型文件与归档目录）
SCAN_DIRS = ["", "editor", "enhance", "preview", "vue-WeChat/src", "vue-WeChat/public",
             "engine_poc", "tools"]
EXCLUDE_EXT = {".png", ".jpg", ".jpeg", ".mp4", ".gif", ".mp3", ".db", ".pyc",
               ".woff", ".woff2", ".ttf", ".zip", ".7z", ".ico", ".webp"}
EXCLUDE_DIR_NAMES = {"node_modules", ".git", "__pycache__", "_archive_dev_20260909",
                     "rime-ice", "dist"}

index = {}   # relpath -> text
for d in SCAN_DIRS:
    base = os.path.join(ROOT, d) if d else ROOT
    if not os.path.isdir(base):
        continue
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIR_NAMES and not x.startswith("_archive")]
        rel = os.path.relpath(dirpath, ROOT)
        # 只扫顶层与浅层，避免进入巨大资源目录
        if rel != "." and rel.count(os.sep) > 2:
            dirnames[:] = []
            continue
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXCLUDE_EXT:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(fp) > 8 * 1024 * 1024:
                    continue
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    index[os.path.relpath(fp, ROOT).replace("\\", "/")] = f.read()
            except Exception:
                pass

print("索引文件数:", len(index))

# 3) 对每个候选，统计在其它文件中的引用
SELFISH = set(candidates)
report = {}
for cand in candidates:
    refs = []
    stem = os.path.splitext(cand)[0]
    pats = [re.escape(cand), re.escape(stem)]
    for relp, text in index.items():
        if os.path.basename(relp) == cand:
            continue
        for pat in pats:
            if re.search(pat, text):
                refs.append(relp)
                break
    report[cand] = refs

no_ref = [c for c, r in report.items() if not r]
print("\n===== 零引用文件 (%d) =====" % len(no_ref))
for c in no_ref:
    sz = os.path.getsize(os.path.join(ROOT, c))
    print("  %-42s %10d B" % (c, sz))

print("\n===== 有引用文件 =====")
for c in candidates:
    r = report[c]
    if r:
        print("  %-42s -> %s" % (c, ", ".join(sorted(set(r))[:6])))

json.dump(report, open(os.path.join(ROOT, "_scan_refs_out.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n明细已写入 _scan_refs_out.json")
