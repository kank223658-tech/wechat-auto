# -*- coding: utf-8 -*-
"""
拼音词库构建脚本（离线，用 jieba + pypinyin + Rime 明月拼音 + curated 高频词）
=============================================================================
用本机已安装的开源库 + 可选数据源构建一份"接近真实输入法"的离线拼音词库：
  - jieba —— 自带 49 万词、1.1 万单字的高频词库（MIT）；
  - pypinyin —— 把每个词/字转成无音调拼音；
  - enhance/rime/rime_data.json —— Rime 明月拼音词典（可选，提供多音字"主读音"与真实词组）；
  - enhance/cjk_freq_extra.json —— curated 中文字频/词频/二元/拼音 boost（可选，显著充实候选）。

产物 enhance/pinyin_data.js，内容为
  window.__WX_PINYIN = {
    "s": { "wo": ["我","握","窝",...], ... },        // 单字：音节 -> 候选字(按真实字频)
    "p": { "women": ["我们", ...], "shijian": ["时间","事件","实践",...], ... }, // 词组
    "sf": { "wo": 241000, ... },                     // 音节 -> 该音节最高频字的频次(打分用)
    "pf": { "women": 361000, ... }                   // 拼音串 -> 该串最高频词的频次(打分用)
  }

特点：
  1. 单字候选丰富（每个音节往往十几个同音字），并按真实字频排序（的/一/是 靠前），候选行更真实；
  2. 支持词组级，且词组用 curated 高频词显著充实（我们/没有/可以 … 与真机一致）；
  3. 多音字用 Rime 主读音（我->wo、重->zhong、行->xing），与真机默认读音一致；
  4. 额外扫描剧本/工作流 text，把其中出现的每个字/每个词都保证收录，
     从而"逐字/逐词"上屏都能与剧本 100% 一致。

用法：
    py build_rime_dict.py              # 可选：下载并解析 Rime 词典(有缓存/联网则生成 rime_data.json)
    py -3.14 build_pinyin_dict.py      # 重新生成 enhance/pinyin_data.js
"""

import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from pypinyin import lazy_pinyin
except ImportError:  # pragma: no cover
    print("缺少 pypinyin，请先 `pip install pypinyin`。")
    raise SystemExit(1)

try:
    import jieba
    jieba.initialize()
except ImportError:  # pragma: no cover
    print("缺少 jieba，请先 `pip install jieba`（用于构建词组库）。")
    raise SystemExit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "enhance", "pinyin_data.js")

SCAN_FILES = ["script.txt", "workflow.json", "demo_workflow.json",
              "reference_workflow.json", "smoke_test.json"]

# 词组最多收录多少（按词频取前 N；加大以贴近真实输入法词库）
MAX_PHRASES = 300000
# 词长上限（放宽到 10 字覆盖更多短语）
MAX_WORD_LEN = 10

