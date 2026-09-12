# -*- coding: utf-8 -*-
"""
创作模式数据层（SQLite）
========================
把「规则库(skill)」与「参考剧本库」从「JSON 整文件覆盖」改为 SQLite 事务存储。

解决旧版三个根因问题：
  1. script_generator._save_raw 把 OSError 直接 pass —— 写失败用户完全不知道；
  2. 整文件覆盖写、无备份 —— 进程中断可能把 JSON 截断；
  3. 参考剧本标题取「文本第一行」，而参考第一行恒为 [历史会话]，导致列表里
     所有参考标题都是「[历史会话]…」，用户根本没法区分要选哪条。

数据文件：create.db（项目根目录，与其它 JSON 同级，便于直接复制备份）
  skills      规则库：由评价拆解出的可校验规则 + 风格要求
  ref_scripts 参考剧本库：带标题、标签、适用主题、效果分
  meta        迁移标记等
"""

import contextlib
import json
import os
import re
import sqlite3
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "create.db")
REF_JSON = os.path.join(ROOT, "reference_scripts.json")
FEEDBACK_JSON = os.path.join(ROOT, "feedback.json")

_lock = threading.RLock()
_initialized = False
_initializing = False
_id_seq = 0


# ============================================================
# 连接 / 建表
# ============================================================

def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def _db():
    """一次事务：正常提交，异常回滚。任何写失败都会抛出去，绝不静默吞掉。"""
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
  id              TEXT PRIMARY KEY,
  type            TEXT NOT NULL DEFAULT 'rule',   -- rule=可校验规则 / style=风格要求
  title           TEXT NOT NULL,
  kind            TEXT,                           -- 规则类型（type=rule 时有效）
  value           TEXT,                           -- JSON：规则参数
  prompt_hint     TEXT,                           -- 注入提示词时的表述
  enabled         INTEGER NOT NULL DEFAULT 1,
  hits            INTEGER NOT NULL DEFAULT 0,     -- 被校验器命中的次数
  source_feedback TEXT,                           -- JSON 数组：来源评价 id
  source_note     TEXT,
  created_at      REAL,
  updated_at      REAL
);

CREATE TABLE IF NOT EXISTS ref_scripts (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  category    TEXT,
  topics      TEXT,                               -- JSON 数组：适用主题
  tags        TEXT,                               -- JSON 数组：手法标签
  summary     TEXT,                               -- 结构摘要
  text        TEXT,
  use_count   INTEGER NOT NULL DEFAULT 0,         -- 被用于生成的次数
  rated_count INTEGER NOT NULL DEFAULT 0,         -- 被评价过的次数
  score_sum   REAL NOT NULL DEFAULT 0,            -- 评分累加
  created_at  REAL,
  updated_at  REAL
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def init_db():
    """建表 + 一次性迁移旧 JSON（幂等）。

    注意：迁移过程会调用 add_reference / add_skill，它们内部也会调用 init_db；
    因此必须用 _initializing 挡住递归，否则会在迁移里无限重入。
    """
    global _initialized, _initializing
    with _lock:
        if _initialized or _initializing:
            return
        _initializing = True
        try:
            conn = _connect()
            try:
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                except sqlite3.OperationalError:
                    # 多进程首次并发建库时可能短暂拿不到写锁；WAL 已由其它连接设置，忽略即可
                    pass
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()
            _migrate_json()
            _migrate_v2()
            _migrate_v3()
            _migrate_v4()
            _migrate_v5()
            _migrate_v6()
            _migrate_v7()
            _migrate_v8()
            _migrate_v9()
            _migrate_v10()
            _initialized = True
        finally:
            _initializing = False


def _meta_get(conn, key, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return row["v"] if row else default


def _meta_set(conn, key, value):
    conn.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                 (key, str(value)))


# ============================================================
# 小工具
# ============================================================

def _now():
    return time.time()


def _new_id(prefix):
    """生成唯一 id：毫秒时间戳 + 进程内自增序号。

    旧版只用毫秒时间戳，同一毫秒内连续插入多条（如迁移时批量建默认规则）
    会撞 UNIQUE 约束直接抛 IntegrityError。
    """
    global _id_seq
    with _lock:
        _id_seq += 1
        seq = _id_seq
    return "%s-%d-%d" % (prefix, int(time.time() * 1000), seq)


def _json_load(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False)


def _as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()]


# ============================================================
# 参考剧本：自动标题 / 摘要 / 标签
# ============================================================

_REF_TITLE_BAD = re.compile(r"^\s*[\[\【]\s*历史会话\s*[\]\】]")


