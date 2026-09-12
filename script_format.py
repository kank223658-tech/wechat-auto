# -*- coding: utf-8 -*-
"""创作模式的「结构化生成 + 本地渲染」层
==========================================
旧版让大模型直接写 `[指令]` 文本，实测 39 条生成结果里有 2 条出现
`[为我方打字]`、`[我等打字]`、`[返回主页`（括号缺失）这类行 ——
`main.parse_script_text` 遇到无法识别的行会【静默丢弃】，剧本凭空少几行，
于是又触发「实时对白不够」→ 重写 → 再丢行，进入死循环。

本模块把生成范式改成：
    模型填结构化 JSON  →  本地渲染成标准 [指令] 文本  →  走老解析链路
这样「格式类失败」一次性消失，而老的手写 [指令] 路径完全不受影响
（模型不听话、或用户自己粘一段文本时，coerce() 也会原样放行）。

另外提供「定向补丁」能力：纠错轮不再整篇重写，而是让模型只给出要改的片段
（find/with），本地做字面替换 —— 省 token，且不会「越改越差」。
"""

import json
import re

import action_registry as ar
import script_translator as st

# ------------------------------------------------------------
# 提示词里给模型看的输出格式说明
# ------------------------------------------------------------

JSON_SPEC = """【输出格式 —— 只输出一个 JSON 对象，不要任何解释、不要 markdown 围栏】
{
  "history": [
    {"contact": "susu",
     "messages": [
       {"who": "peer", "text": "那我先走了 | 23:21"},
       {"who": "me",   "text": "哈哈，很快还会见"},
       {"who": "peer", "text": "[图片] 风景照"}
     ]}
  ],
  "steps": [
    {"action": "打开聊天", "params": {"联系人": "susu"}},
    {"action": "我方打字", "params": {"内容": "刚看到这条 第一反应就是你"}},
    {"action": "打字不发", "params": {"内容": "故意否定 引起注意", "停留": 0.5, "插话": "你这人什么意思？！"}},
    {"action": "删除文字", "params": {"数量": -1}},
    {"action": "切换底部面板", "params": {"面板": "表情", "停留": 0.8}},
    {"action": "发送emoji", "params": {"表情": "捂脸"}},
    {"action": "对方发消息", "params": {"内容": "你眼光可以啊"}}
  ]
}
- history：历史会话块（可以多个 {"contact":…, "messages":[…] }）。contact 写生活化昵称/备注；
  who 只写 "me" / "peer"；时间写在 text 末尾，格式 ` | 23:21`（可省略，省略=紧跟上一条）；
  图片消息在 text 里以 `[图片] 关键词` 开头，表情贴纸以 `[表情] 关键词` 开头，语音以 `[语音] 秒数` 开头，
  链接消息以 `[链接] 标题 | 图片 | 来源` 开头。
- steps：实时指令，按执行顺序排列。action 必须来自【动作表】；
  params 的键必须是该动作自己的参数名（见动作表与能力卡）。
- 图片/表情的值一律写【可用素材】清单里的短名（如「好显身材的连衣裙」「害羞猫咪」）。
- 文本消息内容里可内嵌 3D 黄脸 emoji：把 [名称] 直接写进 text（如 "太开心了[大笑]"、
  "是嘛[捂脸]"），渲染时自动变行内小表情，无需单独一条 发送emoji/对方emoji 步骤；
  名称必须是 names.json 里的名称或别名（共 110 个表情，微笑/捂脸/大笑/爱心/害羞…），
  内嵌标记原样保留。
- 「打字不发 / 我方打字」的 插话 参数支持全部消息格式（行首标记路由，写在插话段里而非独立动作行）：
  `[对方表情] 素材短名`=贴纸、`[对方图片] 素材短名`=图片、`[对方链接] 标题 | 封面 | 来源`=链接卡片、
  `[对方emoji] 微笑`=3D黄脸（名称/编号1~110/随机）、`[对方语音] 5`=语音条、`[对方转账] 金额 | 备注`=转账卡片；
  无标记=纯文字（可内嵌 [微笑]）。多句插话用「；」分隔。
- 绝不能用 "text" 之类的字段代替 steps，也不要写 `[指令]` 文本 —— 输出必须是 JSON。"""


