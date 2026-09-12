# -*- coding: utf-8 -*-
"""把 editor_server._generate_script 改造成「JSON 进、[指令] 出」的新范式。

体检查到的问题（用当前校验器重跑 39 条历史，0 条能过）里，有一类是
「格式不可靠」：模型偶发写出 `[为我方打字]`、`[返回主页`（缺右括号）
这类行，会被解析器静默丢弃 —— 剧本凭空少几行，反而触发「对白不够」，
于是无限重写。这里把生成范式换成：
  1) 首轮：模型输出 JSON（history + steps） -> 本地 script_format.render 成 [指令]；
  2) 纠错轮：只让模型给 patches / append_steps -> 本地定向打补丁，
     而不是整篇重写（省 token，也不会「越改越差」）；
  3) 评分：改用 issues_score（致命×3 + 硬规则×2 + 风格×1），
     不再是「有几个问题」一刀切；
  4) 通过的结果自动沉淀进参考库（以前好结果只躺在生成历史里）。
"""
import ast
import io
import os

PATH = "editor_server.py"

NEW_FUNCS = r'''
# ============================================================
# 创作生成：JSON 进、[指令] 出
# ------------------------------------------------------------
# 老范式是「让模型直接写 [指令] 文本」，实测 39 条历史里有 2 条出现
# `[为我方打字]`、`[返回主页`（缺右括号）这类写法被解析器静默丢弃，
# 剧本凭空空几行 -> 触发「对白不够」-> 被迫重写。
# 新范式把「结构」交给 JSON：模型只填字段，渲染成 [指令] 由本地完成。
# ============================================================

_AUTO_REF_MAX = 12          # 自动沉淀的参考剧本上限（防止参考库被生成结果撑爆）


def _coerce_model_output(raw: str):
    """把模型输出归一成 ([指令] 文本, 产出形态)。

    产出形态：'json'（模型按新范式给了 JSON）/ 'text'（模型仍给了 [指令] 文本）。
    两种都接受：老模型/低温度偶发只给文本时，不至于整轮失败。
    """
    text, src = script_format.coerce(raw)
    if (text or "").strip():
        return text, src
    # JSON 里没有可用 steps（或压根不是 JSON）：把原文当剧本兜底，
    # 交给后面的 check_completeness 去判「它到底像不像剧本」。
    return (raw or "").strip(), "text"


def _apply_critique_output(raw: str, current_text: str):
    """把纠错轮的模型输出落到当前剧本上，返回 (新文本, 方式) 或 (None, 'none')。

    优先用 patches / append_steps 定向打补丁；模型若直接给了整篇 JSON 或
    整篇 [指令] 文本，则退化为全量替换。补丁一条都没打上且没有可用的
    整篇结果时返回 None，让调用方保留上一版（绝不把剧本改没）。
    """
    obj = script_format.extract_json(raw)
    if isinstance(obj, dict):
        has_patch = bool(obj.get("patches"))
        has_append = bool(obj.get("append_steps"))
        if has_patch or has_append:
            text, ok, fail = script_format.apply_patches(current_text, obj.get("patches") or [])
            if has_append:
                text = script_format.apply_append_steps(text, obj.get("append_steps") or [])
            if ok or has_append:
                return text, "patch"
            # find 全部对不上（行号/全角空格差异）：退化为整篇替换
        whole, src = script_format.coerce(obj)
        if (whole or "").strip():
            return whole, src
    text, src = _coerce_model_output(raw)
    if (text or "").strip() and text.strip() != (current_text or "").strip():
        return text, src
    return None, "none"


def _sink_reference(text: str, brief: str, category: str):
    """把一次「零问题通过」的生成结果自动收进参考库。

    体检发现：好结果只进 generate_history，要用户手动「存为参考」才入库，
    于是参考库永远只有最初那 3 条 —— 这恰恰是「越写越好」最该转起来的飞轮。
    自动沉淀的条目会带 note 前缀「自动沉淀」，用户可在参考库里随时删/停用。
    超过 _AUTO_REF_MAX 条时，淘汰自动沉淀里评分最低、最旧的一条。
    """
    body = (text or "").strip()
    if not body:
        return None
    refs = store.list_references()
    for r in refs:
        if str(r.get("text") or "").strip() == body:
            return None                      # 完全重复，不重复入库
    auto = [r for r in refs if str(r.get("note") or "").startswith("自动沉淀")]
    if len(auto) >= _AUTO_REF_MAX:
        auto.sort(key=lambda r: (float(r.get("score") or 0), float(r.get("created_at") or 0)))
        try:
            store.delete_reference(auto[0]["id"])
        except Exception:                    # noqa: BLE001
            pass
    title = "自动沉淀 · %s" % (str(brief or category or "生成结果").strip()[:24])
    return store.add_reference(
        title=title, text=body, category=category or "",
        summary="", kind="full",
        note="自动沉淀（本次生成零问题通过，来自创作主题：%s）" % (str(brief or "")[:40]))


def _find_auto_sunk_ref(text: str):
    """该文本是否已在参考库里（用于回填 history 的 reference_id）。"""
    body = (text or "").strip()
    if not body:
        return None
    for r in store.list_references():
        if str(r.get("text") or "").strip() == body:
            return r
    return None


def _generate_script(payload: dict):
    """执行一次「创作生成」：主题 + 参考剧本 -> 完整 [指令] 文本 + 归一步骤 + 校验报告。

    返回 (result_dict, error_msg)：
      result_dict = {"ok": True, "text": ..., "steps": [...], "warnings": [...],
                     "report": {"issues": [...], "attempts": int, "passed": bool}, "source": "generate"}

    流程（新范式）：
      首轮  模型输出 JSON(history+steps) -> 本地渲染 [指令] -> 完整性 + 结构化校验
      纠错  只让模型给 patches/append_steps -> 本地定向打补丁 -> 重新校验（最多 max_rounds-1 轮）
      收尾  采用「评分最高的一轮」（评分含严重度权重，不再只看问题条数）
            零问题通过 -> 自动沉淀进参考库
    """
    brief = str(payload.get("brief") or "").strip()
    if not brief:
        return None, "请输入创作主题。"
    settings = script_translator.load_settings()
    api_key = (settings.get("deepseek_api_key") or "").strip()
    if not api_key or api_key.upper().startswith("REPLACE"):
        return None, "创作生成需要先配置大模型 API Key（顶部「配置大模型」填入 DeepSeek Key）。"
    model = settings.get("deepseek_model") or script_translator.DEFAULT_MODEL
    base_url = settings.get("deepseek_base_url") or script_translator.DEFAULT_BASE_URL

    ref_ids = payload.get("reference_ids") or []
    category = str(payload.get("category") or "").strip()
    max_rounds = int(payload.get("max_rounds") or script_generator.MAX_CRITIQUE_ROUNDS)
    max_rounds = max(1, min(max_rounds, 5))

    # 没手选参考时，按主题自动挑最相关的 2 条，避免"不勾参考 → 模型完全自由发挥 → 风格飘"。
    auto_refs = False
    if not ref_ids:
        try:
            ref_ids = [r.get("id") for r in store.search_references(brief, 2)]
            auto_refs = bool(ref_ids)
        except Exception:  # noqa: BLE001
            ref_ids = []

    references = script_generator.get_reference_scripts_by_ids(ref_ids)
    ref_titles = [str(r.get("title")) for r in references if r.get("title")]
    people_block = script_translator._library_prompt_block()
    skills = script_generator.load_enabled_skills()
    preferences = script_generator.skills_prompt_block(skills)
    reference_text = script_generator.format_references(references, category)
    # 记录这些参考被用过一次（后续可按「参考效果分」排序/淘汰）
    try:
        store.bump_reference_use([r.get("id") for r in references])
    except Exception:  # noqa: BLE001
        pass

    system_prompt = script_generator.build_generation_prompt(
        actions=ACTIONS, people_block=people_block, preferences=preferences,
        reference_text=reference_text, category=category, skills=skills)

    all_issues = []
    current_text = ""
    attempts = 0
    passed = False
    best = None          # (评分, 文本, 问题清单, 是否通过)：防止「越改越差」
    produce_mode = ""    # 记录最终采用的产出形态（json / text / patch）
    patch_ok = 0

    for attempt in range(max_rounds):
        attempts = attempt + 1
        if attempt == 0:
            user_msg = script_generator._gen_user_message(brief, category, ref_titles)
            sys_prompt = system_prompt
        else:
            sys_prompt = script_generator.build_critique_prompt(
                all_issues, actions=ACTIONS, people_block=people_block,
                reference_text=reference_text, preferences=preferences, category=category,
                violations=[x for x in all_issues if "（规则：" in x], skills=skills)
            user_msg = script_generator._critique_user_message(current_text)
        raw, gen_err = _call_generate_deepseek(api_key, sys_prompt, user_msg, model, base_url)
        if gen_err is not None:
            if attempt == 0:
                return None, f"创作生成调用大模型失败：{gen_err}"
            # 后续轮次失败：保留上一版有效结果
            break
        raw = script_generator.strip_code_fences(raw or "")
        if not raw.strip() and attempt > 0:
            # 纠错轮模型未产出内容：保留上一版有效结果，避免用空内容覆盖后二次空转。
            break

        if attempt == 0:
            text, mode = _coerce_model_output(raw)
        else:
            text, mode = _apply_critique_output(raw, current_text)
            if text is None:
                # 连补丁都产不出来：保留上一版，不覆盖
                break
            patch_ok += 1 if mode == "patch" else 0

        if attempt > 0 and current_text and len(text) < len(current_text) * 0.5:
            # 纠错轮把剧本砍掉一半以上：这是「越改越差」，直接保留上一版。
            break
        current_text = text
        produce_mode = mode

        completeness = script_generator.check_completeness(text)
        # 离线归一（生成结果已是标准 [指令]，避免二次调用大模型）
        steps, warnings, _src = _parse_script_to_steps(text, offline=True)
        structural, violated_skills = script_generator.validate_generated_steps(steps, skills, text)
        all_issues = completeness + structural
        # 评分：致命问题比措辞问题重得多，同分时文本更完整者优先。
        _score = script_generator.issues_score(all_issues) + (-len(text),)
        if best is None or _score < best[0]:
            best = (_score, text, list(all_issues), not all_issues)
        # 命中规则 -> 累加命中次数，让用户在规则面板里看到「它真的在起作用」
        try:
            store.bump_skill_hits(violated_skills)
        except Exception:  # noqa: BLE001
            pass
        # 诊断：把这一轮的系统提示/用户消息/模型原始输出/解析结果落盘，便于排查
        # "生成结果解析不出步骤 / 缺 [打开聊天]" 这类校验失败的真正原因。
        try:
            os.makedirs(_GEN_DEBUG_DIR, exist_ok=True)
            with open(os.path.join(_GEN_DEBUG_DIR, f"round{attempt}.txt"), "w", encoding="utf-8") as fh:
                fh.write("===== mode =====\n" + str(mode) +
                         "\n\n===== system_prompt =====\n" + sys_prompt +
                         "\n\n===== user_msg =====\n" + user_msg +
                         "\n\n===== raw_output =====\n" + (raw or "") +
                         "\n\n===== rendered_text =====\n" + (text or "") +
                         "\n\n===== parsed_steps =====\n" + json.dumps(steps, ensure_ascii=False, indent=2) +
                         "\n\n===== issues =====\n" + "\n".join(all_issues))
        except OSError:
            pass
        if not all_issues:
            passed = True
            break

    # 采用「评分最高的一轮」，而不是无脑用最后一轮：
    # 纠错轮偶尔会把剧本改得更短更差，必须回退到最好的一版。
    if best is not None and str(best[1] or "").strip():
        current_text = best[1]
        all_issues = best[2]
        passed = best[3]

    # 用最终可归一化的文本重新得一份干净步骤（若 critique 后文本有变）
    steps, warnings, _src = _parse_script_to_steps(current_text, offline=True)

    result = {
        "ok": True,
        "text": current_text,
        "steps": steps,
        "warnings": warnings,
        "report": {
            "issues": all_issues,
            "attempts": attempts,
            "passed": passed,
            "rules": len(skills),
            "produce_mode": produce_mode or "json",
            "patch_rounds": patch_ok,
        },
        "ref_titles": ref_titles,
        "auto_refs": auto_refs,
        "source": "generate",
    }

    # 零问题通过 -> 自动沉淀进参考库（「越写越好」的飞轮）
    sunk = None
    if passed and len(steps) >= 40:
        try:
            sunk = _sink_reference(current_text, brief, category)
        except Exception:  # noqa: BLE001
            sunk = None
    result["auto_sunk_reference"] = bool(sunk)
    if sunk:
        result["reference_id"] = sunk.get("id")

    # 落一条生成历史（供「历史生成」面板回看/复用）；存档失败不影响本次返回。
    try:
        entry = script_generator.add_generation_history({
            "brief": brief,
            "category": category,
            "ref_ids": [r.get("id") for r in references],
            "ref_titles": ref_titles,
            "text": current_text,
            "steps": steps,
            "warnings": warnings,
            "report": result["report"],
            "model": model,
            "reference_id": (sunk or {}).get("id"),
        })
        result["history_id"] = entry.get("id")
    except Exception:  # noqa: BLE001
        pass
    return result, None
'''


def read(path):
    return io.open(path, encoding="utf-8").read()


def write(path, s):
    io.open(path, "w", encoding="utf-8", newline="").write(s)


def func_span(src, name):
    tree = ast.parse(src)
    offsets = [0]
    for ln in src.splitlines(True):
        offsets.append(offsets[-1] + len(ln))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return offsets[node.lineno - 1], offsets[node.end_lineno]
    raise SystemExit("找不到函数 " + name)


src = read(PATH)

# 1) 导入 script_format
if "import script_format" not in src:
    anchor = "import create_store as store"
    assert src.count(anchor) == 1
    src = src.replace(anchor, anchor + "\nimport script_format", 1)

# 2) 整体替换 _generate_script（新版本 + 三个辅助函数一并写在它原来的位置）
start, end = func_span(src, "_generate_script")
src = src[:start] + NEW_FUNCS.strip("\n") + "\n" + src[end:]

write(PATH, src)
print("editor_server.py 已改造：_generate_script -> JSON 范式")