def derive_reference_title(text):
    """给参考剧本生成可辨识的标题。

    旧版直接取第一行，而所有参考第一行都是 [历史会话]，于是列表里全是
    「[历史会话]…」。这里改成「主对象 · 会话数 · 首句」的规则标题，
    让用户在参考列表里一眼能分清每一条。
    """
    body = (text or "").strip()
    if not body:
        return "未命名参考"
    names = [n.strip() for n in re.findall(r"\[会话\]\s*([^\n\r]+)", body) if n.strip()]
    opened = [n.strip() for n in re.findall(r"\[打开聊天\]\s*([^\n\r|]+)", body) if n.strip()]
    main = opened[0] if opened else (names[0] if names else "")
    first_line = ""
    for ln in body.splitlines():
        m = re.match(r"\[(?:我方打字|对方发消息)\]\s*(.+)", ln.strip())
        if m:
            first_line = m.group(1).split("|")[0].strip()
            break
    bits = []
    if main:
        bits.append(main)
    if names:
        bits.append("%d 个会话" % len(names))
    if first_line:
        bits.append(first_line[:14])
    title = " · ".join(bits)
    return title or body.splitlines()[0][:20]


def derive_reference_summary(text):
    """结构摘要：会话数、我方/对方消息条数、用到的动作种类。"""
    body = text or ""
    sessions = len(re.findall(r"\[会话\]", body))
    mine = len(re.findall(r"\[我方打字\]", body))
    peer = len(re.findall(r"\[对方发消息\]", body))
    hold = len(re.findall(r"\[打字不发\]", body))
    acts = sorted(set(re.findall(r"\[([^\]]+)\]", body)) - {"历史会话", "历史会话结束", "会话"})
    bits = ["%d 会话" % sessions, "我方 %d 条" % mine, "对方 %d 条" % peer]
    if hold:
        bits.append("打字不发 %d 处" % hold)
    if acts:
        bits.append("动作：" + "、".join(acts[:8]))
    return " · ".join(bits)


# 手法标签：命中关键词即打标签，纯规则、不调大模型
_TAG_RULES = [
    ("共情", ("共情", "理解", "认同", "感受", "辛苦", "累")),
    ("调动情绪", ("情绪", "撩", "逗", "反转", "拉扯", "博弈", "悬念")),
    ("冷读", ("冷读", "猜你", "你是不是", "其实你")),
    ("探知三观", ("三观", "想法", "怎么看", "价值观", "原则")),
    ("拉高格局", ("格局", "层次", "段位", "成熟", "松弛")),
    ("邀约", ("邀约", "见面", "一起", "出来", "请你", "几点", "周末")),
    ("破冰", ("破冰", "第一句", "开场", "刚加")),
    ("已读不回", ("已读不回", "不回", "没回")),
    ("后台消息", ("后台", "未读")),
    ("图片", ("[图片]", "配图", "截图")),
    ("表情", ("[表情]", "表情")),
    ("链接卡", ("[链接]", "发链接")),
]


def derive_reference_tags(text):
    body = text or ""
    return [name for name, kws in _TAG_RULES if any(k in body for k in kws)]


def derive_reference_topics(text, title=""):
    """适用主题：优先取标题/正文里的话题词，取不到就用标签兜底。"""
    body = (text or "") + "\n" + (title or "")
    topics = []
    for name, kws in _TAG_RULES:
        if any(k in body for k in kws):
            topics.append(name)
    # 常见主题词
    for kw in ("已读不回", "来姨妈", "升温", "不知道聊什么", "加班", "聚餐", "表白", "分手", "复合"):
        if kw in body and kw not in topics:
            topics.append(kw)
    return topics[:8]


# ============================================================
# 参考剧本 CRUD
# ============================================================

def _ref_row_to_dict(row):
    d = dict(row)
    d["topics"] = _json_load(d.get("topics"), [])
    d["tags"] = _json_load(d.get("tags"), [])
    d["kind"] = d.get("kind") or "full"      # full=整篇风格模板 / snippet=片段示例
    d["note"] = d.get("note") or ""
    rated = int(d.get("rated_count") or 0)
    d["score"] = round(float(d.get("score_sum") or 0) / rated, 2) if rated else 0
    return d


def list_references():
    init_db()
    with _db() as conn:
        rows = conn.execute("SELECT * FROM ref_scripts ORDER BY created_at DESC").fetchall()
    return [_ref_row_to_dict(r) for r in rows]


def get_reference(ref_id):
    init_db()
    with _db() as conn:
        row = conn.execute("SELECT * FROM ref_scripts WHERE id=?", (str(ref_id),)).fetchone()
    return _ref_row_to_dict(row) if row else None


def get_references_by_ids(ids):
    """按 id 列表取参考（保持挑选顺序）。"""
    wanted = [str(x) for x in (ids or [])]
    if not wanted:
        return []
    items = {r["id"]: r for r in list_references()}
    return [items[i] for i in wanted if i in items]


