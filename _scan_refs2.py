# -*- coding: utf-8 -*-
"""第二轮：只看真实代码引用（排除 .workbuddy 记忆笔记与 md 文档），
并单独分析 enhance/ 目录每个文件的被引用情况。只读。"""
import os, re, json

ROOT = r"G:\weixin-auto"

EXCLUDE_EXT = {".png", ".jpg", ".jpeg", ".mp4", ".gif", ".mp3", ".db", ".pyc",
               ".woff", ".woff2", ".ttf", ".zip", ".7z", ".ico", ".webp", ".json"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".workbuddy", "_archive_dev_20260909"}
# 归档/临时目录不参与引用索引
SKIP_PREFIX = ("_archive",)


def collect():
    index = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        parts = [] if rel == "." else rel.split(os.sep)
        if any(p in SKIP_DIRS or p.startswith(SKIP_PREFIX) for p in parts):
            dirnames[:] = []
            continue
        # 限制深度 3
        if len(parts) > 3:
            dirnames[:] = []
            continue
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXCLUDE_EXT:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(fp) > 20 * 1024 * 1024:
                    continue
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    index[os.path.relpath(fp, ROOT).replace("\\", "/")] = f.read()
            except Exception:
                pass
    return index


index = collect()
print("索引源码文件数:", len(index))

# ---- A. enhance/ 每个文件的被引用情况 ----
enh = os.path.join(ROOT, "enhance")
names = [n for n in sorted(os.listdir(enh)) if os.path.isfile(os.path.join(enh, n))]
print("\n########## enhance/ 文件被引用情况 ##########")
for n in names:
    users = []
    for relp, text in index.items():
        if relp.endswith("/" + n) or relp == "enhance/" + n:
            continue
        if re.search(re.escape(n), text):
            users.append(relp)
    sz = os.path.getsize(os.path.join(enh, n))
    tag = "零引用" if not users else "被引用"
    print("%-8s %-26s %9d B  %s" % (tag, n, sz, ", ".join(sorted(users)[:5])))

# ---- B. enhance 子目录 ----
print("\n########## enhance/ 子目录 ##########")
for d in sorted(os.listdir(enh)):
    p = os.path.join(enh, d)
    if os.path.isdir(p):
        n = sum(len(f) for _, _, f in os.walk(p))
        sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs)
        users = []
        for relp, text in index.items():
            if relp.startswith("enhance/" + d):
                continue
            if re.search(re.escape(d), text):
                users.append(relp)
        print("  %-16s %5d 文件 %9.1f MB  引用: %s" % (d, n, sz / 1e6, ", ".join(sorted(set(users))[:6]) or "无"))

# ---- C. 根目录文件真实引用（排除 md/workbuddy）----
print("\n########## 根目录脚本/配置 真实代码引用 ##########")
for n in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, n)
    if not os.path.isfile(p):
        continue
    ext = os.path.splitext(n)[1].lower()
    if ext not in (".py", ".json", ".txt", ".bat", ".db", ".log"):
        continue
    users = []
    for relp, text in index.items():
        if os.path.basename(relp) == n:
            continue
        if re.search(re.escape(n), text):
            users.append(relp)
    tag = "零引用" if not users else "有引用"
    print("%-8s %-40s %s" % (tag, n, ", ".join(sorted(users)[:6])))
