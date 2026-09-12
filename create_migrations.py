# -*- coding: utf-8 -*-
"""创作模式的规则库 / 参考库治理迁移（v7、v8，各自幂等）

为什么单独放一个文件：
  create_store.py 已经有 6 个内联迁移，再往里塞几百行会越来越难读；
  这里放「治理型」迁移（不是补默认值，而是消解历史遗留的冲突），
  每条改动都写进 source_note，用户能在规则面板里看到「为什么被改了」并改回去。

v7 规则库治理（体检：39 条生成历史用当前校验器重跑 0 条能过，根因全在规则库自身）
v8 参考库分层（整篇做风格模板 + 片段示例做能力示范；搜索打分纳入效果分）
"""
import json
import re

import create_store as store


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _note(old, extra):
    old = str(old or "").strip()
    return (old + "；" + extra).strip("；") if old else extra


# ============================================================
# v7：规则库治理
# ============================================================

def run_v7():
    with store._lock:
        with store._db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v7','1')")
            if cur.rowcount == 0:
                return
            now = store._now()
            # 注意顺序：去重必须排在「语义归位」之后 —— 两条 max_annotations
            # （「表情包不超过3个」和「时间节点标注要少」）值都是 3，但它们管的完全是两件事，
            # 按 kind+value 去重会把其中一条误判成重复并停用。
            # enabled DESC 保证去重时保留的是启用中的那一条（而不是随机的）。
            rows = [dict(r) for r in conn.execute(
                "SELECT id,type,kind,value,title,prompt_hint,enabled,source_note FROM skills"
                " ORDER BY enabled DESC, created_at ASC").fetchall()]

            def _set(sid, **patch):
                fields, values = [], []
                for k, v in patch.items():
                    if k == "value":
                        fields.append("value=?")
                        values.append(store._json_dump(v) if v is not None else None)
                    elif k == "enabled":
                        fields.append("enabled=?")
                        values.append(1 if v else 0)
                    else:
                        fields.append("%s=?" % k)
                        values.append(v)
                fields.append("updated_at=?")
                values.append(now)
                values.append(sid)
                conn.execute("UPDATE skills SET %s WHERE id=?" % ",".join(fields), values)

            # ---- 1) max_annotations 语义归位：表情数 / 时间标注各自独立 ----
            for r in rows:
                if r["kind"] != "max_annotations":
                    continue
                text = str(r["title"] or "") + str(r["prompt_hint"] or "")
                n = _num(store._json_load(r["value"], None))
                if ("表情" in text) or ("emoji" in text.lower()):
                    _set(r["id"], kind="max_emoji_total",
                         title="整份剧本发出的表情不超过 %s 个" % (n or 3),
                         prompt_hint="整份剧本发出的表情（贴纸表情包 + 3D emoji）合计不超过 %s 个，"
                                     "表情是调味料，不要在整段里一直发表情" % (n or 3),
                         source_note=_note(r["source_note"],
                                           "原为 max_annotations（注解处数），语义错位："
                                           "它管的是表情数量，已归位为 max_emoji_total"))
                elif "时间" in text:
                    _set(r["id"], kind="max_time_marks",
                         title="实时对白里的时间标注不超过 %s 处" % (n or 3),
                         prompt_hint="实时对白里的时间分隔条（`内容 | 18:22`）不超过 %s 处，"
                                     "只钉在关键节点，不要每条消息都挂一个时间点"
                                     "（历史会话块里的时间戳不计入）" % (n or 3),
                         source_note=_note(r["source_note"],
                                           "原为 max_annotations（注解处数），语义错位："
                                           "它管的是时间标注，已归位为 max_time_marks"))
                else:
                    _set(r["id"], value=2,
                         title="策略注释不许当成消息发出去",
                         prompt_hint="策略注释 / 心理活动只允许写在 [打字不发] 的技巧说明里，"
                                     "绝不能作为 [我方打字] 发出去；[打字不发] 的正文不限处数",
                         source_note=_note(r["source_note"],
                                           "已统一为「只兜住 [我方打字] 里的策略注释」，"
                                           "不再限制 [打字不发] 的处数"))

            # ---- 2) 去重：同 kind + 同 value 只留一条 ----
            seen = {}
            for r in rows:
                if (r["type"] or "rule") != "rule" or not r["kind"]:
                    continue
                key = (r["kind"], store._json_dump(store._json_load(r["value"], None)))
                if key in seen:
                    _set(r["id"], enabled=0,
                         source_note=_note(r["source_note"],
                                           "与规则「%s」完全重复，已自动停用" % seen[key]))
                else:
                    seen[key] = r["title"] or r["kind"]

            # ---- 2) max_message_chars 取值冲突：保留最严的那条 ----
            mcs = [(r, _num(store._json_load(r["value"], None)))
                   for r in rows if r["kind"] == "max_message_chars"]
            mcs = [(r, n) for r, n in mcs if n]
            if len(mcs) > 1:
                keep = min(mcs, key=lambda x: x[1])
                for r, n in mcs:
                    if r["id"] == keep[0]["id"]:
                        continue
                    _set(r["id"], enabled=0,
                         source_note=_note(r["source_note"],
                                           "与「%s」（上限 %d 字）取值冲突，已自动停用（保留更严的一条）"
                                           % (keep[0]["title"] or "", keep[1])))

            # ---- 4) 篇幅：min_realtime_lines ⟂ max_script_steps 收敛 ----
            for r in rows:
                if r["kind"] != "min_realtime_lines":
                    continue
                n = _num(store._json_load(r["value"], None))
                text = str(r["title"] or "") + str(r["prompt_hint"] or "")
                if "步" in text:
                    _set(r["id"], value=110,
                         title="实时对白不少于 110 条",
                         prompt_hint="实时对白（历史会话块以外的 [我方打字]/[对方发消息]/[打字不发]）"
                                     "不少于 110 条；整份剧本的实时指令不超过 200 步，两条一起满足",
                         source_note=_note(r["source_note"],
                                           "原文案「篇幅拉到150步左右」被抽成了「对白不少于150条」，"
                                           "与 max_script_steps=200 互斥（实测最好的一条 194/200 步）；"
                                           "已按参考剧本实测比例（对白/步数≈0.6：112/189、56/126、"
                                           "125/194）收敛为 110 条"))
                elif n and n > 110:
                    _set(r["id"], value=110,
                         source_note=_note(r["source_note"],
                                           "与 max_script_steps 按参考比例收敛为 110 条"))
            for r in rows:
                if r["kind"] == "max_script_steps":
                    _set(r["id"], title="整份剧本的实时指令不超过 200 步",
                         prompt_hint="整份剧本的实时指令（[历史会话] 块以外的所有 [动作] 行）"
                                     "控制在 200 步以内；实时对白不少于 110 条，两条一起满足；"
                                     "节奏靠「打字不发 → 删除 → 再打字」，不要靠多开来回、"
                                     "堆 [对方正在输入]/[等待] 拉长")

            # 配套：把篇幅预算写进 max_script_steps 已覆盖，另外新增一条 style 汇总
            # ---- 5) max_history_streak：值 3 与标题「2 条」不符 ----
            for r in rows:
                if r["kind"] != "max_history_streak":
                    continue
                n = _num(store._json_load(r["value"], None))
                if n and n != 2:
                    _set(r["id"], value=2,
                         source_note=_note(r["source_note"],
                                           "标题写「最多连续 2 条」而值是 %d，已按标题统一为 2" % n))

            # ---- 6) 插话口径统一（参考剧本约 1:3）----
            hold = 15
            for r in rows:
                if r["kind"] == "min_typing_hold":
                    hold = _num(store._json_load(r["value"], None)) or hold
            ij_ok = max(2, int(round(hold / 3.0)))
            for r in rows:
                if r["kind"] != "min_interjections":
                    continue
                n = _num(store._json_load(r["value"], None)) or ij_ok
                if n != ij_ok:
                    _set(r["id"], value=ij_ok,
                         title="至少 %d 处「插话」" % ij_ok,
                         prompt_hint="整份剧本至少 %d 处带「插话」（约等于 [打字不发] 处数的 1/3）；"
                                     "参考剧本 44~50 处打字不发配 15~18 处插话；"
                                     "插话配太多会显得对方一直在抢话" % ij_ok,
                         source_note=_note(r["source_note"],
                                           "原要求 %d 处，与「打字不发 %d 处」配比失衡"
                                           "（参考剧本约 1:3），已统一为 %d 处"
                                           % (n, hold, ij_ok)))

            # ---- 7) style 条目不该带 value ----
            for r in rows:
                if (r["type"] or "rule") == "style" and store._json_load(r["value"], None) is not None:
                    _set(r["id"], value=None,
                         source_note=_note(r["source_note"], "风格条目不应带数值，已清空 value"))

            # ---- 8) 「出场人物 ≤ 3」补一句：历史会话列表不算出场人物 ----
            for r in rows:
                if r["kind"] == "max_people":
                    _set(r["id"],
                         prompt_hint="真正 [打开聊天] 展开对白的对象不超过 3 人"
                                     "（历史会话列表里有 9 个会话不算出场人物，那只是列表预览）")

            # ---- 9) 补「篇幅预算」风格规则 ----
            if not conn.execute("SELECT 1 FROM skills WHERE prompt_hint LIKE '%篇幅预算%' LIMIT 1").fetchone():
                conn.execute(
                    "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,"
                    "source_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (store._new_id("sk"), "style", "篇幅预算（四个数字一起看）", None, None,
                     "篇幅按一个预算来配：整份实时指令 ≤200 步、实时对白 ≥110 条、"
                     "[打字不发] ≥15 处（越多越好，参考 44~50 处）、插话 ≈ [打字不发] 的 1/3。"
                     "四条互相配套，不要只把其中一条拉满。",
                     1, store._json_dump([]), "系统默认规则（本轮治理：消解互斥规则）", now, now))

            # ---- 10) 补「新功能要用起来」风格规则 ----
            if not conn.execute("SELECT 1 FROM skills WHERE prompt_hint LIKE '%能力卡%' LIMIT 1").fetchone():
                conn.execute(
                    "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,"
                    "source_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (store._new_id("sk"), "style",
                     "新功能要真的用起来（底部面板 / emoji / 朋友圈 / 转账）", None, None,
                     "提示词里每个新动作都附了「何时用 + 片段示例」（能力卡）："
                     "切换底部面板 / 面板切换序列（聊天中段切一下表情面板再收起）、"
                     "发送emoji / 对方emoji（3D 黄脸表情，先弹笑脸面板再发）、"
                     "进入朋友圈 + 点赞 / 评论 / 发朋友圈（开出第二条叙事线）、"
                     "手机状态栏（开场切成参考场景）、转账 / 对方转账（默认关闭，规则要求时才用）。"
                     "整份剧本至少用上其中 1~2 个，而不是通篇只有打字和发消息。",
                     1, store._json_dump([]), "系统默认规则（本轮治理：新功能接入）", now, now))