def add_reference(title="", text="", category="", topics=None, tags=None, summary="",
                  created_at=None, kind="", note=""):
    """新增参考剧本。标题为空或是旧的「[历史会话]…」时，自动生成可辨识标题。

    kind：'full'=整篇（当风格模板）/ 'snippet'=片段示例（当能力示范）。
    留空时按内容自动判定：短小且不含 [历史会话] 的算片段。
    """
    init_db()
    body = (text or "").strip()
    clean_title = (title or "").strip()
    if not clean_title or _REF_TITLE_BAD.match(clean_title) or clean_title in ("未命名", "未命名参考"):
        clean_title = derive_reference_title(body)
    lines = [x for x in body.splitlines() if x.strip()]
    auto_kind = "snippet" if (len(lines) <= 14 and "[历史会话]" not in body) else "full"
    item = {
        "id": _new_id("ref"),
        "title": clean_title,
        "category": (category or "").strip(),
        "topics": _as_list(topics) if topics else derive_reference_topics(body, clean_title),
        "tags": _as_list(tags) if tags else derive_reference_tags(body),
        "summary": (summary or "").strip() or derive_reference_summary(body),
        "text": body,
        "kind": (kind or "").strip() or auto_kind,
        "note": (note or "").strip(),
        "created_at": float(created_at or _now()),
    }
    with _db() as conn:
        conn.execute(
            "INSERT INTO ref_scripts(id,title,category,topics,tags,summary,text,created_at,updated_at,"
            "kind,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (item["id"], item["title"], item["category"], _json_dump(item["topics"]),
             _json_dump(item["tags"]), item["summary"], item["text"], item["created_at"],
             item["created_at"], item["kind"], item["note"]))
    return item


def update_reference(ref_id, patch):
    init_db()
    fields, values = [], []
    for key in ("title", "category", "summary", "text"):
        if key in patch:
            fields.append("%s=?" % key)
            values.append(str(patch.get(key) or "").strip())
    for key in ("topics", "tags"):
        if key in patch:
            fields.append("%s=?" % key)
            values.append(_json_dump(_as_list(patch.get(key))))
    for key in ("kind", "note"):
        if key in patch:
            fields.append("%s=?" % key)
            values.append(str(patch.get(key) or "").strip())
    if not fields:
        return get_reference(ref_id)
    fields.append("updated_at=?")
    values.append(_now())
    values.append(str(ref_id))
    with _db() as conn:
        conn.execute("UPDATE ref_scripts SET %s WHERE id=?" % ",".join(fields), values)
    return get_reference(ref_id)


def delete_reference(ref_id):
    init_db()
    with _db() as conn:
        cur = conn.execute("DELETE FROM ref_scripts WHERE id=?", (str(ref_id),))
    return cur.rowcount > 0


def bump_reference_use(ids, score=None):
    """记录「哪些参考参与了这次生成」，以及该次生成的评分（有分时回填效果分）。"""
    use_ids = [str(x) for x in (ids or []) if str(x).strip()]
    if not use_ids:
        return
    init_db()
    with _db() as conn:
        for rid in use_ids:
            if score is None:
                conn.execute("UPDATE ref_scripts SET use_count=use_count+1, updated_at=? WHERE id=?",
                             (_now(), rid))
            else:
                conn.execute(
                    "UPDATE ref_scripts SET use_count=use_count+1, rated_count=rated_count+1,"
                    " score_sum=score_sum+?, updated_at=? WHERE id=?",
                    (float(score), _now(), rid))


def rate_references(ids, score):
    """把一次评价的分值回填给参与该次生成的参考剧本（用于效果分排序）。"""
    use_ids = [str(x) for x in (ids or []) if str(x).strip()]
    if not use_ids or score is None:
        return
    init_db()
    with _db() as conn:
        for rid in use_ids:
            conn.execute(
                "UPDATE ref_scripts SET rated_count=rated_count+1, score_sum=score_sum+?, updated_at=?"
                " WHERE id=?", (float(score), _now(), rid))


