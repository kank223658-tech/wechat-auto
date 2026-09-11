# -*- coding: utf-8 -*-
"""
剧本创作生成器（男生追女生 / 聊天教学）
=========================================
在已有「脚本模式」转译之上，新增一层"创作"能力：用户输入主题 + 参考剧本，
由大模型直接产出一整套符合 [指令] 标准、内容为"男生追女生技巧"的完整剧本；
随后经「完整性检查 → 结构化校验 → critique 重写」自我纠错，落地到可运行步骤。

与 script_translator 的关系：
  - 复用其 人物库(people.json) / 动作表(ACTION_SCHEMA/ACTION_PARAMS) / call_deepseek /
    设置读写(settings.json)，保证人物与动作口径一致。
  - 这里的生成走「大模型输出 [指令] 文本 + 离线归一」：生成结果本身就是标准 [指令]，
    用 main.parse_script_text 归一即可，避免二次调用大模型。

数据文件（项目根目录）：
  reference_scripts.json   用户的可参考剧本库
  feedback.json            每次生成的打分/留言 + 长期偏好块
  generate_history.json    每次「创作生成」的结果存档（供历史面板回看/复用）
"""

import json
import os
import re

import create_store as store
import script_translator as st

# ============================================================
# 路径
# ============================================================

ROOT = os.path.dirname(os.path.abspath(__file__))
REFERENCE_PATH = os.path.join(ROOT, "reference_scripts.json")
FEEDBACK_PATH = os.path.join(ROOT, "feedback.json")
HISTORY_PATH = os.path.join(ROOT, "generate_history.json")

MAX_CRITIQUE_ROUNDS = 3  # 生成轮数：1 次初稿 + 最多 2 次 critique 重写
HISTORY_LIMIT = 60       # 生成历史最多保留多少条（最新在前，超出丢弃最旧）

# 判定人物类别（学员/美女），与 script_translator 一致
CATEGORIES = ("学员", "美女")


# ============================================================
# 参考剧本库读写
# ============================================================

