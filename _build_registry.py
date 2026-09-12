# -*- coding: utf-8 -*-
"""生成 action_registry.py（动作表唯一来源）。

为什么要有这个脚本：
  项目里动作表长期有三份口径（editor_server.ACTIONS 60 / script_translator.ACTION_SCHEMA 47 /
  ACTION_PARAMS 56），互有缺失。后果是「发送emoji / 切换底部面板 / 转账」等 15 个新动作
  在生成链路里被判非法，用户写「以后多用表情」沉淀出的 required_action 会被静默降级成 style。
  这里把三份合并成一份带元数据的总表，其余全部由它派生。

元数据说明（每个动作）：
  when        一句话「什么时候用」，进生成提示词与能力卡
  snippet     3~6 行片段示例（能力卡）；新功能靠它才可能被模型主动用出来
  script_ok   是否允许出现在 AI 创作的剧本里（数据驱动 / 非叙事 / 默认关闭的动作设 False）
  editor      是否出现在编辑器的动作下拉里（保持现有 UI 不变）
  primary     文本剧本里该动作的「参数」写哪个字段
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------
# 1) 原有动作表：直接抽 editor_server.ACTIONS，避免手工转抄出错
# ------------------------------------------------------------

def extract_editor_actions():
    """抽出现有动作表。

    第一优先：直接从 editor_server.py 里读字面量 `ACTIONS = [...]`（生成器尚未
    改写过的状态，能拿到最原始那份）。
    第二优先：editor_server 已经把 ACTIONS 改成从 action_registry 派生了
    （`ACTIONS = _editor_actions()`），此时 literal_eval 会失败 —— 直接导入
    action_registry 拿上一版结果，保证「重跑生成器」这一步永远可用。
    """
    src = open(os.path.join(ROOT, "editor_server.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "ACTIONS":
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        break
    # 回退：从已生成的 action_registry 里取「编辑器可见」的那部分
    try:
        import importlib
        import action_registry as _ar
        importlib.reload(_ar)
        actions = [dict(a) for a in _ar.ACTIONS if a.get("editor", True)]
        if actions:
            print("（提示）editor_server.ACTIONS 已改为派生式，改用 action_registry 作为基线")
            return actions
    except Exception as exc:                                  # noqa: BLE001
        raise SystemExit("找不到 editor_server.ACTIONS（回退也失败：%s）" % exc)
    raise SystemExit("找不到 editor_server.ACTIONS")


def extract_text_command_map():
    """从 main.py 里抽出 TEXT_COMMAND_MAP（动作名 -> 参数名）。"""
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    i = src.index("TEXT_COMMAND_MAP = {")
    j = src.index("\n}", i)
    body = src[i + len("TEXT_COMMAND_MAP = {"):j]
    out = {}
    for m in re.finditer(r'^\s*"([^"]+)"\s*:\s*(?:"([^"]*)"|(None))\s*,?\s*$', body, re.M):
        out[m.group(1)] = m.group(2) if m.group(3) is None else None
    return out


# ------------------------------------------------------------
# 2) 手工元数据（这是唯一需要人写的地方）
# ------------------------------------------------------------

_WHEN = {
    # ---- 聊天核心 ----
    "打开聊天": "进入某个会话；实时对白的第一步",
    "我方打字": "我方发出去的**真实聊天话术**（口语，不要说教）",
    "打字不发": "键盘上打出「给观众看的技巧字幕/博弈内容」但不发送，随后删掉——全片最精彩的卖点；第 1 段就是这段字幕",
    "删除文字": "清空输入框；紧跟 [打字不发] 之后",
    "对方正在输入": "对方回话前的「对方正在输入…」（不要每条都用）",
    "对方发消息": "对方回复；允许连发 2~3 条制造真实感",
    "对方后台发消息": "别的会话来了消息：画面不变，只刷主页预览 + 未读角标",
    "返回主页": "结束当前会话，回到聊天列表",
    "等待": "真正要停一下的地方（整份 7~12 处，不要每句都跟一个）",
    "转发消息": "转发一条消息（内容带「转发：」前缀）",
    # ---- 图片 / 表情 ----
    "发送图片": "我方发图；关键词只能写【可用素材】清单里的短名",
    "对方发图片": "对方发图（一律选身材/穿搭类）",
    "发送表情": "我方发贴纸表情包（78×78 小气泡）",
    "对方表情": "对方发贴纸表情包",
    "对方后台发表情": "未打开的会话里，对方发来一张表情",
    "发送emoji": "我方发微信 3D 黄脸小表情：先弹笑脸面板→逐个点选→一次发送。也可以不单独占行：直接把 [名称] 写进文本内容里内嵌上屏",
    "对方emoji": "对方发 3D 黄脸小表情（直接上屏，不弹面板）。也可以不单独占行：把 [名称] 写进 [对方发消息] 的文本里内嵌上屏",
    "我方发链接": "我方转发一张链接卡片",
    "对方发链接": "对方发来链接卡片（历史块里最好用的钩子）",
    # ---- 底部面板 / 朋友圈 / 转账 ----
    "切换底部面板": "聊天中段直接切一下表情/更多面板再收起：真实感最强的新动作",
    "面板切换序列": "一口气按既定节奏连切三面板（复刻参考视频的整段节奏）",
    "进入朋友圈": "开出第二条叙事线：朋友圈",
    "打开对方主页": "点她头像看她资料页（制造话题、看她的世界）",
    "进入对方朋友圈": "翻她的朋友圈找话题",
    "闪到对方朋友圈": "从聊天一帧闪进她的朋友圈（黑幕过渡，跳过资料页——真实微信没有这条路径）",
    "闪回聊天": "从主页/朋友圈一帧切回聊天（剪辑感，像视频切镜）；默认自动闪黑过渡",
    "点赞": "给朋友圈动态点赞（该动态必须先存在）",
    "评论": "给朋友圈动态评论：弹菜单→点评论→键盘打字→发送",
    "发朋友圈": "我方发一条朋友圈动态（之后可点赞/评论它）",
    "编辑朋友圈": "预设「我的朋友圈」动态列表（点赞/评论前必须先有动态）",
    "转账": "我方转账（默认关闭；仅当规则明确要求时才用）",
    "对方转账": "对方发来转账（默认关闭；仅当规则明确要求时才用）",
    "手机状态栏": "把手机状态栏切成参考场景（03:14 + 录屏红点），开场用一次",
}

# 新功能靠「片段示例」才可能被模型主动用出来：只给动作名 = 等于没接入。
_SNIPPET = {
    "打字不发": [
        "[打字不发] 故意否定 引起注意 | 0.5 | 你这人什么意思？！",
        "[删除文字] -1",
        "[我方打字] 我猜你今天又被谁惹了",
        "# 三段语义：第1段=键盘上打给观众看的教学字幕/博弈内容（不发送）；第2段=停留秒数；第3段=对方边看你打字边发的插话",
        "# 插话支持全部消息格式（表情包/图片/链接/emoji/语音/转账，行首标记路由）：",
        "[打字不发] 学以致用 | 1.0 | 你不准想太多；[对方表情] 勃然小怒猫咪；[对方图片] 洱海日落；[对方语音] 5",
        "[删除文字] -1",
    ],
    "切换底部面板": [
        "[切换底部面板] 表情 | 0.8      ← 聊天中段切到表情面板再收起",
        "[切换底部面板] 收起 | 0.4",
    ],
    "面板切换序列": [
        "[面板切换序列] [{\"面板\":\"表情\",\"停留\":0.9},{\"面板\":\"更多\",\"停留\":1.1},{\"面板\":\"收起\",\"停留\":0.6}]",
    ],
    "发送emoji": [
        "[发送emoji] 捂脸            ← 弹笑脸面板→点选→发送",
        "[发送emoji] 3,5,8 | 18:22   ← 多个表情逐个进输入框后一次发出",
        "[我方打字] 太开心了[大笑]   ← 内嵌写法：文本里直接 [名称]，随文字一起上屏",
    ],
    "对方emoji": [
        "[对方emoji] 害羞",
        "[对方发消息] 是嘛[捂脸]     ← 内嵌写法：文本里直接 [名称]，无需单独一行",
    ],
    "发送表情": [
        "[发送表情] 害羞猫咪",
    ],
    "点赞": [
        "[进入朋友圈]",
        "[点赞]",
        "[闪回聊天] 回到|香儿",
    ],
    "评论": [
        "[进入朋友圈]",
        "[评论] 这也太好看了吧",
    ],
    "发朋友圈": [
        "[发朋友圈] 今天的风很舒服 | 好显身材的连衣裙",
    ],
    "编辑朋友圈": [
        "[编辑朋友圈] [{\"author\":\"我\",\"text\":\"晚上去吃了火锅\",\"images\":[\"美食\"],\"likes\":[\"香儿\"]}]",
    ],
    "手机状态栏": [
        "[手机状态栏] 转账         ← 开场第一行：切成参考视频状态栏",
    ],
    "转账": [
        "[手机状态栏] 转账",
        "[转账] 接收人=香儿 | 金额=520.00 | 备注=别熬夜",
    ],
    "对方转账": [
        "[对方转账] 接收人=我 | 金额=200.00 | 备注=请你喝奶茶",
    ],
    "对方后台发消息": [
        "[对方后台发消息] 联系人=香儿 | 内容=在忙吗 | 置顶=是",
    ],
    "转发消息": [
        "[转发消息] 转发：聊天案例解析（必看）",
    ],
    "对方表情": [
        "[对方发消息] 在忙吗",
        "[对方表情] 害羞猫咪         ← 对方回一张贴纸表情（比文字更松弛）",
    ],
    "对方后台发表情": [
        "[对方后台发表情] 联系人=香儿 | 表情=害羞猫咪",
        "                        ← 画面不切走，只刷主页预览 + 未读角标",
    ],
    "闪回聊天": [
        "[进入朋友圈]",
        "[点赞] 2",
        "[闪回聊天] 回到=香儿    ← 默认自动闪黑：黑幕盖住跳变，切黑再亮起已在聊天",
        "[闪回聊天] 回到=香儿 | 闪黑=否    ← 不要黑幕的裸硬切（旧版行为）",
    ],
    "闪到对方朋友圈": [
        "[打开聊天] 香儿",
        "[闪到对方朋友圈]             ← 一帧黑幕闪进她的朋友圈（跳过资料页）",
        "[闪回聊天] 回到=香儿        ← 再一帧黑幕闪回聊天，一对剪辑切镜",
    ],
}

# 不进 AI 剧本的动作：数据驱动 / 非叙事 / 默认关闭 / 需要真实交互
_NOT_SCRIPT = {
    "编辑主页", "应用场景", "编辑会话", "后台消息队列", "查看图片",
    "设置头像", "设置背景", "修改昵称", "修改签名", "编辑我的资料", "编辑对方资料",
    "打开对方设置", "加入黑名单", "移出黑名单", "返回上一页",
    "播放视频", "点开图片", "向上滚动", "向下滚动", "滚动到",
    "切换Tab", "隐藏键盘", "发送语音", "对方语音",
    "转账金额", "打开转账面板", "打开转账详情", "关闭转账详情", "接收转账",
    "@成员", "撤回我的消息", "对方撤回消息",
}

# 不在编辑器动作下拉里、但脚本/转译要用的动作（保持 UI 不变）
_EDITOR_HIDDEN = {"我方发链接", "对方发链接", "应用场景", "编辑会话"}

_EXTRA_ACTIONS = [
    {"action": "我方发链接", "category": "聊天", "icon": "🔗",
     "desc": "我方在聊天里发送一张链接卡片（公众号文章/分享链接）：标题文字自动换行，字多撑高卡片；"
             "右侧方形缩略图（可空）；左下角来源名可替换（默认「恋爱技巧」）",
     "params": [{"key": "标题", "label": "链接标题（必填，可自动换行）", "type": "text", "default": ""},
                {"key": "图片", "label": "卡片缩略图（可空）", "type": "text", "default": ""},
                {"key": "来源", "label": "左下角来源名（可空默认恋爱技巧）", "type": "text", "default": "恋爱技巧"},
                {"key": "时间", "label": "时间分隔条（如 18:22，可空）", "type": "text", "default": ""}]},
    {"action": "对方发链接", "category": "聊天", "icon": "🔗",
     "desc": "对方发送一张链接卡片（气泡在左），参数含义同「我方发链接」",
     "params": [{"key": "标题", "label": "链接标题（必填）", "type": "text", "default": ""},
                {"key": "图片", "label": "卡片缩略图（可空）", "type": "text", "default": ""},
                {"key": "来源", "label": "左下角来源名（可空默认恋爱技巧）", "type": "text", "default": "恋爱技巧"},
                {"key": "时间", "label": "时间分隔条（如 18:22，可空）", "type": "text", "default": ""}]},
    {"action": "应用场景", "category": "场景", "icon": "🎬",
     "desc": "套用场景预设（联系人列表 + 人物资料 + 朋友圈 + 聊天底稿）",
     "params": [{"key": "场景", "label": "场景名", "type": "text", "default": ""},
                {"key": "数据", "label": "JSON 数据（可空）", "type": "textarea", "default": ""}]},
    {"action": "编辑会话", "category": "场景", "icon": "🧵",
     "desc": "按数据重建某个会话的全部消息（清空并重放）",
     "params": [{"key": "数据", "label": "JSON 数组 / 对象", "type": "textarea", "default": ""}]},
    {"action": "闪到对方朋友圈", "category": "个人主页", "icon": "⚡",
     "desc": "一帧闪进「对方朋友圈」：黑幕淡入→黑屏下瞬时开资料页+朋友圈→黑幕淡出，"
             "跳过资料页（真实微信没有这条路径），观感是电影切黑再亮起；"
             "「对方」填预设名可顺手切人设（可空=沿用当前人设）",
     "params": [{"key": "对方", "label": "联系人预设名（可空）", "type": "text", "default": ""},
                {"key": "闪黑", "label": "闪黑过渡（是/否，默认是）", "type": "text", "default": "是"},
                {"key": "停留", "label": "切完后停留秒数（可空）", "type": "text", "default": ""}]},
]

# 已有动作的参数/描述覆盖（生成器重跑时以此为准，避免手改生成文件被冲掉）
_PARAM_OVERRIDES = {
    "闪回聊天": [
        {"key": "回到", "label": "闪回后进入的会话（可空=只回聊天列表）", "type": "text", "default": ""},
        {"key": "闪黑", "label": "闪黑过渡（是/否，默认是；闪白=是 时自动失效）", "type": "text", "default": "是"},
        {"key": "闪白", "label": "旧版：切镜瞬间叠一帧白（是/否）", "type": "text", "default": ""},
        {"key": "停留", "label": "停留秒数（可空）", "type": "text", "default": ""},
    ],
    # 这三个动作的旧 PARAM_BASELINE 缺参数（点赞缺「序号」、评论缺「序号」、发送表情缺「发送后」），
    # 导致文本剧本写 `[点赞] 序号=2` 这类命名参数被判非法、整段按位置写法解析成错值。
    # 用覆盖表强制让参数基线与动作参数表对齐。
    "点赞": [
        {"key": "序号", "label": "第几条动态（留空=最后一条）", "type": "number", "default": ""},
    ],
    "评论": [
        {"key": "内容", "label": "评论内容", "type": "textarea", "default": ""},
        {"key": "序号", "label": "第几条动态（留空=最后一条）", "type": "number", "default": ""},
    ],
    "发送表情": [
        {"key": "表情", "label": "表情图片路径", "type": "text", "placeholder": "如：/images/myemoji/xxx.png", "default": ""},
        {"key": "发送后", "label": "发完后底部面板去向", "type": "select", "options": ["自动", "键盘", "收起"], "default": "自动"},
    ],
}
_DESC_OVERRIDES = {
    "打字不发": "键盘上打出「给观众看的教学字幕/博弈内容」（如 礼貌开场、学以致用）但**不发送**——"
             "这是教学视频最精彩的卖点，观众看的就是这段字被打出来再删掉的过程。"
             "三段写法：`[打字不发] 字幕 | 停留秒 | 对方插话1；插话2`；"
             "插话支持全部消息格式（按行首标记路由）：`[对方表情] 短名`贴纸、`[对方图片] 短名`图片、"
             "`[对方链接] 标题 | 封面 | 来源`链接卡、`[对方emoji] 微笑`3D黄脸、`[对方语音] 5`语音条、"
             "`[对方转账] 金额 | 备注`转账卡；无标记=纯文字（文字里的 [微笑] 按内嵌 emoji 渲染）",
    "发送emoji": "我方发送 emoji 小表情（微信新版 3D 表情共 108 个：黄脸+手势/物品/企鹅，"
             "弹笑脸面板→逐个点选→发送，全真机动画）。表情写名称/别名/编号，多个用逗号分隔。"
             "全部可用名称及含义见 /images/wxemoji3d/names.json（编号 1~110=面板显示顺序）。"
             "★ 也可以内嵌：把 [名称] 直接写进 [我方打字]/[打字不发] 的文本里（如 太开心了[大笑]），"
             "随文字一起上屏，不必单独占一行；内嵌写法认 names.json 里的名称与别名",
    "对方emoji": "对方发来 emoji 小表情（直接上屏左侧气泡）。表情写名称/编号/随机，"
             "可用名称见 /images/wxemoji3d/names.json。"
             "★ 也可以内嵌：把 [名称] 直接写进 [对方发消息]/[对方后台发消息] 的内容里（如 是嘛[捂脸]），"
             "随文字一起上屏，不必单独占一行；内嵌写法认 names.json 里的名称与别名",
    "闪回聊天": "硬切回聊天界面：默认自动「闪黑」——黑幕淡入→黑屏下瞬间隐藏「我的朋友圈」"
               "或「对方主页/朋友圈」并完成 Tab 切换/进会话→黑幕淡出，把真实微信没有的"
               "跨画面跳变盖在黑幕下；闪白=是 走旧版闪白，闪黑=否 裸硬切；"
               "「回到」填联系人时，闪回后直接进该会话",
}

_HEADER = '''# -*- coding: utf-8 -*-
"""动作表唯一来源（single source of truth）
============================================
本文件由 `_build_registry.py` 生成，**请勿手改生成区**（上部 ACTIONS / PARAM_BASELINE）。
要改动作，先改 `_build_registry.py` 里的元数据，再重跑：

    py _build_registry.py