def _query_terms(query):
    """把中文主题拆成可匹配的词项。

    旧版只按空格/标点切分，而中文主题（如"女生已读不回怎么聊"）没有空格，
    会变成一整个词，几乎匹配不到任何参考。这里补充中文 2-gram，
    让"已读不回""女生"这类关键词能命中参考剧本的标题/标签/正文。
    """
    q = re.sub(r"[\s,，。；;、/|？?！!：:]+", " ", str(query or "")).strip()
    terms = [t for t in q.split() if len(t) >= 2]
    for t in list(terms):
        if len(t) >= 4 and re.search(r"[\u4e00-\u9fff]", t):
            terms += [t[i:i + 2] for i in range(len(t) - 1)]
    seen, out = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def search_references(query, limit=3):
    """按主题关键词给参考剧本打分，返回最相关的若干条（用于「按主题推荐参考」）。"""
    tokens = _query_terms(query)
    if not tokens:
        return []
    scored = []
    for ref in list_references():
        hay_title = (ref.get("title") or "")
        hay_topics = " ".join(ref.get("topics") or []) + " " + " ".join(ref.get("tags") or [])
        hay_text = ref.get("text") or ""
        score = 0.0
        for t in tokens:
            if t in hay_title:
                score += 4
            if t in hay_topics:
                score += 3
            score += min(hay_text.count(t), 5) * 0.5
        if score > 0:
            # 效果分 / 被采用次数一起参与排序：被评过 5 星、被反复采用的好参考优先。
            # 旧版只看关键词命中，用户辛苦评的分完全不参与挑选。
            score += float(ref.get("score") or 0) * 1.5
            score += min(int(ref.get("use_count") or 0), 10) * 0.3
            # 整篇参考当风格模板更有效；片段只在关键词高度命中时才顶上来
            if (ref.get("kind") or "full") == "full":
                score += 1.0
            scored.append((score, ref))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


# ============================================================
# 规则库（skill）CRUD
# ============================================================

RULE_KINDS = (
    "banned_action",        # 禁用动作，value: 动作名或数组
    "required_action",      # 必须包含的动作
    "min_sessions",         # 最少会话数
    "min_history_messages",  # 历史消息最少条数
    "min_realtime_lines",   # 实时对白最少条数
    "max_message_chars",    # 单条消息最大字数
    "forbid_text",          # 消息里禁止出现的词
    "forbid_annotation_as_message",  # 禁止把心理活动注释当消息发出
    "opening_image",        # 开头要有图片
    "max_people",           # 参与人数上限
    "max_annotations",      # 策略注释/心理活动最多出现几处
    "history_two_sided",    # 历史会话必须双方有来有回
    "max_history_streak",   # 历史会话里同一人最多连续几条
    "min_interjections",    # 至少几处「插话」
    "min_typing_hold",      # 至少几处「打字不发」
    "max_script_steps",     # 整份剧本的实时指令步数上限
    "asset_ref_plain",      # 图片/表情引用只能写图库里的短名
    "asset_ref_exists",     # 图片/表情引用必须能解析到真实文件
    "max_same_emoji",       # 同一个表情最多重复几次
    "max_wait_ratio",       # 紧跟 [等待] 的我方消息占比上限
    "min_burst",            # 实时对白里至少一方连发几条
    "max_emoji_total",      # 整份剧本发出的表情总数上限（含 3D emoji）
    "max_time_marks",       # 时间分隔条处数上限
    "max_history_two_sided",  # 历史会话里最多几个会话带「我：」的回复
)

_KIND_LABELS = {
    "banned_action": "禁用动作",
    "required_action": "必须包含动作",
    "min_sessions": "最少会话数",
    "min_history_messages": "历史消息最少条数",
    "min_realtime_lines": "实时对白最少条数",
    "max_message_chars": "单条消息最大字数",
    "forbid_text": "消息中禁止出现",
    "forbid_annotation_as_message": "禁止把心理活动写成消息",
    "opening_image": "开头必须有图片",
    "max_people": "参与人数上限",
    "max_annotations": "策略注释最多几处",
    "history_two_sided": "历史会话整体要有双方对话",
    "max_history_streak": "历史会话同一人最多连续几条",
    "min_interjections": "至少几处「插话」",
    "min_typing_hold": "至少几处「打字不发」",
    "max_script_steps": "实时指令步数上限",
    "asset_ref_plain": "图片/表情只能写图库短名",
    "asset_ref_exists": "图片/表情必须能解析到真图",
    "max_same_emoji": "同一个表情最多重复几次",
    "max_wait_ratio": "紧跟[等待]的我方消息占比上限",
    "min_burst": "至少一方连发几条",
    "max_emoji_total": "整份表情数量上限",
    "max_time_marks": "时间分隔条数量上限",
    "max_history_two_sided": "历史会话带「我：」回复的会话数上限",
}


def rule_kind_options():
    """给前端用的规则类型下拉选项。"""
    return [{"kind": k, "label": _KIND_LABELS.get(k, k)} for k in RULE_KINDS]


def _skill_row_to_dict(row):
    d = dict(row)
    d["value"] = _json_load(d.get("value"), None)
    d["source_feedback"] = _json_load(d.get("source_feedback"), [])
    d["enabled"] = bool(d.get("enabled"))
    d["kind_label"] = _KIND_LABELS.get(d.get("kind") or "", d.get("kind") or "")
    return d


def list_skills(enabled_only=False):
    init_db()
    with _db() as conn:
        sql = "SELECT * FROM skills"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY enabled DESC, created_at DESC"
        rows = conn.execute(sql).fetchall()
    return [_skill_row_to_dict(r) for r in rows]