def _load_raw(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save_raw(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_reference_scripts() -> list:
    """读取参考剧本库（SQLite）。"""
    return store.list_references()


def save_reference_scripts(scripts: list):
    """兼容旧接口：不再整文件覆盖，改为逐条 upsert（一般无需调用）。"""
    for s in scripts or []:
        if not isinstance(s, dict):
            continue
        if s.get("id") and store.get_reference(s.get("id")):
            store.update_reference(s["id"], {
                "title": s.get("title"), "category": s.get("category"),
                "text": s.get("text"), "summary": s.get("summary"),
                "topics": s.get("topics"), "tags": s.get("tags"),
            })
        else:
            store.add_reference(title=s.get("title") or "", text=s.get("text") or "",
                                category=s.get("category") or "")


def _new_id(prefix: str) -> str:
    import time
    return f"{prefix}-{int(time.time() * 1000)}"


def add_reference_script(title: str, text: str, category: str = "") -> dict:
    """新增一条参考剧本（标题为空或旧式「[历史会话]…」时自动重命名）。"""
    return store.add_reference(title=title or "", text=text or "", category=category or "")


def delete_reference_script(ref_id: str) -> bool:
    return store.delete_reference(ref_id)


def get_reference_scripts_by_ids(ids) -> list:
    """按 id 列表取参考剧本（保持挑选顺序），匹配不到则忽略。"""
    return store.get_references_by_ids(ids)


def format_references(references: list, category: str = "") -> str:
    """把选中的参考剧本拼成提示词里的 few-shot 文本块。

    每条参考带上它的标签与结构摘要，让模型知道"该学什么"；
    并明确声明参考里的人名只是占位，必须替换为人物库里的名字。
    """
    if not references:
        return "（本次未提供参考剧本，请依你掌握的聊天教学套路直接创作）"
    parts = []
    for i, r in enumerate(references, start=1):
        title = str(r.get("title", "未命名"))
        txt = str(r.get("text", ""))
        tags = "、".join(r.get("tags") or []) or "无"
        summary = str(r.get("summary") or "")
        head = f"参考剧本{i}《{title}》\n手法标签：{tags}\n结构摘要：{summary}"
        parts.append(head + "\n" + txt)
    return (
        "【重要】以下参考剧本里的人名、头像只是占位示例，"
        "你必须在成稿里全部替换为【人物库】里的人物，不得照抄参考里的人名。\n"
        "参考剧本里 `[打字不发]` 的正文都是「写给观众看的技巧说明」，这正是要学的写法："
        "你的成稿里**每一处** `[打字不发]` 的正文都要写这种打法说明"
        "（「这一步在做什么、为什么这样聊有效」），"
        "绝不能写成马上要发出去的聊天话术，也不能写成对方的心理活动。\n"
        "参考剧本的 [历史会话] 是最好的学习对象：像微信列表预览，绝大多数会话只留对方最后 1~2 条、"
        "每条都带钩子、时间标注错落，整块里只让 1 个会话带「我：」的回复；"
        "要避免让同一个人在历史会话里连发一大堆。\n\n"
        + "\n\n".join(parts)
    )


# ============================================================
# 生成历史读写（供「历史生成」面板回看 / 复用）
# ============================================================

def load_generation_history() -> list:
    """读取生成历史，最新在前，返回 list[dict]。"""
    data = _load_raw(HISTORY_PATH, {}) or {}
    items = data.get("history", [])
    return items if isinstance(items, list) else []


def save_generation_history(items: list):
    _save_raw(HISTORY_PATH, {"history": items or []})


def add_generation_history(entry: dict) -> dict:
    """把一次生成结果存进历史（最新在前，超出上限截断），返回入库后的条目。"""
    import time as _t
    items = load_generation_history()
    item = dict(entry or {})
    item.setdefault("id", _new_id("gen"))
    item.setdefault("created_at", _t.time())
    items.insert(0, item)
    if len(items) > HISTORY_LIMIT:
        items = items[:HISTORY_LIMIT]
    save_generation_history(items)
    return item


def history_summary(item: dict) -> dict:
    """历史列表用的摘要：不含剧本全文，避免列表接口体积过大。"""
    item = item if isinstance(item, dict) else {}
    report = item.get("report") if isinstance(item.get("report"), dict) else {}
    issues = report.get("issues") or []
    steps = item.get("steps") if isinstance(item.get("steps"), list) else []
    text = str(item.get("text") or "")
    return {
        "id": str(item.get("id") or ""),
        "brief": str(item.get("brief") or ""),
        "category": str(item.get("category") or ""),
        "ref_titles": [str(x) for x in (item.get("ref_titles") or []) if x],
        "created_at": item.get("created_at") or 0,
        "steps": len(steps),
        "chars": len(text),
        "attempts": int(report.get("attempts") or 1),
        "passed": bool(report.get("passed")),
        "issues": len(issues),
        "score": int(item.get("score") or 0),
        "model": str(item.get("model") or ""),
    }


def list_generation_history() -> list:
    """历史摘要列表（最新在前）。"""
    return [history_summary(x) for x in load_generation_history() if isinstance(x, dict)]


def get_generation_history(gen_id: str):
    for x in load_generation_history():
        if isinstance(x, dict) and str(x.get("id")) == str(gen_id):
            return x
    return None


def delete_generation_history(gen_id: str) -> bool:
    items = load_generation_history()
    before = len(items)
    items = [x for x in items if str((x or {}).get("id")) != str(gen_id)]
    if len(items) != before:
        save_generation_history(items)
        return True
    return False


def clear_generation_history() -> int:
    n = len(load_generation_history())
    save_generation_history([])
    return n


def set_generation_score(gen_id: str, score: int) -> bool:
    """把评价星级回写到对应历史条目，让历史列表也能显示打分。"""
    items = load_generation_history()
    ok = False
    for x in items:
        if isinstance(x, dict) and str(x.get("id")) == str(gen_id):
            x["score"] = int(score)
            ok = True
            break
    if ok:
        save_generation_history(items)
    return ok


# ============================================================
# 反馈库读写 / 偏好蒸馏
# ============================================================

def load_feedback() -> dict:
    return _load_raw(FEEDBACK_PATH, {"feedback": [], "preferences": ""})


def save_feedback(data: dict):
    _save_raw(FEEDBACK_PATH, data or {})


def add_feedback(score: int, comment: str, brief: str = "", title: str = "") -> dict:
    """追加一次评价，返回新条目。"""
    data = load_feedback()
    feedback = data.get("feedback", [])
    import time as _t
    item = {
        "id": _new_id("fb"),
        "brief": (brief or "").strip(),
        "title": (title or "").strip(),
        "score": int(score),
        "comment": (comment or "").strip(),
        "created_at": _t.time(),
    }
    feedback.append(item)
    data["feedback"] = feedback
    save_feedback(data)
    return item


def load_enabled_skills() -> list:
    """读取启用的规则/风格条目（生成与校验共用）。"""
    _repair_invalid_action_rules_once()
    return store.list_skills(enabled_only=True)


# 校验器只认「动作表里的动作名」；LLM 常把抽象要求（插话/话题推进/精彩）
# 误拆成 required_action，导致规则永远判不过、每次生成都被打回。
_rules_repaired = False


def _valid_action_names() -> set:
    names = set()
    for a in getattr(st, "ACTION_SCHEMA", []) or []:
        if isinstance(a, dict) and a.get("action"):
            names.add(str(a["action"]))
    names.update(str(k) for k in (getattr(st, "ACTION_ALIASES", {}) or {}))
    return names


def _is_valid_action(value) -> bool:
    v = str(value or "").strip()
    if not v:
        return False
    names = _valid_action_names()
    return v in names or v in (getattr(st, "ACTION_ALIASES", {}) or {})


def _normalize_candidate(c: dict) -> dict:
    """把抽出来的候选规则修正成校验器真正能用的形式。

    无法机械校验的要求（如「插话用起来」「对话要精彩」）降级成 style，
    只注入提示词、不参与校验，避免制造永远无法满足的硬规则。
    """
    if not isinstance(c, dict):
        return c
    kind = str(c.get("kind") or "").strip()
    value = c.get("value")

    def _as_style():
        return {
            "type": "style",
            "title": str(c.get("title") or c.get("prompt_hint") or "").strip()[:40],
            "kind": None,
            "value": None,
            "prompt_hint": str(c.get("prompt_hint") or c.get("title") or "").strip()[:200],
        }

    if kind in ("required_action", "banned_action"):
        vals = value if isinstance(value, (list, tuple)) else [value]
        keep = [v for v in vals if _is_valid_action(v)]
        if not keep:
            return _as_style()
        return {**c, "type": "rule", "kind": kind,
                "value": keep if isinstance(value, (list, tuple)) else keep[0]}

    if kind in ("min_sessions", "min_history_messages", "min_realtime_lines",
                "max_message_chars", "max_people", "max_annotations",
                "max_history_streak", "min_interjections", "min_typing_hold",
                "max_script_steps"):
        try:
            num = int(float(value))
        except (TypeError, ValueError):
            return _as_style()
        if num <= 0:
            return _as_style()
        return {**c, "type": "rule", "kind": kind, "value": num}

    if kind in ("opening_image", "forbid_annotation_as_message", "history_two_sided"):
        return {**c, "type": "rule", "kind": kind, "value": True}

    if kind in ("forbid_text",):
        vals = value if isinstance(value, (list, tuple)) else [value]
        keep = [str(v).strip() for v in vals if str(v).strip()]
        if not keep:
            return _as_style()
        return {**c, "type": "rule", "kind": kind,
                "value": keep if isinstance(value, (list, tuple)) else keep[0]}

    if kind and kind not in store.RULE_KINDS:
        return _as_style()
    if not kind:
        return _as_style()
    return c


def _repair_invalid_action_rules_once():
    """一次性修掉库里已经存在的「假动作」规则（如 required_action=插话）。"""
    global _rules_repaired
    if _rules_repaired:
        return
    _rules_repaired = True
    try:
        for s in store.list_skills():
            if (s.get("type") or "rule") != "rule":
                continue
            if s.get("kind") not in ("required_action", "banned_action"):
                continue
            vals = s.get("value")
            vals = vals if isinstance(vals, list) else [vals]
            if all(_is_valid_action(v) for v in vals if str(v or "").strip()):
                continue
            store.update_skill(s["id"], {
                "type": "style", "kind": None, "value": None,
                "prompt_hint": s.get("prompt_hint") or s.get("title") or "",
                "source_note": (s.get("source_note") or "") + "（非动作名，已转为风格偏好）",
            })
    except Exception:  # noqa: BLE001
        pass


# 规则库里的这两条旧文案把 `[打字不发]` 的正文说成「内容 | 停留 | 对方插话」，
# 与新语义（正文一律是给观众看的技巧说明）冲突，渲染提示词时统一换成新说法，
# 否则旧规则文案会把模型带偏。
_CANONICAL_HINTS = {
    "min_typing_hold": (
        "整份剧本至少 {value} 处 [打字不发]：正文一律写「给观众看的技巧说明」"
        "（为什么这样聊有效，如「以退为进」「故意否定 引起注意」），"
        "停留写在 `| 0.5`；插话是可选的第三段。"
        "展开的会话里要密集出现（连打好几次、删掉再打）"
    ),
    "min_interjections": (
        "整份剧本至少 {value} 处带「插话」，每个展开的会话至少 3 处；"
        "插话必须是对方真发出来的一句口语，只能回应我已经发出去的上一条消息，"
        "不能写成对 [打字不发] 未发送内容的反应，更不能写成对方的心理活动"
    ),
}


def _skill_text(s: dict) -> str:
    hint = _CANONICAL_HINTS.get(str(s.get("kind") or ""))
    if hint:
        try:
            val = int(float(s.get("value")))
        except (TypeError, ValueError):
            val = s.get("value")
        return hint.format(value=val)
    if str(s.get("kind") or "") == "max_annotations":
        # 旧规则：限制「注释」处数。现在 [打字不发] 正文本来就该是技巧说明、不限处数，
        # 这条规则只保留「[我方打字] 里不许写策略注释」的兜底校验，不再作为提示词条目。
        return ""
    return str(s.get("prompt_hint") or s.get("title") or "").strip()


def _preference_lines(pref) -> list:
    """把 feedback.json 里的自由文本偏好拆成一行一条（只取以 - 开头的条目）。"""
    out = []
    for line in str(pref or "").splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        s = s.lstrip("-").strip()
        if len(s) >= 2:
            out.append(s)
    return out


def skills_prompt_block(skills=None) -> str:
    """把规则库拼成提示词块。

    与旧版「一段自由文本偏好」的区别：规则条目是结构化的、可校验的，
    每条都可能在生成后被 validate_generated_steps 命中并触发定向重写。
    """
    items = skills if skills is not None else load_enabled_skills()
    rules = [s for s in items if (s.get("type") or "rule") == "rule"]
    styles = [s for s in items if (s.get("type") or "rule") != "rule"]
    # 兜底：feedback.json 里还有没入库/没启用的历史偏好时也一并注入，
    # 避免出现「用户写了评价、生成时却一条都没看到」的情况。
    known = {_skill_text(s) for s in items if _skill_text(s)}
    legacy = [t for t in _preference_lines(load_feedback().get("preferences", ""))
              if t not in known]
    if not rules and not styles and not legacy:
        return "（暂无生效规则）"
    lines = []
    if rules:
        lines.append("【必须遵守的硬性规则】（生成结果会被逐条校验，违反哪条就按哪条重写）")
        lines += [f"- {_skill_text(s)}" for s in rules if _skill_text(s)]
    if styles:
        if lines:
            lines.append("")
        lines.append("【创作风格偏好】")
        lines += [f"- {_skill_text(s)}" for s in styles if _skill_text(s)]
    if legacy:
        if lines:
            lines.append("")
        lines.append("【长期创作偏好（历史沉淀，尚未入库，同样要遵守）】")
        lines += [f"- {t}" for t in legacy]
    return "\n".join(lines)


def load_preferences_block() -> str:
    """兼容旧调用：返回「生效规则 + 风格偏好」提示词块。"""
    return skills_prompt_block()


def save_preferences_block(pref: str):
    data = load_feedback()
    data["preferences"] = (pref or "").strip()
    save_feedback(data)


def _rule_preferences() -> str:
    """无大模型时，用规则从高分反馈里提炼偏好块。"""
    data = load_feedback()
    feedback = [f for f in data.get("feedback", []) if isinstance(f, dict)]
    if not feedback:
        return ""
    scored = [f for f in feedback if int(f.get("score", 0)) >= 4]
    if not scored:
        return ""
    lines = []
    seen_text = set()
    for f in scored:
        c = str(f.get("comment", "")).strip()
        if c and c not in seen_text:
            seen_text.add(c)
            lines.append(f"- 用户曾评价（{f.get('score')}星）：{c}")
    if not lines:
        return ""
    return "\n".join([
        "以下是从过去多次生成中，用户给出高分评价后沉淀的创作偏好，尽量遵守：",
        *lines,
    ])


def distill_preferences(api_key: str, model: str = None, base_url: str = None) -> str:
    """把历史高分布 + 留言蒸馏成一段「创作偏好 / 技巧」文本，写回 feedback.json。

    有 Key 用大模型汇总；无 Key 用规则兜底。返回偏好块文本。
    """
    data = load_feedback()
    feedback = [f for f in data.get("feedback", []) if isinstance(f, dict)]
    # 只取高分级与含留言的，避免噪音
    useful = [f for f in feedback if int(f.get("score", 0)) >= 4 or str(f.get("comment", "")).strip()]
    if not useful:
        save_preferences_block("")
        return ""
    if not api_key:
        pref = _rule_preferences()
        save_preferences_block(pref)
        return pref
    try:
        lines = []
        for f in useful[-40:]:
            lines.append(
                f"主题：{str(f.get('brief',''))[:80]} | 评分：{f.get('score')} | 留言：{str(f.get('comment',''))[:120]}")
        user_text = "\n".join(lines)
        system = (
            "你是微信聊天剧本的『创作偏好总结器』。下面是用户对多份已（男追女聊天教学）剧本的评价记录。"
            "请总结成一段【可执行的创作偏好/技巧】清单（每行一条，用 - 开头），"
            "包括：题材方向、人物设定、聊天套路（共情/调动情绪/探知三观/拉高格局/邀约等）、"
            "节奏（停顿/插话/后台消息）、画面元素（表情/图片/链接卡）等维度。"
            "只输出清单，不要解释，不要评论。"
        )
        raw = st.call_deepseek(api_key, system, user_text, model or st.DEFAULT_MODEL, base_url or st.DEFAULT_BASE_URL)
        pref = str(raw).strip()
        # 去掉 markdown 围栏
        pref = re.sub(r"^```(?:text|markdown)?\s*", "", pref)
        pref = re.sub(r"\s*```$", "", pref)
        save_preferences_block(pref)
        return pref
    except Exception:  # noqa: BLE001
        pref = _rule_preferences()
        save_preferences_block(pref)
        return pref


# ============================================================
# 完整性检查（防偷工减料）
# ============================================================

# 明确表示"此处省略 / 自行发挥"的占位符。
# 注意：不要用省略号（……、...、…）当占位——它们在正常口语里表示停顿/迟疑/省略语气
# （如"你真是...""不过……也行"），若误判会把本就完整的剧本反复打回重写（病态自我迭代）。
_PLACEHOLDER_RE = re.compile(
    r"(?:\[省略\]|【省略】|\(省略\)|（省略）|此处省略|以下省略|中间省略|"
    r"省略[了0-9一二三四五六七八九十]+字|省略号|省略内容|"
    r"内容自拟|自行发挥|自行补充|自行添加|待补充|待填充|填充内容|填内容|写内容|"
    r"任意发挥|自由发挥|随便写|随便填|TODO|待定|从略|此处从略)"
)

# 单个/连续 xxx / XXX / xxx，可能被用作占位
_PLACEHOLDER_XXX_RE = re.compile(r"(^|\s)((?:x{2,})|(?:X{2,})|(?:？{2,}))(\s|$|[。，])")


def strip_code_fences(text: str) -> str:
    """去掉 markdown 代码块围栏，避免整体被 ``` 包住。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:text|markdown)?\s*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    return t


def check_completeness(text: str) -> list:
    """检测剧本是否存在"偷工减料"占位/缩略，返回问题清单。

    只报明确的占位与过量省略；自然聊天里出现单个省略号不视为问题（避免误报）。
    """
    issues = []
    text = strip_code_fences(text or "")
    if not text.strip():
        return ["生成结果是空的，疑似大模型未产出内容或全部被省略。"]
    # 占位符（「别让他自由发挥」「不要自行发挥」这类自然否定句不算占位）
    for m in _PLACEHOLDER_RE.finditer(text):
        prev = text[max(0, m.start() - 4):m.start()]
        if re.search(r"(别|不要|不用|不必|禁止|避免|不能)", prev):
            continue
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace("\n", " ")
        issues.append(f"检测到省略/占位：『{m.group(0)}』在「…{ctx}…」附近，请补全真实内容。")
    for m in _PLACEHOLDER_XXX_RE.finditer(text):
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace("\n", " ")
        issues.append(f"检测到占位符：『{m.group(0)}』，请改用具体文字。")
    # 行数过少 / 没有对话
    non_empty = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(non_empty) < 5:
        issues.append(f"剧本行数过少（仅 {len(non_empty)} 行），内容疑似被大幅省略。")
    if not re.search(r"[\[\【]\s*(打开聊天|打开会话|进入聊天)\s*[\]】]", text):
        issues.append("剧本里没有 [打开聊天]，构不成会话场景。")
    return issues


# ============================================================
# 生成结果结构化校验（动作级）
# ============================================================

# 这些动作必须有具体文案/内容
_MESSAGE_ACTIONS = {"我方打字", "对方发消息", "打字不发", "发朋友圈", "评论", "转发消息"}
# 这些动作必须有联系人
_CONTACT_ACTIONS = {"打开聊天", "对方后台发消息", "对方后台发表情"}


def _norm_action(name: str) -> str:
    return st.ACTION_ALIASES.get(name, name)


def _as_str_list(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()]


# 「心理活动 / 解说说」的典型词。这些词本应只作为创作说明，不该出现在消息正文里。
_ANNOTATION_HINTS = (
    "需求感", "冷读", "格局", "博弈", "注意力", "铺垫", "拉高", "共情她", "把话题权",
    "降低她的防备", "情绪到位", "主动权", "自我暴露", "不哄不追问", "需求", "框架",
)

# 「策略注释 / 心理活动」的识别线索：真实聊天话术是对着她说、会出现「你」；
# 而解说式注释常用第三人称或策略名词。用于把「最多 2 处注释」这条规则落到实处。
_STRATEGY_NOUNS = (
    "情绪", "节奏", "话题", "话术", "博弈", "冷读", "格局", "需求", "铺垫",
    "场景", "开场", "理由", "朋友圈", "主动权", "框架", "心态", "氛围",
)
_STRATEGY_IMPERATIVES = ("别问", "别提", "别急", "别把", "不要", "切忌")

# 强注释信号：出现就是「给观众看的解说词」，不可能是发出去的话术。
_STRONG_ANNOTATION = (
    "需求感", "冷读", "格局", "博弈", "主动权", "框架", "话术", "方法论",
    "三观", "自我暴露", "把话题权",
)

# 「给观众看的技巧说明」的识别线索。[打字不发] 的正文按用户要求应该是「为什么这样聊有效」
# 的打法说明（如「以退为进」「故意否定 引起注意」），而不是聊天话术草稿。
_TACTIC_HINTS = (
    "试探", "暗示", "共情", "情绪", "主动权", "框架", "节奏", "铺垫", "话题", "安全感",
    "好奇", "误会", "激将", "以退为进", "反客为主", "否定", "肯定", "认同", "调侃", "施压",
    "压力", "后撤", "立住", "推高", "拉扯", "抛", "丢", "留白", "观察", "复制", "反转",
    "标准答案", "思路", "逻辑", "打法", "套路", "技巧", "尺度", "边界", "需求", "冷读",
    "格局", "博弈", "反差", "转移", "引导", "制造", "加深", "点破", "传递", "台阶",
    "退路", "冷处理", "让步", "女生", "对方", "她", "他", "夸", "探知", "扔", "第一步",
    "第二步", "第三步", "别问", "别急",
)

# 打法的「动词/结构」线索：技巧说明几乎都带这些字，而聊天话术很少带。
# 背景（用户实测）：旧版只认 _TACTIC_HINTS 的词表，像「故意慢半拍 让注意力停在我这」
# 「用一句承诺收尾 把约钉死」「已读不回别追 隔天用图重新开场」这些完全合格的打法说明
# 因为没踩中词表被判成「聊天话术草稿」，26 处里误判 6 处，生成循环为此反复重写。
_TACTIC_VERBS = (
    "让", "用", "把", "先", "再", "别", "留", "故意", "主动", "顺势", "适当", "适度",
    "判断", "决定", "退场", "钩子", "收尾", "开场", "稳住", "埋", "补", "压", "抬",
    "换", "拖", "收", "放", "停", "降温", "示弱", "含糊", "承诺", "钉", "点到", "慢半拍",
)


def _looks_like_tactic_note(content: str) -> bool:
    """判断 [打字不发] 的正文是不是「给观众看的技巧说明」而非聊天话术草稿。

    改成反向判断，避免旧版「没踩中词表就判成话术」的大面积误伤：
      - 命中打法词（词表 + 打法动词）→ 是技巧说明；
      - 否则，只有明显是「对着对方说的话」才判成话术草稿：出现「你」，或整句是个问句/感叹句。
    """
    t = (content or "").strip()
    if not t:
        return False
    if any(w in t for w in _TACTIC_HINTS):
        return True
    if any(w in t for w in _TACTIC_VERBS):
        return True
    if "你" in t:
        return False
    if re.search(r"[?？!！]$", t):
        return False
    return True


def _looks_like_strategy_note(content: str) -> bool:
    """判断一条 [我方打字] 的正文是不是「策略注释/心理活动」而非真实话术。

    早先的写法是「出现 她/他/对方 就算注释」，结果把「问她今天被谁惹了」这类
    正常聊天话术也判成注释，生成完永远过不了校验。现在改成：
      - 命中强信号词（需求感/冷读/格局…）直接算注释；
      - 句子里同时出现「你」「我」= 明显在跟对方说话，不算注释；
      - 其余只有在「第三人称/祈使式」叠加「策略名词」时才判为注释。
    """
    t = (content or "").strip()
    if not t:
        return False
    if any(w in t for w in _STRONG_ANNOTATION):
        return True
    if "你" in t or "我" in t:
        return False
    if any(w in t for w in ("她", "他", "对方")) and any(w in t for w in _STRATEGY_NOUNS):
        return True
    if any(w in t for w in _STRATEGY_IMPERATIVES) and any(w in t for w in _STRATEGY_NOUNS):
        return True
    return False


def _count_history_and_realtime(text: str):
    """统计 (历史块内消息行数, 历史块外实时对白行数)。"""
    hist = 0
    real = 0
    in_hist = False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if re.match(r"^[\[\【]\s*历史会话\s*[\]\】]", s):
            in_hist = True
            continue
        if re.match(r"^[\[\【]\s*历史会话结束\s*[\]\】]", s):
            in_hist = False
            continue
        if in_hist:
            if re.match(r"^[\[\【]\s*会话\s*[\]\】]", s):
                continue
            hist += 1
        else:
            if re.match(r"^[\[\【]\s*(我方打字|打字不发|对方发消息|对方后台发消息)\s*[\]\】]", s):
                real += 1
    return hist, real


def _history_sessions(text: str) -> list:
    """解析 [历史会话] 块，返回 [(会话名, [(说话人, 内容), ...]), ...]。

    用于校验「历史会话要有来有回」：旧版把整块当纯文本，看不出是不是一个人刷屏。
    """
    sessions = []
    cur = None
    in_hist = False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^[\[\【]\s*历史会话\s*[\]\】]", s):
            in_hist = True
            continue
        if re.match(r"^[\[\【]\s*历史会话结束\s*[\]\】]", s):
            in_hist = False
            cur = None
            continue
        if not in_hist:
            continue
        m = re.match(r"^[\[\【]\s*会话\s*[\]\】]\s*(.+)$", s)
        if m:
            cur = (m.group(1).strip(), [])
            sessions.append(cur)
            continue
        m = re.match(r"^([^：:|]{1,16})[：:]\s*(.+)$", s)
        if m and cur is not None:
            cur[1].append((m.group(1).strip(), m.group(2).strip()))
    return sessions


def _max_history_streak(text: str):
    """历史会话里同一人最长连续发了几条，返回 (条数, 是谁)。"""
    best, who = 0, ""
    for _name, msgs in _history_sessions(text):
        run, prev = 0, None
        for speaker, _c in msgs:
            run = run + 1 if speaker == prev else 1
            prev = speaker
            if run > best:
                best, who = run, speaker
    return best, who


def _history_time_gaps(text: str) -> list:
    """统计历史会话内部相邻消息的分钟间隔，返回 [gap, ...]。

    用于检查时间戳是否「机械地每分钟一条」：同一会话里连续两条永远差 1 分钟，
    一眼就是编的。参考写法是同一条分钟内、差两三分钟、偶尔隔十几分钟混着来。
    """
    gaps = []
    for _name, msgs in _history_sessions(text):
        prev = None
        for _speaker, content in msgs:
            m = re.search(r"(\d{1,2}):(\d{2})\s*$", str(content or "").strip())
            cur = (int(m.group(1)) * 60 + int(m.group(2))) if m else None
            if prev is not None and cur is not None:
                gaps.append(cur - prev)
            prev = cur
    return gaps


def _history_one_sided_sessions(text: str) -> list:
    """历史会话里「只有一方说话」的会话名列表。"""
    out = []
    for name, msgs in _history_sessions(text):
        if not msgs:
            continue
        speakers = {w for w, _ in msgs}
        mine = any(w in ("我", "我方") for w in speakers)
        others = any(w not in ("我", "我方") for w in speakers)
        if not (mine and others):
            out.append(name)
    return out


def _history_stats(text: str):
    """历史会话统计，返回 (会话总数, 双方来回的会话数, 「我：」出现的总条数)。

    用户给的标准样本里，9 个会话只有 1 个是双方来回（其余只留对方最后一两句），
    所以「双方有来有回」只该在整块级别要求，不能要求每个会话都一问一答。
    """
    total = 0
    two_sided = 0
    mine_lines = 0
    for _name, msgs in _history_sessions(text):
        total += 1
        speakers = {w for w, _ in msgs}
        mine = any(w in ("我", "我方") for w in speakers)
        others = any(w not in ("我", "我方") for w in speakers)
        if mine and others:
            two_sided += 1
        mine_lines += sum(1 for w, _ in msgs if w in ("我", "我方"))
    return total, two_sided, mine_lines


def _count_interjections(steps: list) -> int:
    """统计带「插话」参数的动作数（打字不发/我方打字 的第三段）。"""
    n = 0
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        if _norm_action(s.get("action")) in ("打字不发", "我方打字"):
            p = s.get("params") or {}
            if str(p.get("插话") or "").strip():
                n += 1
    return n


def _count_typing_hold(steps: list) -> int:
    """统计 [打字不发] 动作的处数（内容停在输入框、不发送）。"""
    return sum(1 for s in (steps or [])
               if isinstance(s, dict) and _norm_action(s.get("action")) == "打字不发")


def _norm_text(s) -> str:
    """去掉空白与常见标点，用于判断两句聊天话术是不是「同一句」。"""
    return re.sub(r"[\s，。、！？!?~～…·,.;；:：\"'“”‘’（）()【】\[\]—\-_]+", "", str(s or ""))


def _typing_send_repeats(steps: list) -> list:
    """找出「[打字不发] 的内容又在随后的 [我方打字] 里原样发了一遍」的地方。

    参考剧本的写法：[打字不发] 放策略注释/不要的半句话 -> [删除文字] -1 清空 ->
    [我方打字] 写完整的真实话术，两者内容不同。若相同（或前者是后者的前缀），
    观众会看到同一句话在输入框里出现两次。
    返回 [(打字不发原文, 我方打字原文), ...]。
    """
    out = []
    acts = [s for s in (steps or []) if isinstance(s, dict)]
    for i, s in enumerate(acts):
        if _norm_action(s.get("action")) != "打字不发":
            continue
        held_raw = str((s.get("params") or {}).get("内容") or "").strip()
        held = _norm_text(held_raw)
        if len(held) < 2:
            continue
        for j in range(i + 1, min(i + 4, len(acts))):
            a = _norm_action(acts[j].get("action"))
            if a in ("删除文字", "等待", "对方正在输入"):
                continue
            if a == "我方打字":
                sent_raw = str((acts[j].get("params") or {}).get("内容") or "").strip()
                sent = _norm_text(sent_raw)
                if sent and (sent == held or (len(held) >= 6 and sent.startswith(held))):
                    out.append((held_raw, sent_raw))
            break
    return out


def _interjection_echoes(steps: list) -> list:
    """找出「插话说过的话，随后又用一条 [对方发消息] 重复了一遍」的地方。

    插话本身就是对方发出去的一条消息；再单独发一条同样的内容，观众会看到对方把
    同一句话说了两遍。返回 [插话原文, ...]。
    """
    out = []
    acts = [s for s in (steps or []) if isinstance(s, dict)]
    for i, s in enumerate(acts):
        if _norm_action(s.get("action")) not in ("打字不发", "我方打字"):
            continue
        raw = str((s.get("params") or {}).get("插话") or "").strip()
        if not raw:
            continue
        ij = [_norm_text(x) for x in re.split(r"[；;\n]+", raw) if _norm_text(x)]
        if not ij:
            continue
        for j in range(i + 1, min(i + 5, len(acts))):
            a = _norm_action(acts[j].get("action"))
            if a in ("删除文字", "等待", "对方正在输入"):
                continue
            if a == "对方发消息":
                got = _norm_text((acts[j].get("params") or {}).get("内容"))
                if got and got in ij:
                    out.append(raw)
            if a not in ("打字不发", "我方打字"):
                break
    return out


def _count_people(text: str) -> int:
    """统计「真正展开聊天的对象」数量（[打开聊天] 的目标）。

    旧版把 [会话] 里所有历史联系人都算进来，而「历史会话要铺满屏幕」与
    「出场人物不超过 3 人」本就矛盾：9 个历史会话会恒判超员，
    导致每次生成都被打回重写。这里只数真正打开聊天的人。
    """
    names = set()
    for n in re.findall(r"\[打开聊天\]\s*([^\n\r|]+)", text or ""):
        n = n.strip()
        if n and n not in ("我", "自己", "聊天主页", "主页", "返回主页"):
            names.add(n)
    return len(names)


def _has_opening_image(steps: list, text: str) -> bool:
    for ln in (text or "").splitlines()[:25]:
        if "[图片]" in ln or re.search(r"\[(发送图片|对方发图片)\]", ln):
            return True
    for s in (steps or [])[:6]:
        if isinstance(s, dict) and _norm_action(s.get("action")) in ("发送图片", "对方发图片"):
            return True
    return False


# ============================================================
# 素材引用 / 节奏 的校验辅助
# ------------------------------------------------------------
# 用户实测反馈（一份真实剧本暴露的写法）：
#   1) 图片写成完整文件名——`[对方发图片] /images/avatar/好显身材的连衣裙__1_Missyaa_
#      来自小红书网页版_20260831_185446_546.jpg`；或写成图库里根本没有的描述（「洱海的日落」），
#      运行时破图、配图面板也找不到；
#   2) 表情写成「猫咪捂脸」「柴犬敲木鱼」这类图库里不存在的名字，运行时全回落成同一张默认表情；
#      并且同一个表情反复用（害羞猫咪 3 次）；
#   3) 每发一条消息就 `[等待] 0.3` 跟一个等待，50 处等待把节奏拖成节拍器；
#   4) 严格一问一答（交替率 0.81），没有一方连发。
# 下面这些函数把「引用怎么写」「节奏怎么走」变成可校验的口径。
# ============================================================

_ASSET_RAW_RE = re.compile(r"[/\\]|\.(?:jpe?g|png|gif|webp|bmp)\s*$|_20\d{6}[_-]\d{6}", re.I)
_ASSET_SOURCE_RE = re.compile(r"来自小红书|网页版|comfyui|wechat|微信", re.I)
_EMOJI_ACTIONS = ("发送表情", "对方表情", "对方后台发表情")
_IMAGE_ACTIONS = ("发送图片", "对方发图片")


def _realtime_asset_refs(steps: list):
    """实时步骤里所有图片/表情引用，返回 [(动作名, 引用文本, 'emoji'|'image')]。

    只看实时动作（[编辑主页] 里的历史消息不在此列）：历史块里的图片只是列表预览文本，
    实时动作里的引用才是运行时要真渲染成图片的。
    """
    out = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in _EMOJI_ACTIONS:
            ref = str(p.get("表情") or p.get("图片") or "").strip()
            if ref:
                out.append((act, ref, "emoji"))
        elif act in _IMAGE_ACTIONS:
            ref = str(p.get("图片") or "").strip()
            if not ref:
                # `[图片] 好显身材的连衣裙` 这种写在消息正文里的写法，解析后描述留在「内容」里、
                # 图片为空（等配图面板补图）。这里把「像素材名」的短描述也纳入校验，
                # 否则「洱海的日落」这种图库里没有的描述会绕过校验，到配图面板才暴露。
                desc = str(p.get("内容") or "").strip()
                if re.fullmatch(r"[\u4e00-\u9fff]{2,14}", desc):
                    ref = desc
            if ref:
                out.append((act, ref, "image"))
    return out


def _asset_ref_issue(ref: str) -> str:
    """引用写成文件名/路径/来源后缀时返回说明，否则返回空串。"""
    if not ref:
        return ""
    if _ASSET_RAW_RE.search(ref):
        return "写成了文件名/路径（含扩展名或时间戳）"
    if _ASSET_SOURCE_RE.search(ref):
        return "带上了「来自小红书 / 网页版」这类来源后缀"
    return ""


def _asset_ref_resolvable(ref: str) -> bool:
    """引用能否解析到真实图片（短名 / /images/ 路径 / 外链）。"""
    ref = (ref or "").strip()
    if not ref:
        return True
    if ref.startswith("http://") or ref.startswith("https://"):
        return True
    try:
        import main                                     # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return True                                     # 取不到图库时不要误判
    if ref.startswith("/images/"):
        return bool(main._emoji_url_valid(ref))
    return bool(main._lookup_emoji_file(ref))


def _emoji_repeat_stats(steps: list):
    """返回 (不同表情数, 最高重复次数, 重复最多的表情名)。"""
    refs = [ref for _act, ref, kind in _realtime_asset_refs(steps) if kind == "emoji"]
    if not refs:
        return 0, 0, ""
    counter = {}
    for r in refs:
        counter[r] = counter.get(r, 0) + 1
    name = max(counter, key=lambda k: counter[k])
    return len(counter), counter[name], name


def _wait_beat_ratio(steps: list):
    """返回 (我方消息数, 紧跟着 [等待] 的我方消息数)。"""
    seq = [s for s in (steps or []) if isinstance(s, dict)]
    mine = followed = 0
    for i, s in enumerate(seq):
        if _norm_action(s.get("action")) != "我方打字":
            continue
        mine += 1
        if i + 1 < len(seq) and _norm_action(seq[i + 1].get("action")) == "等待":
            followed += 1
    return mine, followed


def _dialogue_runs(steps: list):
    """返回 (对白条数, 最长连发, 交替率)。交替率越高越像「我一条、对方一条」的朗读。"""
    seq = []
    for s in steps or []:
        act = _norm_action(s.get("action"))
        if act in ("我方打字", "发送表情", "我方发链接", "我方发图片"):
            seq.append("me")
        elif act in ("对方发消息", "对方表情", "对方发图片", "对方后台发消息", "对方后台发表情"):
            seq.append("peer")
    if not seq:
        return 0, 0, 0.0
    max_run = run = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    alt = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    ratio = alt / (len(seq) - 1) if len(seq) > 1 else 0.0
    return len(seq), max_run, round(ratio, 3)


def _collect_messages(steps: list):
    """提取所有「会作为消息上屏」的内容，返回 [(动作名, 内容)]。"""
    out = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in ("我方打字", "打字不发", "对方发消息", "评论", "发朋友圈", "转发消息"):
            content = str(p.get("内容") or p.get("文案") or "").strip()
            if content:
                out.append((act, content))
    return out


def _rule_issues(steps: list, skills: list, text: str):
    """按规则库校验生成结果，返回 (问题清单, 被违反的规则 id 列表)。"""
    issues = []
    violated = []
    _seen_issue_msgs = set()
    action_set = {_norm_action(s.get("action")) for s in (steps or []) if isinstance(s, dict)}
    messages = _collect_messages(steps)
    sessions = len(re.findall(r"\[会话\]", text or ""))
    hist_lines, real_lines = _count_history_and_realtime(text)

    def _need_int(value, default=0):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    for sk in skills or []:
        if not isinstance(sk, dict):
            continue
        if (sk.get("type") or "rule") != "rule":
            continue
        kind = sk.get("kind")
        val = sk.get("value")
        stitle = str(sk.get("title") or sk.get("prompt_hint") or "规则")
        hit_msgs = []
        if kind == "banned_action":
            for a in _as_str_list(val):
                if _norm_action(a) in action_set:
                    hit_msgs.append("出现了禁用动作 [%s]" % a)
        elif kind == "required_action":
            for a in _as_str_list(val):
                if _norm_action(a) not in action_set:
                    hit_msgs.append("缺少必需动作 [%s]" % a)
        elif kind == "min_sessions":
            need = _need_int(val)
            if sessions < need:
                hit_msgs.append("会话数只有 %d，少于要求的 %d" % (sessions, need))
        elif kind == "min_history_messages":
            need = _need_int(val)
            if hist_lines < need:
                hit_msgs.append("历史会话消息只有 %d 条，少于要求的 %d" % (hist_lines, need))
        elif kind == "min_realtime_lines":
            need = _need_int(val)
            if real_lines < need:
                hit_msgs.append("实时对白只有 %d 条，少于要求的 %d" % (real_lines, need))
        elif kind == "max_message_chars":
            need = _need_int(val)
            for act, content in messages:
                # 只约束我方发出的话术；对方/历史消息长短不影响「我方言简意赅」的诉求，
                # 否则会把自然的对方消息也打回重写，造成无谓的反复迭代。
                if act not in ("我方打字", "打字不发"):
                    continue
                if len(content) > need:
                    hit_msgs.append("【%s】内容过长（%d 字，上限 %d）：%s…" % (act, len(content), need, content[:18]))
                    break
        elif kind == "forbid_text":
            for w in _as_str_list(val):
                for act, content in messages:
                    if w in content:
                        hit_msgs.append("【%s】出现禁止词「%s」：%s…" % (act, w, content[:18]))
                        break
                if hit_msgs:
                    break
        elif kind == "forbid_annotation_as_message":
            # [打字不发] 现在按用户要求就是「给观众看的技巧说明」，不算违规；
            # 只有真的会发出去的 [我方打字] 里出现心理活动/解说才是硬伤。
            for act, content in messages:
                if act == "我方打字" and any(h in content for h in _ANNOTATION_HINTS):
                    hit_msgs.append("把心理活动/解说当成消息内容了：%s…" % content[:24])
                    break
        elif kind == "opening_image":
            if not _has_opening_image(steps, text):
                hit_msgs.append("开头没有图片")
        elif kind == "max_people":
            need = _need_int(val)
            people = _count_people(text)
            if need and people > need:
                hit_msgs.append("出场人物 %d 人，超过上限 %d" % (people, need))
        elif kind == "max_annotations":
            # 用户明确：[打字不发] 的正文就是给观众看的技巧说明，不再限制处数；
            # 这条规则只用来兜住「[我方打字] 里写策略注释」这个硬伤（会真的发出去）。
            typed = [c for act, c in messages
                     if act == "我方打字" and _looks_like_strategy_note(c)]
            if typed:
                hit_msgs.append("把策略注释/心理活动当成消息发出去了 %d 处（例：%s）"
                                % (len(typed), "；".join(c[:16] for c in typed[:3])))
        elif kind == "history_two_sided":
            # 只要求「整块里至少有一个会话是双方来回」，不要求每个会话都一问一答：
            # 用户给的标准样本就是 9 个会话里只有 1 个是双方来回，其余只留对方最后一两句。
            need = 1 if isinstance(val, bool) or val is None else max(1, _need_int(val, 1))
            total, two_sided, mine_lines = _history_stats(text)
            if total and mine_lines == 0:
                hit_msgs.append("历史会话里完全没有「我：」的回复"
                                "（至少要有一个会话是「对方说 → 我回 → 对方再说」）")
            elif total and two_sided < need:
                hit_msgs.append("历史会话里只有 %d 个会话是双方来回，至少要有 %d 个"
                                "（其余会话可以只留对方最后一两句，不必每个都一问一答）"
                                % (two_sided, need))
        elif kind == "max_history_streak":
            need = _need_int(val, 3)
            streak, who = _max_history_streak(text)
            if streak > need:
                hit_msgs.append("历史会话里「%s」连续发了 %d 条，超过上限 %d"
                                "（历史要有来有回，不要一个人刷屏）" % (who, streak, need))
        elif kind == "min_interjections":
            need = _need_int(val, 2)
            got = _count_interjections(steps)
            if got < need:
                hit_msgs.append("带「插话」的动作只有 %d 处，少于要求的 %d"
                                "（格式：[打字不发] 技巧说明 | 停留 | 对方插话；"
                                "插话只能是对方真发出来、回应我已发出消息的一句口语）"
                                % (got, need))
        elif kind == "min_typing_hold":
            need = _need_int(val, 2)
            got = _count_typing_hold(steps)
            if got < need:
                hit_msgs.append("[打字不发] 只有 %d 处，少于要求的 %d"
                                "（写法：[打字不发] 技巧说明 | 停留；"
                                "正文写「为什么这样聊有效」，不是聊天话术）"
                                % (got, need))
        elif kind == "asset_ref_plain":
            for act, ref, _k in _realtime_asset_refs(steps):
                why = _asset_ref_issue(ref)
                if why:
                    hit_msgs.append("【%s】素材引用%s：%s…"
                                    "（只写图库里的短名，如「好显身材的连衣裙」「害羞猫咪」；"
                                    "不要写文件路径、扩展名、时间戳或来源后缀）"
                                    % (act, why, ref[:26]))
                    break
        elif kind == "asset_ref_exists":
            for act, ref, _k in _realtime_asset_refs(steps):
                if not _asset_ref_resolvable(ref):
                    hit_msgs.append("【%s】引用的素材在图片库里找不到：%s…"
                                    "（运行时会破图或回落成同一张默认表情；"
                                    "请改成【可用素材】清单里的名字）" % (act, ref[:26]))
                    break
        elif kind == "max_same_emoji":
            need = _need_int(val, 2)
            _distinct, top, top_name = _emoji_repeat_stats(steps)
            if top > need:
                hit_msgs.append("同一个表情「%s」用了 %d 次，超过上限 %d："
                                "表情要换着来，不要整段反复发同一张"
                                % (top_name, top, need))
        elif kind == "max_wait_ratio":
            try:
                cap = float(val)
            except (TypeError, ValueError):
                cap = 0.6
            if cap <= 0:
                cap = 0.6
            mine, followed = _wait_beat_ratio(steps)
            if mine >= 8 and followed * 1.0 / mine > cap:
                hit_msgs.append("[等待] 被当成每句话之间的固定节拍：%d 条我方消息里 %d 条后面紧跟 [等待]"
                                "（%.0f%%，上限 %.0f%%）：等待只留在真正要停一下的地方，"
                                "节奏靠连发 / 打字不发 / 插话，而不是每句都跟一个 0.3 秒"
                                % (mine, followed, followed * 100.0 / mine, cap * 100))
        elif kind == "min_burst":
            need = _need_int(val, 2)
            total, max_run, ratio = _dialogue_runs(steps)
            if total >= 12 and max_run < need:
                hit_msgs.append("实时对白 %d 条却没有任何一方连发（最长连发 %d 条，至少要 %d 条）："
                                "不要严格一问一答，允许一方连着发 2~3 条" % (total, max_run, need))
            elif total >= 12 and ratio > 0.75:
                hit_msgs.append("实时对白交替率 %.2f 偏高（上限 0.75）：几乎每条都是「我一条、对方一条」，"
                                "像朗读脚本；要有一段一方连发 2~3 条。" % ratio)
        if hit_msgs:
            violated.append(str(sk.get("id") or ""))
            for m in hit_msgs[:3]:
                # 同一条问题可能被多条规则同时命中（如两条都写「话要短」），
                # 去重避免把重复的问题堆进重写提示词里。
                if m in _seen_issue_msgs:
                    continue
                _seen_issue_msgs.add(m)
                issues.append("%s（规则：%s）" % (m, stitle))
    return issues, violated


def validate_generated_steps(steps: list, skills=None, text: str = ""):
    """对归一后的步骤做结构化校验。

    返回 (问题清单, 被违反的规则 id 列表)：
      - 问题清单为空 = 通过；
      - 规则 id 列表用于把「哪条规则被命中」回写到规则库的命中次数，
        并让下一轮 critique 定向修复。
    """
    if not steps:
        return (["生成结果没有可执行步骤，请重新生成。"], [])
    issues = []
    has_chat = any(isinstance(s, dict) and _norm_action(s.get("action")) == "打开聊天" for s in steps)
    if not has_chat:
        issues.append("剧本缺少 [打开聊天]，无法构成一段可运行的聊天场景。")

    msg_count = 0
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in _MESSAGE_ACTIONS:
            msg_count += 1
            content = str(p.get("内容") or p.get("文案") or "").strip()
            if not content:
                issues.append(f"【{act}】消息内容为空，不能只写指令不写具体话术。")
            elif re.fullmatch(r"[.。，,、…·\-—_*~！!？?]+", content):
                # 「哦」「好」「嗯」这类单字是真实聊天里正常的短回复，不能算占位；
                # 只有整条都是标点/省略号才判定为没写内容。
                issues.append(f"【{act}】消息内容疑似占位（『{content}』），请写具体话术。")
        if act in _CONTACT_ACTIONS:
            if not str(p.get("联系人") or "").strip():
                issues.append(f"【{act}】缺少联系人，无法定位会话。")
        if act in ("等待", "对方正在输入"):
            sec = p.get("秒数", 1)
            try:
                if float(sec) <= 0:
                    issues.append(f"【{act}】时长必须大于 0（当前 {sec}）。")
            except (TypeError, ValueError):
                issues.append(f"【{act}】时长不是有效数字（{sec}）。")
        if act == "打字不发":
            hold = p.get("停留")
            hold = hold if not isinstance(hold, list) else (hold[0] if hold else None)
            if hold is not None:
                try:
                    if float(hold) < 0:
                        issues.append("【打字不发】停留秒数不能为负。")
                except (TypeError, ValueError):
                    pass
    if 0 < msg_count < 3:
        issues.append(f"对话消息过少（仅 {msg_count} 条），请按参考剧本补充完整聊天过程，不要省略。")

    # ---- 历史会话「像微信列表预览」的硬性检查 ----
    # 用户给的标准样本：9 个会话只有 1 个带「我：」的回复，其余只留对方最后 1~2 条。
    # 旧提示词要求「每个会话都一问一答」，导致模型把历史块写成 10 个会话全部双方来回，
    # 看起来不像微信列表。这里按规则数值（没配规则时默认 2）兜底校验。
    hist_total, hist_two_sided, _hist_mine = _history_stats(text)
    if hist_total >= 3:
        cap = int(rule_numbers(skills or []).get("max_history_two_sided", 2) or 2)
        if hist_two_sided > cap:
            issues.append("历史会话里有 %d 个会话写了「我：」的回复，超过上限 %d"
                          "（要像微信列表预览：只留 1 个会话带我方回复，"
                          "其余只留对方最后 1~2 条，不要每个会话都一问一答）"
                          % (hist_two_sided, cap))

    # ---- 时间戳不能机械地「每分钟一条」----
    # 用户反馈：历史会话里相邻两条消息永远差 1 分钟（21:47 / 21:48 / 21:49），一眼假。
    # 只统计相邻且都带时间的消息，避免中间夹了没时间的消息造成误判。
    gaps = _history_time_gaps(text)
    if len(gaps) >= 3:
        ones = sum(1 for g in gaps if g == 1)
        if ones >= max(3, int(len(gaps) * 0.8)):
            issues.append("历史会话的时间戳几乎是机械的每分钟一条（%d 个相邻间隔里 %d 个正好差 1 分钟）："
                          "同一会话内部要混着来——同一条分钟内、差 2~3 分钟、偶尔隔十几分钟，"
                          "不要每条都 +1 分钟。" % (len(gaps), ones))

    # ---- 篇幅上限：整份剧本的实时指令步数 ----
    # 用户反馈「别 300 多步，控制在 200 步左右」。打字不发要够密，但不能靠无限拉长来堆。
    step_cap = int(rule_numbers(skills or []).get("max_script_steps", 0) or 0)
    if step_cap and len(steps) > step_cap:
        issues.append("整份剧本 %d 步，超过上限 %d 步：把篇幅压到 %d 步左右——"
                      "砍掉重复的来回和多余的 [对方正在输入]/[等待] 空转，"
                      "保留必要的 [打字不发] 节奏，而不是把话术删成摘要。"
                      % (len(steps), step_cap, step_cap))

    # ---- 「打字不发 / 插话」写法合理性检查 ----
    # 参考剧本的写法：[打字不发] 放策略注释或不要的半句话 -> [删除文字] -1 清空 ->
    # [我方打字] 发不同的真实话术。生成时模型常把同一句话打两遍，或让对方回答
    # 还没发出去的内容，或把插话又单独重发一遍——这里逐条兜底。
    for held, sent in _typing_send_repeats(steps):
        issues.append("【打字不发】的内容又被原样发了一遍（『%s』→『%s』）："
                      "打字不发只放策略注释或不要的半句话，随后的 [我方打字] "
                      "必须写不同的话术。" % (held[:14], sent[:14]))
    for echo in _interjection_echoes(steps):
        issues.append("插话『%s』说完又用一条 [对方发消息] 重复了一遍："
                      "插话本身就是对方的消息，不要再用独立消息重发。" % echo[:18])

    # ---- [打字不发] 的正文应该是「给观众看的技巧说明」----
    # 用户明确：打字不发是给观众看的，要写「为什么这样聊」的技巧，不是聊天话术草稿，
    # 也不是对方的心理活动。这里逐条统计，写成话术的直接点名重写。
    held_contents = [str((s.get("params") or {}).get("内容") or "").strip()
                     for s in (steps or [])
                     if isinstance(s, dict) and _norm_action(s.get("action")) == "打字不发"]
    held_contents = [c for c in held_contents if c]
    if len(held_contents) >= 4:
        bad = [c for c in held_contents if not _looks_like_tactic_note(c)]
        if len(bad) > max(1, len(held_contents) * 0.2):
            issues.append("[打字不发] 有 %d/%d 处写成了聊天话术草稿而不是给观众看的技巧说明"
                          "（例：%s）：[打字不发] 的正文一律写「为什么这样聊有效」的打法"
                          "（如「以退为进」「故意否定 引起注意」「把选择权丢给她」），"
                          "不是马上要发出去的话，也不是对方的心理活动。"
                          % (len(bad), len(held_contents),
                             "；".join(c[:12] for c in bad[:5])))

    # ---- 规则库校验（评价沉淀出的硬性规则）----
    rule_issues, violated = _rule_issues(steps, skills or [], text)
    issues += rule_issues
    return (issues, violated)


# ============================================================
# 规则数值 -> 写作规范块
# ------------------------------------------------------------
# 用户反馈的两个硬伤（历史会话写法、插话格式从没出现），根因是：
#   1) 旧提示词把历史会话要求成「每个会话都一问一答」，生成出来 10 个会话全部双方来回，
#      不像微信列表；用户给的标准样本是 9 个会话只有 1 个带「我：」的回复；
#   2) 插话写法藏在第 5 条要求的括号里，没有独立小节，也没有任何规则去校验。
# 这里把「历史会话怎么写 / 插话怎么写」做成独立规范块，数值直接取自规则库，
# 保证「提示词要求的」与「生成后校验的」永远是同一套数字。
# ============================================================

_RULE_NUM_DEFAULTS = {
    "max_history_streak": 2,      # 历史会话里同一人最多连续几条
    "max_history_two_sided": 2,   # 历史会话里最多几个会话带「我：」的回复
    "min_interjections": 2,       # 至少几处插话
    "min_typing_hold": 2,         # 至少几处「打字不发」
    "max_script_steps": 200,      # 实时指令步数上限（0=不限制）
    "max_annotations": 2,         # 策略注释最多几处
    "max_same_emoji": 2,          # 同一个表情最多重复几次
    "max_wait_ratio": 0.6,        # 紧跟 [等待] 的我方消息占比上限
    "min_burst": 2,               # 至少有一方连发几条
}

# 这几个 kind 的值是小数，不能像其它规则那样取整。
_RULE_FLOAT_KINDS = {"max_wait_ratio"}


def rule_numbers(skills=None) -> dict:
    """从规则库读出这几项的数值；没配规则就用默认值。"""
    out = dict(_RULE_NUM_DEFAULTS)
    out["history_two_sided"] = True
    for s in skills or []:
        if not isinstance(s, dict) or (s.get("type") or "rule") != "rule":
            continue
        kind = s.get("kind")
        if kind in _RULE_NUM_DEFAULTS:
            try:
                num = float(s.get("value"))
            except (TypeError, ValueError):
                continue
            if num > 0:
                out[kind] = num if kind in _RULE_FLOAT_KINDS else int(num)
        elif kind == "history_two_sided":
            out["history_two_sided"] = bool(s.get("value"))
    return out


# ============================================================
# 可用素材白名单（图片 / 表情）
# ------------------------------------------------------------
# 用户实测反馈（一份真实剧本）：图片写成「洱海的日落」「试衣间试裙子的自拍」，
# 图库里根本没有对应图，配图面板找不到、运行时渲染成破图；表情写成「柴犬敲木鱼」
# 「猫咪捂脸」「傲娇」「抱拳」——这些只是图片库里的展示标签，文件名里没有这些字，
# 运行时全部回落成同一张默认表情。
# 根因：提示词从没告诉模型「图库里到底有什么」。这里在生成前把「文件名能命中」的
# 可用关键词现算出来写进提示词，并配套可校验规则（asset_ref_plain / asset_ref_exists），
# 做到「提示词只让写真实存在的素材 + 生成后被校验打回」。
# ============================================================

_ASSET_TS_RE = re.compile(r"_\d{8}[_-]\d{6}(?:_\d{3})?$")
# 只丢弃「名字本身」带这些字样的候选（不整文件丢弃，否则「好显身材的连衣裙__1_…来自小红书…」
# 这种带来源后缀的好图会被误杀）。
_ASSET_SKIP_HINTS = ("来自小红书", "微信", "wechat", "img_", "image_", "view1", "comfyui",
                     "cartoon", "qrcode", "url-", "welcome", "launchimage", "聊天记录",
                     "截图", "封面", "头像")
_ASSET_STICKER_HINTS = ("表情包", "猫咪", "柴犬", "狗", "牛", "仓鼠", "吃惊", "没眼看",
                        "毁灭吧", "歪头", "木鱼", "鸟都不鸟你", "赵本山", "抱拳", "捂脸", "泪")
_ASSET_SEXY_HINTS = ("自拍", "美腿", "连衣裙", "性感", "御", "高跟鞋", "沙发", "健身",
                     "喝酒", "穿", "腿", "背影", "相抱")
_ASSET_TEACH_HINTS = ("教学", "教程", "素材", "技巧", "案例", "脱单")

_ASSET_CACHE = {"at": 0.0, "data": None}


def _asset_whitelist():
    """扫描图片库，返回 (表情包关键词, 女生图关键词, 教学图关键词)。

    只保留「写成剧本关键词后能被 main._lookup_emoji_file 命中」的名字，
    因此这些名字运行时一定显示成真图，不会破图、也不会回落成默认表情。
    结果缓存 60 秒，避免每次拼提示词都全量扫目录。
    """
    import time
    now = time.time()
    if _ASSET_CACHE["data"] is not None and now - _ASSET_CACHE["at"] < 60:
        return _ASSET_CACHE["data"]
    result = ([], [], [])
    try:
        import main                                     # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        _ASSET_CACHE.update(at=now, data=result)
        return result
    labels = {}
    try:
        with open(os.path.join(main.FRONTEND_DIR, "public", "images", "_gallery_meta.json"),
                  "r", encoding="utf-8") as fh:
            labels = json.load(fh) or {}
    except (OSError, ValueError):
        labels = {}
    stems = []                              # 所有图片文件名（去扩展名、小写），用于快速判断关键词能否命中
    cands = []
    for d in getattr(main, "_IMAGE_SEARCH_DIRS", []) or []:
        if not os.path.isdir(d):
            continue
        folder = os.path.basename(os.path.normpath(d))
        try:
            fns = sorted(os.listdir(d))
        except OSError:
            continue
        for fn in fns:
            if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
                continue
            stem = os.path.splitext(fn)[0]
            stems.append(stem.lower())
            raw = [_ASSET_TS_RE.sub("", stem.split("__")[0])]
            raw += [_ASSET_TS_RE.sub("", p) for p in stem.split("_")]
            rel = (folder + "/" + fn) if folder not in ("images", "") else fn
            lab = labels.get(rel)
            if lab:
                raw.append(str(lab))
            for c in raw:
                c = (c or "").strip()
                if not (2 <= len(c) <= 14) or c == "表情包":
                    continue
                if not re.fullmatch(r"[\u4e00-\u9fff]+", c):
                    continue
                if any(h in c.lower() for h in _ASSET_SKIP_HINTS):
                    continue
                if any(c == s or c in s or s in c for s in stems):
                    cands.append(c)
    names = set(cands)
    # 复核一遍：确认每个名字真的能被运行时解析到（与 main._lookup_emoji_file 完全一致）
    names = {n for n in names if main._lookup_emoji_file(n)}
    sticker, sexy, teach = [], [], []
    for n in sorted(names):
        if any(h in n for h in _ASSET_TEACH_HINTS):
            teach.append(n)
        elif any(h in n for h in _ASSET_STICKER_HINTS):
            sticker.append(n)
        elif any(h in n for h in _ASSET_SEXY_HINTS):
            sexy.append(n)
    result = (sticker, sexy, teach)
    _ASSET_CACHE.update(at=now, data=result)
    return result


def _asset_block() -> str:
    """把可用素材白名单拼成提示词块；清单为空时退回一句通用要求。"""
    sticker, sexy, teach = _asset_whitelist()
    if not (sticker or sexy or teach):
        return ("【可用素材】写图片/表情时只能引用图片库里真实存在的图：先在「📚 图片库」里"
                "确认有对应文件，再照它的文件名/关键词写，不要自创描述。")
    lines = ["【可用素材 —— 写图片 / 表情只能从下面这些名字里挑】",
             "（这些是图片库里「写进剧本就能命中真图」的关键词；写清单外的名字，运行时会破图"
             "或变成同一张默认表情，配图面板也找不到对应图）"]
    if sticker:
        lines.append("- 表情包（[发送表情] / [对方表情] 用）：" + "、".join(sticker))
    if sexy:
        lines.append("- 对方女生发的图（[图片] / [对方发图片] 用，一律选这类性感/身材/穿搭图）："
                     + "、".join(sexy))
    if teach:
        lines.append("- 我方发图（只有给「学员/粉丝」类会话才发图，用教学类图）：" + "、".join(teach))
    return "\n".join(lines)


def writing_spec_block(skills=None) -> str:
    """生成「剧本书写规范」提示词块：历史会话格式 + 插话格式 + 特殊消息写法。

    历史会话的目标风格（来自用户给的标准样本）：
      - 像微信列表预览：绝大多数会话只留对方最后 1~2 条、不写「我：」；
      - 整块里只有 1 个（最多 max_history_two_sided 个）会话带「我：」的回复；
      - 按最后一条消息时间从新到旧排列，会话内部时间递增；
      - 每条都要有钩子（悬念/暧昧/八卦/具体细节），不要「在吗/吃了吗」这类废话；
      - 同一个人不要连发一大堆，时间标注错落。
    """
    nums = rule_numbers(skills)
    streak = nums["max_history_streak"]
    two_sided_max = nums["max_history_two_sided"]
    interjections = nums["min_interjections"]
    typing_holds = nums["min_typing_hold"]
    max_steps = nums["max_script_steps"]
    return f"""A. 一行一条指令，格式 `[动作名] 参数`；参数里的多段用「|」分隔（停留 / 插话 / 时间）。
   【篇幅】整份剧本的实时指令（历史块以外）控制在 {max_steps} 步以内，含 [打字不发]/[删除文字]/[对方正在输入] 等所有指令行；节奏要密但不要靠无限拉长来堆，宁可用同一句话拆成几次打字/删改，也不要多开一个来回。
B. 【历史会话块】只放「已经发生过」的消息，用来把聊天列表铺满。目标是「微信列表预览」的样子（注意说话人冒号）：
   ```
   [历史会话]
   [会话] susu
   susu：那我先走了 | 23:21
   susu：好不想啊
   我：哈哈，很快还会见
   susu：没完没了加班真的好累啊 | 19:21
   susu：[图片] 视频缩略图：女生的腿
   [会话] 粉丝 军
   粉丝 军：[对方发链接] 聊天案例解析（必看） | 课程封面图 | 恋爱技巧 | 19:19
   [会话] 宝宝
   宝宝：小狗项圈给你买一个 | 19:18
   宝宝：我觉得我们发展太快了 | 19:31
   宝宝：[图片] 风景照
   [会话] SUM
   SUM：我通过了你的朋友验证请求，现在我们可以开始聊天了 | 19:18
   [会话] 芝士栗子
   芝士栗子：鸡要八毛什么意思 | 19:17
   [会话] 不要放糖
   不要放糖：那胖胖的你不喜欢吗 | 19:16
   [会话] 一粥困八天（暧昧期）
   一粥困八天（暧昧期）：泰国果冻干嘛的 | 19:15
   [会话] 绿叶
   绿叶：这个还有味道的？ | 19:14
   [会话] 糯米冻
   糯米冻：你牵着那个妹妹是谁 | 19:10
   [历史会话结束]
   ```
   - 【绝大多数会话只有对方在说】上面 9 个会话里只有 susu 一个带「我：」的回复，其余 8 个只留对方最后 1~2 条、
     不写「我：」。整块里带「我：」的会话至少 1 个、最多 {two_sided_max} 个，而且我方回复要夹在对方消息中间
     （像真聊过），不要每个会话都写成「对方说 → 我回 → 对方再说」的一问一答，那不像微信列表。
   - 【顺序】会话按最后一条消息的时间从新到旧往下排（微信列表顺序）；同一个会话内部，时间从上到下递增。
   - 每个 [会话] 一般写 1~2 条，只有要真正展开的那 1~2 个会话才多写几条（最多 3~5 条）。
   - 历史会话里同一个人最多连续 {streak} 条，超过就必须换会话。
   - 【会话名】用生活化的昵称/备注，可以带关系标注，如「一粥困八天（暧昧期）」「luna-富婆」「粉丝 军」。
   - 【每条都要有钩子】消息要具体、有信息量、带悬念/暧昧/八卦，让人想点开，
     例如「你牵着那个妹妹是谁」「泰国果冻干嘛的」「小狗项圈给你买一个」「鸡要八毛什么意思」；
     禁止「在吗」「吃了吗」「哈哈」「晚安」这类没信息量的寒暄。
   - 【画面要杂】整块里安排 1~2 条图片消息（`[图片] 视频缩略图：女生的腿`、`[图片] 风景照`）、
     1 条链接卡片（`[对方发链接] 标题 | 封面图 | 来源 | 时间`）、1 条系统消息
     （如 `SUM：我通过了你的朋友验证请求，现在我们可以开始聊天了`），让列表看起来是真的。
   - 时间标注写在内容后面（`| 19:21`）。**同一会话内部的时间间隔要错落**：允许同一条分钟内
     （间隔 0 分钟）、差 1~3 分钟、偶尔隔十几分钟混着来；不要每条都整齐地 +1 分钟，
     那样一眼就是编的。
   - 会话数按规则来（没有规则时 9 个；主页一屏最多 9 个，多写的会被丢掉）。
C. 【打字不发 / 插话】—— 这是全片最真实的地方：我还在打字，对方就插进来。写法：
   - `[打字不发] 内容 | 停留`：内容停在输入框不发送，再用 `[删除文字] -1` 清空，
     最后用 `[我方打字]` 发真实话术。插话是**可选的第三段**，只在要制造
     「我还在打字、对方就抢话」时才加：`[打字不发] 内容 | 停留 | 对方插话一句`。
   - **不是每个 [打字不发] 都要配插话**：参考剧本里 44~50 处打字不发只有 15~18 处插话；
     整份剧本插话 {interjections} 处左右就够，配太多会显得对方一直在抢话，反而不真实。
   - `[我方打字] 正在打的这句 | 对方抢白一句`：边打字边被插话，随后把这句话发出去。
   - 多条插话用「；」分隔：`[打字不发] 先调动好奇心 | 0.6 | 你这人什么意思？！；就你会说`
   - 【打字不发写什么 —— 最重要的一条】`[打字不发]` 的正文**每一处**都要是
     **写给观众看的一句话技巧说明**：点出「这一步在做什么、为什么这样聊有效」，
     例如「以退为进」「故意否定 引起注意」「共情+肯定 不要反驳」「把选择权丢给她」
     「再添最后一把火」。
     写的是**打法/技巧**，不是聊天话术草稿，也不是对方的心理活动：
     ✅ 正确：`[打字不发] 故意否定 引起注意 | 0.5`、`[打字不发] 把话题抛回去 让她主动说 | 0.5`
     ❌ 错误：`[打字不发] 那我就陪你聊到天亮`（这是马上要发的话，不是技巧说明）
     ❌ 错误：`[打字不发] 她其实在等你先低头`（这是对方的心理活动，不是技巧）
     **绝不能把紧接着要原样发出去的那句话写进 [打字不发]**——观众会看到同一句出现两次；
     随后的 `[我方打字]` 必须写与它不同的完整话术。
   - 【插话回应什么】插话是**对方**发的一条消息，必须是对方能真发出来的口语，
     只能回应「我已经发出去的上一条消息」，或者对方自己起一个新话题。
     **绝不能回应 [打字不发] 里还没发出去的内容**——
     对方看不到输入框，不可能回答我还没说出口的话（现在打字不发写的是技巧说明，
     对方更不可能回应它）；也不要把「幸灾乐祸」「她其实在等你」这类心理活动/态度词
     写成插话。
   - 插话说过的话，不要再单独用一条 `[对方发消息]` 重复一遍。
   - 整份剧本至少 {typing_holds} 处 `[打字不发]`、至少 {interjections} 处带插话；
     重点是「打字不发」要密集：展开的会话里连着打四五次、删掉再打都是正常的，
     参考剧本里 `[打字不发]` 的数量接近 `[我方打字]` 的一半以上。插话是「参数」，
     不是单独一行，不要写成 `[对方插话] 内容`。
   - 注意区分：`[对方正在输入] 1.0` + `[对方发消息] 内容` 是「我打完、对方再回」，
     没有重叠感；要制造「我还在打字对方就插进来」的紧凑节奏，必须用 C 的写法。
D. 【消息里的特殊内容】写在消息正文开头即可，系统会自动识别：
   - 图片：`[图片] 关键词`（如 `[我方打字] [图片] 好显身材的连衣裙`）——关键词必须是
     【可用素材】清单里的短名。**禁止写文件路径、扩展名、`_20260831_185446` 这类时间戳，
     也不要带「来自小红书 / 网页版」来源后缀**：写成 `[对方发图片] /images/avatar/xxx__1_…_546.jpg`
     或 `[图片] 洱海的日落`（清单外）都会破图、配图面板找不到。
   - 表情：`[表情] 关键词`（如 `[对方发消息] [表情] 害羞猫咪`）——同样只写【可用素材】里的短名；
     同一个表情整份最多用 2 次，换着用（清单外或编出来的名字会全部回落成同一张默认表情）。
   - 链接卡片：`[链接] 标题 | 图片 | 来源`
   - 时间分隔条：消息末尾加 `| 21:40`（历史会话里写在内容后面）。
E. [历史会话] 块只放历史消息；`[打开聊天]` 和实时对白必须写在历史块【外面】的独立指令行。
F. 【`[我方打字]` 与 `[打字不发]` 的分工】`[我方打字]` 一律是能直接发出去的真实聊天话术，
   禁止把方法论/步骤/心理活动写进去；给观众看的技巧说明一律写在 `[打字不发]` 的正文里。
G. 【节奏 —— 别用 `[等待]` 打节拍】参考剧本里 `[等待]` 只出现在真正要停一下的地方
   （整份 7~12 处）；**不要每发一条消息就 `[等待] 0.3`**，那会变成节拍器，也被校验器拦。
   被 `[等待]` 紧跟着的我方消息不要超过六成。更真实的做法是**一方连发 2~3 条**
   （连着几条 `[我方打字]`，或连着几条 `[对方发消息]`），不要每条都严格「我一条 → 对方一条」；
   参考剧本的最长连发是 6~15 条、交替率只有 0.19~0.56，整份对白不要写成朗读稿。"""


# ============================================================
# 生成提示词
# ============================================================

def _format_action_table_compact(actions) -> str:
    """把动作表格式化成提示词里的简表（动作名 + 参数名 + 说明）。"""
    table = actions or st.ACTION_SCHEMA
    lines = []
    for i, a in enumerate(table, start=1):
        action = a["action"]
        desc = a.get("desc", "")
        params = a.get("params", []) or []
        if params:
            bits = []
            for p in params:
                key = p.get("key")
                if key in ("内容", "文案"):
                    bits.append("内容")
                elif key in ("联系人", "会话"):
                    bits.append("联系人")
                elif key in ("数据", "data"):
                    bits.append("数据JSON")
                else:
                    bits.append(key)
            lines.append(f"{i}. [{action}] {'、'.join(bits)} —— {desc}")
        else:
            lines.append(f"{i}. [{action}] —— {desc}")
    return "\n".join(lines)


def build_generation_prompt(actions=None, people_block: str = "", preferences: str = "",
                            reference_text: str = "", category: str = "",
                            skills=None) -> str:
    """构造"创作"系统提示词：角色 + 动作表 + 人物库 + 偏好 + 参考剧本 + 书写规范 + 硬性要求。

    skills：本次生效的规则库条目。用来把「历史会话最多几个带我方回复 / 同一人最多连发几条 /
    至少几处插话 / 策略注释最多几处」这些数值直接写进规范块，做到「提示词要求的」
    与「生成后校验的」是同一套数字 —— 旧版提示词要求「每个会话都一问一答」，
    模型照抄后生成 10 个会话全部双方来回，不像微信列表。
    """
    # 用「人物库」里可选的类别做对象提示
    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\n- 本剧本的角色以「{category}」类别为主，从【人物库】挑该类别人物；"
                    f"若类别里有多人，优先挑本剧本还没用过的那几个，避免同一张脸反复出现。")

    action_text = _format_action_table_compact(actions)
    people_block = people_block or "（人物库为空，请用常见中文名）"
    pref_block = preferences or "（暂无历史沉淀）"
    ref_block = reference_text or "（暂无参考剧本，但请依聊天教学套路创作）"
    spec_block = writing_spec_block(skills)
    asset_block = _asset_block()
    nums = rule_numbers(skills)

    return f"""你是「微信聊天视频仿真剧本」创作助手，专注【男生追女生 / 聊天教学】类剧本。用户给你一个创作主题和若干参考剧本，你要产出一整套【可直接运行】的标准 [指令] 剧本，内容是真实的男生追女生聊天教学片断。

【动作表】（只能使用下列动作，写作标准格式：`[动作名] 参数`，一行一条指令）
{action_text}

{people_block}
{cat_note}

【必须遵守的规则 / 创作偏好】（由你过去的评价沉淀而来；其中硬性规则会在生成后被逐条校验，违反会被打回重写）
{pref_block}

【剧本书写规范 —— 这套软件只认这一种写法，必须严格遵守】
{spec_block}

{asset_block}

【参考剧本】（作为风格与结构模板，重点模仿"每句话背后带什么策略、如何编排节奏"；人物名一律换成【人物库】里的，不要照抄参考里的人名）
{ref_block}

【必选结构骨架 —— 照此编排】
```
[历史会话]
[会话] 人物A
人物A：对方最后一句 | 23:21
人物A：对方又追一条
我：我回过去的一句
人物A：[图片] 伸腿自拍照
[会话] 人物B（暧昧期）
人物B：对方一句带钩子的话 | 19:19
[会话] 人物C
人物C：[对方发链接] 标题 | 封面图 | 来源 | 19:18
[会话] 人物D
人物D：对方一句带钩子的话 | 19:15
[会话] 人物E
人物E：对方一句带钩子的话 | 19:10
…（会话数按规则来，没有规则时 9 个；按最后一条消息时间从新到旧往下排；
  整块里只有 1 个人物带「我：」的回复，其余只留对方最后 1~2 条；
  同一人最多连续 {nums['max_history_streak']} 条）
[历史会话结束]              ← 历史块到此为止，只做"已发生"铺垫
[打开聊天] 人物A            ← 必须是历史块之外独立的一条指令
[我方打字] 第一句实时对白（自然口语，≤15 字）
[打字不发] 给观众看的技巧说明（为什么这样聊有效） | 0.5 | 对方插话一句   ← 插话是参数，不是单独一行
[删除文字] -1
[我方打字] 真实要发的话术（必须和上面 [打字不发] 的内容不同）
[对方发消息] 对方回的一句话
[返回主页]
[等待] 1
```

【硬性要求 —— 必须全部遵守】
1. 输出只能是标准 [指令] 文本（一行一条，如 [打开聊天] 陆香儿 / [我方打字] …）；不要任何解释、不要 markdown 代码块、不要三点号开头。
2. 主题：围绕用户给的创作主题，编排一段"男生追女生"的完整聊天教学：先 [历史会话] 铺底 + 打开聊天 → 我方打字 → 对方插话/后台消息 → 逐步引导（共情/调动情绪/探知三观/拉高格局）→ 情绪到位后铺垫邀约或收尾。
3. 【历史会话像微信列表预览，不是一问一答】绝大多数 [会话] 只留对方最后 1~2 条消息、不写「我：」；整块里只有 1 个（最多 {nums['max_history_two_sided']} 个）会话出现「我：」的回复，且夹在对方消息中间。会话按最后一条消息时间从新到旧排列，会话内部时间从上到下递增；同一人最多连续 {nums['max_history_streak']} 条。**同一会话内部相邻消息的时间间隔要错落**（同一条分钟内、差 2~3 分钟、偶尔隔十几分钟混着来），不要每条都整齐地 +1 分钟。每个会话都写成「对方说 → 我回 → 对方再说」是不合格的，会被打回重写。
4. 【打字不发 + 插话必须用够】整份剧本至少 {nums['min_typing_hold']} 处 `[打字不发]`、至少 {nums['min_interjections']} 处带「插话」；「打字不发」要密集，一个展开的会话里连打四五次很正常。**但插话不是每个 [打字不发] 都配**（参考剧本 44~50 处打字不发只有 15~18 处插话），配太多会显得对方一直在抢话。插话写法：`[打字不发] 技巧说明 | 0.5 | 对方插话一句` 或 `[我方打字] 内容 | 对方插话一句`，多条插话用「；」分隔。不要写成 `[对方插话] 内容`，也不要用「[对方正在输入] + [对方发消息]」代替插话（那样没有重叠感）。三条硬性约束：① `[打字不发]` 的正文必须是**写给观众看的技巧说明**（「这一步在做什么、为什么这样聊有效」，如「以退为进」「故意否定 引起注意」「把选择权丢给她」），**不能是马上要发出去的聊天话术草稿，也不能是对方的心理活动**；其后的 `[我方打字]` 内容必须与它不同；② 插话只能回应我已经发出去的上一条消息或对方自己起的新话题，**不能回应 [打字不发] 里还没发出去的内容**（对方看不到输入框）；③ 插话说过的话，不要再用一条独立的 `[对方发消息]` 重复一遍。
5. 【绝不偷工减料】绝对禁止出现：……、[省略]、【省略】、省略、此处省略、以下省略、内容自拟、自行发挥、待补充、xxx、等等、同上、余下类似 等任何占位/缩略。每一句都要写出真实、完整、具体的中文聊天话术；绝不允许只写"说了句调侃"这类概述。
6. 【`[我方打字]` / `[打字不发]` 分工】`[我方打字]` 一律是自然、口语化的真实聊天话术，禁止把方法论/步骤/心理活动写进消息正文；给观众看的技巧说明（「为什么这样聊有效」）一律写在 `[打字不发]` 的正文里，而且**每个 `[打字不发]` 都要写技巧说明**，不要写成聊天话术草稿。
7. 【保留节奏】每个 [打字不发] 用 `| 0.5` 标注停留；时长/停顿写成数字（0.3~0.8 之间更自然）。写出的时长务必保留，不得归一成默认值。
8. 【人物】只从【人物库】里挑人名，同一剧本里同一个对象不要换名字；[会话] 数量按规则（没有规则时至少 9 个），但只挑其中 2~3 个真正 [打开聊天] 展开对白，其余只留在历史块里把屏幕铺满。
9. 【画面丰富】适当穿插 [发送表情]、[对方后台发消息]、[我方发链接]，让画面真实有层次；图片/表情一律只写【可用素材】清单里的短名（如 `[图片] 好显身材的连衣裙`、`[表情] 害羞猫咪`），禁止写文件路径、扩展名、时间戳或来源后缀，也不要自创图库里没有的描述。不要使用 [转账]、[语音] 等当前未启用的动作（除非上面的硬性规则明确要求）。
10. 结尾可以再来一条 [返回主页] + 一条 [等待] 收束，或继续下一会话，保持整段像一个完整教学短视频。
11. 【篇幅上限】整份剧本的实时指令（[历史会话] 块以外的所有 [动作] 行）控制在 {nums['max_script_steps']} 步以内。打字不发要够密，但不要靠多开来回、堆 [对方正在输入]/[等待] 把剧本拉到 300 步——同一个来回里用「打字不发 → 删除 → 再打字」制造节奏即可。"""


def build_critique_prompt(issues: list, actions=None, people_block: str = "",
                          reference_text: str = "", preferences: str = "",
                          category: str = "", violations=None, skills=None) -> str:
    """构造"纠错重写"系统提示词：问题清单 + 动作表 + 人物库 + 偏好 + 参考剧本。

    与初次生成保持一致，确保模型重写时仍能看到【动作表】与【人物库】；
    否则模型会因"只见问题、未见工具/人物"而拒绝按标准格式输出（如直接回一段
    解释文字而非 [指令] 剧本）。

    violations：被违反的硬性规则说明（来自规则库），用于定向修复。
    skills：本次生效的规则库，用来把书写规范（历史会话像微信列表预览 / 插话格式）一并注入，
            避免重写时又把历史会话改回「每个会话都一问一答」。
    """
    if not issues:
        return "请重新生成一版更完整、更符合要求的剧本。"
    nums = rule_numbers(skills)
    issue_lines = "\n".join(f"- {x}" for x in issues[:20])
    violation_block = ""
    if violations:
        v_lines = "\n".join(f"- {x}" for x in list(violations)[:10])
        violation_block = (
            "\n【你上一版违反的硬性规则 —— 必须逐条改掉，这是本次重写的重点】\n" + v_lines + "\n")

    # 与 build_generation_prompt 相同的上下文，保证重写时信息不缺失。
    action_text = _format_action_table_compact(actions)
    people_block = people_block or "（人物库为空，请用常见中文名）"
    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\n- 本剧本的角色以「{category}」类别为主，从【人物库】挑该类别人物；"
                    f"若类别里有多人，优先挑本剧本还没用过的那几个，避免同一张脸反复出现。")
    pref_block = preferences or "（暂无历史沉淀）"
    ref_block = reference_text or "（暂无参考剧本，但请依聊天教学套路创作）"
    spec_block = writing_spec_block(skills)
    asset_block = _asset_block()

    return f"""你是同一套「微信聊天视频仿真剧本」的纠错助手。用户上一步生成的剧本存在下面这些问题，请你修复并重写。

【上一步的问题】
{issue_lines}
{violation_block}
【动作表】（只能使用下列动作，写作标准格式：`[动作名] 参数`，一行一条指令）
{action_text}

{people_block}
{cat_note}

【必须遵守的规则 / 创作偏好】（由你过去的评价沉淀而来；其中硬性规则会在生成后被逐条校验，违反会被打回重写）
{pref_block}

【剧本书写规范 —— 这套软件只认这一种写法，必须严格遵守】
{spec_block}

{asset_block}

【参考剧本】（作为风格与结构模板；人物名一律换成【人物库】里的，不要照抄参考里的人名）
{ref_block}

【修复要求】
- 保留上一版里可用、正确、完整的部分（好的话术、节奏、结构可原样保留）。
- 针对上面每条问题，逐一改到位：省略/占位 → 补全真实话术；缺联系人 → 补上；空内容 → 写具体内容；过短 → 按参考剧本扩充。
- 输出仍只能是标准 [指令] 文本，一行一条；不许省略、不许用 …、[省略]、内容自拟 等占位；不要把原有正确内容删成摘要。
- 严格只用【动作表】里的动作；人物只从【人物库】选，保持同一对象人名一致；开场可用 [历史会话] 铺垫，再 [打开聊天] + 对白推进。
- 【结构硬性要求】至少 1 条 [打开聊天]，且它必须是【[历史会话] 块之外】的独立指令行、后面紧跟至少 2 条实时对白；[历史会话] 块只放"已发生"消息做铺垫，绝不把实时对白写进历史块；若上一步缺 [打开聊天]，请按此结构【补全】而不要只改文字。
- 【历史会话重写要求】历史块要像微信列表预览：绝大多数 [会话] 只留对方最后 1~2 条、不写「我：」；整块里只有 1 个（最多 {nums['max_history_two_sided']} 个）会话出现「我：」的回复；会话按最后一条消息时间从新到旧排列；同一会话内部相邻消息的时间间隔要错落（同一条分钟内、差 2~3 分钟、偶尔十几分钟），不要每条都 +1 分钟。若上一版几乎每个会话都写了「我：」，必须删到只剩 1 个会话带我方回复，其余只留对方最后 1~2 条。
- 【篇幅重写要求】整份剧本的实时指令控制在 {nums['max_script_steps']} 步以内。超长时优先砍：重复的来回、多余的 [对方正在输入]/[等待]、同一句话的多次删改；不要为了压长度把话术删成摘要或省略。
- 【素材引用重写要求】图片/表情一律只写【可用素材】清单里的短名，禁止写文件路径、扩展名、时间戳或「来自小红书/网页版」来源后缀；同一个表情整份最多用 2 次，换着用。清单里没有的名字不要写。
- 【节奏重写要求】把多余的 `[等待]` 删掉——只保留真正要停一下的地方（整份 7~12 处），不要每条消息后面都跟 `[等待] 0.3`；同时让至少一段出现「一方连发 2~3 条」，不要严格一问一答。
- 【打字不发 + 插话重写要求】按书写规范 C 补足 `[打字不发]` 与带插话的动作：整份剧本至少 {nums['min_typing_hold']} 处 `[打字不发]`、至少 {nums['min_interjections']} 处带插话，插话是参数（`| 停留 | 插话内容`），不是单独一行。**重点改 `[打字不发]` 的正文**：它必须是给观众看的技巧说明（「为什么这样聊有效」，如「以退为进」「故意否定 引起注意」），不是聊天话术草稿、不是对方心理活动——凡是像"那我陪你聊到天亮""她其实在等你先低头"这类，全部改写成打法说明。同时逐条检查：`[打字不发]` 的内容有没有在随后的 `[我方打字]` 里原样又发一遍（有就改成技巧说明或不同的话术）；插话有没有在回答 `[打字不发]` 里没发出去的内容（有就改成回应上一条已发出的消息）；插话有没有被下一条 `[对方发消息]` 重复（有就删掉重复的那条）。"""


def _gen_user_message(brief: str, category: str, ref_titles: list) -> str:
    """构造首次生成时的 user 消息。"""
    desc = str(brief or "").strip()
    cat = f"（人物类别：{category}）" if category in CATEGORIES else ""
    refs = f"参考剧本：{ '、'.join(ref_titles) }" if ref_titles else "无参考剧本"
    return f"创作主题：{desc}\n{cat}\n{refs}\n\n请直接产出整套标准 [指令] 剧本。"


def _critique_user_message(current_text: str) -> str:
    """构造纠错轮次的 user 消息：把上一版剧本原文交给模型修复。"""
    body = (current_text or "").strip()
    if not body:
        return ("请针对上面的问题，根据【动作表】和【人物库】重新输出一版完整剧本，"
                "仍然输出标准 [指令] 文本，不许省略。")
    return ("请针对上面的问题，修复并重写下面这份《上一版待修复剧本》"
            "（保留可用部分，按问题清单逐条改到位，仍然输出完整 [指令] 文本，不许省略）：\n\n"
            "===== 上一版待修复剧本 开始 =====\n" + body +
            "\n===== 上一版待修复剧本 结束 =====")


# ============================================================
# 评价 -> 规则候选（这就是「评价如何变成 skill」的那一步）
# ============================================================

_CANDIDATE_SYSTEM = """你是「微信聊天剧本创作规则抽取器」。
用户对刚生成的一版剧本打了分并写了留言。请把留言里的要求拆成若干条**可执行、可校验**的规则。
只输出 JSON，格式：{"skills":[{"type":"rule","title":"...","kind":"...","value":...,"prompt_hint":"..."}]}

kind 只能取以下之一（value 必须与 kind 匹配）：
- banned_action：禁用某个动作，value 写动作名，如 "转账"、"发送语音"
- required_action：必须包含某个动作，value 写动作名，如 "打字不发"
- min_sessions：最少会话数，value 写整数
- min_history_messages：历史会话消息最少条数，value 写整数
- min_realtime_lines：实时对白最少条数，value 写整数
- max_message_chars：单条消息最大字数，value 写整数
- forbid_text：消息正文禁止出现的词，value 写词，如 "语音"
- forbid_annotation_as_message：禁止把心理活动/解说当成消息发出，value 写 true
- opening_image：开头必须有图片，value 写 true
- max_people：出场人物上限，value 写整数
- max_annotations：仅用于兜底「`[我方打字]` 里写了策略注释」这个硬伤，value 写整数
  （注意：`[打字不发]` 的正文现在就是给观众看的技巧说明，不再限制处数，不要为它建规则）
- history_two_sided：历史会话整体要有双方对话（整块里至少 1 个会话是我和对方来回），value 写 true
  （用户说"历史会话只有她一个人在说""我一句都没回"就填这条；注意：用户并不要求每个会话都一问一答）
- max_history_streak：历史会话里同一个人最多连续发几条，value 写整数
- max_history_two_sided：历史会话里最多几个会话带「我：」的回复，value 写整数
  （用户说"每个会话都有我回的""不像微信列表预览"就填这条，一般填 2）
  （用户说"她一个人刷屏""连着发一大堆"就填 2 或 3）
- min_interjections：至少几处「插话」，value 写整数
  （用户说"插话没用起来""要多用插话""边打字边被打断"就填 10~15）
- min_typing_hold：整份剧本至少几处「打字不发」，value 写整数
  （用户说"打字不发太少""多来点打字不发"就填 10~15）
- max_script_steps：整份剧本的实时指令步数上限，value 写整数
  （用户说"太长了""别 300 多步""控制在 200 步左右"就填 200）
- asset_ref_plain：图片/表情引用只能写图库里的短名，禁止文件路径/扩展名/时间戳/来源后缀，value 写 true
  （用户说"剧本里怎么出现文件名了""配图写的是路径""图片名太长太丑"就填这条）
- asset_ref_exists：图片/表情引用必须能在图片库里找到真实文件，value 写 true
  （用户说"图显示不出来""破图""表情全变成同一张""表情包找不到"就填这条）
- max_same_emoji：同一个表情最多重复几次，value 写整数（一般 2）
  （用户说"表情老是重复""同一个表情发了好几次"就填这条）
- max_wait_ratio：被 [等待] 紧跟着的我方消息占比上限，value 写小数（一般 0.6）
  （用户说"节奏很机械""每条后面都跟一个等待""像节拍器"就填这条）
- min_burst：实时对白里至少有一方连发几条，value 写整数（一般 2 或 3）
  （用户说"太像一问一答了""没有连发""像朗读稿"就填这条）

要求：
- 一条留言尽量拆成 1~6 条独立规则；留言里有具体数值就填进 value。
- title 用简短中文；prompt_hint 写成给大模型的命令句，如「会话数不少于 9 个」。
- 只是主观感受（如「不够精彩」）时，type 用 "style"，不带 kind/value。
- 不要输出解释、不要 markdown 围栏。"""


def _rule_skill_candidates(text: str) -> list:
    """无大模型时的兜底抽取：覆盖最常见的几类明确要求。"""
    out = []

    def add(kind, value, title, hint):
        out.append({"type": "rule", "title": title, "kind": kind, "value": value, "prompt_hint": hint})

    if re.search(r"(不涉及|不要|没有|别).{0,4}转账", text):
        add("banned_action", "转账", "禁用转账", "不要出现转账相关动作")
    if re.search(r"(不涉及|不要|没有|不使用).{0,4}语音", text) or "语音功能" in text:
        add("banned_action", "发送语音", "禁用语音消息", "不要使用语音消息")
    m = re.search(r"会话.{0,6}?(\d+)\s*(?:个|条)", text)
    if m:
        add("min_sessions", int(m.group(1)), "会话数下限", "会话数不少于 %s 个" % m.group(1))
    m = re.search(r"历史会话.{0,8}?(\d+)\s*条", text)
    if m:
        add("min_history_messages", int(m.group(1)), "历史消息下限", "历史会话消息不少于 %s 条" % m.group(1))
    if re.search(r"(太长|话.{0,2}长|短一点|简短|短小)", text):
        add("max_message_chars", 15, "单条消息字数上限", "我方每条消息不超过 15 个字")
    if re.search(r"开头.{0,6}图片", text):
        add("opening_image", True, "开头要有图片", "剧本开头必须插入一张图片")
    if re.search(r"(两个女生|三人|3\s*人|三个人)", text):
        add("max_people", 3, "出场人物上限", "出场人物不超过 3 人")
    if "打字不发" in text:
        add("required_action", "打字不发", "必须使用打字不发", "必须使用 [打字不发] 制造博弈节奏")
    if re.search(r"(心理活动|解说|注释).{0,12}(不要|别|不当成|别当成|禁止)", text) or \
       re.search(r"(不要|别|禁止).{0,12}(心理活动|解说|注释)", text):
        add("forbid_annotation_as_message", True, "禁止心理活动外发",
            "不要把心理活动/解说当成消息正文，正文必须是真实聊天话术")
    if re.search(r"(心理活动|解说|注释|博弈).{0,14}(一两句|少|太多|多)", text) or \
       re.search(r"(一两句|少一点|别太多).{0,14}(心理活动|解说|注释)", text):
        add("max_annotations", 2, "别把心理活动当消息发",
            "心理活动/解说只允许写在 [打字不发] 的技巧说明里，"
            "绝不能写进 [我方打字] 当成消息发出去")
    if re.search(r"(诱惑|擦边|吸引)", text):
        out.append({"type": "style", "title": "内容要有诱惑性",
                    "prompt_hint": "会话内容要有诱惑性、适度擦边，可参考用户提供的案例尺度"})
    if "铺满" in text:
        add("min_history_messages", 20, "历史会话铺满",
            "历史会话消息不少于 20 条，把过往聊天记录铺满屏幕")
    # 插话：能读出次数就变成可校验规则，读不出也至少要求 5 处
    if "插话" in text:
        m = (re.search(r"插话.{0,10}?(\d+)\s*(?:次|处|条)", text)
             or re.search(r"(\d+)\s*(?:次|处|条).{0,10}?插话", text)
             or re.search(r"至少.{0,6}?(\d+).{0,8}?插话", text))
        if m:
            add("min_interjections", int(m.group(1)), "插话次数下限",
                "至少 %s 处用「插话」写法：`[打字不发] 技巧说明 | 停留 | 对方插话一句`，"
                "插话只能是对方真发出来、回应我已发出消息的一句口语" % m.group(1))
        else:
            add("min_interjections", 5, "至少 5 处插话",
                "至少 5 处用「插话」写法：`[打字不发] 技巧说明 | 0.5 | 对方插话一句`")
    # 篇幅上限：用户嫌太长 / 报出步数时变成可校验规则
    ms = re.findall(r"(\d+)\s*多?\s*步", text)
    if ms:
        # 「别 300 多步，控制在 200 步左右」：取较小的那个，通常才是要控制到的目标值
        val = min(int(x) for x in ms)
        add("max_script_steps", val, "实时指令步数上限",
            "整份剧本的实时指令控制在 %d 步以内" % val)
    elif re.search(r"(太长|过长|篇幅|拉长|别.{0,4}那么长)", text):
        add("max_script_steps", 200, "实时指令步数上限",
            "整份剧本的实时指令控制在 200 步以内")
    # 历史会话时间戳别机械地每分钟一条（内置校验，这里只留风格提示）
    if re.search(r"(时间戳|时间标注|时间)", text) and \
       re.search(r"(一分钟|1\s*分钟|机械|整齐|一样|每分)", text):
        out.append({"type": "style", "title": "历史会话时间戳要错落",
                    "prompt_hint": "历史会话内部相邻消息的时间间隔要错落"
                                   "（同一条分钟内、差 2~3 分钟、偶尔隔十几分钟），"
                                   "不要每条都整齐地 +1 分钟"})
    # 打字不发写什么（用户说「打字不发是给观众看的/要写技巧/别写心理活动」时命中）
    if "打字不发" in text and re.search(r"(技巧|观众|为什么|心理|草稿|话术)", text):
        out.append({"type": "style", "title": "[打字不发] 写技巧说明",
                    "prompt_hint": "[打字不发] 的正文是给观众看的一句话技巧说明"
                                   "（「为什么这样聊有效」，如「以退为进」「故意否定 引起注意」），"
                                   "不是聊天话术草稿，也不是对方的心理活动"})
    # 打字不发：读得出次数就变成可校验的数量下限
    if "打字不发" in text:
        m = (re.search(r"打字不发.{0,12}?(\d+)\s*(?:次|处|条)", text)
             or re.search(r"(\d+)\s*(?:次|处|条).{0,12}?打字不发", text))
        if m:
            add("min_typing_hold", int(m.group(1)), "打字不发次数下限",
                "整份剧本至少 %s 处 [打字不发]：正文写「给观众看的技巧说明」，"
                "不是聊天话术草稿" % m.group(1))
        elif re.search(r"(少|不够|多(用|来|加)|增加|加强)", text):
            add("min_typing_hold", 5, "至少 5 处打字不发",
                "整份剧本至少 5 处 [打字不发]：正文写「给观众看的技巧说明」")
    # 历史会话整体要有双方对话（用户吐槽「只有她一个人在说」时最容易命中）
    if (re.search(r"历史.{0,24}(双方|有来有回|来回|互相|对话|我(也|要)?回|"
                  r"一个人|单方面|刷屏)", text)
            or re.search(r"(单方面|一个人|只有她|只有他|刷屏).{0,24}历史", text)):
        add("history_two_sided", True, "历史会话整体要有双方对话",
            "整个历史会话块至少要有 1 个会话是「对方说 → 我回 → 对方再说」，"
            "其余会话可以只留对方最后一两句")
    if re.search(r"(刷屏|连发|连着发|连续发)", text):
        add("max_history_streak", 2, "历史会话同一人最多连续 2 条",
            "历史会话里同一个人最多连续发 2 条，超过必须由另一方接话或换会话")
    # 历史会话别每个都写我的回复（用户要「像微信列表预览」时命中）
    if (re.search(r"(每个会话|逐个会话).{0,8}(都|全).{0,6}(我|回)", text)
            or re.search(r"(一问一答|列表预览|只留对方|像微信列表)", text)):
        add("max_history_two_sided", 2, "历史会话最多 2 个带我的回复",
            "历史会话里最多 2 个会话带「我：」的回复，其余只留对方最后 1~2 条，像微信列表预览")
    # 历史会话内容要有钩子（用户嫌「没信息量/废话」时命中）
    if re.search(r"(没信息量|没意思|废话|太水|干巴巴|钩子|悬念|想点开)", text):
        out.append({"type": "style", "title": "历史会话每条都要有钩子",
                    "prompt_hint": "历史会话每条消息都要具体、有信息量、带悬念/暧昧/八卦，"
                                   "禁止「在吗」「吃了吗」「哈哈」「晚安」这类废话"})
    return out


def extract_skill_candidates(comment, brief="", category="", api_key="",
                             model=None, base_url=None) -> list:
    """把一条评价留言拆成候选规则（不直接入库，交前端确认后保存）。"""
    text = str(comment or "").strip()
    if not text:
        return []
    fallback = _rule_skill_candidates(text)
    if not api_key or str(api_key).upper().startswith("REPLACE"):
        return [_normalize_candidate(c) for c in fallback]
    try:
        user = ("创作主题：%s\n人物类别：%s\n用户评价：%s"
                % (brief or "（未填）", category or "不限", text))
        raw = st.call_deepseek(api_key, _CANDIDATE_SYSTEM, user,
                               model or st.DEFAULT_MODEL, base_url or st.DEFAULT_BASE_URL,
                               timeout=120, max_tokens=2000, json_mode=True)
        data = json.loads(strip_code_fences(raw or "") or "{}")
        items = data.get("skills") if isinstance(data, dict) else None
        out = []
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind") or "").strip()
            if kind and kind not in store.RULE_KINDS:
                kind = ""
            title = str(it.get("title") or "").strip()[:40]
            hint = str(it.get("prompt_hint") or title or "").strip()[:200]
            if not title and not hint:
                continue
            out.append(_normalize_candidate({
                "type": "rule" if kind else "style",
                "title": title or hint[:20],
                "kind": kind or None,
                "value": it.get("value"),
                "prompt_hint": hint,
            }))
        return [_normalize_candidate(c) for c in (out or fallback)]
    except Exception:  # noqa: BLE001
        return [_normalize_candidate(c) for c in fallback]


def save_skill_candidates(candidates, source_feedback=None, enabled=True, source_note=""):
    """把用户确认过的候选规则写入规则库，返回入库后的条目列表。"""
    saved = []
    for c in candidates or []:
        if not isinstance(c, dict):
            continue
        c = _normalize_candidate(c)
        kind = c.get("kind") or None
        if kind and kind not in store.RULE_KINDS:
            kind = None
        saved.append(store.add_skill(
            title=str(c.get("title") or c.get("prompt_hint") or "").strip(),
            kind=kind,
            value=c.get("value"),
            skill_type=str(c.get("type") or ("rule" if kind else "style")),
            prompt_hint=str(c.get("prompt_hint") or "").strip(),
            enabled=enabled,
            source_feedback=source_feedback,
            source_note=source_note,
        ))
    return saved