# 常用中文搭配（前词 -> {后词: 权重}），作为二元模型(bigram)的通用先验；叠加剧本文本的相邻词。
COMMON_BIGRAMS = {
    "我们": {"明天": 20, "一起": 12, "今天": 10, "公司": 8, "下午": 6, "晚上": 6, "明天见": 5},
    "我": {"们": 30, "在": 20, "要": 15, "想": 12, "就": 10, "觉得": 8, "知道": 8, "可以": 6, "到": 6, "给": 4},
    "你": {"好": 25, "们": 20, "在": 12, "要": 10, "先": 6, "可以": 5, "知道": 5, "觉得": 6, "说": 5},
    "他": {"们": 20, "在": 10, "说": 12, "要": 8, "是": 6},
    "今天": {"天气": 15, "下午": 12, "晚上": 10, "中午": 8, "上午": 8, "见": 6, "吃": 6},
    "明天": {"见": 20, "下午": 12, "上午": 10, "晚上": 8, "一起": 6, "公司": 6},
    "下午": {"见": 12, "开会": 10, "去": 8, "出差": 6, "有空": 5, "碰头": 5},
    "晚上": {"吃饭": 15, "见": 12, "聊": 8, "一起": 6, "有空": 5},
    "中午": {"吃饭": 15, "见": 8},
    "公司": {"开": 8, "见": 8, "楼下": 8, "门口": 6, "等你": 4},
    "吃饭": {"了": 12, "吗": 10, "去": 8, "吧": 6, "没": 5},
    "一起": {"吃饭": 12, "去": 10, "走": 8, "吧": 6, "看看": 4},
    "这个": {"时候": 12, "问题": 10, "世界": 5, "方案": 6},
    "什么": {"时候": 12, "意思": 10, "问题": 8, "情况": 6, "事": 5},
    "怎么": {"样": 10, "办": 8, "了": 6, "说": 6},
    "为什么": {"这样": 6, "不": 5, "要": 4},
    "因为": {"我": 8, "你": 6, "他": 5, "所以": 4, "是": 4},
    "所以": {"我": 8, "你": 5, "我们": 5, "要": 4, "就": 4},
    "虽然": {"我": 5, "他": 4, "但是": 3},
    "但是": {"我": 6, "你": 4, "他": 4, "还是": 3},
    "还是": {"我": 4, "你": 3, "去": 3, "要": 3},
    "现在": {"在": 6, "就要": 4, "可以": 4, "去": 4, "是": 3},
    "可以": {"了": 8, "吗": 8, "做": 6, "去": 4, "给我": 3},
    "一下": {"吗": 6, "吧": 4, "好": 4, "看看": 4},
    "知道": {"了": 8, "吗": 8, "这个": 4},
    "觉得": {"很": 8, "好": 6, "可以": 4, "不错": 4, "有点": 3},
    "开始": {"了": 6, "做": 4, "工作": 4},
    "已经": {"到": 5, "完成": 4, "好": 4, "在": 4},
    "在": {"这里": 5, "公司": 5, "等你": 4, "家里": 4, "我家": 4},
    "是": {"我": 6, "什么": 5, "你": 5, "这样": 3},
    "开心": {"吗": 10, "了": 8, "的": 6, "呀": 5, "哦": 4, "啊": 4, "就": 3},
    "开心哈": {"哈": 6, "哈呀": 4},
    "好的": {"吧": 10, "呢": 8, "呀": 6, "啊": 4, "哦": 4, "了": 3, "亲": 3},
    "好": {"的": 15, "吧": 10, "了": 8, "啊": 6, "好": 5, "看": 4, "吃": 4, "处": 3, "久": 3},
    "哈哈": {"哈": 8, "笑": 6, "啊": 3, "好": 3, "嗯": 2},
    "哈哈哈": {"哈": 8, "笑": 4},
    "晚安": {"哦": 8, "啊": 5, "啦": 5, "好梦": 4, "早点睡": 3, "亲": 2},
    "早安": {"哦": 6, "啊": 4, "啦": 4},
    "早上好": {"啊": 6, "呀": 4, "哦": 3, "拜拜": 2},
    "谢谢": {"啦": 10, "哦": 6, "呀": 5, "啊": 4, "你": 4, "亲": 3},
    "感谢": {"你": 8, "啦": 4, "呀": 3},
    "不客气": {"啦": 5, "哈": 4, "哦": 3},
    "对不起": {"啦": 5, "呀": 4, "嘛": 3},
    "吃饭": {"了": 12, "吗": 10, "吧": 6, "去": 4, "没": 4},
    "吃饭了": {"吗": 8, "吧": 4, "没": 3},
    "吃饭吗": {"了": 6, "我": 4, "没": 3},
    "拜拜": {"啦": 6, "哦": 4, "晚安": 3},
    "再见": {"啦": 6, "哦": 4, "拜拜": 3},
    "睡觉": {"了": 10, "吧": 6, "啦": 4, "哦": 3},
    "起床": {"了": 8, "啦": 4, "没": 3},
    "走了": {"啦": 6, "哦": 4, "拜拜": 3},
    "在吗": {"哦": 8, "嗯": 6, "忙吗": 4, "呢": 3},
    "干嘛": {"呢": 10, "哦": 5, "呀": 4, "啊": 3},
    "怎么了": {"啦": 10, "哦": 5, "呀": 4, "啊": 3, "呢": 3},
    "什么": {"时候": 15, "意思": 12, "问题": 10, "情况": 8, "事": 6, "呀": 4},
    "可以": {"了": 10, "吗": 10, "呀": 6, "啊": 5, "吧": 4, "哦": 3},
    "嗯": {"嗯": 8, "哦": 6, "好": 5, "啊": 3},
    "哦": {"哦": 6, "好": 5, "嗯": 4, "啊": 3},
    "行吧": {"哦": 6, "好": 4, "嗯": 3},
    "好吧": {"哦": 6, "那": 5, "行": 4, "嗯": 3},
}
# 字符是否 CJK 汉字（常用区 + 扩展 A）
_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_CJK_IS = lambda c: _CJK.match(c)
_CJK_RUN = re.compile(r"([\u4e00-\u9fff\u3400-\u4dbf]+)|([^\u4e00-\u9fff\u3400-\u4dbf]+)")

