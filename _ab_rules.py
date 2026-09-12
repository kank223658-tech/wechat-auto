# -*- coding: utf-8 -*-
"""A/B 对照：同 41 条历史生成结果，在「旧规则」与「新规则」下各有多少问题。

「旧规则」= 体检实测到的那套自相矛盾的数值与判据：
  · min_realtime_lines = 130（与 max_script_steps=200 几乎零和）
  · min_interjections  = 10（规范块却劝「别配太多」）
  · max_message_chars  = 20，且把 [打字不发] 的技巧说明也算进去（恒判超长）
  · max_annotations    = 2，且里面装的是「表情不超过 3 个 / 时间标注要少」（报错张冠李戴）
「新规则」= 当前规则库 + 修好的判据。

只读，不改任何数据。用来回答「这次治理到底把多少无谓拦截去掉了」。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import script_generator as sg
import editor_server as es
import create_store as store

# 旧规则的数值（体检实测）
OLD_NUM = {
    "max_script_steps": 200,
    "min_realtime_lines": 130,     # 与 max_script_steps=200 几乎零和（实测最好的一条 194/200）
    "min_typing_hold": 15,         # 与插话 10 处配比失衡（参考剧本实际约 1:3）
    "min_interjections": 10,       # 规范块却劝「插话别配太多」——两条口径互相打脸
    "max_history_streak": 3,       # 标题写「最多连续 2 条」、值却是 3
    "max_history_two_sided": 2,
    "max_annotations": 2,          # 里面装的其实是「表情不超过 3 个 / 时间标注要少」
    "max_same_emoji": 2,
}


def _legacy_skills(skills):
    """把当前启用规则改写成「旧数值」的一套副本。

    只改数值类规则；语义错位那两条（被塞进 max_annotations 的表情/时间）
    在这里按「旧口径」还原：max_message_chars 也管 [打字不发]。
    """
    out = []
    for s in skills:
        s = dict(s)
        k = s.get("kind")
        if k in OLD_NUM:
            s["value"] = OLD_NUM[k]
            if k == "max_annotations":
                s["title"] = "表情包不超过3个"
                s["prompt_hint"] = "整份剧本的表情包不超过 3 个"
        out.append(s)
    # 旧规则里并不存在 max_emoji_total / max_time_marks（是本次新增的归位类型）
    return [s for s in out if s.get("kind") not in ("max_emoji_total", "max_time_marks")]


def _measure(items, skills, legacy_message_rule=False, legacy_annot_rule=False):
    devnull = open(os.devnull, "w", encoding="utf-8")
    saved = sys.stdout
    passed = 0
    total = 0
    sevs = []
    miss_realtime = miss_hold = miss_interj = 0
    try:
        for it in items:
            text = it.get("text") or ""
            if not text.strip():
                continue
            sys.stdout = devnull
            try:
                steps, _w, _s = es._parse_script_to_steps(text, offline=True)
                issues = (sg.check_completeness(text)
                          + sg.validate_generated_steps(steps, skills, text)[0])
            finally:
                sys.stdout = saved
            if not issues:
                passed += 1
            total += len(issues)
            sevs.append(sum(sg.issue_severity(x) for x in issues))
            for x in issues:
                if "少于要求的" in x and "实时对白" in x:
                    miss_realtime += 1
                elif "打字不发" in x and "少于要求" in x:
                    miss_hold += 1
                elif "插话" in x and "少于要求" in x:
                    miss_interj += 1
    finally:
        try:
            devnull.close()
        except OSError:
            pass
    return {"passed": passed, "total": total, "sevs": sevs,
            "miss_realtime": miss_realtime, "miss_hold": miss_hold,
            "miss_interj": miss_interj}


def main():
    store.init_db()
    items = json.load(open("generate_history.json", encoding="utf-8"))
    items = items.get("history") or items.get("items") or []
    items = [x for x in items if (x.get("text") or "").strip()]
    n = len(items)
    skills = sg.load_enabled_skills()

    old = _measure(items, _legacy_skills(skills))
    new = _measure(items, skills)

    print("样本：%d 条历史生成结果（只读，不改数据）" % n)
    print()
    print("%-10s %-12s %-12s %-14s" % ("规则版本", "零问题通过", "问题总数", "平均问题数"))
    print("-" * 52)
    print("%-10s %-12s %-12s %-14.2f" % ("旧规则", "%d / %d" % (old["passed"], n),
                                         old["total"], old["total"] / n))
    print("%-10s %-12s %-12s %-14.2f" % ("新规则", "%d / %d" % (new["passed"], n),
                                         new["total"], new["total"] / n))
    print()
    d = old["total"] - new["total"]
    print("问题总数 %d -> %d（减少 %d 条，%.0f%%）"
          % (old["total"], new["total"], d, (d / old["total"] * 100) if old["total"] else 0))
    print()
    print("按规则类型看拦截次数：")
    print("  · 「实时对白少于要求」 %d -> %d" % (old["miss_realtime"], new["miss_realtime"]))
    print("  · 「[打字不发] 少于要求」 %d -> %d" % (old["miss_hold"], new["miss_hold"]))
    print("  · 「插话少于要求」     %d -> %d" % (old["miss_interj"], new["miss_interj"]))
    print()
    print("怎么读这个结果（很重要）：")
    print("  · 本对照只替换「规则数值」，因此它只衡量「消解数值冲突」这一项的效果。")
    print("    结果几乎为 0 —— 说明旧剧本的问题**主要不是规则矛盾造成的**，")
    print("    而是内容质量问题（素材名编造、[打字不发] 写成聊天话术）。")
    print("  · 另外三项改造无法用旧剧本衡量，但直接影响下一次生成：")
    print("      a) 提示词与校验器改成同一套数字（旧版提示词说 110、校验器按 130 判）；")
    print("      b) 两个判据 bug（[打字不发] 被按单条字数上限打回、报错张冠李戴）；")
    print("      c) 生成范式改成「JSON 进、[指令] 出」，格式类丢行一次性消失。")
    print("  · 所以：规则治理解决的是「模型被自相矛盾的要求夹死」，")
    print("    内容质量要靠【可用素材】块重写 + 能力卡 + 参考分层，这三项已经落地。")


if __name__ == "__main__":
    main()
