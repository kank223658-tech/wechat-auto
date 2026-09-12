# -*- coding: utf-8 -*-
"""_diag_generate.py —— 「创作模式」生成质量体检（只读，不改任何数据）

四个体检项：
  1) 动作表口径差异：editor_server.ACTIONS / script_translator.ACTION_SCHEMA / ACTION_PARAMS
  2) 新功能覆盖缺口：新动作在 script_generator.py（提示词+书写规范+校验器）里出现过没有
  3) 规则库冲突/重复检测：互斥规则对、重复规则、语义错位规则
  4) 历史重跑：用【当前】校验器把 generate_history.json 全部重跑一遍，统计通过率与高频问题

用法：
    py _diag_generate.py                 # 打印 + 写 _diag_gen_report.md
    py _diag_generate.py --limit 20      # 只重跑最近 20 条历史
"""

import collections
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

REPORT = os.path.join(ROOT, "_diag_gen_report.md")

# 本轮要检查的新动作/新能力（来自最近的界面复刻工作）
NEW_FEATURES = [
    "切换底部面板", "面板切换序列", "发送emoji", "对方emoji",
    "发送表情", "对方表情", "对方后台发表情",
    "点赞", "评论", "发朋友圈", "编辑朋友圈",
    "打开转账面板", "转账", "对方转账", "接收转账",
    "手机状态栏", "闪回聊天", "@成员", "转发消息",
]

out = []


def w(line=""):
    out.append(line)
    print(line)


def section(t):
    w()
    w("## " + t)
    w()


# ============================================================
# 1) 动作表口径差异
# ============================================================

def load_actions():
    import editor_server as es
    import script_translator as st
    a_es = [a["action"] for a in es.ACTIONS]
    a_schema = [a["action"] for a in st.ACTION_SCHEMA]
    a_params = list(st.ACTION_PARAMS.keys())
    return a_es, a_schema, a_params


def check_action_tables():
    a_es, a_schema, a_params = load_actions()
    s_es, s_schema, s_params = set(a_es), set(a_schema), set(a_params)
    section("1) 动作表口径差异（三份表互有缺失 = 新功能永远不会生效）")
    w("| 表 | 条数 | 用途 |")
    w("|---|---|---|")
    w("| `editor_server.ACTIONS` | %d | 拼生成提示词的动作表 |" % len(a_es))
    w("| `script_translator.ACTION_SCHEMA` | %d | 校验器 `_valid_action_names()` 的合法动作名来源 |" % len(a_schema))
    w("| `script_translator.ACTION_PARAMS` | %d | `validate_steps()` 参数归一/默认值 |" % len(a_params))
    w()
    w("**只在前端动作表里、校验器不认的（后果：以它写的规则会被静默降级成 style，永远不生效）**")
    missing_schema = sorted(s_es - s_schema)
    w()
    w("```")
    w("、".join(missing_schema) or "（无）")
    w("```")
    w()
    w("**参数归一缺失（后果：参数不吃默认值、不做类型转换，运行时报错或静默用错值）**")
    missing_params = sorted(s_es - s_params)
    w()
    w("```")
    w("、".join(missing_params) or "（无）")
    w("```")
    return missing_schema, missing_params


# ============================================================
# 2) 新功能在生成链路里的覆盖
# ============================================================

def check_new_feature_coverage():
    src = open(os.path.join(ROOT, "script_generator.py"), encoding="utf-8").read()
    try:
        import action_registry as R
        cards = {c["action"]: c for c in R.capability_cards()}
        script_ok = {a["action"]: bool(a.get("script_ok", True)) for a in R.ACTIONS}
    except Exception:                                             # noqa: BLE001
        cards, script_ok = {}, {}
    section("2) 新功能在「创作链路」里的覆盖（能力卡 + 提示词 + 书写规范 + 校验器）")
    w("判据（本轮已改为看「有没有能力卡」，而不是数关键词）：")
    w("能力卡 = 「什么时候用 + 片段长什么样」，会随提示词的【能力卡】段落一起发给模型。")
    w("没有能力卡的动作，模型只在一行动作表里见过名字 → 实际不会主动用。")
    w()
    w("| 动作 | 能力卡 | 能力卡内说明 | 可给 AI 写 | 状态 |")
    w("|---|---|---|---|---|")
    gaps = []
    for name in NEW_FEATURES:
        c = cards.get(name)
        ok_script = script_ok.get(name, True)
        if c:
            flag = "✅ 已接入"
        elif not ok_script:
            flag = "· 内部动作（由别的动作驱动，无需 AI 直接写）"
        else:
            flag = "❌ 缺能力卡"
            gaps.append(name)
        w("| %s | %s | %s | %s | %s |" % (
            name, "有" if c else "—",
            (c["when"][:34] + "…") if c and len(c["when"]) > 34 else (c["when"] if c else "—"),
            "是" if ok_script else "否", flag))
    w()
    w("未接入的动作：**%s**" % ("、".join(gaps) or "无"))
    return gaps


