# -*- coding: utf-8 -*-
"""
候选词方案一键回滚脚本
======================
把 enhance/_backup/<时间戳>/ 里的候选词相关文件拷回 enhance/，恢复改动前的状态。

用法：
    py restore_candidate_backup.py                # 回滚到最近一次备份
    py restore_candidate_backup.py 20260904_0053  # 回滚到指定备份（可只填时间戳）
    py restore_candidate_backup.py --list         # 只列出当前所有备份，不改动

说明：
    备份目录：enhance/_backup/<yyyyMMdd_HHmmss>/
    可回滚文件：pinyin_data.js / cjk_freq_extra.json / keyboard.js / keyboard.css
                build_pinyin_dict.py / gen_freq_data.py
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(ROOT, "enhance", "_backup")
TARGETS = [
    "pinyin_data.js",
    "cjk_freq_extra.json",
    "keyboard.js",
    "keyboard.css",
    "build_pinyin_dict.py",
    "gen_freq_data.py",
]


def _list_backups():
    """返回按时间从新到旧排序的备份目录绝对路径列表。"""
    if not os.path.isdir(BACKUP_ROOT):
        return []
    names = sorted(os.listdir(BACKUP_ROOT), reverse=True)
    return [os.path.join(BACKUP_ROOT, n) for n in names if os.path.isdir(os.path.join(BACKUP_ROOT, n))]


def _list_backup_names():
    return [os.path.basename(p) for p in _list_backups()]


def _resolve(selector):
    """根据用户输入解析出目标备份目录；None 表示用最近一次备份。"""
    if not selector:
        b = _list_backups()
        if not b:
            return None, "没有找到任何备份，请先创建备份（见 build_rime_dict.py / 备份步骤）。"
        return b[0], None
    sel = str(selector).strip()
    for p in _list_backups():
        if os.path.basename(p).startswith(sel):
            return p, None
    return None, f"找不到匹配「{sel}」的备份目录。"


def _restore(backup_dir):
    """把备份目录中的候选词文件拷回 enhance/。返回 (恢复文件数, 错误)。"""
    if not os.path.isdir(backup_dir):
        return 0, f"备份目录不存在：{backup_dir}"
    restored = 0
    missing = []
    for name in TARGETS:
        src = os.path.join(backup_dir, name)
        if not os.path.isfile(src):
            missing.append(name)
            continue
        shutil.copy2(src, os.path.join(ROOT, "enhance", name))
        restored += 1
    err = None
    if missing:
        err = "以下文件备份中缺失，未恢复：" + ", ".join(missing)
    return restored, err


def main():
    args = [a for a in sys.argv[1:]]
    if "--list" in args or "-l" in args:
        names = _list_backup_names()
        if not names:
            print("没有找到任何备份。")
            return 0
        print("当前备份（从新到旧）：")
        for n in names:
            print("  " + n)
        return 0

    selector = None
    for a in args:
        if not a.startswith("-"):
            selector = a
            break

    backup_dir, err = _resolve(selector)
    if err:
        print("错误：" + err)
        return 1
    restored, err = _restore(backup_dir)
    if err:
        print("警告：" + err)
    print(f"已从 {os.path.basename(backup_dir)} 恢复 {restored} 个文件到 enhance/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())