def get_skill(skill_id):
    init_db()
    with _db() as conn:
        row = conn.execute("SELECT * FROM skills WHERE id=?", (str(skill_id),)).fetchone()
    return _skill_row_to_dict(row) if row else None


def add_skill(title, kind=None, value=None, skill_type="rule", prompt_hint="",
              enabled=True, source_feedback=None, source_note=""):
    init_db()
    sid = _new_id("sk")
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,source_note,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (sid, skill_type, (title or "").strip() or "未命名规则", kind,
             _json_dump(value) if value is not None else None,
             (prompt_hint or "").strip(), 1 if enabled else 0,
             _json_dump(_as_list(source_feedback)), (source_note or "").strip(), now, now))
    return get_skill(sid)


def update_skill(skill_id, patch):
    init_db()
    fields, values = [], []
    for key in ("title", "kind", "prompt_hint", "type", "source_note"):
        if key in patch:
            fields.append("%s=?" % key)
            values.append(patch.get(key))
    if "value" in patch:
        fields.append("value=?")
        values.append(_json_dump(patch.get("value")) if patch.get("value") is not None else None)
    if "enabled" in patch:
        fields.append("enabled=?")
        values.append(1 if patch.get("enabled") else 0)
    if "source_feedback" in patch:
        fields.append("source_feedback=?")
        values.append(_json_dump(_as_list(patch.get("source_feedback"))))
    if not fields:
        return get_skill(skill_id)
    fields.append("updated_at=?")
    values.append(_now())
    values.append(str(skill_id))
    with _db() as conn:
        conn.execute("UPDATE skills SET %s WHERE id=?" % ",".join(fields), values)
    return get_skill(skill_id)


def delete_skill(skill_id):
    init_db()
    with _db() as conn:
        cur = conn.execute("DELETE FROM skills WHERE id=?", (str(skill_id),))
    return cur.rowcount > 0


def bump_skill_hits(skill_ids):
    """校验命中时累加命中次数，让用户看到规则真的在起作用。"""
    ids = [str(x) for x in (skill_ids or []) if str(x).strip()]
    if not ids:
        return
    init_db()
    with _db() as conn:
        for sid in ids:
            conn.execute("UPDATE skills SET hits=hits+1, updated_at=? WHERE id=?", (_now(), sid))


def clear_skills():
    init_db()
    with _db() as conn:
        conn.execute("DELETE FROM skills")


# ============================================================
# 迁移旧 JSON
# ============================================================

def _migrate_json():
    """把旧的 reference_scripts.json / feedback.json 里的偏好导入 SQLite（只做一次）。

    用「主键抢占」保证原子性：只有一个线程/进程能 INSERT 成功，
    其余 rowcount=0 直接返回。旧版先查标记再写入，检查与写入之间有间隙，
    ThreadingHTTPServer 的多个请求线程会同时通过检查，导致重复迁移几十次。
    """
    with _lock:
        with _db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v1','1')")
            if cur.rowcount == 0:
                return

        # 参考剧本
        if os.path.exists(REF_JSON):
            try:
                with open(REF_JSON, "r", encoding="utf-8") as fh:
                    data = json.load(fh) or {}
                for s in data.get("scripts", []) or []:
                    if not isinstance(s, dict):
                        continue
                    add_reference(
                        title=s.get("title") or "",
                        text=s.get("text") or "",
                        category=s.get("category") or "",
                        created_at=s.get("created_at") or _now(),
                    )
            except (OSError, ValueError):
                pass

        # 旧偏好 -> 待确认的风格规则
        if os.path.exists(FEEDBACK_JSON):
            try:
                with open(FEEDBACK_JSON, "r", encoding="utf-8") as fh:
                    fb = json.load(fh) or {}
                pref = fb.get("preferences") or ""
                for line in str(pref).splitlines():
                    line = line.strip()
                    if not line.startswith("-"):
                        continue
                    text = line.lstrip("-").strip()
                    if len(text) < 2:
                        continue
                    add_skill(
                        title=text, skill_type="style", prompt_hint=text,
                        enabled=False, source_note="来自旧版偏好，请确认是否启用")
            except (OSError, ValueError):
                pass