# ============================================================
# 3) 规则库冲突检测
# ============================================================

# 互斥规则对：(规则A的kind特征, 规则B的kind特征, 说明, 建议, 已消解？)
# 第 5 项 = 该互斥对是否已被本轮改造消解（消解了就不再报成问题，只在报告里留一行「已消解」）。
#   min_realtime_lines ⟂ max_script_steps：已合并成「篇幅预算」，两条数字由 _apply_budget 收敛。
#   max_people ⟂ min_sessions：已把 _count_people 的统计口径改成「只数 [打开聊天] 的目标」，
#     历史会话列表里的 9 个联系人不再计入出场人物。
CONFLICT_PAIRS = [
    (("min_realtime_lines", None), ("max_script_steps", None),
     "配额接近零和：旧值 130 条实时对白 + 每个 [打字不发] 配一条 [删除文字]（15 处即 15 步）"
     "+ 打开聊天/返回主页/等待/编辑主页，总步数已经逼近 190~195（实测最好的一条正是 194/200）。"
     "余量 <5%，模型夹在中间：19 条卡「对白不够」、7 条卡「步数超」。",
     "已合并成一个「篇幅预算」：max_script_steps=200 时对白按参考比例收敛到 110 条，"
     "提示词与校验器取同一套数字。", True),
    (("max_people", None), ("min_sessions", None),
     "限制出场人物 ≤ N 人，又要求会话数 ≥ M 个——旧版把 [会话] 里所有历史联系人都算成「出场人物」，"
     "9 个历史会话会恒判超员（实测 4 条因此被打回）。",
     "已把出场人物口径改为「只数 [打开聊天] 真正展开的目标」，历史列表里的联系人不再计入。", True),
    (("min_history_messages", None), ("history_two_sided", None),
     "「历史会话只写一条消息」与「至少一个会话是双方来回」互斥——只写一条就不可能有来回。",
     "已停用 min_history_messages；历史会话按「是否会被点开」分档。", True),
    (("forbid_text", None), ("min_history_messages", None),
     "逐条禁令 + 条数下限叠加时容易互相挤压（例如既禁词又要凑条数）。",
     "最少条数类规则不宜超过 2 条同时启用。", False),
]

# 语义错位：同类规则被塞进了不属于它的内容
KIND_MISUSE = [
    ("max_annotations", ("表情包", "表情"), "「表情包总数上限」被塞进 max_annotations（注解处数上限）→ 报错文案张冠李戴，用户看到「（规则：表情包不超过3个）」却说消息里发了心理活动。", "新增 max_emoji_total 规则类型。"),
    ("max_annotations", ("时间节点", "时间标注", "时间分隔"), "「时间节点标注处数」被塞进 max_annotations → 同上。", "新增 max_time_marks 规则类型。"),
    ("max_message_chars", ("打字不发",), "「话术要短小精悍」的作用域被套到了 `[打字不发]` 上，而 `[打字不发]` 是给观众看的技巧说明，天然比话术长 → 恒打不通过。", "max_message_chars 只约束 [我方打字]（代码 1110 行把 打字不发 也算进去了）。"),
]


