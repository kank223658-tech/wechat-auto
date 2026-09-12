# -*- coding: utf-8 -*-
"""第三批：用户已确认的「存疑项」清理。带年龄过滤（默认空转）。"""
import os, sys, shutil, time, glob

ROOT = r"G:\weixin-auto"
APPLY = len(sys.argv) > 1 and sys.argv[1] == "apply"
CUTOFF = time.time() - 60 * 60

# 目录 / 大块
dirs = [
    "engine_poc",            # 输入法引擎试验工程（含内嵌 .git）
    "enhance/_backup",       # 09-04~09-05 时间戳快照 = restore_candidate_backup 的回滚源
    "enhance/_ref_metrics",
    "enhance/rime",          # 明月拼音旧词库（主程序走 rime-ice 雾凇）
    "复刻_界面",              # 手写复刻界面尝试，已被 vue-WeChat 正式实现取代
]

# 单文件
files = [
    "editor/_del_measure.html",
    "editor/_probe.html",
    "vue-WeChat/public/_transfer_test.html",
]

# 根目录演示 / 测试用配置与脚本（引用数全部为 0）
demos = [
    "complex_demo.json", "demo_full_ops.json", "demo_transfer.json",
    "demo_workflow.json", "workflow_delcheck.json", "workflow_sparse.json",
    "workflow_test.json", "smoke_test.json", "verify_ui.json",
    "diff_keyboard.txt", "script_demo_fix.txt",
    "link_workflow.json", "link_video_workflow.json",
    "link_video_script.txt", "link_demo.txt",
    "demo_multi.py", "demo_chat_image.py", "make_demo.py",
    "make_pullpush_video.py", "measure_ui.py", "fetch_apple_emoji.py",
]

# preview/ 只清内容、保留目录（preview_ui.py 会往里写，且自身会 makedirs）


def size_of(p):
    if os.path.isfile(p):
        return os.path.getsize(p), 1
    s = n = 0
    for dp, _, fs in os.walk(p):
        for f in fs:
            try:
                s += os.path.getsize(os.path.join(dp, f))
                n += 1
            except Exception:
                pass
    return s, n


def fresh(p):
    if os.path.isfile(p):
        return os.path.getmtime(p) > CUTOFF
    for dp, _, fs in os.walk(p):
        for f in fs:
            try:
                if os.path.getmtime(os.path.join(dp, f)) > CUTOFF:
                    return True
            except Exception:
                pass
    return False


plan = []
skipped = []
for rel in dirs + files + demos:
    p = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.exists(p):
        continue
    if fresh(p):
        skipped.append(rel)
        continue
    plan.append((rel, p))
# preview 内容
prev = os.path.join(ROOT, "preview")
prev_items = []
if os.path.isdir(prev):
    for fn in os.listdir(prev):
        fp = os.path.join(prev, fn)
        if os.path.isfile(fp) and not fresh(fp):
            prev_items.append(("preview/" + fn, fp))

print("=" * 74)
print("空转预览" if not APPLY else "★ 实际执行 ★")
print("=" * 74)
tot = 0
print("\n--- 目录 ---")
for rel, p in plan:
    if os.path.isdir(p):
        s, n = size_of(p)
        tot += s
        print(f"    {rel:36s} {n:5d} 文件  {s/1e6:8.2f} MB")
print("\n--- 单文件 / 演示配置 ---")
for rel, p in plan:
    if os.path.isfile(p):
        s, n = size_of(p)
        tot += s
        print(f"    {rel:36s} {s:8d} B")
print(f"\n--- preview/ 内容 {len(prev_items)} 个 ---")
for rel, p in prev_items:
    tot += os.path.getsize(p)
print(f"    共 {sum(os.path.getsize(p) for _, p in prev_items)/1e6:.2f} MB")

print(f"\n合计释放约：{tot/1e6:.2f} MB")
if skipped:
    print("因太新跳过：", skipped)

def _rmtree_force(path):
    """Windows 下 .git 里的对象文件是只读的，rmtree 会失败 —— 先清只读位再删。"""
    def onerr(func, p, exc):
        try:
            import stat
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            raise
    shutil.rmtree(path, onerror=onerr)


if APPLY:
    print("\n开始删除……")
    ok = err = 0
    for rel, p in plan:
        try:
            if os.path.isfile(p):
                os.remove(p)
            else:
                _rmtree_force(p)
            ok += 1
        except Exception as e:
            err += 1
            print(f"   [失败] {rel}: {e}")
    for rel, p in prev_items:
        try:
            os.remove(p)
            ok += 1
        except Exception as e:
            err += 1
            print(f"   [失败] {rel}: {e}")
    print(f"完成：成功 {ok} 项，失败 {err} 项")
else:
    print("\n（空转模式，未删除任何文件）")
