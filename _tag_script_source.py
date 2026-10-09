# -*- coding: utf-8 -*-
"""剧本来源标记工具 —— 区分「用户导入」与「AI 生成」

用法（系统 Python312，需在项目根目录跑）：
    py _tag_script_source.py --scan             只判定并打印，不改文件
    py _tag_script_source.py --apply            把标记写进剧本首行（幂等，可重复跑）
    py _tag_script_source.py --strip            移除全部标记（回滚）
    py _tag_script_source.py --report           生成 剧本库/_来源台账.md 与 _来源台账.json
    py _tag_script_source.py --verify           复核：标记 + 跑一次质量门（抽查 3 篇）
    py _tag_script_source.py --set <路径> <值>  手工指定某一篇（写进 _来源覆盖.json，优先级最高）

标记长这样（写在文件第一行，解析器整行跳过、不影响跑片）：
    # 来源：用户导入 · 出处：手写入库
    # 来源：AI生成 · 出处：对标改编（母稿1324）
    # 来源：AI生成 · 出处：软件生成器

判定信号（每条都可复跑，不靠记忆）：
    S0 手工覆盖    _来源覆盖.json（--set 写入，优先级最高）
    S0b 参考件     文件名含「参考原文/参考剧本/_参考_/参考范本」→ 用户导入
    S1 底稿声明    文件开头自带「# 底稿：…」→ 对标改编 / 剧本内改编
    S2 母稿同源    与 _工作文件/_docx_text_*.txt 6-gram 重合 ≥8%   → AI生成·对标改编
    S3 目录归属    在 _inprogress/成品 下、或在 剧本/（对标转录）    → AI生成
    S4 内容同源    与 _inprogress、成品 任一篇 6-gram 重合 ≥60%（同一批的初稿/定稿）→ AI生成
    S5 生成历史    generate_history.json 的 brief 命中             → AI生成
    S6 生成器头    首行是 "# 选题：" / "# 剧本：" / "# ===="       → AI生成
    S7 兜底        以上都无                                        → 用户导入（手写入库）
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT_LIB = os.path.join(ROOT, "剧本库")
SCRIPT_DIR = os.path.join(ROOT, "剧本")
DOCX_DIR = os.path.join(ROOT, "_工作文件")
CREATE_DB = os.path.join(ROOT, "create.db")
GEN_HISTORY = os.path.join(ROOT, "generate_history.json")
OVERRIDE_FILE = os.path.join(ROOT, "_来源覆盖.json")

TAG_RE = re.compile(r"^\s*#\s*来源\s*[：:]\s*(用户导入|AI生成)\s*(?:[·・]\s*出处\s*[：:]\s*(.+?))?\s*$")
GEN_HEAD_RE = re.compile(r"^\s*#\s*(选题|剧本)\s*[：:]|^\s*#\s*={4,}", re.M)
BOTTOM_RE = re.compile(r"^\s*#\s*底稿\s*[：:]\s*(.+?)\s*$", re.M)
MOTHER_NO_RE = re.compile(r"(\d{3,5})\s*赞")
HEAD_SCAN_LINES = 30   # 只看文件开头这么多行里的声明

USER = "用户导入"
AI = "AI生成"

# 目录白名单/黑名单：_归档（历史归档）与 _bak*（备份）不动
SKIP_DIR_PARTS = ("_bak", "_归档", "_backup", "__pycache__")

# 参考件：用户手写/收集的原文、范本，不参与「AI 产出」比对（否则会把用户手稿当 AI 稿）
REF_KEYS = ("参考原文", "参考剧本", "_参考_", "参考范本")


# --------------------------------------------------------------------------- #
# 基础
# --------------------------------------------------------------------------- #
def read_text(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def norm_text(s):
    """剥掉指令/人名/时间/标点，用于同源比对。"""
    s = re.sub(r"^\[[^\]]*\]", "", s, flags=re.M)
    s = re.sub(r"^[^：:\n]{1,14}[：:]", "", s, flags=re.M)
    s = re.sub(r"\|\s*\d.*$", "", s, flags=re.M)
    return re.sub(r"[\s，。！？、,.!?~…\-—·\"“”'’；;：:\[\]]", "", s)


def grams_of(text, n=6):
    t = norm_text(text)
    return set(t[i:i + n] for i in range(len(t) - n + 1))


def load_mothers():
    """7 篇对标母稿的 6-gram（_docx_text_*.txt）。"""
    out = {}
    if not os.path.isdir(DOCX_DIR):
        return out
    for fn in sorted(os.listdir(DOCX_DIR)):
        if not fn.startswith("_docx_text_") or not fn.endswith(".txt"):
            continue
        m = re.search(r"(\d+)赞", fn)
        key = m.group(1) if m else fn[:24]
        out[key] = grams_of(read_body(os.path.join(DOCX_DIR, fn)))
    return out


def load_pools():
    """AI 生产痕迹池：中间稿 + 成品 + 剧本/ 的 6-gram（用于「内容同源」判定）。"""
    pools = {}
    bases = [os.path.join(SCRIPT_LIB, "_inprogress"),
             os.path.join(SCRIPT_LIB, "成品"),
             SCRIPT_DIR]
    for base in bases:
        if not os.path.isdir(base):
            continue
        for dp, dn, fns in os.walk(base):
            dn[:] = [d for d in dn if not any(p in d for p in SKIP_DIR_PARTS)]
            for fn in fns:
                if not fn.lower().endswith(".txt"):
                    continue
                if any(k in fn for k in REF_KEYS):   # 参考件不当 AI 生产的「母本」
                    continue
                p = os.path.join(dp, fn)
                pools[p] = grams_of(read_body(p))
    return pools


def pack_of(pool_path):
    """pool 文件 → 人可读的「出处」文案。"""
    rel = os.path.relpath(pool_path, ROOT).replace("\\", "/")
    if "/_inprogress/" in rel:
        seg = rel.split("/_inprogress/")[1].split("/")
        return seg[0] if len(seg) > 1 else "中间稿"
    if "/成品/" in rel:
        seg = rel.split("/成品/")[1].split("/")
        return f"成品批次·{seg[0]}" if len(seg) > 1 else "成品批次"
    return "对标转录"


def load_gen_briefs():
    if not os.path.exists(GEN_HISTORY):
        return []
    try:
        hist = json.load(open(GEN_HISTORY, encoding="utf-8")).get("history", [])
    except Exception:
        return []
    return [(h.get("brief") or "").strip() for h in hist]


def load_overrides():
    if os.path.exists(OVERRIDE_FILE):
        try:
            return json.load(open(OVERRIDE_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_overrides(d):
    json.dump(d, open(OVERRIDE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def iter_targets():
    """要处理的剧本文件（相对 ROOT 的路径）。"""
    out = []
    for base in (SCRIPT_LIB, SCRIPT_DIR):
        if not os.path.isdir(base):
            continue
        for dp, dn, fns in os.walk(base):
            dn[:] = [d for d in dn if not any(p in d for p in SKIP_DIR_PARTS)]
            if any(p in dp for p in SKIP_DIR_PARTS):
                continue
            for fn in fns:
                if fn.lower().endswith(".txt"):
                    out.append(os.path.join(dp, fn))
    return sorted(out)


# --------------------------------------------------------------------------- #
# 判定
# --------------------------------------------------------------------------- #
def best_overlap(g, pool, use_parent=False):
    """g 对 pool 求最高重合。use_parent=True 时取 max(占稿比, 占池比)，用于「母稿被沿用多少」。"""
    best, key = 0.0, ""
    if not g:
        return best, key
    for k, v in pool.items():
        if not v:
            continue
        inter = len(g & v)
        if not inter:
            continue
        r = inter / len(g)
        if use_parent:
            r = max(r, inter / len(v))
        if r > best:
            best, key = r, k
    return best, key


def parse_bottom(text):
    """文件开头自带的「# 底稿：…」声明（用户跑 AI 改编时写进去的出处）。"""
    head = "\n".join(text.split("\n")[:HEAD_SCAN_LINES])
    m = BOTTOM_RE.search(head)
    return m.group(1).strip() if m else ""