# ============================================================
# v8：参考库分层 + 搜索打分纳入效果分
# ============================================================

def run_v9():
    """一次性修补：v7 首次执行时的顺序 bug 造成的两处残留。

    v7 最初把「按 kind+value 去重」放在了「语义归位」之前，而
    「表情包不超过3个」与「时间节点标注要少」两条 max_annotations 的值都是 3、
    却管着完全不同的两件事，于是被当成重复互相停用：
      - 「表情包不超过3个」被停用（它本该是启用中的 max_emoji_total）；
      - 「时间节点标注要少」被落到了 else 分支，重新变成了 max_annotations。
    v7 内部的顺序已修正（见 create_migrations.run_v7 顶部说明），
    这里只负责把已经跑过一次的库修补回来。幂等。
    """
    with store._lock:
        with store._db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v9','1')")
            if cur.rowcount == 0:
                return
            now = store._now()
            rows = [dict(r) for r in conn.execute(
                "SELECT id,kind,value,title,enabled,source_note FROM skills"
                " ORDER BY enabled DESC, created_at ASC").fetchall()]

            # 1) 「表情数」规则应当生效（它是用户明确写的数字，不该躺着不动）
            for r in rows:
                if r["kind"] == "max_emoji_total" and not r["enabled"]:
                    conn.execute(
                        "UPDATE skills SET enabled=1, updated_at=?, source_note=? WHERE id=?",
                        (now, _note(r["source_note"],
                                    "v7 首次执行时的去重顺序 bug 把它误停用了，已恢复启用"), r["id"]))

            # 2) 剩下多余的那条 max_annotations 归位成 max_time_marks
            ann = [r for r in rows if r["kind"] == "max_annotations"]
            if len(ann) > 1:
                # 保留「策略注释不许当成消息发出去」这条；其余按来源归位
                for r in ann[1:]:
                    conn.execute(
                        "UPDATE skills SET kind='max_time_marks', enabled=0, value=?,"
                        " title=?, prompt_hint=?, updated_at=?, source_note=? WHERE id=?",
                        (store._json_dump(3),
                         "实时对白里的时间标注不超过 3 处",
                         "实时对白里的时间分隔条（`内容 | 22:`）不超过 3 处，只钉在关键节点，"
                         "不要每条消息都挂一个时间点（历史会话块里的时间戳不计入）",
                         now, _note(r["source_note"],
                                    "原为 max_annotations（注解处数），语义错位：它管的是时间标注，"
                                    "已归位为 max_time_marks"), r["id"]))

            # 3) 再跑一遍去重（此时顺序已正确），顺手把残留的重复收干净
            seen = {}
            for r in rows:
                if not r["kind"]:
                    continue
                key = (r["kind"], store._json_dump(store._json_load(r["value"], None)))
                if key in seen:
                    conn.execute(
                        "UPDATE skills SET enabled=0, updated_at=?, source_note=? WHERE id=?",
                        (now, _note(r["source_note"],
                                    "与规则「%s」完全重复，已自动停用" % seen[key]), r["id"]))
                else:
                    seen[key] = r["title"] or r["kind"]


