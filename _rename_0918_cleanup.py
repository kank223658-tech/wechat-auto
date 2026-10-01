# -*- coding: utf-8 -*-
"""收尾：改名工作脚本移入 _probe_tmp/_rename_0918/（备份目录与报告保留根目录可查）。"""
import os, shutil, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"G:\weixin-auto"
DST = os.path.join(ROOT, "_probe_tmp", "_rename_0918")
os.makedirs(DST, exist_ok=True)
names = ["_rename_0918_scan_backup.py", "_rename_0918_context_dump.py",
         "_rename_0918_apply.py", "_rename_0918_docs.py", "_rename_0918_db.py",
         "_rename_0918_baseline.py", "_rename_0918_verify.py",
         "_rename_0918_scan_report.txt", "_rename_0918_context_report.txt",
         "_rename_0918_apply_report.txt", "_rename_0918_docs_report.txt",
         "_rename_0918_db_report.txt", "_rename_0918_baseline.json"]
for n in names:
    src = os.path.join(ROOT, n)
    if os.path.isfile(src):
        shutil.move(src, os.path.join(DST, n))
        print("moved", n)
print("OK")
