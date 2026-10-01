# -*- coding: utf-8 -*-
"""剧本逻辑门：查机械门（_check_script_quality.py）管不了的「跨句/全局一致性」。

用法：
    py _check_script_logic.py 剧本.txt [--require-ledger]

为什么需要它：
  模型是「往下接话」不是「维护一个世界」——局部每句通顺，跨上百句就前后矛盾。
  本门只查状态级问题，不查格式（格式归机械门）：
    L1 指令合法：行首 [指令] 必须是软件真认识的名字（白名单从 main.py 动态提取，
       不硬编码，杜绝指令名漂移；抓「[对方发]」这类手滑）
    L2 时间线：所有显式 HH:MM 全局非递减（跨零点场景请压在同一自然日）
    L3 人物一致：历史块 [会话] X 里说话人只能是 X 或我；X / [打开聊天] X 必须在
       people.json 里；[对方后台发消息] 名字不应是当前正打开的会话
    L4 撞名：联系人名出现在奶茶/口味/吃喝等台词语境里（如口味名=联系人名）
    L5 信息越界（A/B）：她紧跟着的消息若大段复述上一条 [观众字幕]，
       等于她「听见了」打给观众看的内心戏
    L6 承诺兑付：读配套《状态台账》，每个「承诺/钩子」的兑付词必须在首提词之后出现
    L7 台账关系阶段：台账列的阶段时间必须在剧本里按顺序真实存在
    L8 占位符残留：{ } / 【待补】 / XXX / TODO / 占位
    L9 指代落地：「急了？/真的假的/然后呢」这类反应型短句必须紧跟她的某句话——
       若之前她一句话都没说过、或中间已隔 ≥3 条我方消息，=反应失去对象（漂浮句，提示级）
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))

# 新写法指令（机械门 _NEW2OLD 里归一，但 main.py 映射表没有这些字面值）
_EXTRA_COMMANDS = {
    "我方发消息", "观众字幕", "清空输入框", "我方发图片", "她插话",
    "我方发emoji", "我方发语音", "对方发emoji", "对方发语音",
    "历史会话", "历史会话结束", "会话",
}
# 历史块里的行内内容标记（只在 [历史会话] 段内合法）
_HISTORY_CONTENT_TOKENS = {"图片", "链接", "表情"}

_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_LEAD_TOKEN_RE = re.compile(r"\[([^\[\]]+)\]")
_SPEAKER_LINE_RE = re.compile(r"^([^:\[\]#][^:：]{0,11})\s*[：:]\s*(.*)$")


def load_command_whitelist():
    """从 main.py 源码提取 TEXT_COMMAND_MAP 的键，不 import main（避免重依赖）。"""
    main_py = os.path.join(ROOT, "main.py")
    src = open(main_py, encoding="utf-8").read()
    m = re.search(r"TEXT_COMMAND_MAP\s*=\s*\{", src)
    brace = m.end() - 1
    depth, i = 0, brace
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = src[brace:i + 1]
    keys = set(re.findall(r'"([^"]+)"\s*:', body))
    return keys | _EXTRA_COMMANDS


def load_people():
    """people.json 展平：{人名: 类别}。"""
    data = json.load(open(os.path.join(ROOT, "people.json"), encoding="utf-8"))
    people = {}
    for cat, members in data.items():
        if isinstance(members, dict):
            for name in members:
                people[name] = cat
    return people


def find_ledger(script_path):
    """配套台账：同目录下 <basename>.台账.md / *.ledger.md / 文件名含「台账」。"""
    d = os.path.dirname(script_path)
    base = os.path.basename(script_path)
    stem = base[:-4] if base.lower().endswith(".txt") else base
    candidates = [stem + ".台账.md", stem + ".ledger.md"]
    for c in candidates:
        p = os.path.join(d, c)
        if os.path.isfile(p):
            return p
    return None


def parse_ledger(text):
    """解析台账：人物锁 / 关系阶段（时间） / 承诺（首提词→兑付词）。"""
    lock_names, stage_times, promises = [], [], []
    section = None
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("##"):
            section = s
            continue
        if "人物锁" in (section or "") and s.startswith(("-", "*")):
            m = re.match(r"^[-*]\s*(?:主线|学员[/／]?粉丝|其他出场|配角)\s*[：:]\s*(.+)$", s)
            if m:
                raw_names = re.sub(r"[（(].*?[)）]", "", m.group(1))
                for nm in re.split(r"[、,，]+", raw_names):
                    nm = nm.strip()
                    if nm:
                        lock_names.append(nm)
        elif "关系阶段" in (section or ""):
            mt = _TIME_RE.search(s)
            if mt:
                stage_times.append((int(mt.group(1)) * 60 + int(mt.group(2)), s))
        elif "承诺" in (section or "") and s.startswith(("-", "*")):
            body = s.lstrip("-* ").strip()
            first = pay = None
            for part in (p.strip() for p in body.split("|")):
                if part.startswith("首提词"):
                    first = part.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif part.startswith("兑付词"):
                    pay = part.split("：", 1)[-1].split(":", 1)[-1].strip()
            if first and pay:
                promises.append((first, pay, body))
    return lock_names, stage_times, promises


def _bigrams(s):
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def check_file(path, whitelist, people, require_ledger=False):
    lines = open(path, encoding="utf-8").read().splitlines()
    print("=" * 72)
    print("◆", os.path.basename(path))
    errors, warnings = [], []

    in_history = False
    current_speaker = None      # 历史块当前 [会话] 主角
    open_chat = None            # 实时区当前打开的会话
    timeline = []               # (分钟, 行号, 文本)
    first_word_index = {}       # 词 -> 首次出现行号（1-based）
    subtitle_events = []        # (行号, 字幕文本)
    # L9 指代落地状态
    her_seen = False            # 实时区她是否已开口（含后台消息）
    my_since_her = 0            # 距她上一条之后，我方已发几条
    my_run = []                 # 她上一条之后我方的 (行号, 正文)
    _REACTION_RE = re.compile(
        r"急了|真的假的|然后呢|还来|又来|别啊|谁急|慌什么|蒙了吧|想啥呢|说你呢|"
        r"干嘛呢|咋回事|不至于|你确定|你猜")
    # 确认型问题：球递给她，她不接、我方不能自己答
    _CONFIRM_RE = re.compile(r"你确定|确定吗|想好了|真的要|你认真|不后悔")

    for idx, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s:
            continue

        if s == "[历史会话]":
            in_history = True
            continue
        if s == "[历史会话结束]":
            in_history = False
            current_speaker = None
            continue

        token_m = _LEAD_TOKEN_RE.match(s) if s.startswith("[") else None

        if in_history:
            if s.startswith("[会话]"):
                current_speaker = s[len("[会话]"):].strip()
                if current_speaker and current_speaker not in people:
                    errors.append("L3 第%d行 历史会话「%s」不在 people.json" % (idx, current_speaker))
                continue
            if token_m and token_m.group(1) in _HISTORY_CONTENT_TOKENS:
                continue   # 行内 [图片]/[链接]/[表情] 内容标记
            m = _SPEAKER_LINE_RE.match(s)
            if m and current_speaker:
                spk = m.group(1).strip()
                if spk not in (current_speaker, "我"):
                    errors.append("L3 第%d行 [会话] %s 里出现了第三说话人「%s」"
                                  % (idx, current_speaker, spk))
            # 历史块不做指令白名单判定
            continue

        # ---------- 实时区 ----------
        if token_m:
            token = token_m.group(1)
            if token not in whitelist:
                errors.append("L1 第%d行 未知指令 [%s]（软件不认识=该步会被丢弃；"
                              "若确是新指令先加进 main.py TEXT_COMMAND_MAP）" % (idx, token))
            if token == "打开聊天":
                open_chat = s[len("[打开聊天]"):].strip()
                if open_chat and open_chat not in people:
                    errors.append("L3 第%d行 [打开聊天] 「%s」不在 people.json" % (idx, open_chat))
            if token == "返回主页":
                open_chat = None

            # ---- L9 指代落地：先按角色记账，再查反应型短句 ----
            _HER_UTTER = {"对方发消息", "她插话", "对方发图片", "对方发表情",
                          "对方发emoji", "对方后台发消息", "对方后台发表情"}
            _MY_UTTER = {"我方发消息", "我方发表情", "我方发emoji", "我方发图片"}
            if token in _HER_UTTER:
                her_seen = True
                # 她回话了：检查这段我方连发里是否有确认型问题被自己抢着答了
                for i, (qn, qb) in enumerate(my_run):
                    after = len(my_run) - 1 - i
                    if qb and _CONFIRM_RE.search(qb) and after >= 2:
                        warnings.append(
                            "L9 第%d行 确认型问题「%s」问了她，她的回话却晚了 %d 条"
                            "我方消息——中间我方等于自问自答（她的回答要紧跟问题，"
                            "或把问题删掉）" % (qn, qb, after))
                my_since_her = 0
                my_run = []
            elif token in _MY_UTTER:
                my_since_her += 1
                body = ""
                if token == "我方发消息":
                    body = s[len("[我方发消息]"):].split("|")[0].strip()
                    if _REACTION_RE.search(body) and (not her_seen or my_since_her >= 3):
                        warnings.append(
                            "L9 第%d行 反应型短句「%s」在语境里没有落点——她还没开口或中间"
                            "已隔 %d 条我方消息（谁？对什么反应？改成由她刚说的具体内容"
                            "长出来的句子）" % (idx, body, my_since_her - 1))
                my_run.append((idx, body))

        # L2 时间
        mt = None
        if s.startswith("[对方后台发消息]"):
            tail = s.rsplit("|", 1)
            if len(tail) == 2:
                mt = _TIME_RE.search(tail[1])
                # bg 行格式：名字 | 内容 | 时间
                parts = [p.strip() for p in s[len("[对方后台发消息]"):].split("|")]
                if len(parts) >= 3 and parts[0] not in people:
                    errors.append("L3 第%d行 后台消息联系人「%s」不在 people.json" % (idx, parts[0]))
                if len(parts) >= 3 and open_chat and parts[0] == open_chat:
                    warnings.append("L3 第%d行 后台消息来自当前正打开的「%s」——"
                                    "后台消息应是我在看别的会话时别人发来的" % (idx, parts[0]))
        else:
            tail = s.rsplit("|", 1)
            if len(tail) == 2 and not s.startswith("[观众字幕]"):
                mt = _TIME_RE.search(tail[1])
        if mt:
            timeline.append((int(mt.group(1)) * 60 + int(mt.group(2)), idx, s))

        # L4 撞名：台词里出现联系人名 + 吃喝语境
        if s.startswith(("[我方发消息]", "[对方发消息]", "[她插话]")):
            body = s.split("]", 1)[1]
            for name in people:
                if name in body and re.search(r"奶茶|口味|喝|吃|糖|甜|去冰|加料", body):
                    warnings.append("L4 第%d行 台词里「%s」是联系人名，又在吃喝语境"
                                    "（观众会出戏，换个口味/说法）：%s" % (idx, name, s[:40]))

        # 首提词索引（供台账兑付检查）
        if not s.startswith(("#", "[")):
            pass
        for w in list(people):
            pass

        if s.startswith("[观众字幕]"):
            sub = s[len("[观众字幕]"):].split("|")[0].strip()
            subtitle_events.append((idx, sub))

        # 全文任意行的词首次出现位置
        # （在台账检查段统一处理）

    # ---- L2 时间非递减 ----
    for (t1, n1, _), (t2, n2, s2) in zip(timeline, timeline[1:]):
        if t2 < t1:
            errors.append("L2 第%d行 时间倒流：早于第%d行 → %s（跨零点也按数字判，"
                          "时间线压在同一自然日内）" % (n2, n1, s2[:50]))

    # ---- L5 信息越界：她的下一条消息复述观众字幕 ----
    line_set = lines
    for (ln, sub) in subtitle_events:
        bg_sub = _bigrams(sub)
        if len(bg_sub) < 3:
            continue
        # 在字幕之后 6 行内找她第一条消息（遇我方发消息/打开聊天即停）
        for j in range(ln, min(ln + 6, len(lines))):
            t = line_set[j].strip()
            if t.startswith(("[我方发消息]", "[打开聊天]", "[返回主页]")):
                break
            if t.startswith(("[她插话]", "[对方发消息]")):
                body = t.split("]", 1)[1]
                bg_msg = _bigrams(body)
                if bg_sub and len(bg_sub & bg_msg) / len(bg_sub) > 0.6:
                    warnings.append("L5 第%d行 她的消息大段复述了上一条观众字幕，"
                                    "像她「听见了」给观众看的字幕（信息越界）" % (j + 1))
                break

    # ---- L8 占位符 ----
    for idx, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith("#") or not s:
            continue
        if re.search(r"\{[^}]*\}|【待|XXX|TODO|占位|待补", s, re.I):
            errors.append("L8 第%d行 占位符残留：%s" % (idx, s[:50]))

    # ---- 台账 L6/L7 ----
    ledger = find_ledger(path)
    if ledger:
        print("  台账：%s" % os.path.basename(ledger))
        lock_names, stage_times, promises = parse_ledger(open(ledger, encoding="utf-8").read())
        full_text = "\n".join(lines)

        # 人物锁：锁的名字必须出现在剧本
        for nm in lock_names:
            for token in re.split(r"[、,/\s]+", nm):
                if token and token not in full_text:
                    warnings.append("台账 人物锁「%s」在剧本里没出现" % token)

        # L7 阶段时间在剧本中按顺序存在
        script_times = [t for t, _, _ in timeline]
        cursor = -1
        for mins, row in stage_times:
            later = [k for k in script_times if k > cursor]
            if mins not in later:
                errors.append("L7 台账阶段「%s」的时间在剧本里不存在或顺序不对" % row.strip())
                cursor = mins
            else:
                cursor = mins

        # L6 承诺兑付：兑付词行号 > 首提词行号
        def first_line_of(word):
            for k, raw in enumerate(lines, 1):
                if word in raw:
                    return k
            return None

        for first, pay, body in promises:
            nf = first_line_of(first)
            np_ = first_line_of(pay)
            if nf is None:
                errors.append("L6 承诺首提词「%s」在剧本里没出现（%s）" % (first, body[:40]))
            elif np_ is None:
                errors.append("L6 承诺未兑付：首提词「%s」之后找不到兑付词「%s」" % (first, pay))
            elif np_ < nf:
                errors.append("L6 兑付词「%s」出现在首提词「%s」之前——顺序倒挂" % (pay, first))
    elif require_ledger:
        errors.append("L? 缺少配套《状态台账》（文件名同剧本、后缀 .台账.md，"
                      "模板见 .workbuddy/skills/创作模式全流程/状态台账模板.md）")
    else:
        warnings.append("未找到配套《状态台账》（改编/手写稿建议建台账；"
                        "加 --require-ledger 可改为强制）")

    for w in warnings:
        print("  [提示]", w)
    for e in errors:
        print("  [问题]", e)
    print("结论：", "全部通过 ✅" if not errors else "存在 %d 个逻辑问题 ❌" % len(errors))
    return not errors


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    require_ledger = "--require-ledger" in sys.argv
    if not paths:
        print("用法：py _check_script_logic.py 剧本.txt [--require-ledger]")
        sys.exit(2)
    whitelist = load_command_whitelist()
    people = load_people()
    ok_all = True
    for p in paths:
        if "参考" in os.path.basename(p):
            print("=" * 72)
            print("◆", os.path.basename(p), "（参考样本，跳过）")
            continue
        ok_all = check_file(p, whitelist, people, require_ledger) and ok_all
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