# 剧本词/整段的超大词频：保证排到候选最前、不被 [:18] 截断
# 真实输入法"正确预测到剧本那句话"就等价于把它排第一，这里用大权值实现。
_SCRIPT_BOOST = 10_000_000


def _py(s: str) -> str:
    """一段文字 -> 无音调拼音串（如 '我们' -> 'women'）。非纯拼音返回空。"""
    try:
        py = "".join(lazy_pinyin(s))
    except Exception:  # noqa: BLE001
        return ""
    # 只要纯 ASCII 字母（含 ü 以外的韵母由 v 表示，仍是字母）
    if not py or not py.isascii() or not py.isalpha():
        return ""
    return py.lower()


def script_texts() -> list:
    """读取剧本/工作流文件中的文本（按字符拼接，供标点不干扰 jieba）。"""
    texts = []
    for fn in SCAN_FILES:
        path = os.path.join(ROOT, fn)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                data = fh.read()
            texts.append(data)
        except OSError:
            continue
    return texts


def script_runs() -> list:
    """收集所有剧本文本里的「整段连续中文」，作为要优先上屏的短语。

    例：'晚上一起吃饭' 会作为一个整段短语收录，保证 queryPinyin 在该拼音串下
    第一候选就是它，从而「候选高亮 == 上屏文字」，与真机整句中一致性。
    """
    runs = []
    seen = set()
    for text in script_texts():
        for m in _CJK_RUN.finditer(text):
            run = m.group(1)
            if run and len(run) >= 2 and run not in seen:
                seen.add(run)
                runs.append(run)
    return runs