# ------------------------------------------------------------
# JSON -> [指令] 文本
# ------------------------------------------------------------

_ME_WORDS = {"me", "我", "我方", "myself", "self", "i"}
_PEER_WORDS = {"peer", "对方", "她", "他", "ta"}

_HISTORY_IMAGE_PREFIX = ("[图片]", "【图片】", "[配图]", "【配图】")
_HISTORY_LINK_PREFIX = ("[链接]", "【链接】", "[小程序卡片]", "【小程序卡片】")


def _fmt_num(v):
    """0.5 -> '0.5'，1.0 -> '1'（避免渲染出 `停留=1.0` 这种别扭写法）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return ("%g" % f)


def _render_history_message(contact, m):
    if isinstance(m, str):
        m = {"who": "peer", "text": m}
    if not isinstance(m, dict):
        return None
    text = str(m.get("text") or m.get("内容") or "").strip()
    if not text:
        return None
    # 允许模型把时间写在 text 末尾（`内容 | 23:21`），也允许单独给 time 字段
    time_s = str(m.get("time") or m.get("时间") or "").strip()
    if not time_s:
        parts = [x.strip() for x in text.split("|")]
        if len(parts) >= 2 and re.fullmatch(r"(?:\d{1,2}:\d{2}|昨天\s*\d{1,2}:\d{2}|"
                                            r"(?:星期|周)[一二三四五六日天]|\d+\s*(?:分钟|小时|天)前)",
                                            parts[-1] or ""):
            time_s = parts[-1]
            text = " | ".join(parts[:-1]).strip()
    who = str(m.get("who") or m.get("from") or "peer").strip().lower()
    if who in _ME_WORDS:
        speaker = "我"
    elif who in _PEER_WORDS:
        speaker = contact or "对方"
    else:
        speaker = str(m.get("who") or "").strip() or contact or "对方"
    kind = str(m.get("kind") or "").strip().lower()
    if kind in ("image", "图片", "pic", "photo") and not text.startswith(_HISTORY_IMAGE_PREFIX):
        text = "[图片] " + text
    elif kind in ("link", "链接", "card") and not text.startswith(_HISTORY_LINK_PREFIX):
        text = "[链接] " + text
    line = "%s：%s" % (speaker, text)
    if time_s:
        line += " | " + time_s
    return line


def render_history(history) -> list:
    """history 数组 -> [历史会话] … [历史会话结束] 的行列表。"""
    out = []
    if not isinstance(history, list) or not history:
        return out
    body = []
    for sess in history:
        if isinstance(sess, str):
            sess = {"contact": sess, "messages": []}
        if not isinstance(sess, dict):
            continue
        contact = str(sess.get("contact") or sess.get("会话") or sess.get("name") or "").strip()
        msgs = sess.get("messages") or sess.get("消息") or []
        lines = [x for x in (_render_history_message(contact, m) for m in msgs) if x]
        if not lines:
            continue
        body.append("[会话] " + (contact or "对方"))
        body.extend(lines)
    if not body:
        return out
    out.append("[历史会话]")
    out.extend(body)
    out.append("[历史会话结束]")
    return out


def _named_pairs(params) -> str:
    """把参数渲染成 `键=值 | 键=值`（给「文本里没有天然参数位」的多参数动作）。"""
    bits = []
    for k, v in params.items():
        if v in (None, ""):
            continue
        if isinstance(v, (dict, list)):
            bits.append("%s=%s" % (k, json.dumps(v, ensure_ascii=False)))
        elif isinstance(v, bool):
            bits.append("%s=%s" % (k, "是" if v else "否"))
        else:
            bits.append("%s=%s" % (k, v))
    return " | ".join(bits)


# 这些动作的文本写法有专门的解析约定（见 main.parse_script_text），
# 必须按它的分段顺序渲染，不能笼统地用 `键=值`。
_SPECIAL_ARG_ORDER = {
    "打字不发": ("内容", "停留", "插话"),
    "我方打字": ("内容", "插话"),
    "我方发链接": ("标题", "图片", "来源"),
    "对方发链接": ("标题", "图片", "来源"),
    "对方后台发消息": ("联系人", "内容"),
    "对方后台发表情": ("联系人", "表情"),
    "后台消息队列": ("数据",),
}


def render_step(step) -> str:
    """一个 step dict -> 一行 `[动作] 参数`。"""
    if isinstance(step, str):
        return step.strip()
    if not isinstance(step, dict):
        return ""
    action = str(step.get("action") or step.get("动作") or "").strip()
    # 别名归一：渲染出来的必须是规范动作名（parse 也认别名，但规范名最稳）
    action = (getattr(st, "ACTION_ALIASES", {}) or {}).get(action, action)
    if not action:
        return ""
    params = step.get("params") or step.get("参数") or {}
    if not isinstance(params, dict):
        params = {}
    # 丢弃该动作参数表里没有的键：模型偶尔会塞进「时间」「备注」这类它自己
    # 发明的参数，渲染出来会变成 `[手机状态栏] 深夜 | 22:40` —— 解析器认不出，
    # 整段被吞进第一个字段（模式=「深夜 | 22:40」），运行时行为完全错。
    table = ar.param_defaults().get(action)
    if table:
        params = {k: v for k, v in params.items() if k in table}

    def _val(key, v):
        if key in ("停留", "秒数"):
            return _fmt_num(v)
        if isinstance(v, bool):
            return "是" if v else "否"
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v).strip()

    order = _SPECIAL_ARG_ORDER.get(action)
    if order:
        vals = []
        for k in order:
            v = params.get(k)
            vals.append("" if v in (None, "") else _val(k, v))
        while vals and not vals[-1]:
            vals.pop()
        return ("[%s] %s" % (action, " | ".join(vals))).rstrip()

    # 与默认值相同的参数不必写进剧本（写了也只是噪音）；写完再看剩几个参数：
    # 只剩一个 -> 用位置写法（`[发送emoji] 捂脸`）；不止一个 -> 用命名写法
    # （`[切换底部面板] 面板=表情 | 停留=0.8`，多参数动作只有这样才不丢参数）。
    real = [(k, v) for k, v in params.items() if v not in (None, "")]
    default = _defaults_for(action)
    real = [(k, v) for k, v in real if not (k in default and str(default[k]) == str(v))]
    if len(real) == 1:
        k, v = real[0]
        return "[%s] %s" % (action, _val(k, v))
    if len(real) > 1:
        # 按动作表的参数顺序输出，保证同一份 JSON 每次渲染出的文本完全一致
        # （否则 dict 顺序会造成同一剧本两次生成文本不同，无法比对/去重）。
        if default:
            order = {k: i for i, k in enumerate(default.keys())}
            real.sort(key=lambda kv: order.get(kv[0], 999))
        return "[%s] %s" % (action, _named_pairs(dict(real)))
    return "[%s]" % action


_DEFAULTS_CACHE = {}


def _defaults_for(action):
    if action not in _DEFAULTS_CACHE:
        _DEFAULTS_CACHE[action] = ar.param_defaults().get(action) or {}
    return _DEFAULTS_CACHE[action]


def render(data) -> str:
    """生成 JSON -> 标准 [指令] 文本。"""
    if isinstance(data, str):
        return data.strip()
    if not isinstance(data, dict):
        return ""
    lines = []
    lines.extend(render_history(data.get("history")))
    steps = data.get("steps") or data.get("动作") or []
    if isinstance(steps, str):
        return (data.get("text") or "").strip()
    for s in steps:
        line = render_step(s)
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


# ------------------------------------------------------------
# 模型输出 -> [指令] 文本（JSON / 纯文本都能吃）
# ------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json|text|markdown)?\s*\n?|\n?\s*```\s*$")


def _strip_fences(raw: str) -> str:
    t = (raw or "").strip()
    for _ in range(2):
        t2 = _FENCE_RE.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    return t


def extract_json(text: str):
    """从一段可能夹着说明文字的回复里取出第一个完整 JSON 对象/数组。"""
    t = _strip_fences(text or "")
    if not t:
        return None
    try:
        return json.loads(t)
    except (TypeError, ValueError):
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i = t.find(opener)
        if i < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for j in range(i, len(t)):
            ch = t[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except (TypeError, ValueError):
                        break
    return None


def looks_like_json(text: str) -> bool:
    t = _strip_fences(text or "")
    return t.startswith("{") or t.startswith("[")


def coerce(raw):
    """把模型输出统一成 ([指令] 文本, 形态)。

    形态 kind：
      "json"   模型按 JSON 输出（理想情况）
      "text"   模型直接给了 [指令] 文本（老路径 / 兜底，照旧放行）
      "empty"  什么都没拿到

    容忍 dict / list 直入（调用方已经自己 json.loads 过的场景），
    免得再被序列化一次。
    """
    if isinstance(raw, dict):
        rendered = render(raw)
        return (rendered, "json") if rendered else ("", "empty")
    if isinstance(raw, list):
        rendered = render({"steps": raw})
        return (rendered, "json") if rendered else ("", "empty")
    t = _strip_fences(raw or "")
    if not t:
        return "", "empty"
    if looks_like_json(t):
        data = extract_json(t)
        if isinstance(data, dict):
            # 允许 {"text": "..."} 这种偷懒写法
            if "steps" not in data and "history" not in data:
                inner = data.get("text") or data.get("script") or data.get("剧本")
                if isinstance(inner, str) and inner.strip():
                    return inner.strip(), "text"
            rendered = render(data)
            if rendered:
                return rendered, "json"
            return "", "empty"
        if isinstance(data, list):
            rendered = render({"steps": data})
            if rendered:
                return rendered, "json"
            return "", "empty"
    # 不是 JSON：按老路径当 [指令] 文本
    return t, "text"


# ------------------------------------------------------------
# 定向补丁：纠错轮只改失败片段，不整篇重写
# ------------------------------------------------------------

PATCH_SPEC = """【输出格式 —— 只输出要改的部分，不要重写整篇】
{
  "patches": [
    {"find": "直接抄原文里要改的那一行（可含相邻一两行）", "with": "替换后的内容（可多行）"}
  ],
  "append_steps": [ {"action": "我方打字", "params": {"内容": "要补的一句"}} ]
}
- find 必须与《当前剧本》里的原文【一字不差】（含空格与标点），且在全文里只出现一次；
  找不到或出现多次的补丁会被本地丢弃，等于白改。