def _sync_snippet_refs(conn, now=None):
    """把动作表里的能力卡片段同步进参考库（幂等，只补缺、不改用户改过的）。

    能力卡是「新功能怎么演」的示范；没有它们，模型只见过动作名、永远想不起来用。
    每次 init_db 都会跑一遍：以后往 action_registry 里加新动作 + 片段，
    参考库会自动跟着长出来，不需要再手写一条迁移。
    """
    now = now or store._now()
    try:
        import action_registry as ar
        cards = ar.capability_cards()
    except Exception:                                          # noqa: BLE001
        return 0
    existing = {str(r["title"] or "") for r in
                conn.execute("SELECT title FROM ref_scripts").fetchall()}
    added = 0
    for c in cards:
        title = "片段 · " + c["action"]
        if title in existing:
            continue
        body = "\n".join(c["snippet"])
        summary = "演的是：%s" % (c["when"] or c["desc"] or c["action"])
        conn.execute(
            "INSERT INTO ref_scripts(id,title,category,topics,tags,summary,text,"
            "created_at,updated_at,kind,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (store._new_id("ref"), title, "", store._json_dump([]),
             store._json_dump(["新功能", c["action"]]), summary, body,
             now, now, "snippet", "系统内置片段示例（新功能接入用）"))
        added += 1
    return added