def classify(path, mothers, pools, briefs, overrides):
    """返回 (来源, 出处, 依据, 明细)。

    优先级：S0 手工覆盖 / 参考件 → S1 底稿声明 → S2 母稿同源 → S3 目录归属
            → S4 内容同源 → S5 生成历史 → S6 生成器头 → S7 兜底（用户导入）
    """
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    text = read_body(path)          # 剥掉已写的来源标记，避免「标记影响判定」
    first = text.split("\n", 1)[0].strip()
    topic = os.path.splitext(os.path.basename(path))[0]

    # S0 显式覆盖（最高优先级）
    if rel in overrides:
        v = overrides[rel]
        if isinstance(v, dict):
            return v.get("来源", USER), v.get("出处", ""), "S0 手工指定", ""
        return str(v), "", "S0 手工指定", ""

    # S0b 参考件：用户手写/收集的原文或范本（名字里带「参考」），一定是用户导入
    base = os.path.basename(path)
    if any(k in base for k in REF_KEYS):
        return USER, "参考原文（手写/收集）", "S0 参考件", ""

    g = grams_of(text)

    # S1 底稿声明：文件自己写了「# 底稿：…」，最可信
    decl = parse_bottom(text)
    if decl:
        if "对标" in decl or "直男许诺" in decl or "母稿" in decl:
            ov, key = best_overlap(g, mothers, use_parent=True)
            if ov < 0.05:
                m2 = MOTHER_NO_RE.search(decl)
                key = m2.group(1) if m2 else "?"
            return AI, f"对标改编（母稿{key}）", "S1 底稿声明", f"{ov*100:.1f}%"
        if "剧本库" in decl:
            inner = decl.split("剧本库")[-1].lstrip("\\/").replace("_inprogress\\", "").replace("_inprogress/", "")
            inner = re.split(r"[（(]", inner)[0].strip()
            return AI, f"剧本内改编（底稿：{inner}）", "S1 底稿声明", ""
        return AI, f"改编（{decl[:28]}）", "S1 底稿声明", ""

    # S2 母稿同源（无声明时的兜底，阈值高于「公共话术地板」约 5.6%）
    ov, key = best_overlap(g, mothers, use_parent=True)
    if ov >= 0.08:
        return AI, f"对标改编（母稿{key}）", "S2 母稿同源", f"{ov*100:.1f}%"

    # S3 目录归属：中间稿 / 成品批次 / 对标转录，这些一定是软件产出的
    if "/_inprogress/" in rel:
        seg = rel.split("/_inprogress/")[1].split("/")
        name = seg[0] if len(seg) > 1 else "散稿"
        if name.endswith("_参考改编"):
            return AI, f"对标改编（底稿未标注·{name}）", "S3 目录归属", ""
        return AI, f"软件管线（{name}）", "S3 目录归属", ""
    if "/成品/" in rel:
        seg = rel.split("/成品/")[1].split("/")
        name = seg[0] if len(seg) > 1 else "成品批次"
        return AI, f"成品批次·{name}", "S3 目录归属", ""
    if rel.startswith("剧本/"):
        return AI, "对标转录（video2script）", "S3 目录归属", ""

    # S4 内容同源：与中间稿/成品/转录任一篇 6-gram 重合 ≥60%（同一批的初稿→定稿）
    ov, pool = best_overlap(g, pools)
    if ov >= 0.60:
        return AI, pack_of(pool), "S4 内容同源", f"{ov*100:.1f}% vs {os.path.basename(pool)}"

    # S5 生成历史（brief 命中）
    for b in briefs:
        b = b.strip()
        if len(b) >= 5 and (b == topic or b in topic or topic in b):
            return AI, "软件生成器（generate_history）", "S5 生成历史", ""

    # S6 生成器头
    if GEN_HEAD_RE.match(first):
        return AI, "软件生成器（自带选题头）", "S6 生成器头", ""

    # S7 兜底：无任何生产痕迹
    return USER, "手写入库", "S7 无生产痕迹", ""