# ============================================================
# 迁移 v2：让「评价沉淀」真正生效
# ============================================================
# 背景（旧版根因）：v1 把 feedback.json 里的偏好导成 skills 时统一 enabled=False，
# 而生成提示词只读 enabled 的 skills —— 结果用户积累的 17 条偏好一条都没进提示词，
# 生成时「必须遵守的规则」是空的，越写越差。v2 做两件事：
#   1. 启用这些旧偏好（它们是用户亲手写的，本就不该默认关掉）；
#   2. 把其中能机械校验的句子升级成「带 kind 的规则」，让校验器真的能拦。
_LEGACY_RULE_PATTERNS = (
    (re.compile(r"会话.{0,8}?(\d+)\s*(?:个|条)"), "min_sessions",
     lambda m: int(m.group(1))),
    (re.compile(r"历史会话.{0,8}?(\d+)\s*条"), "min_history_messages",
     lambda m: int(m.group(1))),
    (re.compile(r"(?:话术|内容|消息|发送).{0,8}?(?:短|简短|精悍)|太长|别太长|不要太长"),
     "max_message_chars", lambda m: 15),
    (re.compile(r"开头.{0,8}图片"), "opening_image", lambda m: True),
    (re.compile(r"不(?:涉及|要|使用|出现|用).{0,4}转账"), "banned_action",
     lambda m: "转账"),
    (re.compile(r"不(?:涉及|要|使用|出现|用).{0,6}语音"), "banned_action",
     lambda m: "发送语音"),
    (re.compile(r"(?:控制在|不超过|最多).{0,6}?(\d+)\s*人"), "max_people",
     lambda m: int(m.group(1))),
    (re.compile(r"打字不发"), "required_action", lambda m: "打字不发"),
    (re.compile(r"(?:心理活动|解说|方法论).{0,12}(?:不要|别|少|一两句|不当成|别当成)"
                r"|(?:不要|别|少).{0,12}(?:心理活动|解说|方法论)"),
     "forbid_annotation_as_message", lambda m: True),
)


def _upgrade_legacy_rule(text: str):
    """把一条自然语言偏好尽量映射成 (kind, value)；映射不到返回 (None, None)。"""
    for pat, kind, conv in _LEGACY_RULE_PATTERNS:
        m = pat.search(text or "")
        if m:
            try:
                return kind, conv(m)
            except (TypeError, ValueError):
                continue
    return None, None


def _migrate_v2():
    """一次性：启用旧偏好、并把可校验项升级为规则。幂等，只在第一次真正执行。"""
    with _lock:
        with _db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v2','1')")
            if cur.rowcount == 0:
                return
            rows = conn.execute(
                "SELECT id,title,prompt_hint,type,kind FROM skills WHERE source_note=?",
                ("来自旧版偏好，请确认是否启用",)).fetchall()
            for row in rows:
                text = str(row["prompt_hint"] or row["title"] or "")
                kind, value = _upgrade_legacy_rule(text)
                if kind:
                    conn.execute(
                        "UPDATE skills SET enabled=1, type='rule', kind=?, value=?, updated_at=?,"
                        " source_note=? WHERE id=?",
                        (kind, _json_dump(value), _now(),
                         "来自旧版偏好（已自动升级为可校验规则）", row["id"]))
                else:
                    conn.execute(
                        "UPDATE skills SET enabled=1, updated_at=?, source_note=? WHERE id=?",
                        (_now(), "来自旧版偏好（已自动启用）", row["id"]))


def _migrate_v3():
    """一次性：内置「策略注释最多 2 处」规则。

    用户明确要求：心理活动/手法说明可以打字在输入框里当教学提示，但整份剧本最多 2 处，
    否则会变成满屏解说、不像真人聊天。这条规则让校验器真的能拦下来。
    """
    with _lock:
        with _db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v3','1')")
            if cur.rowcount == 0:
                return
            exists = conn.execute(
                "SELECT 1 FROM skills WHERE kind='max_annotations' LIMIT 1").fetchone()
            if exists:
                return
            now = _now()
            conn.execute(
                "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,"
                "source_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (_new_id("sk"), "rule", "策略注释最多 2 处（我方打字里禁止）", "max_annotations",
                 _json_dump(2),
                 "策略注释/心理活动不许作为 [我方打字] 发出去；[打字不发] 里的教学注释整份最多 2 处",
                 1, _json_dump([]), "系统默认规则", now, now))


