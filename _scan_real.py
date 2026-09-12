# -*- coding: utf-8 -*-
"""第三轮：只从「真正的运行入口」出发，统计谁在用 enhance/ 与根目录资源。
入口 = main.py / editor_server.py / preview_ui.py / enhance/_embed_boot.js /
       enhance/config.js / editor/*.html / vue-WeChat/src/** 只读扫描。"""
import os, re, json

ROOT = r"G:\weixin-auto"

CONSUMERS = []


def add(fp):
    if os.path.isfile(fp):
        CONSUMERS.append(os.path.relpath(fp, ROOT).replace("\\", "/"))


for f in ["main.py", "editor_server.py", "preview_ui.py", "script_generator.py",
          "script_translator.py", "create_store.py", "sound_engine.py",
          "make_story_video.py", "preview_ui.py",
          "enhance/_embed_boot.js", "enhance/config.js",
          "editor/index.html", "editor/scene.html", "editor/concurrent.html",
          "editor/manual.js", "editor/shared_picker.js", "editor/moments_editor.js",
          "settings.json", "settings.example.json"]:
    add(os.path.join(ROOT, f))

# vue-WeChat 源码（排除 node_modules / dist / 大资源）
for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "vue-WeChat")):
    dirnames[:] = [d for d in dirnames if d not in ("node_modules", "dist", ".git")]
    rel = os.path.relpath(dirpath, ROOT)
    if rel.count(os.sep) > 3:
        dirnames[:] = []
        continue
    for fn in filenames:
        if os.path.splitext(fn)[1].lower() in (".js", ".vue", ".html", ".json", ".css"):
            add(os.path.join(dirpath, fn))

texts = {}
for c in CONSUMERS:
    try:
        if os.path.getsize(os.path.join(ROOT, c)) > 20 * 1024 * 1024:
            continue
        with open(os.path.join(ROOT, c), "r", encoding="utf-8", errors="ignore") as f:
            texts[c] = f.read()
    except Exception:
        pass
print("真实入口文件数:", len(texts))

# A. enhance/ 全量文件名 -> 被哪些入口引用
enh = os.path.join(ROOT, "enhance")
print("\n########## enhance/ 被真实入口引用情况 ##########")
for n in sorted(os.listdir(enh)):
    p = os.path.join(enh, n)
    if not os.path.isfile(p):
        continue
    users = [c for c, t in texts.items() if re.search(re.escape(n), t)]
    sz = os.path.getsize(p)
    print("[%s] %-24s %9d B  %s" % ("用到" if users else "没人用", n, sz, ", ".join(sorted(users)[:6])))

# B. 根目录 py 是否被入口 import
print("\n########## 根目录 .py 是否被入口 import ##########")
for n in sorted(os.listdir(ROOT)):
    if not n.endswith(".py") or n.startswith("_"):
        continue
    stem = n[:-3]
    users = [c for c, t in texts.items()
             if c != n and re.search(r"(import\s+%s\b|from\s+%s\s+import)" % (re.escape(stem), re.escape(stem)), t)]
    print("[%s] %-30s %s" % ("被import" if users else "独立脚本", n, ", ".join(sorted(users))))

# C. 根目录 json/txt/bat 是否被入口读取
print("\n########## 根目录 json/txt/bat 被入口读取情况 ##########")
for n in sorted(os.listdir(ROOT)):
    ext = os.path.splitext(n)[1].lower()
    if ext not in (".json", ".txt", ".bat", ".db", ".log"):
        continue
    users = [c for c, t in texts.items() if re.search(re.escape(n), t)]
    sz = os.path.getsize(os.path.join(ROOT, n))
    print("[%s] %-38s %10d B  %s" % ("用到" if users else "没人用", n, sz, ", ".join(sorted(users)[:6])))