下游全部从这里派生，不再各写一份：
  - editor_server.ACTIONS            （编辑器动作下拉，保持原样）
  - script_translator.ACTION_SCHEMA  （转译提示词 / 校验器合法动作名）
  - script_translator.ACTION_PARAMS  （参数归一与默认值）
  - script_generator 生成提示词的动作表 + 能力卡
  - script_generator._valid_action_names()

字段说明：
  action   规范动作名（别名归一后）
  desc     一句话说明（进提示词）
  when     什么时候用（能力卡「何时用」，见 _build_registry.py 的 _WHEN）
  snippet  3~6 行片段示例（能力卡，见 _SNIPPET）
  script_ok 是否允许出现在 AI 创作的剧本里
  editor    是否出现在编辑器动作下拉里
  primary   文本剧本 `[动作] 参数` 里那个「参数」叫什么
"""

import json

# ============================================================
# 生成区（勿手改）
# ============================================================

'''


def main():
    actions = extract_editor_actions()
    names = {a["action"] for a in actions}
    for extra in _EXTRA_ACTIONS:
        if extra["action"] not in names:
            actions.append(extra)
            names.add(extra["action"])

    tcm = extract_text_command_map()

    for a in actions:
        name = a["action"]
        a["when"] = _WHEN.get(name, "")
        a["snippet"] = _SNIPPET.get(name, [])
        a["script_ok"] = name not in _NOT_SCRIPT
        a["editor"] = name not in _EDITOR_HIDDEN
        if name in _DESC_OVERRIDES:
            a["desc"] = _DESC_OVERRIDES[name]
        if name in _PARAM_OVERRIDES:
            a["params"] = [dict(p) for p in _PARAM_OVERRIDES[name]]
        if name in tcm:
            a["primary"] = tcm[name]
        else:
            # 兜底：第一个参数键；「数据类」动作没有自然的文本参数
            p0 = (a.get("params") or [{}])[0].get("key")
            a["primary"] = p0 if p0 not in ("数据", "data") else None
        a["params"] = a.get("params") or []

    # 参数基线：保留现有 ACTION_PARAMS 行为，避免派生导致默认值漂移
    import script_translator as st
    baseline = {}
    for k, v in st.ACTION_PARAMS.items():
        baseline[k] = {kk: vv for kk, vv in v.items()}

    # 覆盖过的动作，参数基线也按覆盖表重算（否则新增参数如「闪黑」吃不到默认值）
    def _coerce_default(default, dtype):
        if default in (None, ""):
            return None
        if dtype == "number":
            try:
                return float(default)
            except (TypeError, ValueError):
                return default
        return str(default)

    for name, params in _PARAM_OVERRIDES.items():
        baseline[name] = {p["key"]: _coerce_default(p.get("default"), p.get("type"))
                          for p in params}

    out = [_HEADER]
    out.append("ACTIONS = ")
    out.append(_pformat(actions))
    out.append("\n\n# 现有 ACTION_PARAMS 的行为基线（派生时优先沿用，避免默认值漂移）\nPARAM_BASELINE = ")
    out.append(_pformat(baseline))
    out.append("\n\n# 生成区结束\n")
    out.append(_RUNTIME)
    text = "".join(out)
    path = os.path.join(ROOT, "action_registry.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("已写出 %s（%d 个动作，%d 字符）" % (path, len(actions), len(text)))


def _pformat(obj):
    """缩进友好的 Python 字面量输出（dict 保持插入顺序）。"""
    import pprint
    return pprint.pformat(obj, width=118, sort_dicts=False)


_RUNTIME = r'''
# ============================================================
# 派生接口（下游只调这些）
# ============================================================

PRIMARY_KEY_FALLBACK = "内容"


def by_name() -> dict:
    return {a["action"]: a for a in ACTIONS}


def names() -> set:
    return {a["action"] for a in ACTIONS}


def editor_actions() -> list:
    """给 editor_server.ACTIONS 用（保持编辑器 UI 不变）。"""
    return [a for a in ACTIONS if a.get("editor", True)]


def script_actions() -> list:
    """允许出现在 AI 创作剧本里的动作。"""
    return [a for a in ACTIONS if a.get("script_ok", True)]


def schema() -> list:
    """给 script_translator.ACTION_SCHEMA 用：{action, desc, params:[{key,label}]}。"""
    out = []
    for a in ACTIONS:
        out.append({
            "action": a["action"],
            "desc": a["desc"],
            "params": [{"key": p["key"], "label": p.get("label", p["key"])}
                       for p in a.get("params") or []],
        })
    return out


def _coerce(default, dtype):
    if default in (None, ""):
        return None
    if dtype == "number":
        try:
            return float(default)
        except (TypeError, ValueError):
            return default
    return str(default)


def param_defaults() -> dict:
    """给 script_translator.ACTION_PARAMS 用：动作 -> {参数名: 缺省值}。

    已有动作沿用 PARAM_BASELINE（保持原行为不变）；新动作按各自的参数表推导，
    这样「以前没进过参数表」的 8 个新动作也能正常归一、吃默认值。
    """
    out = {}
    for a in ACTIONS:
        name = a["action"]
        if name in PARAM_BASELINE:
            out[name] = dict(PARAM_BASELINE[name])
            continue
        derived = {}
        for p in a.get("params") or []:
            derived[p["key"]] = _coerce(p.get("default"), p.get("type"))
        out[name] = derived
    # 参数基线里有、但动作表里没有的（历史遗留），一并保留，别让老剧本失效
    for name, d in PARAM_BASELINE.items():
        out.setdefault(name, dict(d))
    return out


def primary_param(action: str):
    """文本剧本 `[动作] 参数` 里那个「参数」的字段名；无参数动作返回 None。"""
    a = by_name().get(action)
    if not a:
        return None
    p = a.get("primary")
    if p:
        return p
    first = (a.get("params") or [{}])[0].get("key")
    return first if first not in ("数据", "data") else None


def capability_cards(only=None) -> list:
    """能力卡：{action, when, snippet, desc}。新功能必须靠它才可能被用出来。"""
    out = []
    for a in ACTIONS:
        if not a.get("script_ok", True):
            continue
        if only is not None and a["action"] not in only:
            continue
        if not (a.get("when") and a.get("snippet")):
            continue
        out.append({"action": a["action"], "when": a["when"],
                    "snippet": list(a.get("snippet") or []), "desc": a.get("desc", "")})
    return out


def to_json() -> str:
    return json.dumps({"actions": ACTIONS}, ensure_ascii=False, indent=1)
'''


if __name__ == "__main__":
    main()