# --------------------------------------------------------------------------- #
# 标记读写
# --------------------------------------------------------------------------- #
def get_tag(text):
    for ln in text.split("\n", 1)[0:1]:
        m = TAG_RE.match(ln)
        if m:
            return (m.group(1), (m.group(2) or "").strip())
    return None


def make_tag(source, note):
    return f"# 来源：{source} · 出处：{note}" if note else f"# 来源：{source}"


def set_tag(text, source, note):
    """把标记放到第一行（已存在则替换），保留原有换行风格。"""
    tag = make_tag(source, note)
    lines = text.split("\n")
    if lines and TAG_RE.match(lines[0]):
        lines[0] = tag
    else:
        lines.insert(0, tag)
    return "\n".join(lines)


def strip_tag(text):
    lines = text.split("\n")
    if lines and TAG_RE.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines)


def read_body(path):
    """正文（剥掉我们自己写的来源标记）——判定必须只看正文，否则标记会污染判定。"""
    return strip_tag(read_text(path))


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def do_scan(apply=False, only_set=False):
    mothers = load_mothers()
    pools = load_pools()
    briefs = load_gen_briefs()
    overrides = load_overrides()
    rows = []
    for p in iter_targets():
        try:
            src, note, why, extra = classify(p, mothers, pools, briefs, overrides)
        except Exception as e:  # 单篇异常不拖垮全库
            src, note, why, extra = USER, "读取失败", f"ERR {e}", ""
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        rows.append((rel, src, note, why, extra))
        if apply:
            t = read_text(p)
            nt = set_tag(t, src, note)
            if nt != t:
                write_text(p, nt)
    rows.sort(key=lambda r: (r[1], r[0]))
    n_user = sum(1 for r in rows if r[1] == USER)
    n_ai = len(rows) - n_user
    print(f"共 {len(rows)} 篇：用户导入 {n_user} ｜ AI生成 {n_ai}"
          f"{'（已写入标记）' if apply else '（仅扫描，未改文件）'}")
    print("-" * 100)
    for rel, src, note, why, extra in rows:
        mark = "👤" if src == USER else "🤖"
        print(f"{mark} {src:<6} {note:<24} [{why}]{(' ' + extra) if extra else ''}  {rel}")
    return rows


