# -*- coding: utf-8 -*-
"""
Rime 明月拼音词典采集与解析
===========================
从 Rime 官方仓库下载 `luna_pinyin.dict.yaml`（明月拼音），解析出：
  - 单字：字 -> 拼音
  - 词组：词 -> 拼音串（连写，如 'women'）+ 优先级序号（越小越靠前）
并把结果写成 enhance/rime/rime_data.json，供 build_pinyin_dict.py 合并使用。

要点（与真机 Rime 一致）：
  - 词典按 `sort: by_weight` 排序，条目出现顺序即真实优先级；
  - 多音节用空格分隔（如 `一丘之貉\t yi qiu zhi he`），连写去空格得到拼音串；
  - 词尾可选第三列权重（极少见，忽略可，仅用顺序做排序信号）。

用法：
    py build_rime_dict.py            # 下载(若无缓存)并解析，生成 rime_data.json

断网兜底：若已存在 enhance/rime/luna_pinyin.dict.yaml 缓存则直接解析；
否则尝试联网下载；两者都失败时退出，勿中断后续构建（build_pinyin_dict.py 会回退 jieba）。
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
RIME_DIR = os.path.join(ROOT, "enhance", "rime")
DICT_NAME = "luna_pinyin.dict.yaml"
DICT_PATH = os.path.join(RIME_DIR, DICT_NAME)
OUT = os.path.join(RIME_DIR, "rime_data.json")

# 词典原始文件地址（rime-luna-pinyin 官方仓库）
DICT_URLS = [
    "https://raw.githubusercontent.com/rime/rime-luna-pinyin/master/luna_pinyin.dict.yaml",
    "https://raw.githubusercontent.com/rime/rime-prelude/master/luna_pinyin.dict.yaml",
]

# 只收常用汉字，过滤生僻符号/BMP 外字符（如 〇、ㄓ、扩展区生僻字），避免候选条被奇怪字符占据
_CJK = re.compile(r"^[\u4e00-\u9fff]+$")
# 拼音串只允许小写字母 / v（ü 的替代）
_PY = re.compile(r"^[a-zv]+$")
# 词条行：汉字<TAB>拼音[<TAB>权重]；可选注释行以 # 开头
_ENTRY = re.compile(r"^([^\t#\s]+)\t([^\t#]+)(?:\t([^\t#]*))?$")


def _download():
    """下载词典到 RIME_DIR；已有缓存则跳过，失败返回 False。"""
    if os.path.isfile(DICT_PATH):
        return True
    os.makedirs(RIME_DIR, exist_ok=True)
    for url in DICT_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if not data:
                continue
            # 按 utf-8 写回（保留 BOM 无关），并校验能解码
            text = data.decode("utf-8")
            if "name:" not in text or "\t" not in text:
                continue
            with open(DICT_PATH, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"[Rime] 已下载 {DICT_NAME}（{len(text)//1024} KB）")
            return True
        except Exception as exc:                    # noqa: BLE001
            print(f"[Rime] 下载 {url} 失败：{exc}")
    return False


def _parse():
    """解析词典，返回 dict。返回 None 表示解析失败（调用方回退）。"""
    if not os.path.isfile(DICT_PATH):
        return None
    char_readings = {}   # 字 -> {py, w} 主读音
    syl_chars = {}       # 拼音 -> [字]，按词典顺序（供组词联想）
    phrases = []         # [(词, 拼音串)]，按词典顺序
    seen_phrase = set()
    in_body = False
    rank = 0
    with open(DICT_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 词典头部是 `--- 元信息 ...`，条目在第一个 `...` 之后开始
            if in_body:
                pass
            elif line == "---":
                continue
            elif line == "...":
                in_body = True
                continue
            else:
                continue                                    # 跳过头部元信息行
            m = _ENTRY.match(line)
            if not m:
                continue
            word, py_raw = m.group(1).strip(), m.group(2).strip()
            # 权值：多数为「读音概率百分比」（如 我=wo 100%、我=e 0%），也可能是权重数字；取不到则为 -1
            weight_raw = m.group(3).strip() if m.group(3) else ""
            try:
                weight = float(weight_raw.replace("%", "")) if weight_raw else -1.0
            except ValueError:
                weight = -1.0
            # 拼音：去空格连写；过滤含非字母（如带调符号 / 空白缺失）的行
            py = "".join(re.findall(r"[a-z]+", py_raw.lower()))
            if not py or not _PY.match(py):
                continue

            # 单字：记录该字在该读音下的概率，用于取「主读音」
            if len(word) == 1 and _CJK.match(word):
                # 记录该音节下的常用字（供组词联想用），去重
                if word not in syl_chars.setdefault(py, []):
                    syl_chars[py].append(word)
                # 主读音：概率最高的读音（缺省概率 -1，0 视为有效低位）
                cur = char_readings.get(word)
                if cur is None:
                    char_readings[word] = {"py": py, "w": weight}
                elif weight > cur["w"]:
                    char_readings[word] = {"py": py, "w": weight}
                rank += 1
                continue

            # 词组：按词登记到对应拼音串，记录顺序作为优先级信号
            if not _CJK.match(word):
                continue
            if word in seen_phrase:
                continue
            seen_phrase.add(word)
            phrases.append((word, py))
            rank += 1

    if not char_readings and not phrases:
        return None
    # 单字：取主读音
    chars = {ch: v["py"] for ch, v in char_readings.items()}
    # 词组优先级：以「该拼音串内第一次出现的顺序」为准；同一词只保留最早的顺序
    phrase_rank = {}
    for i, (word, _py2) in enumerate(phrases):
        phrase_rank.setdefault(word, i)
    return {
        "chars": chars,                 # {字: 主读音拼音}
        "syl_chars": syl_chars,         # {拼音: [字]} 按词典顺序，供组词联想
        "phrases": phrases,             # [(词, 拼音串)] 按词典顺序
        "phrase_rank": phrase_rank,     # {词: 顺序}
    }


def main():
    if not _download():
        print("[Rime] 无缓存且联网失败，跳过 Rime 合并（build_pinyin_dict.py 会回退 jieba）。")
        return 0
    data = _parse()
    if data is None:
        print("[Rime] 词典解析失败，跳过 Rime 合并。")
        return 1
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"[Rime] 已生成 {OUT}：单字 {len(data['chars'])}，音节 {len(data['syl_chars'])}，词组 {len(data['phrases'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())