- 只改问题清单点到的地方，其余行原样保留；不要动没问题的地方。
- 需要新增对白就写进 append_steps（按【动作表】的结构化写法）；删掉一行就把 with 写成空字符串。
- 不要输出整篇剧本；不要输出解释文字。"""


def number_lines(text: str) -> str:
    """给剧本加行号，便于模型在补丁里引用（也方便人核对）。"""
    out = []
    for i, ln in enumerate((text or "").splitlines(), start=1):
        out.append("%4d| %s" % (i, ln))
    return "\n".join(out)


def apply_patches(text: str, patches) -> tuple:
    """按 find/with 做字面替换。

    返回 (新文本, 成功数, 失败数)。
    失败（找不到 / 命中多处的）直接跳过 —— 宁可少改，也不要把剧本改坏；
    如果一条都没成功，调用方应回退到「整篇重写」或保留上一版。
    """
    out = text or ""
    ok = fail = 0
    if not isinstance(patches, list):
        return out, 0, 0
    for p in patches:
        if not isinstance(p, dict):
            fail += 1
            continue
        find = p.get("find") or p.get("old") or p.get("原文")
        with_ = p.get("with")
        if with_ is None:
            with_ = p.get("new") or p.get("替换")
        if with_ is None:
            with_ = ""
        if not isinstance(find, str) or not find.strip():
            fail += 1
            continue
        if out.count(find) != 1:
            fail += 1
            continue
        out = out.replace(find, str(with_), 1)
        ok += 1
    return out, ok, fail


def apply_append_steps(text: str, steps) -> str:
    """把补出来的步骤渲染后追加到剧本末尾（插在最后一条 [返回主页]/[等待] 之前）。"""
    lines = [render_step(s) for s in (steps or [])]
    lines = [x for x in lines if x]
    if not lines:
        return text
    body = (text or "").rstrip().splitlines()
    # 末尾的收尾指令（返回主页 / 等待）留在最后，新内容插到它们前面
    tail_count = 0
    for ln in reversed(body):
        if re.match(r"^[\[\【]\s*(返回主页|等待|隐藏键盘)\s*[\]\】]", ln.strip()):
            tail_count += 1
        else:
            break
    if tail_count:
        head = body[:len(body) - tail_count]
        tail = body[len(body) - tail_count:]
        return "\n".join(head + lines + tail)
    return "\n".join(body + lines)