def _load_json(path):
    """读取 JSON，失败返回 None（可选数据源，缺省不中断构建）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# Rime 词组的基础权重：远低于 curated 高频词（我们=36100、谢谢=9000、开心=4000），
# 仅作「低频真实词补充」，排在日常高频词之后，避免生僻/繁体词盖过常用词。
_RIME_BOOST = 500

# 雾凇拼音词条上限：按真实词频取前 N。候选条只显示 ~8 项，取前 10 万足够覆盖常用词，
# 同时避免词典过大导致注入耗时飙升（>20MB 的 JS 一次 evaluate 要十几秒以上）。
WUSONG_MAX_WORDS = 100000


def build() -> dict:
    freq = jieba.dt.FREQ
    t0 = time.time()

    # ---- 0) 可选数据源：Rime 主读音/词组 + curated 高词频 + 雾凇拼音词频 ----
    extra = _load_json(os.path.join(ROOT, "enhance", "cjk_freq_extra.json")) or {}
    rime = _load_json(os.path.join(ROOT, "enhance", "rime", "rime_data.json")) or {}
    wusong = _load_json(os.path.join(ROOT, "enhance", "rime-ice", "wusong_data.json")) or {}
    extra_char = extra.get("char_freq") or {}
    extra_word = extra.get("word_freq") or {}
    extra_big = extra.get("bigram") or {}
    extra_py = extra.get("pinyin_boost") or {}
    rime_chars = rime.get("chars") or {}
    wusong_word = wusong.get("word_weight") or {}
    wusong_char = wusong.get("char_weight") or {}                     # 字 -> 真实字频（雾凇/8105）      # 字 -> 主读音

    def char_py(ch: str) -> str:
        """字 -> 拼音：以 pypinyin 为主（与 main.py _pinyin_of 一致、读音正确），Rime 主读音仅兜底。

        注意：Rime 词典对个别常用字的读音权重有误（如 开 被判成 jian 95%），
        若以 Rime 优先会把"开"错分到 jian 音节、导致 kai 候选缺失常用字。
        pypinyin 的默认读音是标准常用读音，且与打字驱动侧一致，故作为主来源。
        """
        py = _py(ch)
        if py:
            return py
        return rime_chars.get(ch) or ""

    char_freq = {}
    word_freq = {}
    # jieba 简体字库的「单字」集合，用于过滤 Rime 词组里的繁体/生僻字
    freq_single = {w for w in freq if len(w) == 1}

    # ---------- 1) 单字：音节 -> 候选字（按真实字频降序） ----------
    s = {}
    singles = sorted((w for w in freq if len(w) == 1), key=lambda w: -freq[w])
    for ch in singles:
        py = char_py(ch)
        if not py:
            continue
        s.setdefault(py, []).append(ch)
        char_freq[ch] = max(char_freq.get(ch, 1), freq.get(ch, 1))
    # 合并 curated 字频（Jun Da 字频表）：补全字 + 刷新常用字频率（如 的=58200）
    for ch, cf in extra_char.items():
        if len(ch) != 1:
            continue
        py = char_py(ch)
        if not py:
            continue
        if ch not in char_freq:
            s.setdefault(py, []).append(ch)
        char_freq[ch] = max(char_freq.get(ch, 1), cf)

    # ---------- 2) 词组：拼音串 -> 候选词（合并 jieba + curated + Rime） ----------
    p = {}
    multis = sorted((w for w in freq if 1 < len(w) <= MAX_WORD_LEN), key=lambda w: -freq[w])
    for w in multis[:MAX_PHRASES]:
        py = _py(w)
        if not py:
            continue
        p.setdefault(py, []).append(w)
        word_freq[w] = max(word_freq.get(w, 1), freq.get(w, 1))
    # curated 高频词（我们=36100、没有=35000 …），显著充实候选、贴近真机
    for w, wf in extra_word.items():
        if not w or len(w) > MAX_WORD_LEN:
            continue
        py = _py(w)
        if not py:
            continue
        if w not in word_freq:
            p.setdefault(py, []).append(w)
        word_freq[w] = max(word_freq.get(w, 1), wf)
    # pinyin_boost：拼音串 -> {词: 频}，直接补充候选
    for py_boost, wdict in extra_py.items():
        if not isinstance(wdict, dict):
            continue
        for w, wf in wdict.items():
            if not w or len(w) > MAX_WORD_LEN:
                continue
            if w not in word_freq:
                p.setdefault(py_boost, []).append(w)
            word_freq[w] = max(word_freq.get(w, 1), wf)
    # Rime 词组：真实成语/词库，仅作低频补充（排在 curated 常用词之后）。
    # 过滤掉含繁体/生僻字（不在 jieba 简体字库 freq 单字表里）的词，避免候选冒出「開/瀉/們」这类繁体。
    for w, wpy in rime.get("phrases") or []:
        if not w or len(w) > MAX_WORD_LEN or w in word_freq:
            continue
        if any(c not in freq_single for c in w):
            continue
        p.setdefault(wpy, []).append(w)
        word_freq[w] = max(word_freq.get(w, 1), _RIME_BOOST)

    # 雾凇拼音：真实语料词频，按权值取前 WUSONG_MAX_WORDS，参与候选排序。
    # 用 pypinyin 定键（与打字驱动一致），避免雾凇个别注音（如「这 zhei」）与标准音冲突；
    # 只收简体常用字构成的词；词频「替换」为雾凇真实值，让候选顺序更贴近真机。
    for w, wt in sorted(wusong_word.items(), key=lambda kv: -kv[1])[:WUSONG_MAX_WORDS]:
        if not w or len(w) > MAX_WORD_LEN:
            continue
        if any(c not in freq_single for c in w):
            continue
        py = _py(w)
        if not py:
            continue
        if w not in word_freq:
            p.setdefault(py, []).append(w)
        word_freq[w] = wt                                    # 用雾凇真实词频（替换 curated/jieba）
    # 雾凇单字频：仅用于 s 的单字排序（8105 真实字频），不改 sf 打分尺度（sf 仍用 Jun Da/jieba 尺度，
    # 避免 word/single-char 打分量级失衡、viterbi 偏向拆字）。只覆盖已有的常用字。
    ws_char_order = {}
    for ch, wt in wusong_char.items():
        if len(ch) != 1 or ch not in char_freq:
            continue
        ws_char_order[ch] = wt

    # ---------- 3) 保证剧本/工作流里的字与词一定在库中，且排到最前 ----------
    for text in script_texts():
        for ch in set(_CJK.findall(text)):                     # 每个汉字进单字表
            py = char_py(ch)
            if not py:
                continue
            if ch not in s.setdefault(py, []):
                s[py].append(ch)
            char_freq.setdefault(ch, 1)                        # 单字只保证存在，不做高权值
        for w in jieba.lcut(text):                             # 每个被切出的词进词组表
            w = w.strip()
            if not w or len(w) > MAX_WORD_LEN:
                continue
            py = _py(w)
            if not py:
                continue
            if w not in p.setdefault(py, []):
                p[py].append(w)
            word_freq[w] = max(word_freq.get(w, 1), _SCRIPT_BOOST)
    for run in script_runs():
        py = _py(run)
        if not py or len(py) > 26:
            continue
        if run not in p.setdefault(py, []):
            p[py].append(run)
        word_freq[run] = max(word_freq.get(run, 1), _SCRIPT_BOOST)

    # ---------- 4) 排序 + 截断 + 频次表（放宽候选条：单字 40、词组 24） ----------
    for k in p:
        p[k].sort(key=lambda w: -word_freq.get(w, 1))
        p[k] = p[k][:10]                                      # 每键保留候选条够用的高频词，控制体积
    sf = {}
    for k in s:
        # 排序：优先按雾凇真实字频(ws_char_order)，其次按原尺度 char_freq；sf 打分仍用原尺度
        s[k].sort(key=lambda ch: -ws_char_order.get(ch, char_freq.get(ch, 1)))
        s[k] = s[k][:40]
        sf[k] = max(char_freq.get(ch, 1) for ch in s[k]) or 1
    pf = {}
    for k in p:
        pf[k] = max(word_freq.get(w, 1) for w in p[k]) or 1

    n_char = sum(len(v) for v in s.values())
    n_phrase = sum(len(v) for v in p.values())

    # ---- 5) 二元模型（COMMON_BIGRAMS + curated 搭配 + 剧本相邻词） ----
    bg = dict((k, dict(v)) for k, v in COMMON_BIGRAMS.items())
    for pv, nxt in extra_big.items():
        if not isinstance(nxt, dict):
            continue
        dst = bg.setdefault(pv, {})
        for nw, wt in nxt.items():
            dst[nw] = max(dst.get(nw, 0), wt)
    for text in script_texts():
        words = [w for w in jieba.lcut(text) if w and _CJK.match(w[0])]
        for i in range(1, len(words)):
            pv, nw = words[i - 1], words[i]
            bg.setdefault(pv, {}).setdefault(nw, 0)
            bg[pv][nw] += 1
    for pv in list(bg.keys()):
        top = sorted(bg[pv].items(), key=lambda kv: -kv[1])[:10]
        bg[pv] = dict(top)

    print(f"构建完成：{len(s)} 音节 / {n_char} 单字；{len(p)} 拼音串 / {n_phrase} 词组；{len(bg)} 前词(二元)；耗时 {time.time()-t0:.1f}s")
    return {"s": s, "p": p, "sf": sf, "pf": pf, "bg": bg}


def main() -> int:
    payload = build()
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    js = ("/* AUTO-GENERATED by build_pinyin_dict.py — 离线拼音候选词库（jieba+pypinyin+补充数据） */\n"
          "window.__WX_PINYIN = " + data + ";\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(js)
    print(f"已生成 {OUT}（{len(js)/1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())