def _migrate_v4():
    """一次性：内置「历史会话要双方有来有回 / 要用插话」等规则，并修掉互相打架的旧规则。

    背景（用户实测反馈）：生成出来的 [历史会话] 常常是「一个女生从头到尾一个人刷屏、
    我一句话都没回」，插话格式也从来没出现过。根因是规则库里根本没有能校验这两件事的
    规则 —— 提示词里只有一句很弱的风格偏好，模型不会当回事，校验器也拦不下来。
    v4 补上三条可校验的默认规则，并把被误改、互相矛盾的旧规则修好。
    """
    with _lock:
        with _db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v4','1')")
            if cur.rowcount == 0:
                return
            now = _now()

            defaults = (
                ("历史会话必须双方有来有回", "history_two_sided", True,
                 "整个历史会话块至少要有 1 个会话是「对方说 → 我回 → 对方再说」双方来回；"
                 "其余会话可以只留对方最后一两句，不必每个会话都机械地你来我往"),
                ("历史会话里同一人最多连续 2 条", "max_history_streak", 2,
                 "历史会话里同一个人最多连续发 2 条，再往下必须由另一方接话"),
                ("至少 2 处「插话」", "min_interjections", 2,
                 "至少 2 处用「插话」写法：[打字不发] 内容 | 0.5 | 对方插话一句"
                 "（或 [我方打字] 内容 | 对方插话一句），多条插话用「；」分隔"),
            )
            for title, kind, value, hint in defaults:
                exists = conn.execute(
                    "SELECT 1 FROM skills WHERE kind=? LIMIT 1", (kind,)).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,"
                    "source_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (_new_id("sk"), "rule", title, kind, _json_dump(value), hint,
                     1, _json_dump([]), "系统默认规则", now, now))

            # 修数据：逐条读出来判断，避免 SQL 里对 JSON 字符串做 CAST 时踩坑
            rows = conn.execute(
                "SELECT id,kind,value,title,prompt_hint,source_note FROM skills").fetchall()
            for row in rows:
                kind = row["kind"]
                try:
                    num = int(float(_json_load(row["value"], None)))
                except (TypeError, ValueError):
                    continue
                # 「策略注释最多 2 处」被误改成更大的数字（如 10）时改回 2
                if kind == "max_annotations" and num > 2 and "2" in str(row["title"] or ""):
                    conn.execute("UPDATE skills SET value=?, updated_at=? WHERE id=?",
                                 (_json_dump(2), now, row["id"]))
                # 「历史会话只写 1 条」与「历史会话要铺满/双方有来有回」直接冲突，自动停用
                if kind == "min_history_messages" and num <= 1:
                    conn.execute(
                        "UPDATE skills SET enabled=0, updated_at=?, source_note=? WHERE id=?",
                        (now, (str(row["source_note"] or "") + "（与「历史会话铺满/双方有来有回」冲突，已自动停用）").strip(),
                         row["id"]))

            # 「全程不打开的会话无需处理」会诱导模型不给历史会话补我方回复，
            # 与「历史会话必须双方有来有回」直接冲突，自动停用（用户可在规则库重新勾选）。
            for row in conn.execute(
                    "SELECT id,prompt_hint,title,source_note FROM skills "
                    "WHERE enabled=1 AND (kind IS NULL OR kind='')").fetchall():
                text = str(row["prompt_hint"] or row["title"] or "")
                if "不打开" in text and "无需处理" in text:
                    conn.execute(
                        "UPDATE skills SET enabled=0, updated_at=?, source_note=? WHERE id=?",
                        (now, (str(row["source_note"] or "") + "（与「历史会话必须双方有来有回」冲突，已自动停用）").strip(),
                         row["id"]))


def _migrate_v5():
    """一次性：按用户给的目标样本重调「历史会话」相关规则。

    用户给出的目标历史会话（9 个会话、每个 1~3 条、每条都带钩子、时间错落）说明：
    - 历史会话不该要求「每个会话都必须双方来回」，那样会写成机械的问答；
      正确要求是「整个历史块里至少有一个会话是双方来回」；
    - 历史消息总数 20 条对这个风格偏高，会逼模型往每个会话里灌废话，降到 12 条；
    - 真正的差别在「每条都要有钩子」（悬念/暧昧/八卦/具体细节），补一条风格规则。
    """
    with _lock:
        with _db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v5','1')")
            if cur.rowcount == 0:
                return
            now = _now()

            # 1) 历史会话「双方有来有回」改成整块级别
            conn.execute(
                "UPDATE skills SET title=?, prompt_hint=?, updated_at=? "
                "WHERE kind='history_two_sided'",
                ("历史会话整体要有双方对话（不要求每个会话）",
                 "整个历史会话块至少要有 1 个会话是「对方说 → 我回 → 对方再说」双方来回；"
                 "其余会话可以只留对方最后一两句（像微信列表），不要每个会话都机械地你来我往",
                 now))

            # 2) 历史消息条数 20 -> 12（配合「每个会话 1~3 条」的目标风格）
            for row in conn.execute(
                    "SELECT id,value,prompt_hint,title FROM skills "
                    "WHERE kind='min_history_messages'").fetchall():
                try:
                    num = int(float(_json_load(row["value"], None)))
                except (TypeError, ValueError):
                    continue
                if num > 12:
                    hint = str(row["prompt_hint"] or "")
                    hint = hint.replace("20 条", "12 条").replace("20条", "12条")
                    if "12" not in hint:
                        hint = "历史会话消息不少于 12 条（9 个会话，每个 1~2 条把屏幕铺满即可）"
                    conn.execute(
                        "UPDATE skills SET value=?, prompt_hint=?, updated_at=? WHERE id=?",
                        (_json_dump(12), hint, now, row["id"]))

            # 3) 补一条「历史会话要有钩子」的风格规则（可自行停用/修改）
            exists = conn.execute(
                "SELECT 1 FROM skills WHERE prompt_hint LIKE '%钩子%' LIMIT 1").fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,"
                    "source_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (_new_id("sk"), "style", "历史会话每条都要有钩子",
                     None, None,
                     "历史会话每条消息都要具体、有信息量、带悬念/暧昧/八卦，让人想点开，"
                     "例如「你牵着那个妹妹是谁」「泰国果冻干嘛的」「小狗项圈给你买一个」"
                     "「鸡要八毛什么意思」；禁止「在吗」「吃了吗」「哈哈」「晚安」这类没信息量的寒暄",
                     1, _json_dump([]), "系统默认规则（按你的目标样本调整）", now, now))