def run_v10():
    """每次启动都跑：把动作表新加的能力卡片段补进参考库（幂等）。"""
    with store._lock:
        with store._db() as conn:
            return _sync_snippet_refs(conn)


def run_v8():
    with store._lock:
        with store._db() as conn:
            # 参考剧本加 kind / note 两列（full=整篇风格模板 / snippet=片段示例）
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(ref_scripts)").fetchall()}
            if "kind" not in cols:
                conn.execute("ALTER TABLE ref_scripts ADD COLUMN kind TEXT DEFAULT 'full'")
            if "note" not in cols:
                conn.execute("ALTER TABLE ref_scripts ADD COLUMN note TEXT DEFAULT ''")

            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v8','1')")
            if cur.rowcount == 0:
                return
            now = store._now()

            # 按内容自动分层：短小（<= 14 行）且不含 [历史会话] 的，视为片段示例
            for row in conn.execute("SELECT id,text,kind FROM ref_scripts").fetchall():
                text = str(row["text"] or "")
                lines = [x for x in text.splitlines() if x.strip()]
                is_snippet = len(lines) <= 14 and "[历史会话]" not in text
                if (row["kind"] or "full") != ("snippet" if is_snippet else "full"):
                    conn.execute("UPDATE ref_scripts SET kind=?, updated_at=? WHERE id=?",
                                 ("snippet" if is_snippet else "full", now, row["id"]))

            # 把新功能片段示例作为「参考片段」入库
            _sync_snippet_refs(conn, now)