def do_strip():
    n = 0
    for p in iter_targets():
        t = read_text(p)
        nt = strip_tag(t)
        if nt != t:
            write_text(p, nt)
            n += 1
    print(f"已移除标记：{n} 篇")


def do_report(rows=None):
    if rows is None:
        rows = do_scan(apply=False)
    md = ["# 剧本来源台账", "",
          "> 由 `_tag_script_source.py --report` 生成。标记格式：剧本首行 `# 来源：…`。",
          f"> 共 {len(rows)} 篇：用户导入 {sum(1 for r in rows if r[1]==USER)} ｜ "
          f"AI生成 {sum(1 for r in rows if r[1]!=USER)}", "",
          "| 来源 | 出处 | 判定依据 | 路径 |", "|---|---|---|---|"]
    for rel, src, note, why, extra in rows:
        md.append(f"| {src} | {note} | {why}{(' ' + extra) if extra else ''} | `{rel}` |")
    md_path = os.path.join(SCRIPT_LIB, "_来源台账.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(md) + "\n")
    json_path = os.path.join(SCRIPT_LIB, "_来源台账.json")
    json.dump([{"path": r[0], "source": r[1], "note": r[2], "why": r[3], "extra": r[4]}
               for r in rows], open(json_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"已生成：{os.path.relpath(md_path, ROOT)} / {os.path.relpath(json_path, ROOT)}")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "--scan":
        do_scan(apply=False)
    elif cmd == "--apply":
        do_scan(apply=True)
        do_report()
    elif cmd == "--strip":
        do_strip()
    elif cmd == "--report":
        do_report()
    elif cmd == "--set":
        rel, val = args[1].replace("\\", "/"), args[2]
        note = args[3] if len(args) > 3 else ""
        ov = load_overrides()
        ov[rel] = {"来源": val, "出处": note}
        save_overrides(ov)
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            write_text(p, set_tag(read_text(p), val, note))
        print(f"已指定：{rel} → {val}{(' · ' + note) if note else ''}")
    else:
        print(f"未知命令 {cmd}\n")
        print(__doc__)


if __name__ == "__main__":
    main()