def _migrate_v7():
    """一次性：治理规则库的重复 / 冲突 / 语义错位（实现在 create_migrations.run_v7）。

    为什么单独成文件：本文件已有 6 个内联迁移，「治理型」迁移（消解历史遗留冲突）
    逐条都要写清楚为什么改，几百行塞进来会越来越难读。改动全部只落在规则库，
    不动任何生成结果，每条都在 source_note 里说明原因。
    """
    try:
        import create_migrations
        create_migrations.run_v7()
    except Exception:  # noqa: BLE001
        pass


def _migrate_v8():
    """一次性：参考剧本库分层（整篇 / 片段）+ 把新功能片段示例入库。"""
    try:
        import create_migrations
        create_migrations.run_v8()
    except Exception:  # noqa: BLE001
        pass


def _migrate_v9():
    """一次性：修补 v7 首次执行的顺序 bug 造成的两处残留（详见 create_migrations.run_v9）。"""
    try:
        import create_migrations
        create_migrations.run_v9()
    except Exception:  # noqa: BLE001
        pass


def _migrate_v10():
    """每次启动：把动作表新加的能力卡片段补进参考库（幂等，只补缺）。"""
    try:
        import create_migrations
        create_migrations.run_v10()
    except Exception:  # noqa: BLE001
        pass


def _migrate_v6():
    """一次性：把「素材引用 / 表情重复 / 节奏机械」沉淀成可校验规则。

    背景（用户实测反馈，一份真实剧本）：剧本里出现
      - `[对方发图片] /images/avatar/好显身材的连衣裙__1_Missyaa_来自小红书网页版_20260831_185446_546.jpg`
        ——把文件名/来源后缀原样写进剧本；或写成图库里没有的描述（「洱海的日落」）→ 破图；
      - 表情写「猫咪捂脸」「柴犬敲木鱼」这类图库里不存在的名字 → 全部回落成同一张默认表情，
        并且同一个表情反复用（害羞猫咪 3 次）；
      - 每发一条消息就 `[等待] 0.3` 跟一个等待（50 处），严格一问一答（交替率 0.81）。
    提示词侧已同步补上【可用素材】白名单与节奏写法；这里补四条可校验规则，
    让模型乱写时生成阶段就被打回重写。
    """
    with _lock:
        with _db() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('migrated_v6','1')")
            if cur.rowcount == 0:
                return
            now = _now()
            defaults = (
                ("图片/表情只能写图库里的短名", "asset_ref_plain", True,
                 "图片/表情引用一律写【可用素材】清单里的短名（如「好显身材的连衣裙」「害羞猫咪」）；"
                 "禁止写文件路径、扩展名、时间戳（_20260831_185446）或「来自小红书/网页版」来源后缀"),
                ("图片/表情必须能解析到真图", "asset_ref_exists", True,
                 "图片/表情引用必须能在图片库里找到真实文件；找不到的（如「洱海的日落」「柴犬敲木鱼」）"
                 "运行时会破图或回落成同一张默认表情，生成阶段就会被判不合格"),
                ("同一个表情最多重复 2 次", "max_same_emoji", 2,
                 "同一个表情关键词整份剧本最多用 2 次，换着用，不要整段反复发同一张"),
                ("不要用 [等待] 打节拍", "max_wait_ratio", 0.6,
                 "[等待] 只用在真正要停一下的地方：被 [等待] 紧跟着的我方消息不超过六成；"
                 "节奏靠连发 / 打字不发 / 插话，而不是每发一条都跟一个 0.3 秒"),
                ("实时对白要有一方连发", "min_burst", 2,
                 "实时对白里至少有一段是同一方连发 2~3 条（连着几条 [我方打字] 或 [对方发消息]），"
                 "不要每条都严格「我一条 → 对方一条」；交替率不要超过 0.75"),
            )
            for title, kind, value, hint in defaults:
                exists = conn.execute(
                    "SELECT 1 FROM skills WHERE kind=? LIMIT 1", (kind,)).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO skills(id,type,title,kind,value,prompt_hint,enabled,source_feedback,"
                    "source_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (_new_id("sk"), "rule", title, kind, _json_dump(value), hint,
                     1, _json_dump([]), "系统默认规则（来自剧本实测）", now, now))
