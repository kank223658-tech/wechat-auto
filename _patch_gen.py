# -*- coding: utf-8 -*-
"""一次性：把 script_generator 的生成/纠错提示词改造成「JSON 输出 + 能力卡 + 预算配套」。

用 ast 定位函数边界整体替换（比长字符串 Edit 稳，避免 Edit 工具静默丢改动）。
"""
import ast
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_generator.py")
src = io.open(P, encoding="utf-8").read()
done = []


def _offsets(lines):
    out = [0]
    for ln in lines:
        out.append(out[-1] + len(ln))
    return out


def replace_func(text, name, new_src):
    """按函数名整体替换（ast 给的 lineno 是行号，必须先换算成字符偏移）。"""
    tree = ast.parse(text)
    offs = _offsets(text.splitlines(keepends=True))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = offs[node.lineno - 1]
            end = offs[node.end_lineno]
            return text[:start] + new_src.rstrip("\n") + "\n" + text[end:]
    raise SystemExit("找不到函数 " + name)


def sub(old, new, tag, count=1):
    global src
    assert src.count(old) == count, "%s 匹配 %d 次（期望 %d）" % (tag, src.count(old), count)
    src = src.replace(old, new, count)
    done.append(tag)


NEW_ACTION_TABLE = '''def _format_action_table_compact(actions=None) -> str:
    """把「可进 AI 剧本的动作」格式化成提示词简表：动作名 + 参数名 + 何时用。

    旧版直接把 editor_server.ACTIONS（60 条，含编辑主页/应用场景这类数据驱动动作）
    整份塞进提示词，既长又杂，而且每个动作只有一句 desc、没有「什么时候该用」——
    新动作（发送emoji / 切换底部面板 / 点赞…）名字躺在表里，模型永远不会主动用。

    现在从 action_registry.script_actions() 取（32 条），并带上 when。
    `actions` 参数仅为兼容旧调用保留（调用方传的 editor ACTIONS 会漏掉
    「我方发链接/对方发链接」这些 editor=False 的动作，所以不再采用）。
    """
    table = ar.script_actions()
    lines = []
    for i, a in enumerate(table, start=1):
        name = a["action"]
        bits = [p.get("key") for p in (a.get("params") or [])
                if p.get("key") not in ("数据", "data")]
        when = a.get("when") or a.get("desc") or ""
        pstr = ("（" + "、".join(bits) + "）") if bits else ""
        lines.append("%2d. [%s]%s —— %s" % (i, name, pstr, when))
    return "\\n".join(lines)


def capability_block() -> str:
    """能力卡：新功能「什么时候用 + 长什么样」。

    体检结论：`切换底部面板 / 面板切换序列 / 发送emoji / 点赞 / 手机状态栏 / 闪回聊天`
    这些动作在 script_generator 里出现 0 次 —— 只有一行动作表里的名字，
    没有「什么时机用」的说明、参考剧本里也从没演过，等于新功能根本没接入生成链路。
    一张能力卡 = 何时用 + 3~6 行片段示例。
    """
    cards = ar.capability_cards()
    if not cards:
        return ""
    lines = ["【能力卡 —— 新功能「什么时候用 + 长什么样」，想用就照片段写】"]
    for c in cards:
        lines.append("- [%s] %s" % (c["action"], c["when"]))
        for snip in (c.get("snippet") or [])[:3]:
            lines.append("    " + snip)
    return "\\n".join(lines)
'''

