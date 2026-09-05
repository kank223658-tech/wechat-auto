# -*- coding: utf-8 -*-
"""
雾凇拼音（rime-ice）词典采集与解析
==================================
从 iDvel/rime-ice 仓库下载并解析词典，产出缓存 enhance/rime-ice/wusong_data.json：
  - word_weight  词 -> 权重（真实语料词频，多音词取最高权重频次）
  - char_weight  字 -> 权重（来自 8105 常用字表 + base 单字条目）

只采集「权重」，不做读音判定；读音由 build_pinyin_dict.py 用 pypinyin 统一建档，
从而避免雾凇个别注音（如「这 zhei」「开 jian」）与标准音/打字驱动不一致的问题。

词典文件：cn_dicts/base.dict.yaml（基础词库）、ext.dict.yaml（扩展）、8105.dict.yaml（通用规范汉字表）。
格式：词<TAB>拼音<TAB>权重，多音节拼音以空格分隔；# 注释行；权重为整数（词频）。

用法：py build_wusong_dict.py
断网/下载失败：已存在缓存则直接用；否则退出，build_pinyin_dict.py 回退现有 jieba/curated。
"""
import json
import os
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "enhance", "rime-ice")
OUT = os.path.join(CACHE_DIR, "wusong_data.json")

BASE_URL = "https://raw.githubusercontent.com/iDvel/rime-ice/main/cn_dicts/"
FILES = ["base.dict.yaml", "ext.dict.yaml", "8105.dict.yaml"]

# 词频保留下限：过滤掉权值极低的专名/生僻词，避免候选被噪声刷屏、词库过度膨胀
MIN_WORD_WT = 60
# 单字频下限（8105 里很多字权值为 1，保留所有在常用字范围的字即可；此下限仅防极端噪声）
MIN_CHAR_WT = 0
# CJK 常用字范围（\u4e00-\u9fff），过滤扩展区生僻字（如 𤭢/鿫）
_CJK = re.compile(r"^[\u4e00-\u9fff]+$")
# 条目：词<TAB>拼音<TAB>权重
_ENTRY = re.compile(r"^(\S+)\t([a-z ]+)\t(\d+)\s*$")
# 拼音连写字（如 'a a' -> 'aa'）；仅用于过滤「是否含非法字符」，实际键由 build 用 pypinyin 重算
_PY = re.compile(r"^[a-z]+$")


def _download():
    for f in FILES:
        p = os.path.join(CACHE_DIR, f)
        if os.path.isfile(p):
            print(f"[雾凇] 复用缓存 {f}（{os.path.getsize(p)//1024} KB）")
            continue
        try:
            req = urllib.request.Request(BASE_URL + f, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            text = data.decode("utf-8")
            if "\t" not in text:
                print(f"[雾凇] 跳过（内容异常）{f}")
                continue
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"[雾凇] 已下载 {f}（{len(text)//1024} KB）")
        except Exception as exc:                    # noqa: BLE001
            print(f"[雾凇] 下载 {f} 失败：{exc}")
    return all(os.path.isfile(os.path.join(CACHE_DIR, f)) for f in FILES)


def _parse_file(path, word_weight, char_weight):
    """解析单个词典文件，写实到 word_weight/char_weight。"""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line in ("---", "...", "..."):
                continue
            m = _ENTRY.match(line)
            if not m:
                continue
            word, py_raw, wt = m.group(1), m.group(2).replace(" ", ""), int(m.group(3))
            if not py_raw or not _PY.match(py_raw):
                continue
            # 单字：只收常用字范围，记录最大权重（多读音时取最常用读音的权重）
            if len(word) == 1 and _CJK.match(word):
                if wt >= MIN_CHAR_WT:
                    if word in char_weight:
                        char_weight[word] = max(char_weight[word], wt)
                    else:
                        char_weight[word] = wt
                continue
            # 词：仅保留词组，记录最大权重
            if not _CJK.match(word):
                continue
            if wt >= MIN_WORD_WT:
                if word in word_weight:
                    word_weight[word] = max(word_weight[word], wt)
                else:
                    word_weight[word] = wt


def main():
    if not _download():
        print("[雾凇] 无本地缓存且联网失败，跳过雾凇合并（build_pinyin_dict.py 回退 jieba/curated）。")
        return 0
    word_weight = {}
    char_weight = {}
    for f in FILES:
        _parse_file(os.path.join(CACHE_DIR, f), word_weight, char_weight)
    if not word_weight and not char_weight:
        print("[雾凇] 词典解析为空，跳过。")
        return 1
    data = {"word_weight": word_weight, "char_weight": char_weight}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"[雾凇] 已生成 {OUT}：词 {len(word_weight)}，常用字 {len(char_weight)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())