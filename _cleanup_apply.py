# -*- coding: utf-8 -*-
"""清理执行器（默认空转）。
安全策略：
  1) 年龄过滤：最近 60 分钟内被改动过的文件/目录 一律跳过（并发会话在跑）
  2) 备忘保护：凡在 .workbuddy/memory/*.md 里被提到过的 _*.py 一律保留
  3) 被占用/锁定的文件跳过并记录，不中断
用法： python _cleanup_apply.py          -> 空转，只打印
       python _cleanup_apply.py apply    -> 真删
"""
import os, re, sys, shutil, time, glob

ROOT = r"G:\weixin-auto"
APPLY = len(sys.argv) > 1 and sys.argv[1] == "apply"
CUTOFF = time.time() - 60 * 60          # 60 分钟
PROBE_OK = []
SKIPPED_LOCKED = []
SKIPPED_FRESH = []
SKIPPED_PROTECTED = []


def is_fresh(p):
    try:
        return os.path.getmtime(p) > CUTOFF
    except Exception:
        return True


def dir_is_fresh(p):
    """目录内任一文件是新的，整目录跳过。"""
    for dp, _, fs in os.walk(p):
        for f in fs:
            if is_fresh(os.path.join(dp, f)):
                return True
    return False


# ---------- 1. 从项目备忘里提取受保护的脚本名 ----------
protected = set()
for mf in glob.glob(os.path.join(ROOT, ".workbuddy", "memory", "*.md")):
    txt = open(mf, "r", encoding="utf-8", errors="ignore").read()
    protected |= set(re.findall(r'\b(_[A-Za-z0-9_]+\.py)\b', txt))
    protected |= set(re.findall(r'\b(_[A-Za-z0-9_]+\.json)\b', txt))
