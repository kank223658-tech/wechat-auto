# -*- coding: utf-8 -*-
"""把 create_store.py 里被 Edit 工具静默丢掉的三处改动补上（幂等，带断言）。"""
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "create_store.py")
s = open(P, encoding="utf-8").read()
changed = []


def sub1(old, new, tag):
    global s
    assert s.count(old) == 1, "%s: 匹配 %d 次" % (tag, s.count(old))
    s = s.replace(old, new, 1)
    changed.append(tag)


# 1) init_db 迁移链
sub1("            _migrate_v6()\n            _initialized = True",
     "            _migrate_v6()\n            _migrate_v7()\n            _migrate_v8()\n            _initialized = True",
     "init_db 链")

# 2) _ref_row_to_dict：带上 kind / note
sub1('''    d["tags"] = _json_load(d.get("tags"), [])
    rated = int(d.get("rated_count") or 0)''',
     '''    d["tags"] = _json_load(d.get("tags"), [])
    d["kind"] = d.get("kind") or "full"      # full=整篇风格模板 / snippet=片段示例
    d["note"] = d.get("note") or ""
    rated = int(d.get("rated_count") or 0)''',
     "_ref_row_to_dict")

# 3) add_reference：写入 kind / note（并按内容自动分层）
sub1('''    item = {
        "id": _new_id("ref"),
        "title": clean_title,
        "category": (category or "").strip(),
        "topics": _as_list(topics) if topics else derive_reference_topics(body, clean_title),
        "tags": _as_list(tags) if tags else derive_reference_tags(body),
        "summary": (summary or "").strip() or derive_reference_summary(body),
        "text": body,
        "created_at": float(created_at or _now()),
    }
    with _db() as conn:
        conn.execute(
            "INSERT INTO ref_scripts(id,title,category,topics,tags,summary,text,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (item["id"], item["title"], item["category"], _json_dump(item["topics"]),
             _json_dump(item["tags"]), item["summary"], item["text"], item["created_at"], item["created_at"]))
    return item''',
     '''    lines = [x for x in body.splitlines() if x.strip()]
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
    return item''',
     "add_reference INSERT")

open(P, "w", encoding="utf-8").write(s)
print("已补:", "、".join(changed))