def check_rule_conflicts():
    import create_store as store
    skills = store.list_skills()
    # 只有「启用中」的规则才会真的参与校验；已停用的（自动治理停用的重复/冲突项）
    # 不该再被报成问题，否则每次体检都会看到一堆已经处理过的旧账。
    rules = [s for s in skills if (s.get("type") or "rule") == "rule" and s.get("enabled")]
    styles = [s for s in skills if (s.get("type") or "rule") != "rule" and s.get("enabled")]
    off = [s for s in skills if not s.get("enabled")]
    by_kind = collections.defaultdict(list)
    for s in rules:
        by_kind[s.get("kind")].append(s)

    section("3) 规则库体检（启用 %d 条：硬规则 %d / 风格偏好 %d；已停用 %d 条）"
            % (len(rules) + len(styles), len(rules), len(styles), len(off)))
    if off:
        w("> 已停用 %d 条（多为自动治理时的重复/冲突项，可在规则面板里恢复）：%s"
          % (len(off), "、".join("`%s`" % (s.get("kind") or "?") for s in off[:12])
             + ("…" if len(off) > 12 else "")))
        w()

    # 3.1 同 kind 多值 = 潜在冲突/重复
    w("### 3.1 同一规则类型出现多条（值不同 = 冲突，值相同 = 冗余）")
    w()
    w("| 规则类型 | 条数 | 取值 | 判定 |")
    w("|---|---|---|---|")
    dup = 0
    for kind, items in sorted(by_kind.items(), key=lambda x: -len(x[1])):
        if len(items) < 2:
            continue
        vals = []
        for it in items:
            v = it.get("value")
            if isinstance(v, list):
                v = "|".join(str(x) for x in v)
            vals.append(str(v))
        uniq = set(vals)
        verdict = "⚠️ 取值不同，冲突" if len(uniq) > 1 else "⚠️ 完全重复，冗余"
        dup += 1
        w("| `%s` | %d | %s | %s |" % (kind, len(items), "、".join(sorted(uniq)), verdict))
    if dup == 0:
        w("| — | — | — | 无重复 ✅ |")

    # 3.2 互斥规则对（按「数值是否真的不可同时满足」判定，而不是「两条都存在」）
    w()
    w("### 3.2 互斥规则对（按数值判定：两条规则的数字是否真的无法同时满足）")
    w()
    try:
        import script_generator as sg
        nums = sg.rule_numbers(skills)
        cap = int(nums.get("max_script_steps") or 0)
        reels = int(nums.get("min_realtime_lines") or 0)
        holds = int(nums.get("min_typing_hold") or 0)
        # 每处 [打字不发] 后面通常跟一条 [删除文字]，另加油漆类开销（打开/返回/历史块）
        floor = reels + holds * 1.2 + 12
        headroom = (cap - floor) / cap * 100 if cap else 0
        w("- 篇幅预算：上限 %d 步 / 对白 ≥%d 条 / 打字不发 ≥%d 处。" % (cap, reels, holds))
        w("  按「每处打字不发配一条删除文字 + 约 12 步油漆」估算最少需要约 **%.0f 步**，"
          "余量 **%.0f%%**。" % (floor, headroom))
        if cap and floor > cap:
            w("  ⚠️ 仍然不可同时满足（需要 %.0f > 上限 %d）：把 min_realtime_lines 降到 %d 以下，"
              "或把 max_script_steps 提到 %.0f 以上。"
              % (floor, cap, int((cap - holds * 1.2 - 12) // 1), floor))
        else:
            w("  ✅ 可同时满足（两条数字已按预算收敛，提示词与校验器取同一套值）。")
    except Exception as exc:                                      # noqa: BLE001
        w("（预算检查跳过：%s）" % exc)
    w()
    found = 0
    resolved = 0
    for (ka, va), (kb, vb), why, fix, done in CONFLICT_PAIRS:
        ha = [s for s in by_kind.get(ka, []) if va is None or str(s.get("value")) == va]
        hb = [s for s in by_kind.get(kb, []) if vb is None or str(s.get("value")) == vb]
        if not ha or not hb:
            continue
        if done:
            resolved += 1
            w("- ✅ 已消解：`%s` ⟂ `%s` —— %s" % (ka, kb, fix))
            continue
        found += 1
        w("- **`%s`(%s) ⟂ `%s`(%s)**" % (ka, ",".join(str(s.get("value")) for s in ha),
                                          kb, ",".join(str(s.get("value")) for s in hb)))
        w("  - 为什么打架：%s" % why)
        w("  - 怎么改：%s" % fix)
    if found == 0 and resolved == 0:
        w("（未命中预置的互斥对 ✅）")
    elif found == 0:
        w()
        w("**当前启用中的规则里没有未消解的互斥对 ✅**")

    # 3.3 语义错位
    w()
    w("### 3.3 规则语义错位（值被塞进了不属于它的类型 → 报错文案前言不搭后语）")
    w()
    misuse = 0
    for kind, kws, why, fix in KIND_MISUSE:
        for s in by_kind.get(kind, []):
            blob = str(s.get("title") or "") + str(s.get("prompt_hint") or "")
            if any(k in blob for k in kws):
                misuse += 1
                w("- 规则「%s」（`%s=%s`）：%s" % (str(s.get("title"))[:26], kind, s.get("value"), why))
                w("  - 怎么改：%s" % fix)
    if misuse == 0:
        w("（未命中）")

    # 3.4 规则 vs 书写规范块的硬编码数字
    w()
    w("### 3.4 规则库数值 vs 书写规范块（两处口径是否一致）")
    w()
    try:
        import script_generator as sg
        nums = sg.rule_numbers(skills)
        hold = int(nums.get("min_typing_hold") or 0)
        interj = int(nums.get("min_interjections") or 0)
        expect = max(2, int(round(hold / 3.0)))
        w("- `[打字不发]` **%d 处**、插话 **%d 处**（配比 1:%.1f）。"
          "书写规范块与校验器都取自同一份 `rule_numbers()`，不再各写一套数字。"
          % (hold, interj, (hold / interj) if interj else 0))
        if interj != expect:
            w("  ⚠️ 插话数与「打字不发 ÷ 3」不一致（期望 %d）——参考剧本实测比例约 1:3，"
              "插话配太多会显得对方一直在抢话。可在规则面板把 min_interjections 调成 %d。"
              % (expect, expect))
        else:
            w("  ✅ 与参考剧本实测比例（约 1:3）一致。")
        w("- 篇幅三者（步数上限 %d / 对白下限 %d / 打字不发下限 %d）由同一套预算收敛，"
          "提示词与校验器不再互相抢额度。" % (
              int(nums.get("max_script_steps") or 0),
              int(nums.get("min_realtime_lines") or 0), hold))
    except Exception as exc:                                      # noqa: BLE001
        w("（跳过：%s）" % exc)
    return len(rules), len(styles), dup, found, misuse


# ============================================================
# 4) 历史重跑
# ============================================================

def check_history(limit=0):
    import script_generator as sg
    import editor_server as es
    path = os.path.join(ROOT, "generate_history.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        section("4) 历史重跑")
        w("读不到 generate_history.json，跳过。")
        return
    items = d.get("history") or d.get("items") or (d if isinstance(d, list) else [])
    if limit:
        items = items[:limit]
    skills = sg.load_enabled_skills()

    section("4) 用【当前】校验器重跑 %d 条生成历史" % len(items))
    agg = collections.Counter()
    names = {}
    passed_current = 0
    recorded_pass = 0
    rounds = collections.Counter()
    devnull = open(os.devnull, "w", encoding="utf-8")
    _stdout = sys.stdout
    for it in items:
        text = it.get("text") or ""
        rep = it.get("report") or {}
        if rep.get("passed"):
            recorded_pass += 1
        rounds[rep.get("attempts")] += 1
        if not text.strip():
            continue
        sys.stdout = devnull           # 屏蔽解析期的大量 warning 输出
        try:
            steps, _w2, _s = es._parse_script_to_steps(text, offline=True)
            issues = sg.check_completeness(text) + sg.validate_generated_steps(steps, skills, text)[0]
        finally:
            sys.stdout = _stdout
        if not issues:
            passed_current += 1
        for x in issues:
            key = re.sub(r"\d+", "N", str(x))[:58]
            agg[key] += 1
            names.setdefault(key, str(x))
    try:
        devnull.close()
    except OSError:
        pass

    w()
    w("- 生成当时记录的「一次通过」：**%d / %d**" % (recorded_pass, len(items)))
    w("- 用当前校验器重跑后仍通过：**%d / %d**（0 = 校验器现在几乎拦死所有结果）" % (passed_current, len(items)))
    w("- 轮数分布（当时用了几轮）：%s" % dict(sorted((k or 0, v) for k, v in rounds.items())))
    w()
    w("### 高频未通过问题 TOP20")
    w()
    w("（数字已归一成 N —— 同一类问题在不同剧本里的具体条数不同，按类归并才看得出主次；")
    w("  括号里是它命中最多的一条原文示例。）")
    w()
    w("| 次数 | 问题（同类归并） | 示例 |")
    w("|---|---|---|")
    for k, n in agg.most_common(20):
        sample = str(names.get(k, "")).replace("|", "\\|")
        w("| %d | %s | %s |" % (n, k.replace("|", "\\|"), sample[:70] + ("…" if len(sample) > 70 else "")))
    return agg


def check_parse_fragility(limit=0):
    """统计「模型写的行被离线解析静默丢掉」的情况——丢掉的越多，剧本越短，
    越容易反过来触发「对白条数不够」的规则，形成重写死循环。"""
    import editor_server as es
    path = os.path.join(ROOT, "generate_history.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return
    items = d.get("history") or d.get("items") or []
    if limit:
        items = items[:limit]
    section("5) 格式容错体检（被静默丢掉的行 = 剧本凭空变短 → 触发「对白不够」→ 重写死循环）")
    w()
    w("判据：`main.parse_script_text` 遇到无法识别的行会 `print('[剧本警告] …已跳过')` 后丢弃该行。")
    w("这里捕获这些输出，统计「模型写了但被扔掉」的指令。")
    w()
    agg = collections.Counter()
    n_record = 0
    _stdout = sys.stdout
    for it in items:
        text = it.get("text") or ""
        if not text.strip():
            continue
        buf = io.StringIO()
        sys.stdout = buf
        try:
            es._parse_script_to_steps(text, offline=True)
        finally:
            sys.stdout = _stdout
        lines = [x for x in buf.getvalue().splitlines() if "剧本警告" in x]
        if lines:
            n_record += 1
        for x in lines:
            agg[re.sub(r"第 \d+ 行", "第 N 行", str(x))[:78]] += 1
    w("- 有 %d / %d 条生成结果里存在被静默丢弃的指令行。" % (n_record, len(items)))
    w()
    if agg:
        w("| 次数 | 被丢掉的行 |")
        w("|---|---|")
        for k, n in agg.most_common(12):
            w("| %d | `%s` |" % (n, k.replace("|", "\\|")))
    else:
        w("（没有丢行）")
    w()
    w("对策：把「让模型输出 JSON、本地渲染成 [指令]」当成生成主路径，")
    w("格式类失败会一次性消失；文本解析只留作兼容用户手写的老路径。")


def check_reference_quality():
    """参考库体检：每条参考自己能不能过当前校验器。

    为什么要这一节：用户一直觉得「参考不够好」，但笼统地说没用 ——
    把每条参考拿当前规则打一遍分，就能看出「哪条参考在教坏习惯」，
    而不是继续往库里堆整篇。
    """
    import create_store as store
    import editor_server as es
    import script_generator as sg

    section("6) 参考库体检（每条参考自己能不能过当前校验器）")
    try:
        skills = sg.load_enabled_skills()
        refs = store.list_references()
    except Exception as exc:                                      # noqa: BLE001
        w("（跳过：%s）" % exc)
        return
    snips = [r for r in refs if (r.get("kind") or "full") == "snippet"]
    fulls = [r for r in refs if (r.get("kind") or "full") == "full"]
    w("整篇（当风格模板）**%d** 条 / 片段（当能力示范）**%d** 条。"
      "提示词里最多取 2 条整篇 + 6 条片段。" % (len(fulls), len(snips)))
    w()
    w("| 参考 | 行数 | 解析步数 | 问题数 | 最严重的问题 |")
    w("|---|---|---|---|---|")
    weak = []
    for r in fulls:
        t = str(r.get("text") or "")
        steps, _w, _s = es._parse_script_to_steps(t, offline=True)
        issues = sg.check_completeness(t) + sg.validate_generated_steps(steps, skills, t)[0]
        worst = max((sg.issue_severity(x) for x in issues), default=0)
        first = (issues[0] if issues else "—")
        if len(issues) >= 3:
            weak.append((r.get("title"), len(issues)))
        w("| %s | %d | %d | %d | %s |" % (
            str(r.get("title"))[:30], len(t.splitlines()), len(steps), len(issues),
            (first[:60] + "…") if len(first) > 60 else first))
    w()
    if weak:
        w("⚠️ 下面这些整篇参考**自己过不了当前规则**（拿它当 few-shot 等于在教坏习惯）：")
        for title, n in weak:
            w("- 《%s》 —— %d 个问题" % (str(title)[:34], n))
        w()
        w("建议：整篇参考只留 1~2 条最干净的（或者等「自动沉淀」攒出新的零问题剧本后再来挑），")
        w("其余删掉或降级成片段；新功能一律用【片段示例】教，不要靠整篇。")
    else:
        w("✅ 整篇参考都能过当前规则。")
    w()
    w("（提示词只会取 2 条整篇当风格模板，所以「库里有多少」不等于「模型看到多少」；")
    w(" `search_references` 会优先挑评分高、被采用次数多的。）")


def check_root_causes(limit=0):
    """把历史重跑出来的问题**归类**，找出真正的头号堵点。

    为什么要有这一节：单看「问题条数」只知道差在哪，看不出该先修哪。
    归类之后才看得清 —— 规则冲突只占一小部分，真正反复卡住模型的是
    「素材名编造」「[打字不发] 写成聊天话术」这两类（各占 1/6 以上）。
    """
    import script_generator as sg
    import editor_server as es
    path = os.path.join(ROOT, "generate_history.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return
    items = d.get("history") or d.get("items") or []
    items = [x for x in items if (x.get("text") or "").strip()]
    if limit:
        items = items[:limit]
    skills = sg.load_enabled_skills()

    def classify(x):
        if "引用的素材名" in x or "引用的素材在图片库里找不到" in x:
            return ("① 素材名编造（写了图库里没有的图/表情）",
                    "提示词的【可用素材】块已改成「编号 + 反面例子 + 逐字挑」；"
                    "报错也会直接给出「清单里最接近的是 X」。")
        if "打字不发" in x and ("话术草稿" in x or "少于要求" in x):
            return ("② [打字不发] 写成了聊天话术 / 数量不够",
                    "参考剧本自己在这一点上就不一致（它也没写满），"
                    "建议整篇参考只留最干净的一条，其余用【片段示例】。")
        if "时间戳几乎是机械的" in x:
            return ("③ 历史会话时间戳机械 +1 分钟", "已在规范块里给出「同分钟内/差2~3分钟/隔十几分钟」的混排写法。")
        if "交替率" in x:
            return ("④ 实时对白没有连发（我一条你一条像朗读）", "规范块要求「至少一段一方连发 2~3 条」。")
        if "实时对白只有" in x:
            return ("⑤ 实时对白条数不够", "已按参考剧本比例收敛（110 条），提示词与校验器取同一套数字。")
        if "历史会话" in x:
            return ("⑥ 历史会话写法（写成了一问一答 / 同一人刷屏）", "规范块 B 段已给出「微信列表预览」的标准样本。")
        if "超过上限" in x and "步" in x:
            return ("⑦ 步数超上限", "给了篇幅预算，要求「靠拆句拉节奏，不靠堆空转指令」。")
        if "内容过长" in x:
            return ("⑧ 单条话术过长", "上限 20 字；[打字不发] 的技巧说明不再计入。")
        if "出场人物" in x or "会话数只有" in x:
            return ("⑨ 人物 / 会话数量", "已消解互斥：出场人物只数 [打开聊天] 的目标。")
        if "表情" in x and "重复" in x:
            return ("⑩ 同一表情重复太多", "规则上限 2 次。")
        if "插话" in x:
            return ("⑪ 插话写法 / 数量", "统一为「打字不发 ÷ 3」，规范块与规则库同一来源。")
        return ("⑫ 其他 / 单条偶发", "—")

    agg = collections.Counter()
    fixes = {}
    devnull = open(os.devnull, "w", encoding="utf-8")
    saved = sys.stdout
    total = 0
    for it in items:
        text = it.get("text") or ""
        sys.stdout = devnull
        try:
            steps, _w, _s = es._parse_script_to_steps(text, offline=True)
            issues = (sg.check_completeness(text)
                      + sg.validate_generated_steps(steps, skills, text)[0])
        finally:
            sys.stdout = saved
        total += len(issues)
        for x in issues:
            label, fix = classify(x)
            agg[label] += 1
            fixes.setdefault(label, fix)
    try:
        devnull.close()
    except OSError:
        pass

    section("7) 真正的头号堵点（把 %d 条历史的问题归类，共 %d 个）" % (len(items), total))
    w("规则冲突只占一部分；下面按出现次数排序 —— 先修排在最前面的，收益最大。")
    w()
    w("| 次数 | 占比 | 堵点 | 已经做的处置 |")
    w("|---|---|---|---|")
    for k, n in agg.most_common():
        w("| %d | %.0f%% | %s | %s |" % (n, (n / total * 100) if total else 0, k, fixes.get(k, "")))
    w()
    w("> 注：这批是**旧规则下生成的旧成品**，所以它反映的是「历史痛点分布」，")
    w("> 而不是「现在的生成质量」。现在的改动要等下一次真实生成才能验证。")


def main():
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            limit = 0

    w("# 创作模式（AI 生成剧本）质量体检报告")
    w()
    w("生成时间：脚本实时生成 · 只读诊断，未修改任何数据")
    check_action_tables()
    check_new_feature_coverage()
    check_rule_conflicts()
    check_history(limit)
    check_parse_fragility(limit)
    check_reference_quality()
    check_root_causes(limit)

    w()
    w("---")
    w("重跑本报告：`py _diag_generate.py`")
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n[报告已写入] " + REPORT)


if __name__ == "__main__":
    main()