NEW_FORMAT_REFERENCES = '''def format_references(references: list, category: str = "") -> str:
    """把选中的参考剧本拼成提示词里的 few-shot 文本块（分层）。

    体检结论：库里只有 3 条整篇参考，其中一条是「对方 0 条」的纯单边剧本，
    另一条我方 62 / 对方 6 —— 整篇堆多了只会教出「自言自语」；
    而新功能在整篇参考里一处都没演过，模型从参考这条路也学不到。

    所以分两层：
      - 【风格模板】整篇参考最多 2 条，学「每句话背后带什么策略、节奏怎么排」；
      - 【片段示例】短片段（kind=snippet，含系统内置的新功能片段），
        每条标注「演的是什么」，直接示范某个动作怎么用。
    """
    if not references:
        return "（本次未提供参考剧本，请依你掌握的聊天教学套路直接创作）"
    fulls = [r for r in references if (r.get("kind") or "full") == "full"][:2]
    snips = [r for r in references if (r.get("kind") or "full") == "snippet"][:6]

    parts = []
    if fulls:
        blocks = []
        for i, r in enumerate(fulls, start=1):
            tags = "、".join(r.get("tags") or []) or "无"
            summary = str(r.get("summary") or "")
            head = "参考剧本%d《%s》\\n手法标签：%s\\n结构摘要：%s" % (
                i, str(r.get("title", "未命名")), tags, summary)
            blocks.append(head + "\\n" + str(r.get("text", "")))
        parts.append(
            "【风格模板】以下整篇参考用来学「每句话背后带什么策略、如何编排节奏」，"
            "重点模仿结构与打法，而不是照抄句子；人物名一律换成【人物库】里的。\\n"
            "参考剧本里 `[打字不发]` 的正文都是「写给观众看的技巧说明」，"
            "你的成稿里**每一处** `[打字不发]` 都要写这种打法说明"
            "（「这一步在做什么、为什么这样聊有效」），"
            "绝不能写成马上要发出去的聊天话术，也不能写成对方的心理活动。\\n"
            "参考剧本的 [历史会话] 是最好的学习对象：像微信列表预览，绝大多数会话只留对方最后 1~2 条、"
            "每条都带钩子、时间标注错落，整块里只让 1 个会话带「我：」的回复。\\n\\n"
            + "\\n\\n".join(blocks))
    if snips:
        lines = []
        for r in snips:
            note = str(r.get("note") or r.get("summary") or "").strip()
            lines.append("· %s%s\\n%s" % (
                str(r.get("title", "片段")),
                ("（%s）" % note) if note else "",
                str(r.get("text", ""))))
        parts.append("【片段示例】这些是「某个动作该怎么演」的短示范，"
                     "成稿里用到对应动作时照着写。\\n" + "\\n".join(lines))
    if not parts:
        return "（本次未提供参考剧本，请依你掌握的聊天教学套路直接创作）"
    return "\\n\\n".join(parts)
'''

# ---------------- 执行 ----------------

src = replace_func(src, "_format_action_table_compact", NEW_ACTION_TABLE)
done.append("_format_action_table_compact + capability_block")
src = replace_func(src, "format_references", NEW_FORMAT_REFERENCES)
done.append("format_references")

# ---- 书写规范块：数字全部来自 rule_numbers，插话按 1/3 统一口径 ----
sub('''    typing_holds = nums["min_typing_hold"]
    max_steps = nums["max_script_steps"]''',
    '''    typing_holds = nums["min_typing_hold"]
    max_steps = nums["max_script_steps"]
    realtime_floor = nums["min_realtime_lines"]''', "spec 取数")

sub('''   【篇幅】整份剧本的实时指令（历史块以外）控制在 {max_steps} 步以内，含 [打字不发]/[删除文字]/[对方正在输入] 等所有指令行；节奏要密但不要靠无限拉长来堆，宁可用同一句话拆成几次打字/删改，也不要多开一个来回。''',
    '''   【篇幅预算】四个数字一起满足、不要只把某一条拉满：整份实时指令（历史块以外，含 [打字不发]/[删除文字]/[对方正在输入] 等所有指令行）≤ {max_steps} 步、实时对白 ≥ {realtime_floor} 条、[打字不发] ≥ {typing_holds} 处、插话 ≈ [打字不发] 的 1/3。节奏要密，但靠「同一句话拆成几次打字/删改」，不要靠多开来回、堆空转指令把剧本拉长。''',
    "spec 篇幅预算")

sub('''   - **不是每个 [打字不发] 都要配插话**：参考剧本里 44~50 处打字不发只有 15~18 处插话；
     整份剧本插话 {interjections} 处左右就够，配太多会显得对方一直在抢话，反而不真实。''',
    '''   - **不是每个 [打字不发] 都要配插话**：参考剧本里 44~50 处打字不发只配 15~18 处插话，
     也就是大约每 3 处打字不发配 1 处插话。整份剧本至少 {interjections} 处带插话；
     你打字不发写得越密，插话按 1/3 跟着加即可，但不要每个都配，那样显得对方一直在抢话。
     （规则库与校验器用的是同一个数，不会出现「一边要求 N 处、一边劝你少配」的矛盾。）''',
    "spec 插话口径")

sub('''   参考剧本的最长连发是 6~15 条、交替率只有 0.19~0.56，整份对白不要写成朗读稿。"""''',
    '''   参考剧本的最长连发是 6~15 条、交替率只有 0.19~0.56，整份对白不要写成朗读稿。
H. 【新功能要用起来】下面的【能力卡】列了几个新动作的「何时用 + 片段示例」——
   整份剧本至少用上其中 1~2 个（切换底部面板 / 发送emoji / 朋友圈 / 手机状态栏），
   不要通篇只有 [我方打字] 和 [对方发消息]：真机聊天里人本来就会切面板、发表情、打错再删。"""''',
    "spec 新功能")

io.open(P, "w", encoding="utf-8").write(src)
print("已改:", "、".join(done))