# 依赖感知：正向收集——受保护脚本「内部引用到」的其它 _*.py（公共库），一并保护
for _ in range(6):                      # 传递闭包，最多 6 轮
    added = set()
    for name in list(protected):
        fp = os.path.join(ROOT, name)
        if not os.path.isfile(fp):
            continue
        try:
            txt = open(fp, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        deps = set(re.findall(r'\b(_[A-Za-z0-9_]+\.py)\b', txt))
        # 也认 import _ascii / from _ascii import …（不带 .py 的写法）
        for mod in re.findall(r'(?:^|\n)\s*(?:import|from)\s+(_[A-Za-z0-9_]+)', txt):
            deps.add(mod + ".py")
        for dep in deps:
            if dep not in protected and os.path.isfile(os.path.join(ROOT, dep)):
                added.add(dep)
    if not added:
        break
    protected |= added

# 执行器自身不删
protected.add("_cleanup_apply.py")

print(f"[保护] 需保留的脚本 {len(protected)} 个：")
print("       " + ", ".join(sorted(protected)))
print()

# ---------- 2. 目标清单 ----------
targets = []

# A 层：日志 / 临时 dump / 设计草稿
targets += [
    ("A", "enhance/_tmp_p.json"),
    ("A", "enhance/_tmp_wx.json"),
    ("A", "editor/_redesign/scene.html.bak_prepv"),
    ("A", "editor/_redesign/scene.html.bak_fit"),
    ("A", "editor/_redesign/scene.html.bak_sync"),
    ("A", ".cursor/debug-189770.log"),
]
for f in glob.glob(os.path.join(ROOT, "vue-WeChat", "*.log")):
    targets.append(("A", os.path.relpath(f, ROOT)))
for f in glob.glob(os.path.join(ROOT, "_runtime", "t26*")):
    targets.append(("A", os.path.relpath(f, ROOT)))
for f in glob.glob(os.path.join(ROOT, "_runtime", "_*.log")) + \
         glob.glob(os.path.join(ROOT, "_runtime", "vue_serve.log")) + \
         glob.glob(os.path.join(ROOT, "_runtime", "editor_server_launch*.log")):
    targets.append(("A", os.path.relpath(f, ROOT)))
# 根 __pycache__
targets.append(("A", "__pycache__"))

# B 层：根目录一次性脚本 / 测试 JSON / 截图帧图 / 长期未动的探针目录
for f in sorted(glob.glob(os.path.join(ROOT, "_*.py"))):
    targets.append(("B", os.path.relpath(f, ROOT)))
for f in sorted(glob.glob(os.path.join(ROOT, "_*.json"))):
    targets.append(("B", os.path.relpath(f, ROOT)))
for f in sorted(glob.glob(os.path.join(ROOT, "_*.png"))) + \
         sorted(glob.glob(os.path.join(ROOT, "_*.jpg"))) + \
         sorted(glob.glob(os.path.join(ROOT, "_*.jpeg"))) + \
         sorted(glob.glob(os.path.join(ROOT, "_*.txt"))) + \
         sorted(glob.glob(os.path.join(ROOT, "_*.mp4"))):
    targets.append(("B", os.path.relpath(f, ROOT)))
for d in ["_fs", "_ref3", "_ref3b", "_ref3c", "_ref3d", "_ref3e", "_ref30",
          "_ref_crop", "_ref_frames", "_ref_tf", "_ref_tf2", "_vg60",
          "_block_frames", "_block_verify", "_ps_probe"]:
    targets.append(("B", d))

# 注：第三节「存疑」项（engine_poc / enhance/_backup / enhance/rime /
#     复刻_界面 / 演示配置 / preview 等）用户本轮未选中，不在此清单内。

# C 层：上一轮归档
targets.append(("C", "_archive_dev_20260909"))

# ---------- 3. 过滤 + 统计 ----------
plan = {"A": [], "B": [], "C": []}
seen = set()
for layer, rel in targets:
    if rel in seen:
        continue
    seen.add(rel)
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        continue
    name = os.path.basename(rel)
    if name in protected:
        SKIPPED_PROTECTED.append(rel)
        continue
    if os.path.isdir(p):
        if dir_is_fresh(p):
            SKIPPED_FRESH.append(rel + "  (目录内有新文件)")
            continue
    else:
        if is_fresh(p):
            SKIPPED_FRESH.append(rel)
            continue
    plan[layer].append((rel, p))

print("=" * 72)
print("空转结果" if not APPLY else "★ 实际执行 ★")
print("=" * 72)
grand = 0.0
for layer in ("A", "B", "C"):
    items = plan[layer]
    sz = 0
    for rel, p in items:
        if os.path.isfile(p):
            sz += os.path.getsize(p)
        else:
            for dp, _, fs in os.walk(p):
                for f in fs:
                    try:
                        sz += os.path.getsize(os.path.join(dp, f))
                    except Exception:
                        pass
    grand += sz
    print(f"\n--- {layer} 层：{len(items)} 项，{sz / 1e6:.1f} MB ---")
    for rel, _ in items:
        print("   ", rel)

print(f"\n合计可回收：{grand / 1e6:.1f} MB")
print(f"\n[跳过] 因太新（60分钟内动过）{len(SKIPPED_FRESH)} 项：")
for r in SKIPPED_FRESH:
    print("   ", r)
print(f"\n[跳过] 受备忘保护 {len(SKIPPED_PROTECTED)} 项：")
for r in SKIPPED_PROTECTED:
    print("   ", r)

# ---------- 4. 执行 ----------
if APPLY:
    print("\n" + "=" * 72)
    print("开始删除……")
    ok = err = 0
    for layer in ("A", "B", "C"):
        for rel, p in plan[layer]:
            try:
                if os.path.isfile(p):
                    os.remove(p)
                else:
                    shutil.rmtree(p)
                ok += 1
            except Exception as e:
                err += 1
                SKIPPED_LOCKED.append(f"{rel} -> {e}")
                print(f"   [失败] {rel}: {e}")
    print(f"完成：成功 {ok} 项，失败 {err} 项")
    if SKIPPED_LOCKED:
        print("[失败明细]")
        for r in SKIPPED_LOCKED:
            print("   ", r)
else:
    print("\n（空转模式，未删除任何文件。加 apply 参数才真删。）")
