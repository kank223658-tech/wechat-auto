# -*- coding: utf-8 -*-
"""
剧本转译引擎（内置 DeepSeek V4 Flash）
========================================
把用户输入的剧本文本（标准格式或松散自然语言）翻译成
机器可执行的规范化步骤列表（与 workflow.json 完全一致）。

两条路径：
  1. LLM 路径：调用 DeepSeek chat/completions（OpenAI 兼容，标准库 urllib），
     由 deepseek-v4.1-flash-expires-on-0910 翻译剧本并自动补全仿真动作；
  2. 离线路径：无 API Key / 网络失败 / 解析失败时，
     用规则解析标准剧本格式（复用 main.parse_script_text），保证基础能力可用。

配置保存在项目根目录 settings.json，环境变量 DEEPSEEK_API_KEY 优先。
"""

import json
import os
import random
import re
import urllib.error
import urllib.request

# ============================================================
# 配置
# ============================================================

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(ROOT, "settings.json")
# 人物库：人名 -> 头像路径，脚本里写 [会话] 名字时自动套用（可由场景编辑器「保存到人物库」写入）
PEOPLE_PATH = os.path.join(ROOT, "people.json")

DEFAULT_MODEL = "deepseek-v4.1-flash-expires-on-0910"
DEFAULT_BASE_URL = "https://api.deepseek.com"
API_TIMEOUT_SEC = 60

DEFAULT_SETTINGS = {
    "deepseek_api_key": "",
    "deepseek_model": DEFAULT_MODEL,
    "deepseek_base_url": DEFAULT_BASE_URL,
    # 「打字不发」的默认滞留时长（秒）。脚本里写 `[打字不发] 内容 | 0.3` 可逐条覆盖；
    # 不写时就使用这个默认值，方便统一调整节奏而不必改每条。
    "typing_hold_default": 1.5,
}

# 常用别名 -> 规范动作名（LLM 输出与离线剧本都归一到这里）
ACTION_ALIASES = {
    "回到聊天主页": "返回主页",
    "返回聊天主页": "返回主页",
    "回到主页": "返回主页",
    "返回": "返回主页",
    "回聊天主页": "返回主页",
    "对方打字": "对方发消息",
    "对方正在输入中": "对方正在输入",
    "对方后台发言": "对方后台发消息",
    "后台对方消息": "对方后台发消息",
    "后台发消息": "对方后台发消息",
    "后台消息": "后台消息队列",
    "打开会话": "打开聊天",
    "进入聊天": "打开聊天",
    "进入聊天会话": "打开聊天",
    "点赞动态": "点赞",
    "给动态点赞": "点赞",
    "发表评论": "评论",
    "评论动态": "评论",
    "看朋友圈": "进入朋友圈",
    "进入朋友圈页面": "进入朋友圈",
    "打开个人主页": "打开对方主页",
    "进入个人主页": "打开对方主页",
    "查看个人主页": "打开对方主页",
    "个人主页": "打开对方主页",
    "对方主页": "打开对方主页",
    "查看对方资料": "打开对方主页",
    "查看对方朋友圈": "进入对方朋友圈",
    "看对方朋友圈": "进入对方朋友圈",
    "对方朋友圈": "进入对方朋友圈",
    # 联系人设置页 / 拉黑
    "打开设置": "打开对方设置",
    "打开联系人设置": "打开对方设置",
    "联系人设置": "打开对方设置",
    "对方设置": "打开对方设置",
    "设置页": "打开对方设置",
    "拉黑": "加入黑名单",
    "拉黑对方": "加入黑名单",
    "拉黑他": "加入黑名单",
    "把他拉黑": "加入黑名单",
    "解除拉黑": "移出黑名单",
    "取消拉黑": "移出黑名单",
    "上一页": "返回上一页",
    "后退": "返回上一页",
    "编辑对方主页": "编辑对方资料",
    "设置对方资料": "编辑对方资料",
    # 我的资料 / 我的朋友圈
    "编辑我的主页": "编辑我的资料",
    "编辑个人资料": "编辑我的资料",
    "修改我的资料": "编辑我的资料",
    "设置我的资料": "编辑我的资料",
    "我的资料": "编辑我的资料",
    "编辑我的朋友圈": "编辑朋友圈",
    "设置朋友圈": "编辑朋友圈",
    "编辑动态": "编辑朋友圈",
    "滚屏": "向下滚动",
    "滚动": "向下滚动",
    "滑动": "向下滚动",
    "向上滚动": "向上滚动",
    "上滑": "向上滚动",
    "向上滑": "向上滚动",
    "滚上去": "向上滚动",
    "滚到顶": "滚动到",
    "滚动到顶": "滚动到",
    "滚动到底": "滚动到",
    "滚到底": "滚动到",
    "闪回聊天": "闪回聊天",
    "闪回": "闪回聊天",
    "硬切": "闪回聊天",
    "切回聊天": "闪回聊天",
    "直接返回聊天": "闪回聊天",
    "剪辑返回": "闪回聊天",
    "看视频": "播放视频",
    "点开视频": "播放视频",
    "播放朋友圈视频": "播放视频",
    "点开图片": "点开图片",
    "点开朋友圈图片": "点开图片",
    "查看朋友圈图片": "点开图片",
    "看朋友圈图片": "点开图片",
    "点开配图": "点开图片",
    "查看配图": "点开图片",
    "切换标签": "切换Tab",
    "切换tab": "切换Tab",
    "等待等待": "等待",
    "发朋友圈动态": "发朋友圈",
    "发语音": "发送语音",
    "我方发送图片": "发送图片",
    "对方发送图片": "对方发图片",
    # 链接卡片别名
    "我发链接": "我方发链接",
    "发链接": "我方发链接",
    "发送链接": "我方发链接",
    "分享链接": "我方发链接",
    "发文章": "我方发链接",
    "发送文章": "我方发链接",
    "发卡片": "我方发链接",
    "发送卡片": "我方发链接",
    "对方发链接": "对方发链接",
    "对面发链接": "对方发链接",
    "对方发送链接": "对方发链接",
    "对方发文章": "对方发链接",
}

# 每个动作的参数清单（参数名 -> 缺省值）。
# None / "" 表示"必填或由用户提供，缺省不补"；其它值表示可选参数缺省时自动补全。
ACTION_PARAMS = {
    "打开聊天": {"联系人": None},
    "我方打字": {"内容": None, "插话": None, "时间": None},
    "打字不发": {"内容": None, "停留": 1.5, "插话": None},
    "删除文字": {"数量": -1},
    "对方正在输入": {"秒数": 1.2},
    "对方发消息": {"内容": None, "头像": None, "时间": None},
    "对方后台发消息": {"联系人": None, "内容": None, "图片": None, "头像": None, "发送者": None, "置顶": None, "时间": None},
    "后台消息队列": {"数据": None, "时间": None},
    "查看图片": {"图片": None, "打开": None, "停留": None, "焦点": None, "放大倍率": None},
    "返回主页": {},
    "切换Tab": {"Tab": "微信"},
    "隐藏键盘": {},
    "进入朋友圈": {},
    "打开对方主页": {"对方": None},
    "进入对方朋友圈": {},
    "打开对方设置": {"对方": None},
    "加入黑名单": {"确认": "确定", "加载秒": 1.4, "停留": 0.8},
    "移出黑名单": {"确认": "确定", "加载秒": 1.4, "停留": 0.8},
    "返回上一页": {},
    "编辑对方资料": {"数据": None, "data": None, "对方": None},
    "向下滚动": {"像素": 300},
    "向上滚动": {"像素": 300},
    "滚动到": {"位置": "底部"},
    "播放视频": {"视频": None, "序号": 1, "停留": None},
    "点开图片": {"序号": "1", "停留": None},
    "闪回聊天": {"停留": None, "回到": None, "闪白": None},
    "点赞": {},
    "评论": {"内容": None},
    "发朋友圈": {"内容": None, "图片": None},
    "编辑朋友圈": {"数据": None},
    "编辑我的资料": {"数据": None},
    "应用场景": {"场景": None, "scene": None, "数据": None, "data": None},
    "编辑会话": {"数据": None, "data": None},
    "设置头像": {"图片": None},
    "设置背景": {"图片": None},
    "修改昵称": {"昵称": None},
    "修改签名": {"签名": None},
    "编辑主页": {"数据": None},
    "发送图片": {"图片": None, "打开": None, "停留": None, "焦点": None, "放大倍率": None, "时间": None},
    "对方发图片": {"图片": None, "打开": None, "停留": None, "焦点": None, "放大倍率": None, "时间": None},
    # ---- 链接卡片动作（与 main.execute_step / __wxChatExt 对齐） ----
    "我方发链接": {"标题": None, "图片": None, "来源": "心灵知行", "时间": None},
    "对方发链接": {"标题": None, "图片": None, "来源": "心灵知行", "时间": None},
    "发送语音": {"秒数": 3},
    "对方语音": {"秒数": 3},
    "撤回我的消息": {},
    "对方撤回消息": {},
    "转发消息": {"内容": None},
    "@成员": {"昵称": None},
    "等待": {"秒数": 1},
    # ---- 转账类动作（与 editor_server.ACTIONS / main.execute_step 对齐） ----
    "打开转账面板": {},
    "转账金额": {"接收人": None, "金额": None, "备注": None, "密码": None},
    "转账": {"接收人": None, "金额": None, "备注": None},
    "对方转账": {"接收人": None, "金额": None, "备注": None},
    # ---- 表情类动作 ----
    "发送表情": {"表情": None},
    "对方表情": {"表情": None},
    "对方后台发表情": {"联系人": None, "表情": None, "时间": None},
}

# 这些动作的「秒数/停留」参数应解析为数字（float），而不是字符串，
# 保证编辑器预览与运行时类型一致，也便于「内联停留 | 秒数」等写法被正确当作数字处理。
NUMERIC_PARAMS = {
    "等待": {"秒数"},
    "对方正在输入": {"秒数"},
    "打字不发": {"停留"},
    "发送语音": {"秒数"},
    "对方语音": {"秒数"},
    "加入黑名单": {"加载秒", "停留"},
    "移出黑名单": {"加载秒", "停留"},
}

# 内置动作表（未传入 editor_server.ACTIONS 时用这个生成提示词）
ACTION_SCHEMA = [
    {"action": "打开聊天", "desc": "从聊天列表点击进入指定会话", "params": [{"key": "联系人", "label": "联系人名称"}]},
    {"action": "我方打字", "desc": "手机键盘动画逐字打字 + 回车发送；内容以 [链接] 开头时改发一张链接卡片", "params": [{"key": "内容", "label": "消息内容"}, {"key": "插话", "label": "对方插话（边打字边对面发，可空）"}]},
    {"action": "打字不发", "desc": "打出文字但不发送，停在输入框展示（正文写「给观众看的技巧说明」）", "params": [{"key": "内容", "label": "技巧说明（给观众看）"}, {"key": "停留", "label": "停留秒数"}, {"key": "插话", "label": "对方插话（打字后对面逐条回，可空）"}]},
    {"action": "删除文字", "desc": "退格删除输入框字符（-1 清空）", "params": [{"key": "数量", "label": "删除字符数"}]},
    {"action": "对方正在输入", "desc": "聊天头部显示「对方正在输入...」", "params": [{"key": "秒数", "label": "显示秒数"}]},
    {"action": "对方发消息", "desc": "对方消息以左侧气泡整句上屏；内容以 [链接] 开头时改发一张链接卡片", "params": [{"key": "内容", "label": "消息内容"}, {"key": "头像", "label": "对方头像（可空）"}]},
    {"action": "对方后台发消息", "desc": "给「当前不在看的会话」投递一条对方消息，画面不变，仅把该会话在主页的预览+未读角标刷新（之后返回主页可看到）；内容以 [图片] 开头时变成图片气泡，以 [链接] 开头时变成链接卡片", "params": [{"key": "联系人", "label": "目标会话联系人"}, {"key": "内容", "label": "消息内容（[图片] 开头=图片消息，[链接] 开头=链接卡片）"}, {"key": "图片", "label": "配图路径（图片消息用，可空）"}, {"key": "链接", "label": "链接卡片参数（{标题,图片,来源}，链接消息用，可空）"}, {"key": "头像", "label": "对方头像（可空）"}, {"key": "发送者", "label": "群聊发送者名（可空）"}, {"key": "置顶", "label": "来消息置顶（是/否，可空默认是）"}]},
    {"action": "后台消息队列", "desc": "装载一批后台消息并【立刻】在后台发出去：执行到这一行时，队列里每条消息马上投递给对应会话，刷新主页预览+未读角标，之后打开该会话即可看到（不再按秒/步延迟）", "params": [{"key": "数据", "label": "JSON 数组，形如 [{联系,内容,头像,置顶},...]"}]},
    {"action": "查看图片", "desc": "点开图片放大查看后关闭", "params": [{"key": "图片", "label": "图片路径"}, {"key": "打开", "label": "开法（是=点开并放大/只点开=不放大/可空=不开）"}, {"key": "停留", "label": "停留秒数（可空）"}, {"key": "焦点", "label": "放大位置 x,y（0~1，可空）"}, {"key": "放大倍率", "label": "放大倍率（如 2.0，可空用默认）"}]},
    {"action": "返回主页", "desc": "切回聊天列表主页", "params": []},
    {"action": "切换Tab", "desc": "点击底部 Tab（微信/通讯录/发现/我）", "params": [{"key": "Tab", "label": "Tab 名称"}]},
    {"action": "隐藏键盘", "desc": "收起手机键盘", "params": []},
    {"action": "进入朋友圈", "desc": "从发现页进入朋友圈", "params": []},
    {"action": "打开对方主页", "desc": "点对方消息头像 → 打开「对方个人资料页」：头像/昵称/微信号/地区/朋友资料/朋友圈缩略图/视频号/发消息", "params": [{"key": "对方", "label": "人设名（可空，留空用场景配置的对方）"}]},
    {"action": "进入对方朋友圈", "desc": "从对方资料页点「朋友圈」进入对方朋友圈（全屏封面+动态列表）", "params": []},
    {"action": "打开对方设置", "desc": "点对方资料页右上角「…」推入联系人设置页（编辑备注/设置权限/星标/加入黑名单/投诉/删除联系人）", "params": [{"key": "对方", "label": "人设名（可空）"}]},
    {"action": "加入黑名单", "desc": "拉黑全过程动画：设置页拨「加入黑名单」开关变绿 → 底部确认弹窗 → 确定 → 「正在加载」加载动画（确认=取消则演示取消路径）", "params": [{"key": "确认", "label": "确定/取消"}, {"key": "加载秒", "label": "正在加载秒数"}]},
    {"action": "移出黑名单", "desc": "把已拉黑的联系人移出黑名单（开关关掉 + 确认弹窗 + 加载动画）", "params": [{"key": "确认", "label": "确定/取消"}, {"key": "加载秒", "label": "正在加载秒数"}]},
    {"action": "返回上一页", "desc": "对方朋友圈 → 对方资料页 → 聊天页（iOS 推出转场）", "params": []},
    {"action": "编辑对方资料", "desc": "整体替换「对方」的资料与朋友圈数据（昵称/微信号/地区/头像/封面/签名/朋友圈缩略图/视频号/动态）", "params": [{"key": "数据", "label": "预设名 / JSON 对象"}]},
    {"action": "向下滚动", "desc": "自然滚动指定像素（我的朋友圈/对方朋友圈均可）", "params": [{"key": "像素", "label": "像素值"}]},
    {"action": "向上滚动", "desc": "向上滚动指定像素（我的朋友圈/对方朋友圈均可）", "params": [{"key": "像素", "label": "像素值"}]},
    {"action": "滚动到", "desc": "把朋友圈滚到顶部或底部（对方朋友圈优先，没开时用我的朋友圈）", "params": [{"key": "位置", "label": "顶部/底部"}]},
    {"action": "点开图片", "desc": "点开朋友圈动态里的配图全屏查看（对方朋友圈优先，没开时用我的朋友圈）；序号「2」=第2条第1张，「2,3」=第2条第3张", "params": [{"key": "序号", "label": "第几条动态,第几张图（可空默认 1）"}, {"key": "停留", "label": "停留秒数（可空）"}]},
    {"action": "播放视频", "desc": "点开朋友圈视频全屏播放（留空视频=点开朋友圈里第 N 个视频动态）", "params": [{"key": "视频", "label": "视频地址（可空）"}, {"key": "序号", "label": "第几个视频（可空）"}, {"key": "停留", "label": "停留秒数（可空=按视频时长）"}]},
    {"action": "闪回聊天", "desc": "硬切回聊天界面：瞬间隐藏我的朋友圈/对方主页朋友圈（无滑出转场），观感像视频剪辑的一次切镜；「回到」填联系人则闪回后直接进该会话", "params": [{"key": "停留", "label": "停留秒数（可空）"}, {"key": "回到", "label": "闪回后进入的会话（可空）"}, {"key": "闪白", "label": "是否闪一帧白（是/否）"}]},
    {"action": "点赞", "desc": "给最后一条朋友圈动态点赞", "params": []},
    {"action": "评论", "desc": "键盘动画打字发表评论", "params": [{"key": "内容", "label": "评论内容"}]},
    {"action": "发朋友圈", "desc": "发表文字朋友圈", "params": [{"key": "内容", "label": "文案"}, {"key": "图片", "label": "配图（可空）"}]},
    {"action": "编辑朋友圈", "desc": "重建「我的朋友圈」动态列表（作者/文案/配图/视频/点赞/评论）；也支持 {me:{...},posts:[...]} 对象一次改主页资料+动态", "params": [{"key": "数据", "label": "JSON 数组 / 对象"}]},
    {"action": "编辑我的资料", "desc": "编辑「我」的主页资料：昵称/头像/朋友圈封面/个性签名", "params": [{"key": "数据", "label": "JSON 对象"}]},
    {"action": "设置头像", "desc": "修改我的头像（全局同步）", "params": [{"key": "图片", "label": "图片路径"}]},
    {"action": "设置背景", "desc": "修改朋友圈封面背景", "params": [{"key": "图片", "label": "图片路径"}]},
    {"action": "修改昵称", "desc": "修改我的昵称（全局同步）", "params": [{"key": "昵称", "label": "新昵称"}]},
    {"action": "修改签名", "desc": "修改我的个性签名", "params": [{"key": "签名", "label": "个性签名"}]},
    {"action": "编辑主页", "desc": "按数据重建聊天列表主页（会话列表）", "params": [{"key": "数据", "label": "JSON 数组"}]},
    {"action": "发送图片", "desc": "我方在聊天里发送一张图片；打开=是 则发送后自动点开放大查看再关闭", "params": [{"key": "图片", "label": "图片路径"}, {"key": "打开", "label": "开法（是=点开并放大/只点开=不放大/否=不开，可空）"}, {"key": "停留", "label": "查看停留秒数（可空）"}, {"key": "焦点", "label": "放大位置 x,y（0~1，可空）"}, {"key": "放大倍率", "label": "放大倍率（如 2.0，可空用默认）"}]},
    {"action": "对方发图片", "desc": "对方发送一张图片；打开=是 则上屏后自动点开放大查看再关闭", "params": [{"key": "图片", "label": "图片路径"}, {"key": "打开", "label": "开法（是=点开并放大/只点开=不放大/否=不开，可空）"}, {"key": "停留", "label": "查看停留秒数（可空）"}, {"key": "焦点", "label": "放大位置 x,y（0~1，可空）"}, {"key": "放大倍率", "label": "放大倍率（如 2.0，可空用默认）"}]},
    {"action": "我方发链接", "desc": "我方在聊天里发送一张链接卡片（公众号文章/分享链接）：标题文字自动换行，字多撑高卡片；右侧方形缩略图（可空，缺省显示空占位方框）；左下角来源名可替换（默认「心灵知行」）", "params": [{"key": "标题", "label": "链接标题（必填，可自动换行）"}, {"key": "图片", "label": "卡片缩略图（路径/文件名/关键词，可空；留空按标题自动匹配）"}, {"key": "来源", "label": "左下角来源名（可空默认心灵知行）"}, {"key": "时间", "label": "时间分隔条（如 18:22，可空）"}]},
    {"action": "对方发链接", "desc": "对方发送一张链接卡片（气泡在左），参数含义同「我方发链接」", "params": [{"key": "标题", "label": "链接标题（必填）"}, {"key": "图片", "label": "卡片缩略图（可空）"}, {"key": "来源", "label": "左下角来源名（可空默认心灵知行）"}, {"key": "时间", "label": "时间分隔条（如 18:22，可空）"}]},
    {"action": "发送语音", "desc": "我方发送语音消息", "params": [{"key": "秒数", "label": "语音秒数"}]},
    {"action": "对方语音", "desc": "对方发送语音消息", "params": [{"key": "秒数", "label": "语音秒数"}]},
    {"action": "撤回我的消息", "desc": "撤回我方最后一条消息", "params": []},
    {"action": "对方撤回消息", "desc": "对方撤回一条消息", "params": []},
    {"action": "转发消息", "desc": "我方转发一条消息", "params": [{"key": "内容", "label": "转发内容"}]},
    {"action": "@成员", "desc": "在输入框 @ 成员", "params": [{"key": "昵称", "label": "成员昵称"}]},
    {"action": "等待", "desc": "自然等待指定秒数", "params": [{"key": "秒数", "label": "等待秒数"}]},
]

# 系统不再维护硬编码「默认联系人」名单：人物只有一个来源，即【人物库】people.json，
# 由场景编辑器「保存到人物库」写入。脚本里引用的人名凡不在人物库中，一律视为「没有」，
# 由转译逻辑按同类名替换或提示，绝不套用某个内置默认联系人、也不给它头像。
EXTRA_IMAGES = [
    "/images/header/header02.png",
    "/images/bg/cover.jpg",
    "/images/bg/night.jpg",
    "/images/bg/mao.jpg",
    "/images/bg/alarm.jpg",
    "/images/bg/bg02.jpg",
]

# ---- 人物库分组（用户约定的两类人，绝不混淆）----
CATEGORIES = ("学员", "美女")
# 脚本里人名出现这些字样 => 判定为「学员」；否则默认「美女」
STUDENT_HINTS = ("学员", "学生", "同学", "粉丝")


# ============================================================
# 设置读写
# ============================================================

def load_settings() -> dict:
    """读取 settings.json；环境变量 DEEPSEEK_API_KEY 优先。"""
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data.update(json.load(fh))
    except (OSError, ValueError):
        pass
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        data["deepseek_api_key"] = env_key
    return data


def save_settings(patch: dict) -> dict:
    """把部分配置写回 settings.json，返回合并后的完整配置。"""
    data = load_settings()
    for k, v in (patch or {}).items():
        if k in DEFAULT_SETTINGS:
            data[k] = v
    with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return data


def _typing_hold_default() -> float:
    """读取「打字不发」默认滞留时长（秒），配置缺失或非法时回落到 1.5。"""
    try:
        val = load_settings().get("typing_hold_default", 1.5)
        return float(val)
    except (TypeError, ValueError):
        return 1.5


# ============================================================
# 系统提示词
# ============================================================

def _format_action_table(actions) -> str:
    """把动作表格式化成提示词里的编号清单。"""
    lines = []
    for i, a in enumerate(actions, start=1):
        action = a["action"]
        desc = a.get("desc", "")
        params = a.get("params", []) or []
        if params:
            bits = []
            for p in params:
                default = p.get("default")
                if default in (None, ""):
                    bits.append(f"{p['key']}({p['label']})")
                else:
                    bits.append(f"{p['key']}({p['label']}，默认{default})")
            lines.append(f"{i}. {action} —— 参数：{'、'.join(bits)}。{desc}")
        else:
            lines.append(f"{i}. {action} —— 无参数。{desc}")
    return "\n".join(lines)


def build_system_prompt(actions=None, name_map: dict = None) -> str:
    """构造转译系统提示词。actions 缺省用内置 ACTION_SCHEMA。

    name_map：{剧本原名: 库中替换名}，可把「历史会话块已确定的人名替换」透传给 AI，
    让它把同一旧名替换成脚本主页卡片里用的那个【同一个人】，避免它在 [打开聊天] 里
    又随机换一个不同的人，造成「主页卡片与下面点点开的聊天对不上」。
    """
    table = actions or ACTION_SCHEMA
    extra_lines = "、".join(EXTRA_IMAGES)
    library_block = _library_prompt_block()
    action_text = _format_action_table(table)
    # 人物替换表：AI 遇到这些旧名时【必须】换成右侧指定的人（而不要自己另挑），
    # 保证与历史会话主页卡片用人一致，杜绝「主页是甲、打开聊天却是乙」的错乱。
    if name_map:
        rows = "；".join(f"「{k}」→「{v}」" for k, v in name_map.items())
        map_block = f"\n【人物替换表】（遇到下列剧本原名，一律替换成右侧的人名，不得自选其它人；同一个原名无论出现多少次都用同一个人）\n{rows}\n"
    else:
        map_block = ""

    return f"""你是「微信聊天视频仿真剧本翻译器」。用户输入一段剧本——可能是标准的仿真指令格式，也可能是不太规范的自然语言描述。你的任务是把剧本翻译成一份"机器可执行的动作序列"：只输出一个 JSON 数组，数组每一项是一个动作步骤，格式为 {{"action": "动作名", "params": {{"参数名": 值, ...}}}}。

【动作表】（只能使用下列动作，不得自创动作名或参数名）
{action_text}

{library_block}
其它可用图片：{extra_lines}
{map_block}
【翻译规则】
1. 输出必须且只能是上述格式的 JSON 数组。不要任何解释文字，不要 markdown 代码块标记，不要 `` 包裹。
2. 剧本中出现的消息内容必须原样保留，不得改写、不得翻译、不得润色。
3. 自动补全仿真动作，但【必须保留剧本里已写明的所有时长】，不得改动、不得归一、不得换成缺省值：
   - 涉及"我方打字 / 打字不发 / 对方发消息 / 对方正在输入 / 查看图片 / 发送图片 / 发送语音"等对话动作时，如果之前还没有进入该会话，先自动补一条"打开聊天"；对话结束后若要切到其它页面，自动补"返回主页"。
   - "对方发消息"之前若剧本**没有**写"对方正在输入"，才自动补一条"对方正在输入"，秒数用 1~2；剧本里一旦写了"对方正在输入 X秒"，就必须输出 X 秒，秒数一丝不改。
   - 页面切换、重要动作之间若剧本**没有**写"等待"，才自动补"等待"（0.3~0.8 秒）；剧本里已明确写出的"等待 X秒"必须原样保留，输出 X 秒。
   - 剧本里写的"打字不发 内容 | 0.3"表示打字后停留 0.3 秒，停留值必须原样输出（参数 停留=0.3）；未写"| 秒数"时不强制补缺省。
   - "打字不发 内容 | 0.3 | 对方消息"或"我方打字 内容 | 对方消息"表示在打字间隔/打字后由对方插话：把"对方消息"原样写进该动作的 插话 参数（多句时用"；"分隔，逐字保留，勿改写）；没有"| 插话"时不输出 插话。
   - 凡是剧本里已写明时长的动作，一律用剧本给的时长，绝不替换成缺省值。
   - 剧本没写但真实操作必须有前置的动作（例如点赞/评论前要"进入朋友圈"、"切换Tab 发现"）要自动补全。
4. 人物的唯一来源是【人物库】。剧本里出现的所有人物名，必须且只能从【人物库】中选：
   - 若剧本里的人名已在【人物库】中，直接沿用该人名，并用它后面那张头像路径，不要自造。
   - 若剧本里的人名【不在】人物库，把它替换成人物库里【同类别人】的名字；判断依据：人名含「学员/学生/粉丝」等字样 → 用【学员】组的人；否则 → 用【美女】组的人。替换时在同类里【随机】挑一个人（不要总选人物库列表最前面的那几个，避免主角永远是同一张脸），且优先挑自己这个剧本里还没用过的，避免同一人脸反复出现。如果库里同类人只有一个，那就用它。
   - 替换只换人名；该人物剩下的对话内容、动作节奏全部原样保留，不要改动。同一个未知名在本剧本内无论出现多少次，都必须替换成同一个人，绝不能一会儿换成甲、一会儿换成乙。
   - 绝不把「学员」类换到「美女」类，或反过来。
5. 剧本里出现的联系人，无论是否在默认名单里，只要它在【人物库】里没有对应头像，就必须在整个动作序列最前面自动生成一条"编辑主页"动作（同样地，若剧本里压根没写"编辑主页"，只要后面有"打开聊天"也补一条）：它的 数据 参数直接给一个 JSON 数组（不要用字符串），为剧本中出现的每个联系人生成一条 {{"name": 联系人名, "text": 一句合理的最近消息, "avatar": 用【人物库】里那个人对应的头像路径}}。注意：之后所有"打开聊天"都要能在这个列表里找到对应联系人。绝不要把人物库里不存在的人名填进 数据。
6. 如果剧本是自然语言叙述（例如"我和孙权聊了下周聚餐的事，他说周三有空，我回复好的到时候见"），把它翻译成对应的对话动作序列：打开聊天 → 我方打字 → 对方正在输入 → 对方发消息 → ...；人名按规则 4 归一。
7. 忽略标题、注释、空行（如"## 五、剧本格式规范"、以 # 开头的行）。剧本里已经是标准格式的指令（如"[打开聊天] 小明"）就按原意翻译。
8. 不要脑补用户没有提到的动作和聊天内容（自动补全规则要求的前置动作、等待除外）。
9. "编辑主页"和"编辑朋友圈"的 数据 参数直接给嵌套的 JSON 数组（作为参数值），不要包成字符串；"打开聊天"的 联系人、"我方打字"/"对方发消息"的 内容 等参数填实际文本。
10. 剧本里某条消息以 [图片] / [配图] / 【图片】 / 【配图】 开头（例如「[图片] 一张对镜自拍照」），表示这条消息是一张图片：仍按「对方发消息」或「我方打字」这类消息动作输出，但 内容 参数值必须原样保留 [图片] 前缀（如 内容: "[图片] 一张对镜自拍照"）。系统会把该步自动转成「对方发图片 / 发送图片」并弹出配图面板，让你补上真实图片路径。不要把 [图片] 当作普通聊天文字删掉、改写或丢给「查看图片」动作。
11. 剧本里某条消息以 [链接] / 【链接】 / 【小程序卡片】 / 【分享】 开头（例如「[链接] 聊天案例解析（必看） 解决聊天一聊就死的千年难题」），表示这条消息是一张链接卡片（类似公众号文章/分享链接：标题文字 + 方形缩略图 + 左下来源名）。仍按对应的消息动作输出，但 内容 参数值必须原样保留 [链接] 前缀（如 内容: "[链接] 聊天案例解析（必看） 解决聊天一聊就死的千年难题"），不要把它当普通文字删掉、改写或转成「查看图片」动作。链接标题里含「| 图片 | 来源」时可一并保留（如 内容: "[链接] 标题 | 图片名 | 来源名"）。
12. 涉及「个人主页 / 对方资料页 / 对方朋友圈」的说法（例如"点开对方头像看资料""进她朋友圈看看""翻一下她的朋友圈""从聊天进个人主页再进朋友圈"）：
   - 先确保已经"打开聊天"（不在聊天页时自动补一条 返回主页 + 打开聊天 对应联系人）；
   - 再看对方资料页用"打开对方主页"；看对方朋友圈用"进入对方朋友圈"（它会自动先补上资料页，无需你再写"打开对方主页"）；
   - 看完要退回聊天页时，用若干条"返回上一页"（朋友圈 → 资料页 → 聊天页），不要用"返回主页"（那会直接跳回微信主页）；
   - 要换一套对方的资料/朋友圈内容时用"编辑对方资料"，数据参数给嵌套 JSON 对象（不要包成字符串）。

【示例】
用户剧本：
[回到聊天主页]
[等待] 0.5
[打开聊天] 小明
[等待] 0.8
[我方打字] 在吗，晚上的方案改好了发你
[等待] 0.5
[对方正在输入] 1.2
[对方发消息] 好的，辛苦啦

期望输出（"小明"不在人物库 → 按规则换成人物库里的一个美女，如"香儿"，并自动补"编辑主页"）：
[{{"action": "编辑主页", "params": {{"数据": [{{"name": "香儿", "text": "在吗？", "avatar": "/images/avatar/..."}}]}}}}, {{"action": "返回主页", "params": {{}}}}, {{"action": "等待", "params": {{"秒数": 0.5}}}}, {{"action": "打开聊天", "params": {{"联系人": "香儿"}}}}, {{"action": "等待", "params": {{"秒数": 0.8}}}}, {{"action": "我方打字", "params": {{"内容": "在吗，晚上的方案改好了发你"}}}}, {{"action": "等待", "params": {{"秒数": 0.5}}}}, {{"action": "对方正在输入", "params": {{"秒数": 1.2}}}}, {{"action": "对方发消息", "params": {{"内容": "好的，辛苦啦"}}}}]"""


# ============================================================
# DeepSeek API 调用（标准库 urllib，OpenAI 兼容格式）
# ============================================================

def call_deepseek(api_key: str, system_prompt: str, user_text: str,
                  model: str = DEFAULT_MODEL,
                  base_url: str = DEFAULT_BASE_URL,
                  timeout: float = None, max_tokens: int = None,
                  json_mode: bool = True, meta: bool = False):
    """调用 chat/completions，返回 assistant 的文本内容。失败抛异常。

    timeout：请求超时秒数，缺省用 API_TIMEOUT_SEC（60）。生成类长输出可传更大值。
    max_tokens：限制返回长度，缺省由模型默认。
    json_mode：True 时强制模型输出 JSON（response_format: json_object），
               用于「转译」这类要解析成 JSON 数组的场景；创作生成要的是纯 [指令] 文本，
               传 False 关闭 json_object，允许自由文本返回（否则模型会违心包一层 JSON 或报错）。
    meta：True 时返回 (content, {"finish_reason":..., "usage":...})，供调用方判断
          「是不是被输出长度截断」（推理模型会把预算耗在 reasoning 上，正文为空/被截断）。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    _timeout = float(timeout) if timeout else API_TIMEOUT_SEC

    def _post() -> str:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=_timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")

    try:
        body = _post()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400 and "response_format" in detail:
            # 个别端点不支持 response_format：去掉后重试一次
            payload.pop("response_format", None)
            body = _post()
        else:
            raise RuntimeError(f"DeepSeek API 返回 {exc.code}：{detail}") from exc

    try:
        result = json.loads(body)
        choice = result["choices"][0]
        content = choice["message"]["content"]
        if meta:
            return content, {"finish_reason": choice.get("finish_reason"),
                             "usage": result.get("usage") or {}}
        return content
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"DeepSeek API 响应无法解析：{body[:500]}") from exc


# ============================================================
# JSON 提取与校验
# ============================================================

def _extract_json_array(text: str):
    """从 LLM 回复中稳健提取第一个 JSON 数组（支持嵌套、代码块围栏）。

    返回 (list|None, 错误信息|None)。
    """
    if not text or not text.strip():
        return None, "模型没有返回内容"
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    if start < 0:
        return None, "回复中找不到 JSON 数组"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
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
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate), None
                except ValueError as exc:
                    return None, f"JSON 解析失败：{exc}"
    return None, "JSON 数组未闭合"


def validate_steps(steps: list):
    """规范化步骤：别名归一、剔除未知参数、补可选参数缺省值。

    返回 (steps, warnings)。
    """
    out = []
    warnings = []
    for step in steps:
        if not isinstance(step, dict):
            warnings.append(f"忽略无效步骤：{step}")
            continue
        action = str(step.get("action", "")).strip()
        action = ACTION_ALIASES.get(action, action)
        if not action:
            warnings.append("忽略缺少 action 的步骤。")
            continue
        params = step.get("params")
        params = params if isinstance(params, dict) else {}
        if action in ACTION_PARAMS:
            clean = {}
            hold_provided = False
            for key, default in ACTION_PARAMS[action].items():
                if key in params and params[key] is not None and str(params[key]).strip() != "":
                    clean[key] = params[key]
                    if key == "停留":
                        hold_provided = True
                elif default not in (None, ""):
                    clean[key] = default
            # 「打字不发」未写停留时，用可配置的全局默认（settings.typing_hold_default），
            # 而不是写死的 1.5，方便统一调整节奏。
            if action == "打字不发" and not hold_provided:
                clean["停留"] = _typing_hold_default()
            # 时长类参数统一转成 float（秒数/停留），避免字符串与数字混用
            for key in NUMERIC_PARAMS.get(action, ()):
                if key in clean:
                    try:
                        clean[key] = float(clean[key])
                    except (TypeError, ValueError):
                        pass
            out.append({"action": action, "params": clean})
        else:
            warnings.append(f"未知动作「{action}」，已保留但运行时会跳过。")
            out.append({"action": action, "params": params})
    return out, warnings


# ============================================================
# 时长回填：把剧本里明确写出的时长，重新写到转译结果上（兜底 LLM 归一）
# ------------------------------------------------------------
# LLM 即使被提示要求保留时长，也可能把「0.1」「0.4」这类小值归一成缺省值
# （如 对方正在输入 1.2、等待 1）。这一步在转译/离线解析完成后，按顺序重新读取
# 源码里的显式时长，覆盖到对应步骤上，保证「写进剧本的时长」始终生效。
# 对离线解析结果而言，值与源码一致，属无副作用回填；对 LLM 结果则纠正被归一的时长。
# ============================================================

_SOURCE_TIMING_RE = re.compile(r"^\[(.+?)\]\s*(.*)$")


def _coerce_float(value):
    """把可转 float 的字符串转成 float；空值/不可转原样返回，布尔保持原样。"""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _extract_source_timings(source_text: str):
    """按顺序提取剧本源码里明确写出的时长。

    返回 (waits, typings, dwells)：
      waits:   ['X', ...]  按顺序对应每个 [等待] X
      typings: ['X', ...]  按顺序对应每个 [对方正在输入] X
      dwells:  [('内容', 'Y'), ...]  按顺序对应每个 [打字不发] 内容 | Y
    """
    waits, typings, dwells = [], [], []
    for raw in (source_text or "").splitlines():
        line = raw.strip()
        m = _SOURCE_TIMING_RE.match(line)
        if not m:
            continue
        cmd, arg = m.group(1).strip(), m.group(2).strip()
        if cmd == "等待":
            if arg:
                waits.append(arg)
        elif cmd == "对方正在输入":
            if arg:
                typings.append(arg)
        elif cmd == "打字不发" and "|" in arg:
            # `[打字不发] 内容 | 0.3 | 插话`：第 2 段才是停留秒数，第 3 段是对方插话。
            # 之前用 partition("|") 只按第一个竖线切分，会把「插话」一并算进停留值，
            # 导致 _reassert 把 停留 写成 "0.3 | 插话..." 这类废串。这里显式取第 2 段。
            parts = [x.strip() for x in arg.split("|")]
            content = parts[0]
            hold = parts[1] if len(parts) >= 2 else ""
            dwells.append((content, hold))
    return waits, typings, dwells


def _reassert_source_timings(steps: list, source_text: str) -> list:
    """把源码里明确写出的时长，按顺序覆盖到对应动作步骤上（原地修改并返回）。

    - 只覆盖「源码里明确写了时长」的动作（等待 / 对方正在输入 / 打字不发|秒）。
    - 按出现顺序逐条匹配同类动作，写进的值转成 float。
    - 对离线解析结果而言值与源码一致，属无副作用回填；对 LLM 结果则纠正被归一的时长。
    """
    waits, typings, dwells = _extract_source_timings(source_text)
    wq, tq, dq = list(waits), list(typings), list(dwells)
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        if action == "等待" and wq:
            params["秒数"] = _coerce_float(wq.pop(0))
        elif action == "对方正在输入" and tq:
            params["秒数"] = _coerce_float(tq.pop(0))
        elif action == "打字不发":
            # 「停留」必须只回填到真正写了「| 秒」的那一条，且要跟「内容」对上。
            # 之前按出现顺序对每条 打字不发 都 pop 一次，而 dwells 里只有带「| 秒」的
            # 条目，导致：早于它的 打字不发 被错误套上停留值、下一条 打字不发 直接
            # IndexError。这里改成「按内容匹配」——只有内容一致的那条才刷新停留。
            if dq:
                for _i, (_c, _hold) in enumerate(dq):
                    if _c == str(params.get("内容", "")).strip():
                        if _hold:
                            params["停留"] = _coerce_float(_hold)
                        dq.pop(_i)
                        break
    return steps


# ============================================================
# 时间标注回填：把源码里 `内容 | 时间` 的时刻，写回转译结果（兜底 LLM 归一）
# ------------------------------------------------------------
# 时间标注（时间分隔条占位）由 main.parse_script_text 在离线路径直接解析成 params["时间"]；
# 但 LLM 路径可能把它漏掉。这里按「动作 + 内容」重新回填，保证打进剧本里的时间始终生效。
# ============================================================

def _extract_source_times(source_text: str):
    """按顺序提取剧本源码里明确写出的时间标注（时间分隔条占位）。

    返回 list[(action, content, time)]，对应每个 `[动作] 内容 | 时间`。
    对「对方后台发消息」，content 取「联系人 | 内容」里的内容部分；对「发送图片/对方发图片」，
    content 取图片路径——分别用于与步骤 params["内容"] / params["图片"] 匹配。
    """
    try:
        from main import _strip_trailing_time  # noqa: PLC0415
    except Exception:     # noqa: BLE001
        _strip_trailing_time = lambda a: (a, None)  # noqa: E731
    # 可带时间的动作：文本走 params["内容"]，图片走 params["图片"]
    time_actions = {"我方打字", "对方发消息", "对方后台发消息", "后台消息队列",
                    "发送图片", "对方发图片"}
    out = []
    for raw in (source_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SOURCE_TIMING_RE.match(line)
        if not m:
            continue
        cmd, arg = m.group(1).strip(), m.group(2).strip()
        cmd = ACTION_ALIASES.get(cmd, cmd)   # 归一（我方发送图片->发送图片 等）
        if cmd not in time_actions:
            continue
        if "|" not in arg:
            continue
        stripped, t = _strip_trailing_time(arg)
        if not t:
            continue
        if cmd in ("发送图片", "对方发图片"):
            content = stripped            # 图片路径
        elif cmd == "对方后台发消息" and "|" in stripped:
            content = stripped.split("|", 1)[1].strip()
        else:
            content = stripped
        out.append((cmd, content, t))
    return out


def _reassert_source_times(steps: list, source_text: str) -> list:
    """把源码里 `内容 | 时间` 标注的时刻，按「动作 + 内容」回填到对应步骤（原地并返回）。"""
    time_actions = {"我方打字", "对方发消息", "对方后台发消息", "后台消息队列",
                    "发送图片", "对方发图片"}
    img_actions = {"发送图片", "对方发图片"}
    times = _extract_source_times(source_text)
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if action not in time_actions:
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        key = "图片" if action in img_actions else "内容"
        content = str(params.get(key, "")).strip()
        for _i, (a, c, t) in enumerate(times):
            if a == action and content == c:
                params["时间"] = t
                times.pop(_i)
                break
    return steps


# ============================================================
# 「打字不发 + 紧跟 [等待] X」：把 X 吸收为打字不发的停留
# ------------------------------------------------------------
# 用户习惯的写法是：
#   [打字不发] 还有这种事？不对劲 先试探一手
#   [等待] 0.5
#   [删除文字] 全部
# 这里的 [等待] 0.5 实际就是「打字不发」在输入框的停留时长。系统若不识别，
# 会给「打字不发」再叠加一个固定的默认停留（默认 1.5 秒），导致文字在输入框
# 停得比 [等待] 更长、节奏变慢、且与写出的时长不一致。
# 本组函数把「紧跟 [打字不发] 后面的 [等待] X」吸收成该条打字不发的 停留=X，
# 并删掉那条 [等待]，使总暂停恰为 X，不再叠加默认停留。
# ============================================================

def _source_typing_wait_absorptions(source_text: str):
    """按顺序返回每个 [打字不发] 行的「吸收」信息。

    返回 list[dict|None]，每项对应源码中出现的一个 [打字不发]（不含注释/空行）：
      - 若该行没有内联「| 秒」、且它在源码里【紧跟】一条 [等待] X（中间无其它指令行），
        则该项为 {"hold": float(X)}；
      - 否则为 None（不吸收：已写内联 | 秒 的保持显式停留；不是紧跟 [等待] 的也不处理）。

    依据源码顺序判定，避免把 LLM 自动补的中间等待误当作「用户写的那条 [等待]」。
    """
    entries = []
    for raw in (source_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SOURCE_TIMING_RE.match(line)
        if not m:
            continue
        entries.append((m.group(1).strip(), m.group(2).strip()))
    out = []
    for idx, (cmd, arg) in enumerate(entries):
        if cmd != "打字不发":
            continue
        if "|" in arg:                                   # 已写内联 | 秒：保持显式停留
            out.append(None)
            continue
        nxt = entries[idx + 1] if idx + 1 < len(entries) else None
        if nxt and nxt[0] == "等待":
            try:
                out.append({"hold": float(nxt[1])})
            except (TypeError, ValueError):
                out.append(None)
        else:
            out.append(None)
    return out


def merge_typing_waits(steps: list, source_text: str) -> list:
    """把「[打字不发] 内容」紧跟「[等待] X」吸收为：打字不发 停留=X，并删掉那条 [等待]。

    - 仅当源码里该条 [打字不发] 未写内联「| 秒」、且它在源码中【紧跟】[等待] X、
      同时转译后的步骤里它也【紧跟】一条 [等待] 时才会吸收（双保险，避免误吞
      LLM 自动补的中间等待）。
    - 吸收后总暂停恰为 X；不再为「打字不发」叠加默认停留。

    返回新的步骤列表（原地吸收，返回同一引用）。
    """
    absorbs = _source_typing_wait_absorptions(source_text)
    idx = 0
    out = []
    i = 0
    n = len(steps)
    while i < n:
        step = steps[i]
        out.append(step)
        if isinstance(step, dict) and step.get("action") == "打字不发":
            info = absorbs[idx] if idx < len(absorbs) else None
            idx += 1
            if info and isinstance(step.get("params"), dict):
                nxt = steps[i + 1] if i + 1 < n else None
                if isinstance(nxt, dict) and nxt.get("action") == "等待":
                    step["params"]["停留"] = info["hold"]
                    i += 1                               # 吸收（删除）紧跟的 [等待]
        i += 1
    return out


# ============================================================
# 叙事风格剧本归一化（离线解析前置）
# ------------------------------------------------------------
# AI/大模型生成的脚本常写成「叙事 / 半自然语言」而不是纯 [指令] 格式，
# 导致离线解析把这些行当「无法识别」整体跳过、整段动作丢失。这里把这些常见写法
# 归一化成标准 [指令] 参数行，让离线解析也能识别，避免 AI 不可用时剧本被架空。
#
# 识别并转换的写法：
#   我方在键盘打字“不正面回复 制造悬念”，随后清空输入框
#        -> [打字不发] 不正面回复 制造悬念  +  [删除文字] -1
#   我方在键盘打字“直接戳穿”
#        -> [打字不发] 直接戳穿
#   随后清空输入框  /  清空输入框
#        -> [删除文字] -1
#   [对方插话] 我感觉她挺喜欢你的
#        -> [对方正在输入] 0.8  +  [对方发消息] 我感觉她挺喜欢你的
#   [对方发转账] 微信转账 ¥900.00
#        -> [对方转账] 900.00
#   [操作] 领取转账，显示“已收款 ¥900.00”
#        -> 运行时无「领取转账」动作，跳过并给出提示
#   [我方发送图片] [图片] 封面
#        -> [发送图片] [图片] 封面
#   [视频结束] ...
#        -> 忽略
# ============================================================

# 「我方在键盘打字“内容”，随后清空输入框」——注意内容里的中文引号可能成对或单边
_NARR_TYPING_CLEAR = re.compile(
    r'^\s*(?:我方在键盘打字|我方正在键盘打字|我方键盘输入|我方输入|我打字|在键盘打字|键盘输入)\s*'
    r'[“"「『]?(?P<c>.*?)[”"」』]?\s*[，,]\s*(?:随后清空输入框|随即清空输入框|然后清空输入框|清空输入框)\s*[。.]?\s*$')
# 「我方在键盘打字“内容”」（没写清空）
_NARR_TYPING_ONLY = re.compile(
    r'^\s*(?:我方在键盘打字|我方正在键盘打字|我方键盘输入|我方输入|我打字|在键盘打字|键盘输入)\s*'
    r'[“"「『]?(?P<c>.*?)[”"」』]?\s*[。.]?\s*$')
# 「随后清空输入框」/「清空输入框」
_NARR_CLEAR = re.compile(
    r'^\s*(?:随后清空输入框|随即清空输入框|然后清空输入框|清空输入框)\s*[。.]?\s*$')
# [对方插话] X
_NARR_PEER_INSERT = re.compile(r'^\s*[\[\【]\s*对方插话\s*[\]】]\s*(?P<c>.+?)\s*$')
# [对方发转账] X
_NARR_PEER_TRANSFER = re.compile(r'^\s*[\[\【]\s*对方发转账\s*[\]】]\s*(?P<c>.+?)\s*$')
# [操作] / [步骤] 开头（如 [操作] 领取转账，显示“已收款 ¥900.00”）
_NARR_OP_LEAD = re.compile(r'^\s*[\[\【]\s*(?:操作|步骤)\s*[\]】]\s*(?P<c>.*)$')
# [我方发送图片] X / [我发送图片] X
_NARR_SEND_IMAGE = re.compile(r'^\s*[\[\【]\s*(?:我方发送图片|我发送图片)\s*[\]】]\s*(?P<c>.*?)\s*$')
# [对方发送图片] X -> 对方发图片（别名）
_NARR_PEER_SEND_IMAGE = re.compile(r'^\s*[\[\【]\s*对方发送图片\s*[\]】]\s*(?P<c>.*?)\s*$')
# [视频结束] —— 结尾标记
_NARR_VIDEO_END = re.compile(r'^\s*[\[\【]\s*视频结束\s*[\]】]')


def _extract_amount(text: str):
    """从一段文字里提取金额数字（取第一个 ¥/￥/数字 组合），提取不到返回 None。"""
    m = re.search(r"[¥￥]?\s*(\d+(?:\.\d+)?)", text or "")
    if m:
        return m.group(1)
    return None


# 会话内「说话人：内容」行 -> 标准消息指令
# ------------------------------------------------------------
# 用户在剧本里「打开聊天」后，常直接写对方已有的消息，例如：
#   [打开聊天] 陆香儿
#   陆香儿：我今晚好想哭
#   陆香儿：[图片] 一张自拍照
# 这里负责把「说话人：内容」行（不在历史会话块里）归一成标准消息指令：
#   - 「我/我方/me/自己」说话人 -> [我方打字]
#   - 其它说话人（对方）-> [对方发消息]
# 这样历史块剥离后残留的这类行不会再被 parse_script_text 当成未知行丢弃。
# 内容以 [图片]/[配图] 开头时保留前缀，后续由 convert_image_marker_steps 转成图片动作。
# 仅当「当前已打开某个会话」时才生效；[返回主页] 等离开会话后失效，避免误吞普通文本。
# ------------------------------------------------------------
_CONV_OPEN_RE = re.compile(
    r"^\s*[\[【]\s*(?:打开聊天|打开会话|进入聊天|进入聊天会话|进入会话)\s*[\]】]\s*(.+?)\s*$")
_CONV_HOME_RE = re.compile(
    r"^\s*[\[【]\s*(?:返回主页|回到主页|回到聊天主页|返回聊天主页|回聊天主页|回到)\s*[\]】]")
_SPEAKER_LINE_RE = re.compile(r"^(.+?)[：:](.*)$")


def _is_bracket_lead(line: str) -> bool:
    """行首是否是方括号/书括号（即一条动作指令）。"""
    s = (line or "").strip()
    return s.startswith(("[", "【"))


def convert_inline_speaker_messages(text: str) -> str:
    """把「已打开的会话」内的「说话人：内容」行转成标准消息指令行。

    - 「我/我方/me/自己」说话人 -> [我方打字] 内容
    - 其它说话人（对方）-> [对方发消息] 内容
    - 内容以 [图片]/[配图] 开头时原样保留前缀，交后续 convert_image_marker_steps 转图片动作。
    - 时间标注（`内容 | 21:17`）保留，交由 parse_script_text 的尾部时间剥离摘出。

    上下文跟随 [打开聊天]/[打开会话]（及别名）进入会话，[返回主页]/[回到主页] 后失效；
    历史会话块已在调用前被 split_history_block 剥离，因此这里的说话人行都属于会话内消息。
    返回转换后的全文。
    """
    if not text:
        return text
    lines = text.split("\n")
    out = []
    cur_contact = None
    for line in lines:
        raw = line.strip()
        if not raw:
            out.append(line)
            continue
        m = _CONV_OPEN_RE.match(raw)
        if m:
            cur_contact = (m.group(1) or "").strip()
            out.append(line)
            continue
        # 离开会话：清空上下文，后续「说话人：内容」行不再当作消息
        if _CONV_HOME_RE.match(raw):
            cur_contact = None
            out.append(line)
            continue
        # 仅在当前已打开的会话内、且该行不是动作指令时，才尝试转成消息
        if cur_contact and not _is_bracket_lead(raw):
            sp = _SPEAKER_LINE_RE.match(raw)
            if sp:
                speaker = _normalize_speaker(sp.group(1))
                body = sp.group(2).strip()
                if body:
                    if speaker == "我":
                        out.append(f"[我方打字] {body}")
                    else:
                        out.append(f"[对方发消息] {body}")
                    continue
        out.append(line)
    return "\n".join(out)


def normalize_narrative_script(text: str):
    """把叙事 / 半自然语言剧本归一化成标准 [指令] 参数行。

    返回 (normalized_text, warnings)。无法识别的行原样保留，交由 parse_script_text
    自行「跳过并提示」，绝不静默丢弃用户内容。
    """
    warnings = []
    # 先把「当前会话内的 说话人：内容」行转成标准消息指令，避免它们被当作未知行丢弃。
    text = convert_inline_speaker_messages(text or "")
    out = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            out.append("")
            continue
        # 我方在键盘打字“X”，随后清空输入框 -> 打字不发 + 删除文字
        m = _NARR_TYPING_CLEAR.match(raw)
        if m:
            content = m.group("c").strip()
            if content:
                out.append(f"[打字不发] {content}")
            out.append("[删除文字] -1")
            continue
        # 我方在键盘打字“X”（未写清空）-> 打字不发
        m = _NARR_TYPING_ONLY.match(raw)
        if m:
            content = m.group("c").strip()
            if content:
                out.append(f"[打字不发] {content}")
            continue
        # 随后清空输入框 -> 删除文字
        if _NARR_CLEAR.match(raw):
            out.append("[删除文字] -1")
            continue
        # [对方插话] X -> 对方正在输入 + 对方发消息
        m = _NARR_PEER_INSERT.match(raw)
        if m:
            content = m.group("c").strip()
            if content:
                out.append("[对方正在输入] 0.8")
                out.append(f"[对方发消息] {content}")
            continue
        # [对方发转账] X -> 对方转账（提取金额）
        m = _NARR_PEER_TRANSFER.match(raw)
        if m:
            content = m.group("c").strip()
            amount = _extract_amount(content)
            if amount is None:
                warnings.append(f"「{raw}」未识别出金额，已跳过（可写成 [对方转账] 金额）。")
            else:
                out.append(f"[对方转账] {amount}")
            continue
        # [操作]/[步骤] 开头：仅当是「领取转账」时提示不支持，其余原样保留
        m = _NARR_OP_LEAD.match(raw)
        if m and "领取" in m.group("c"):
            warnings.append("「[操作] 领取转账」暂不支持：当前运行时只有「对方发来转账卡片」，"
                            "没有「点开身份证领取」动作，已跳过该步。")
            continue
        # [我方发送图片] X -> 发送图片
        m = _NARR_SEND_IMAGE.match(raw)
        if m:
            content = m.group("c").strip()
            out.append(f"[发送图片] {content}" if content else "[发送图片]")
            continue
        # [对方发送图片] X -> 对方发图片（别名）
        m = _NARR_PEER_SEND_IMAGE.match(raw)
        if m:
            content = m.group("c").strip()
            out.append(f"[对方发图片] {content}" if content else "[对方发图片]")
            continue
        # [视频结束] -> 忽略
        if _NARR_VIDEO_END.match(raw):
            continue
        out.append(raw)
    return "\n".join(out), warnings


# ============================================================
# 离线兜底：标准剧本格式规则解析
# ============================================================

def _warn_missing_emoji_images(steps, warnings):
    """离线解析时扫一遍表情动作步骤，引用到不存在的图时追加「提示用户补图」的告警。

    只处理剧本里成段的表情动作（`[发送表情]`/`[对方表情]`/`[对方后台发表情]` 等），
    把短名字/文件名解析不到真实图片的项挑出来提示。这样离线预览就会提醒用户：
    哪个表情包还没放图、需要上传后才能真实显示，而不是运行到那儿才静默回退。
    历史会话块里内嵌的表情由 `_line_to_message -> _resolve_history_emoji` 单独提示。
    """
    if not isinstance(steps, list):
        return
    try:
        from main import (ACTION_ALIASES, MY_EMOJI_ACTIONS, PEER_EMOJI_ACTIONS,
                          BG_PEER_EMOJI_ACTIONS, DEFAULT_EMOJI_ALIASES,
                          _norm_emoji_ref, _lookup_emoji_file, _emoji_url_valid)
    except Exception:                # noqa: BLE001
        return
    emoji_actions = (MY_EMOJI_ACTIONS | PEER_EMOJI_ACTIONS | BG_PEER_EMOJI_ACTIONS)
    seen = set()
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        action = ACTION_ALIASES.get(s.get("action"), s.get("action"))
        if action not in emoji_actions:
            continue
        p = s.get("params") or {}
        raw = str(p.get("表情", p.get("图片", "")))
        ref = _norm_emoji_ref(raw)
        if not ref or ref in DEFAULT_EMOJI_ALIASES or ref in seen:
            continue
        seen.add(ref)
        if ref.startswith("http"):
            continue                                   # 外链表情信任存在
        if _emoji_url_valid(ref):
            continue                                   # 真实存在的 /images/ 图
        if _lookup_emoji_file(ref):
            continue                                   # 短名字/文件名搜到了图
        warnings.append(
            f"表情「{raw}」没找到对应图片文件，运行时会回退为默认表情。"
            f"想让这个表情包真实显示，请把它的图片放进「表情包图片」文件夹（自动同步），"
            f"或放进 vue-WeChat/public/images/avatar/、images/emoji/，"
            f"再在剧本里用它的文件名/关键词引用。")


def translate_offline(text: str):
    """离线解析标准剧本格式（[指令] 参数），别名归一，未知指令记 warning。

    返回 (steps, warnings)。
    """
    warnings = []
    text, narr_warnings = normalize_narrative_script(text or "")
    warnings += narr_warnings
    try:
        from main import parse_script_text, ACTION_ALIASES as MAIN_ALIASES  # noqa: PLC0415
    except Exception as exc:                                    # noqa: BLE001
        warnings.append(f"离线解析器加载失败：{exc}")
        return [], warnings

    raw_steps = parse_script_text(text or "")
    steps, extra = validate_steps(
        {"action": s["action"], "params": s.get("params", {})} for s in raw_steps)
    warnings += extra
    _warn_missing_emoji_images(steps, warnings)
    return steps, warnings


# ============================================================
# 统一入口
# ============================================================

# 消息动作 -> 图片动作：把「内容以 [图片]/[配图] 开头」的消息步骤转成图片动作。
# 镜像脚本模式 syncImageAttach 的做法，保证离线/AI 解析产物在脚本模式与并发界面、
# 以及运行器读到的步骤都一致（否则并发界面会当成纯文字发出、且配图清单少一个槽位）。
_MESSAGE_TO_IMAGE_ACTION = {
    "对方发消息": "对方发图片",
    "我方打字": "发送图片",
    "打字不发": "发送图片",
    "发送消息": "发送图片",
}
_IMAGE_MARKER_RE = re.compile(r"^\s*(?:[\[【]\s*(?:图片|配图)\s*[\]】])")
_MESSAGE_TEXT_KEYS = ("内容", "文案")


def convert_image_marker_steps(steps: list) -> list:
    """把「消息动作 + 内容以 [图片]/[配图] 开头」的步骤，转成图片动作。

    内容参数剥掉标记前缀后作为可读描述保留在「内容」里；真实图片路径写入「图片」
    （当前无图则留空，交给前置配图面板补图）。已是图片动作或有真实路径的步骤原样保留。
    就地改写并返回同一引用。
    """
    if not isinstance(steps, list):
        return steps
    for step in steps:
        if not isinstance(step, dict):
            continue
        target = _MESSAGE_TO_IMAGE_ACTION.get(step.get("action"))
        if not target:
            continue
        params = step.get("params") or {}
        if not isinstance(params, dict):
            continue
        content = ""
        for k in _MESSAGE_TEXT_KEYS:
            if k in params and params[k] is not None:
                content = params[k]
                break
        if not isinstance(content, str):
            continue
        m = _IMAGE_MARKER_RE.match(content)
        if not m:
            continue
        desc = content[m.end():].strip() or "图片消息"
        prev = params.get("图片")
        step["action"] = target
        step["params"] = {"图片": prev if isinstance(prev, str) else "", "内容": desc}
    return steps


# 消息动作 -> 链接动作：把「内容以 [链接]/【链接】/[小程序卡片] 开头」的消息步骤转成链接卡片动作。
# 与 convert_image_marker_steps 对称：离线/AI 解析都要求保留 [链接] 前缀，这里统一收敛成
# 「我方发链接 / 对方发链接」，让编辑器配图清单、链接图库预载、运行器都按链接卡片处理，
# 而不是把它当普通文字发出（封面/来源也会被正确解析，不再落到「插话」里）。
_MESSAGE_TO_LINK_ACTION = {
    "对方发消息": "对方发链接",
    "我方打字": "我方发链接",
    "发送消息": "我方发链接",
    "打字不发": "我方发链接",
}
_LINK_MARKER_RE = re.compile(
    r"^\s*(?:[\[【]\s*(?:链接|小程序卡片|分享)\s*[\]】])\s*(.*)$")


def convert_link_marker_steps(steps: list) -> list:
    """把「消息动作 + 内容以 [链接] 开头」的步骤，转成链接卡片动作。

    内容形如 `[链接] 标题 | 图片 | 来源`：按 `|` 拆出标题/图片/来源（来源缺省「心灵知行」）；
    时间分隔条（params["时间"]）保留。已是「我方发链接/对方发链接」的步骤、以及自带链接分支的
    「对方后台发消息」原样保留。就地改写并返回同一引用。
    """
    if not isinstance(steps, list):
        return steps
    for step in steps:
        if not isinstance(step, dict):
            continue
        target = _MESSAGE_TO_LINK_ACTION.get(step.get("action"))
        if not target:
            continue
        params = step.get("params") or {}
        if not isinstance(params, dict):
            continue
        content = ""
        for k in _MESSAGE_TEXT_KEYS:
            if k in params and params[k] is not None:
                content = params[k]
                break
        if not isinstance(content, str):
            continue
        m = _LINK_MARKER_RE.match(content)
        if not m:
            continue
        parts = [x.strip() for x in m.group(1).strip().split("|")]
        title = parts[0] if parts else ""
        image = parts[1] if len(parts) > 1 and parts[1] != "-" else ""
        source = parts[2] if len(parts) > 2 and parts[2] else "心灵知行"
        if not title and not image:
            continue
        # 封面引用（「课程封面图」这类关键词/文件名）先按同一套规则解析成真实 URL，
        # 让编辑器的配图清单直接显示封面缩略图，而不是显示「未配图」却在实际运行时自动配图。
        # 解析落空（空 / 「无」等「不要图」关键词）时保留原引用，交运行时复现同样的空封面。
        try:
            _resolved = _resolve_link_image_ref(title, image)
        except Exception:            # noqa: BLE001
            _resolved = ""
        new_params = {"标题": title, "图片": _resolved or image, "来源": source}
        if params.get("时间"):
            new_params["时间"] = params["时间"]
        step["action"] = target
        step["params"] = new_params
    return steps


def _contact_name_of_step(step: dict) -> str:
    """从单个步骤里读出「联系人 / 会话名」字段（可能为空字符串）。"""
    params = step.get("params") or {}
    if not isinstance(params, dict):
        return ""
    return str(params.get("联系人") or params.get("name") or "").strip()


def _iter_edit_home_names(params: dict):
    """从「编辑主页 / 编辑会话 / 应用场景」的 数据 数组里，逐个产出会话名。

    产出的是会话条目 dict（供需要时就地改写其 name），以及该条目的名字。
    """
    data = params.get("数据")
    if isinstance(data, list):
        for it in data:
            if isinstance(it, dict) and it.get("name"):
                yield it, str(it["name"]).strip()


def normalize_step_people(steps: list, pre_mapping: dict = None) -> list:
    """把步骤列表里的人名按人物库做一次确定性归一。

    只处理「既不在人物库、也不是系统默认联系人」的名字：把它替换成人物库里
    同类别的别人名（学员/美女不混）。同一剧本里同一个未知名会映射到同一个人，
    避免出现"同一人两个名字"。已存在的人物库名、默认联系人名原样保留。

    pre_mapping 可传入 {原名: 替换后的人名}，用于延续上一阶段（如历史会话块）已做出的
    替换决定，保证前后一致。这些值同时会被标记为已占用，避免后续再把它们当作候选。

    同时会为「编辑主页 / 编辑会话 / 应用场景」里每个会话条目补上人物库头像：
    解析后的名字若在人物库中，就套用该头像，保证 AI 输出即便漏掉 avatar 也能自动匹配。

    返回新的步骤列表（原地替换名字，返回同一引用以便继续使用）。
    """
    people_flat = _people_flat()
    if not people_flat:
        return steps
    used = set(pre_mapping.values()) if pre_mapping else set()   # 已被选用的库人名
    mapping = dict(pre_mapping or {})                            # 未知原名 -> 替换后的人名

    # 第一遍：收集剧本里真正引用的、且属于"库中人 / 默认联系人"的名字，当作已占用，
    # 后续替换时不再重复选它们。library 的名字若没被用到，仍可作为替换候选。
    for step in steps:
        if not isinstance(step, dict):
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        action = step.get("action")
        if action == "打开聊天":
            n = _contact_name_of_step(step)
            if n and n in people_flat:
                used.add(n)
        elif action in ("编辑主页", "编辑会话", "应用场景"):
            for _it, it_name in _iter_edit_home_names(params):
                if it_name in people_flat:
                    used.add(it_name)
        elif action == "对方后台发消息":
            n = str(params.get("联系人", params.get("会话", ""))).strip()
            if n and n in people_flat:
                used.add(n)
        elif action in ("后台消息队列", "后台消息"):
            data = params.get("数据", params.get("data", params.get("队列")))
            if isinstance(data, list):
                for _it in data:
                    if isinstance(_it, dict):
                        cn = str(_it.get("联系", _it.get("contact", ""))).strip()
                        if cn and cn in people_flat:
                            used.add(cn)

    def _resolve(name: str) -> str:
        # `懒猫不懒（暧昧期）` 这类带关系注释的写法先还原成库里的名字，再判断是否需替换。
        name = _normalize_people_name(name, people_flat)
        if name in people_flat:
            return name
        if name in mapping:
            return mapping[name]
        repl = _pick_replacement(name, used, people_flat)
        if repl:
            mapping[name] = repl["name"]
            used.add(repl["name"])
            return repl["name"]
        return name

    for step in steps:
        if not isinstance(step, dict):
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        action = step.get("action")
        # 打开聊天 / 相关对话动作里的 联系人
        if action == "打开聊天":
            name = _contact_name_of_step(step)
            if name:
                params["联系人"] = _resolve(name)
        # 对方后台发消息：联系人也要归一，保证与主页/打开聊天用的是同一个人
        if action == "对方后台发消息":
            n = str(params.get("联系人", params.get("会话", ""))).strip()
            if n:
                params["联系人"] = _resolve(n)
        # 后台消息队列：数据数组里每条的联系人也归一（王心乐→库中映射名）
        if action in ("后台消息队列", "后台消息"):
            data = params.get("数据", params.get("data", params.get("队列")))
            if isinstance(data, list):
                for it in data:
                    if isinstance(it, dict):
                        cn = str(it.get("联系", it.get("contact", ""))).strip()
                        if cn:
                            r = _resolve(cn)
                            if "联系" in it:
                                it["联系"] = r
                            if "contact" in it:
                                it["contact"] = r
        # 重建主页 / 会话 / 场景：数据数组里每个会话的 name，并自动补上人物库头像
        if action in ("编辑主页", "编辑会话", "应用场景"):
            for it, it_name in _iter_edit_home_names(params):
                it["name"] = _resolve(it_name)
                resolved = it["name"]
                info = people_flat.get(resolved)
                if info:
                    it["avatar"] = info["avatar"]
    return steps


def _extract_bg_queue_contacts(data) -> list:
    """从「后台消息队列」的数据里提取联系人名列表（用于主页兜底）。

    data 可能是 JSON 数组、JSON 字符串或 .json 文件路径；每条形如
    {"联系":X,...} / {"contact":X,...}，解析失败返回空列表。
    """
    try:
        if isinstance(data, str):
            data = data.strip()
            if data.endswith(".json") and os.path.isfile(data):
                with open(data, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = json.loads(data)
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    names = []
    for it in data:
        if isinstance(it, dict):
            n = str(it.get("联系", it.get("contact", "")) or "").strip()
            if n:
                names.append(n)
    return names


def ensure_all_contacts_in_home(steps: list) -> list:
    """确保 [编辑主页] 的「数据」列表覆盖此后所有 [打开聊天] 引用的联系人。

    历史会话块生成的 [编辑主页] 只覆盖块内的联系人；若剧本其余部分（例如 LLM 转译结果）
    又通过 [打开聊天] 引用了块内没有的联系人（如"范思琪""酸奶不酸"），运行期会因
    "聊天列表中找不到联系人"而 fail。本函数在拼好最终步骤后做一次兜底：
    凡是 [打开聊天] 的联系人不在 [编辑主页] 数据里，就补一条
    {{"name": 联系人名, "text": "", "avatar": 人物库头像}}（人物库没有该名字时 avatar 留空，
    运行时用默认头像），保证每个 "打开聊天" 都能在首页列表里找到对应项。

    - 若步骤里根本没有 [编辑主页]，则在最前面插入一条，其数据由所有 [打开聊天] 联系人构成。
    - 同名不重复追加；已有联系人原样保留，不动它已有的 messages / text。

    返回新的步骤列表（原地补齐，返回同一引用）。
    """
    # 找出唯一的 [编辑主页]（若有），并收集其已有的联系人名
    home = None
    home_exists = False
    existing = set()
    for i, step in enumerate(steps):
        if isinstance(step, dict) and step.get("action") == "编辑主页":
            home_exists = True
            data = (step.get("params") or {}).get("数据")
            if isinstance(data, list):
                home = data
                existing = {str(it.get("name", "")).strip()
                            for it in home if isinstance(it, dict)}
            break
    # 收集所有 [打开聊天] / [对方后台发消息] / [后台消息队列] 引用的联系人（按出现顺序去重）
    contacts = []
    seen = set()

    def _add_contact(n: str):
        if n and n not in seen:
            seen.add(n)
            contacts.append(n)

    for step in steps:
        if not isinstance(step, dict):
            continue
        pp = step.get("params") or {}
        act = step.get("action")
        if act == "打开聊天":
            _add_contact(str(pp.get("联系人", "")).strip())
        elif act == "对方后台发消息":
            _add_contact(str(pp.get("联系人", pp.get("会话", ""))).strip())
        elif act in ("后台消息队列", "后台消息"):
            data = pp.get("数据", pp.get("data", pp.get("队列")))
            for n in _extract_bg_queue_contacts(data):
                _add_contact(n)
    if not contacts:
        return steps
    if home is None:
        if home_exists:
            # 数据来自 .json 文件路径，无法内联补联系人；贸然插入一条会与文件版冲突，直接跳过。
            return steps
        # 没有 [编辑主页]：在最前面插入一条，用所有联系人初始化
        home = []
        steps.insert(0, {"action": "编辑主页", "params": {"数据": home}})
    people_flat = _people_flat()
    for n in contacts:
        if n in existing:
            continue
        info = people_flat.get(n)
        home.append({"name": n, "text": "", "avatar": info["avatar"] if info else ""})
        existing.add(n)
    return steps


def cap_home_and_align_contacts(steps: list, warnings: list = None) -> list:
    """离线解析专用：主页一屏最多显示 9 个会话，超出部分丢弃并对齐 [打开聊天]。

    主页会话列表是固定布局（9 行 × 110px，容器 overflow hidden），第 10 个起不可见。
    因此离线解析把历史块 10+ 个会话全塞进 [编辑主页] 会导致：
      - 主页显示不下，多出来的会话在画面里根本没有；
      - [打开聊天] 引用了这些屏幕外/历史块里不存在的人时，ensure 兜底把它们追加进主页，
        变成第 10、11…… 个，前后人物对不上、视频错乱。

    本函数在 ensure 兜底之前执行：
      1. [编辑主页] 数据只保留前 9 个会话（第 10 个及之后丢弃，保持剧本原有顺序）；
      2. 把所有 [打开聊天] 引用的联系人检查一遍：若不在主页前 9 个里，按剧本顺序
         把它对齐到主页前 9 个里「尚未被其它 [打开聊天] 占用」的联系人（保持主页
         排队顺序），保证打开的人一定是主页上显示的人。

    返回新的步骤列表（原地修改，返回同一引用）。
    """
    if warnings is None:
        warnings = []
    home = None
    for s in steps:
        if isinstance(s, dict) and s.get("action") == "编辑主页":
            data = (s.get("params") or {}).get("数据")
            if isinstance(data, list):
                home = data
            break
    if home is None:
        return steps
    # 1) 截断到前 9 个会话（保持剧本顺序）
    if len(home) > 9:
        dropped = home[9:]
        del home[9:]
        names = "、".join(str(d.get("name", "？")) for d in dropped)
        warnings.append(f"主页一屏最多显示 9 个会话，已丢弃第 10 个及之后的会话：{names}")
    home_names = [str(d.get("name", "")).strip() for d in home if isinstance(d, dict)]
    # 2) 收集所有「引用联系人」的动作里的联系人（按出现顺序去重）。
    #    打开聊天 优先级最高（决定主流程进哪个会话），其后是 对方后台发消息/对方后台发表情/
    #    后台消息队列（给主页投递消息，同样要求联系人在主页可见，否则运行期会"找不到会话"）。
    contacts = []
    seen = set()

    def _add(c):
        if c and c not in seen:
            seen.add(c)
            contacts.append(c)

    def _act_contact(s):
        p = s.get("params") or {}
        return str(p.get("联系人") or p.get("会话") or "").strip()

    for s in steps:
        if isinstance(s, dict) and s.get("action") == "打开聊天":
            _add(_act_contact(s))
    for s in steps:
        if not isinstance(s, dict):
            continue
        a = s.get("action")
        if a in ("对方后台发消息", "对方后台发表情"):
            _add(_act_contact(s))
        elif a in ("后台消息队列", "后台消息"):
            p = s.get("params") or {}
            data = p.get("数据", p.get("data", p.get("队列")))
            if isinstance(data, list):
                for it in data:
                    if isinstance(it, dict):
                        _add(str(it.get("联系", it.get("contact", ""))).strip())
    # 3) 不在主页前 9 里的联系人，按顺序对齐到主页里「尚未被占用」的某个联系人
    used = {n for n in contacts if n in home_names}   # 已占用（本来就在主页里的）
    queue = [n for n in home_names if n not in used]  # 主页里还没被点开过的人，按顺序排队
    mapping = {}                                      # 旧联系人 -> 主页联系人
    for n in contacts:
        if n in home_names:
            continue
        if queue:
            mapping[n] = queue.pop(0)
        else:
            warnings.append(
                f"联系人「{n}」不在历史会话里，且主页前 9 个联系人都已被占用，"
                f"请把它加入历史会话块的前 9 位。")
    if mapping:
        for s in steps:
            if not isinstance(s, dict):
                continue
            p = s.get("params") or {}
            a = s.get("action")
            if a == "打开聊天":
                old = str(p.get("联系人", "")).strip()
                if old in mapping:
                    p["联系人"] = mapping[old]
            elif a in ("对方后台发消息", "对方后台发表情"):
                old = str(p.get("联系人") or p.get("会话", "")).strip()
                if old in mapping:
                    p["联系人"] = mapping[old]
            elif a in ("后台消息队列", "后台消息"):
                data = p.get("数据", p.get("data", p.get("队列")))
                if isinstance(data, list):
                    for it in data:
                        if isinstance(it, dict):
                            old = str(it.get("联系", it.get("contact", ""))).strip()
                            if old in mapping:
                                if "联系" in it:
                                    it["联系"] = mapping[old]
                                if "contact" in it:
                                    it["contact"] = mapping[old]
        for old, new in mapping.items():
            warnings.append(
                f"联系人「{old}」不在主页前 9 个里，已对齐到主页人物「{new}」，"
                f"保证引用（打开聊天/后台消息等）与主页显示一致。若不想被替换，"
                f"请把它写进历史会话块的前 9 位。")
    return steps


def translate(text: str, actions=None, api_key: str = None,
              model: str = None, base_url: str = None, pre_mapping: dict = None) -> dict:
    """把剧本文本转译为规范化步骤列表。

    pre_mapping 可传入 {原名: 替换后的人名}（如历史会话块已做出的人名替换），
    透传给 normalize_step_people，保证与历史块里已确定的人名保持一致。

    返回 {"steps": [...], "warnings": [...], "source": "llm"|"offline"}
    """
    settings = load_settings()
    api_key = (api_key or settings.get("deepseek_api_key") or "").strip()
    model = model or settings.get("deepseek_model") or DEFAULT_MODEL
    base_url = base_url or settings.get("deepseek_base_url") or DEFAULT_BASE_URL
    warnings = []

    # 先把「叙事 / 半自然语言」写法（打字不发+清空、对方插话、对方发转账、我方发送图片、
    # 视频结束等）归一化成标准 [指令] 行。这样无论走 LLM 还是离线兜底，都能稳定识别这些
    # 大模型未必认识的松散写法，避免「脚本没能正确识别步骤」。original_text 保留原文本，
    # 供下方的时长回填与「打字不发+等待」吸收逻辑按【用户写出的原始时长】工作。
    original_text = text or ""
    text, narr_warnings = normalize_narrative_script(original_text)
    warnings += narr_warnings

    if api_key:
        try:
            prompt = build_system_prompt(actions, name_map=pre_mapping)
            raw = call_deepseek(api_key, prompt, text, model, base_url)
            steps, err = _extract_json_array(raw)
            if steps is not None:
                steps, extra = validate_steps(steps)
                warnings += extra
                normalize_step_people(steps, pre_mapping)
                _reassert_source_timings(steps, original_text)
                _reassert_source_times(steps, original_text)
                # 「打字不发 内容」紧跟「[等待] X」：把 X 吸收为打字不发的停留，
                # 不再叠加默认停留，也删掉那条被吸收的 [等待]。
                steps = merge_typing_waits(steps, original_text)
                if not steps:
                    warnings.append("转译结果为空，请检查剧本内容。")
                return {"steps": steps, "warnings": warnings, "source": "llm"}
            warnings.append("LLM 返回内容解析失败，已降级为离线解析：" + str(err))
        except Exception as exc:                                # noqa: BLE001
            warnings.append(f"调用 DeepSeek 失败，已降级为离线解析：{exc}")

    steps, extra = translate_offline(text)
    warnings += extra
    normalize_step_people(steps, pre_mapping)
    _reassert_source_timings(steps, original_text)
    _reassert_source_times(steps, original_text)
    steps = merge_typing_waits(steps, original_text)
    if not steps:
        warnings.append("未识别出任何有效指令，请检查剧本文本是否符合标准格式。")
    return {"steps": steps, "warnings": warnings, "source": "offline"}


# ============================================================
# 两人对话剧本 -> 对话记录（用于场景编辑器「剧本一键注入」预置消息历史）
# ============================================================

DIALOGUE_SYSTEM_PROMPT = """你是「微信两人聊天剧本整理助手」。用户会粘贴一段两人对话剧本，格式可能不规范（比如说话人没加冒号、错别字、多人串行、夹带表情符号）。你的任务是把这段剧本整理成一份"对话记录"。

只输出一个 JSON 对象：{"dialogue": [{"speaker": "说话人", "text": "该句内容"}, ...]}

要求：
1. 严格按原文先后顺序，不要增删、合并或重新排序任何一句话。
2. 说话人尽量保留原文叫法；若说话人是"我 / 我方 / me / 我自己 / 自己"，统一写成"我"。
3. 只保留两人之间的对话内容；明显不属于对话的干扰行请忽略。
4. 修正明显错别字与格式错误，但不要改动句子原意。
5. text 只填该句正文，不要带说话人前缀、不要带冒号。
6. 若某句以 "[图片]" 或 "[配图]"（含全角【图片】）开头，代表这条消息是一张图片：
   - 在该项里额外加一个布尔字段 "image": true；
   - text 填成该图片的描述文字（去掉 "[图片]/[配图]" 前缀，如 "一张对镜自拍照"），若没有描述就填空字符串。
7. 其它类似 "[纠结]" 之类的方括号只是普通语气/表情词，保持原样放进 text，不要当作图片标记。
只输出 JSON 对象，不要任何解释。"""


def _normalize_speaker(sp) -> str:
    """把「我/我方/me/自己」等称呼统一成「我」。"""
    low = ((sp or "").strip()).lower()
    if low in ("我", "我方", "me", "我自己", "自己"):
        return "我"
    return (sp or "").strip()


# 图片消息标记：一行内容以 [图片] / [配图] / 【图片】 / 【配图】 开头即为一条图片消息。
_IMAGE_HEAD_RE = re.compile(r"^\s*(?:[\[【]\s*(?:图片|配图)\s*[\]】])")


def _pic_marker(body: str):
    """检测 body 是否以 [图片]/[配图] 标记开头。

    返回 (是否图片, 描述文本)：是图片时剥掉标记前缀，返回去除后的描述；
    不是图片时原样返回 (False, body)。
    """
    body = body or ""
    m = _IMAGE_HEAD_RE.match(body)
    if m:
        return True, body[m.end():].strip()
    return False, body


def _extract_dialogue(text: str):
    """从 LLM 回复中提取 {"dialogue": [...]} 或一个 JSON 数组。

    返回 (list|None, 错误信息|None)，各项为 {"speaker","text"}。
    """
    if not text or not text.strip():
        return None, "模型没有返回内容"
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    items = None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("dialogue"), list):
            items = obj["dialogue"]
        elif isinstance(obj, list):
            items = obj
        else:
            return None, "返回内容不是预期的 JSON 结构"
    except ValueError:
        arr, err = _extract_json_array(text)
        if arr is None:
            return None, err
        items = arr
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        sp = it.get("speaker")
        tx = it.get("text")
        if sp is None and isinstance(it.get("sender"), str):
            sp = it.get("sender")
        if tx is None and isinstance(it.get("content"), str):
            tx = it.get("content")
        if not isinstance(sp, str) or not isinstance(tx, str):
            continue
        if not tx.strip():
            continue
        entry = {"speaker": _normalize_speaker(sp), "text": tx.strip()}
        if it.get("image"):
            entry["image"] = True
        else:
            # 兜底：LLM 可能保留了 [图片] 前缀，视为图片并剥掉前缀作为描述
            is_img, desc = _pic_marker(tx.strip())
            if is_img:
                entry["image"] = True
                entry["text"] = desc
        out.append(entry)
    if not out:
        return None, "LLM 返回的数组为空或字段不完整"
    return out, None


def _offline_dialogue(text: str):
    """确定性逐行解析：每行按第一个「：/:」切分成「说话人：内容」。

    返回 (dialogue, warnings)。
    """
    warnings = []
    dialogue = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)[：:](.*)$", line)
        if not m:
            warnings.append("跳过无法识别的行：" + line[:20])
            continue
        speaker = _normalize_speaker(m.group(1))
        body = m.group(2).strip()
        if not body:
            continue
        is_img, desc = _pic_marker(body)
        entry = {"speaker": speaker, "text": desc}
        if is_img:
            entry["image"] = True
        dialogue.append(entry)
    return dialogue, warnings


def build_dialogue(text: str, api_key: str = None,
                   model: str = None, base_url: str = None) -> dict:
    """把两人对话剧本整理成 [{'speaker','text'}] 列表。

    优先用 DeepSeek 归一（格式有误也能修），失败 / 无 key 时降级为确定性逐行解析。

    返回 {"dialogue": [...], "warnings": [...], "source": "llm"|"offline"}
    """
    settings = load_settings()
    api_key = (api_key or settings.get("deepseek_api_key") or "").strip()
    model = model or settings.get("deepseek_model") or DEFAULT_MODEL
    base_url = base_url or settings.get("deepseek_base_url") or DEFAULT_BASE_URL
    warnings = []

    if api_key:
        try:
            raw = call_deepseek(api_key, DIALOGUE_SYSTEM_PROMPT, text, model, base_url)
            dia, err = _extract_dialogue(raw)
            if dia:
                return {"dialogue": dia, "warnings": warnings, "source": "llm"}
            warnings.append("LLM 返回内容解析失败，已降级为离线解析：" + str(err))
        except Exception as exc:                                # noqa: BLE001
            warnings.append("调用 DeepSeek 失败，已降级为离线解析：" + str(exc))

    dia, offline_warnings = _offline_dialogue(text)
    warnings += offline_warnings
    if not dia:
        warnings.append("未能从剧本中提取出对话，请确认每行是「说话人：内容」格式。")
    return {"dialogue": dia, "warnings": warnings, "source": "offline"}


# ============================================================
# 历史会话块：单文本剧本里直接写「人名 + 会话 + 对白」-> [编辑主页] 步骤
# ------------------------------------------------------------
# 用途：让用户在脚本模式直接写历史会话，无需再进场景编辑器或手写嵌套 JSON。
# 例：
#   [历史会话]
#   [会话] 陆香儿
#   陆香儿：我今晚好想哭
#   我：哭什么呀
#   陆香儿：[图片] 一张自拍照
#   我：[语音] 5秒
#   [会话] 小明
#   小明：周末有空吗
#   我：有的，怎么了
#   [历史会话结束]
#   [打开聊天] 陆香儿
#   ...
# 解析后 -> [{"action":"编辑主页","params":{"数据":[{name,messages:[...]},...]}}]
# ============================================================

# 历史会话块的起始 / 结束 / 会话头标记（兼容中英文方括号与全书角括号）
_HISTORY_START_RE = re.compile(r"^\s*[\[\【]\s*(?:历史会话|历史会话区|会话历史)\s*[\]】]\s*$")
_HISTORY_END_RE = re.compile(r"^\s*[\[\【]\s*历史会话结束\s*[\]】]\s*$")
_CONV_HEAD_RE = re.compile(r"^\s*[\[\【]\s*会话\s*[\]】]\s*(.+?)\s*$")
# 行首是方括号/书括号 => 是动作指令（如 [打开聊天]），用于判定历史块结束
_BRACKET_LEAD_RE = re.compile(r"^\s*[\[\【]")
# 会话内的时间标注行（如 `[时间戳] 21:17` / `【时间戳】21:17`）：属于历史块内的
# 分隔条占位，不是动作指令，不应终止历史块（否则会截断后续会话，导致会话加载不完全）。
_TIME_STAMP_RE = re.compile(r"^\s*[\[\【]\s*(?:时间戳|时间)\s*[\]】]")
_VOICE_HEAD_RE = re.compile(r"^\s*[\[\【]\s*语音\s*[\]】]")
_VOICE_SECONDS_RE = re.compile(r"(\d+)\s*秒")
# 链接消息标记：一行内容以 [链接] / 【链接】 开头即为一条链接卡片消息。
_LINK_HEAD_RE = re.compile(
    r"^\s*[\[\【]\s*(链接|小程序卡片|分享|对方发链接|我方发链接|对面发链接|"
    r"发送链接|发链接|对方发文章|我方发文章)\s*[\]】]")
# 表情消息标记：一行内容以 [表情] / 【表情】 开头即为一条表情贴纸消息。
# 兼容各种常用写法——`[对方表情]`、`[发送表情]`、`[发表情]`、`[表情包]`、`[发贴纸]`、
# `[对方发表情]`、`[我方发表情]` 等（只要括号里的词包含「表情 / 贴纸」就视为表情消息），
# 否则历史会话里的 `[对方表情] 猫咪捂脸` 会被当成一段纯文本，视频里显示文字而非表情贴纸。
_EMOJI_HEAD_RE = re.compile(
    r"^\s*[\[\【]\s*([^\]】]*?(?:表情|贴纸)[^\]】]*?)\s*[\]】]", re.IGNORECASE)

# 历史会话里「[表情] 描述」的表情图兜底 url（wxemoji 里的一张，渲染为表情贴纸气泡）。
_DEFAULT_HISTORY_EMOJI = "/images/wxemoji/wx_1.png"


def _resolve_history_emoji(desc: str, warnings=None, who=""):
    """按 [表情] 后的描述词，在图片目录里搜一张表情图；搜不到用默认 wxemoji 兜底。

    只搜表情照片目录（images/emoji、images/wxemoji、images/avatar），避免误命中正文里的
    关键词图片。返回 /images/... URL；无论如何都返回非空，保证渲染成表情贴纸而非文字。

    warnings：可传入告警列表。当描述词在图片目录里搜不到对应图片时，追加一条
    「提示用户补图」的告警，让离线解析阶段就提醒用户：这个表情包还没有对应图片文件，
    需要上传后才能真实显示，而不是幕后静默回落成默认表情。
    """
    desc = (desc or "").strip()
    if not desc:
        return _DEFAULT_HISTORY_EMOJI
    try:
        from main import _lookup_emoji_file  # 复用 main 的「按名字搜表情图」（懒加载避免循环导入）
        hit = _lookup_emoji_file(desc)
    except Exception:                # noqa: BLE001
        hit = ""
    if hit:
        return hit
    if warnings is not None:
        who = (who or "").strip()
        prefix = f"{who}：" if who else ""
        warnings.append(
            f"历史会话里的表情「{prefix}{desc}」没找到对应图片文件，已回退为默认表情。"
            f"想让这个表情包真实显示，请把它的图片放进「表情包图片」文件夹（自动同步），"
            f"或放进 vue-WeChat/public/images/avatar/、images/emoji/，"
            f"再在剧本里用它的文件名/关键词引用。")
    return _DEFAULT_HISTORY_EMOJI


def _resolve_link_image_ref(title: str, ref: str) -> str:
    """历史链接卡片图片兜底：复用 main._resolve_link_image 把描述词/短文件名/空 解析成真实 URL。

    与实时「我方发链接」保持同一套解析规则（封面 / 视频封面 / 随机 / 文件名 / 图库关键词 /
    按标题自动匹配），保证历史会话里的链接卡片也能显示真实封面，而非把「案例封面」这类
    描述词直接当 src（破图）。main 不可用时回退为原引用。

    额外增强：「封面.jpg」这类「封面 + 扩展名」写法，会先剥离扩展名再按封面关键词挑封面图，
    避免被当成普通文件名匹配失败落空（例如封面应为 link 图库里的男生.jpg）。
    """
    ref = (str(ref or "")).strip()
    title = str(title or "")
    try:
        from main import _resolve_link_image, _resolve_link_cover
    except Exception:            # noqa: BLE001
        return ref
    # 「封面」+扩展名（封面.jpg / 封面图.png）：先剥离扩展名，若内容属「封面」描述词，
    # 则按标题挑一张封面图，避免当成普通文件名匹配失败落空。
    m = re.match(r"^(.+?)(\.\w{1,5})$", ref)
    base = m.group(1) if m else ref
    if base and ("封面" in base or base.lower().startswith("cover")):
        try:
            return _resolve_link_cover(title)
        except Exception:            # noqa: BLE001
            pass
    return _resolve_link_image(title, ref)


def _line_to_message(line: str, warnings=None):
    """把一行「说话人：内容」转成一条消息 dict；无法解析返回 None。

    说话人「我/我方/me/自己」归一为 dir=me（右侧绿泡），其它为 dir=peer（左侧白泡）。
    内容以 [语音] 开头 -> kind=voice；以 [图片]/[配图] 开头 -> kind=image；
    以 [表情]/[对方表情]/[发表情] 等表情标记开头 -> kind=emoji；否则 kind=text。
    支持尾部时间标注（时间分隔条占位）：`说话人：内容 | 18:22` -> 消息带 time 字段。

    warnings：可传入告警列表；表情图解析不到真实图片时会追加「提示用户补图」的告警。
    """
    line = (line or "").strip()
    if not line:
        return None
    m = re.match(r"^(.+?)[：:](.*)$", line)
    if not m:
        return None
    speaker = _normalize_speaker(m.group(1))
    body = m.group(2).strip()
    if not body:
        return None
    # 时间标注：`内容 | 18:22` / `内容 | 昨天 23:52`，剥离后剩余为正文
    time_field = None
    if "|" in body:
        try:
            from main import _strip_trailing_time  # 复用 main 的时间标注剥离（懒加载避免循环导入）
            body, time_field = _strip_trailing_time(body)
        except Exception:                # noqa: BLE001
            body, time_field = body, None
    is_me = (speaker == "我")
    # 表情贴纸消息：[表情]/【表情】/【对方表情】/【发送表情】 等开头。
    # 后面文字（如「万事皆OK」）作为描述/关键词，用它去「表情库/头像/wxemoji」目录里搜一张图；
    # 搜不到用默认 wxemoji 兜底，并通过 warnings 提示用户补图。
    emoji_m = _EMOJI_HEAD_RE.match(body)
    if emoji_m:
        marker = (emoji_m.group(1) or "").strip()
        desc = body[emoji_m.end():].strip()
        emoji_url = _resolve_history_emoji(desc, warnings, who=speaker)
        # 标记里带「对方 / 对面」明确是对方发的表情（覆盖说话人推断），否则按说话人方向。
        if "对方" in marker or "对面" in marker:
            is_me = False
        msg = {"dir": "me" if is_me else "peer", "kind": "emoji",
               "text": (desc or "表情"), "image": emoji_url}
    # 语音消息：[语音]（可带秒数，如 [语音] 5秒）
    elif _VOICE_HEAD_RE.match(body):
        seconds = 3
        scale = _VOICE_SECONDS_RE.search(body)
        if scale:
            seconds = int(scale.group(1))
        msg = {"dir": "me" if is_me else "peer", "kind": "voice",
               "text": "", "seconds": seconds}
    # 链接卡片消息：[链接]/【链接】/【小程序卡片】开头。
    # 格式：`[链接] 标题 | 图片 | 来源`；标题=标记后内容，图片/来源/时间用 `|` 分隔。
    # 图片缺省时留空 -> 前端渲染空占位方框（用户要求「图片用占位即可」）；来源缺省「心灵知行」。
    else:
        lm = _LINK_HEAD_RE.match(body)
        if lm:
            # 标记里写明「对方 / 我方」时以标记为准（历史会话行常写成
            # 「粉丝 军：[对方发链接] 标题 | 图 | 来源 | 19:19」）。
            _marker = lm.group(1) or ""
            if "对方" in _marker or "对面" in _marker:
                is_me = False
            elif "我方" in _marker:
                is_me = True
            rest = body[lm.end():].strip()
            parts = [x.strip() for x in rest.split("|")]
            link_title = parts[0] if parts and parts[0] else ""
            img_ref = parts[1] if (len(parts) > 1 and parts[1] != "-") else ""
            # 历史链接卡片的图：与实时「我方发链接」一致，走 _resolve_link_image 归一，
            # 支持「封面/视频封面/随机/短文件名/关键词/留空按标题匹配」等写法，
            # 避免把「案例封面」这类描述词直接当 src 导致破图；命中不了返回 ''（渲染空占位方框）。
            image = _resolve_link_image_ref(link_title, img_ref)
            link_msg = {
                "dir": "me" if is_me else "peer",
                "kind": "link",
                "title": link_title,
                "image": image,
            }
            if len(parts) > 2 and parts[2]:
                link_msg["source"] = parts[2]
            else:
                link_msg["source"] = "心灵知行"
            msg = link_msg
        else:
            is_img, desc = _pic_marker(body)
            if is_img:
                # 历史块里 [图片] 只给了描述没给路径：按描述词兜底搜一张现成图（用户要求「随便找图片」），
                # 保证渲染成图片气泡而非 src 为空。搜不到再用默认该会话占位图，绝不留下空 src 破图。
                img_url = _resolve_history_emoji(desc)  # 复用搜图，命中任意图片目录
                msg = {"dir": "me" if is_me else "peer", "kind": "image",
                       "text": desc, "image": img_url}
            else:
                msg = {"dir": "me" if is_me else "peer", "kind": "text", "text": body}
    if time_field:
        msg["time"] = time_field
    return msg


# 历史会话块里允许用「指令式」写法表示一条会话内消息，省去"说话人："前缀。若不处理，
# [我方发链接] 这类行首以 [ 开头的行会被 _BRACKET_LEAD_RE 误判为"动作指令"，导致历史块
# 提前结束、该行被当成独立动作排到剧本前面，执行时因不在聊天页而报错。
# 这里把消息型指令转成「说话人：[标记] 内容」行供 _line_to_message 复用；
# 非消息型指令（导航/流程类）返回 None，仍按"结束历史块"处理。
def _history_directive_msg(line: str):
    m = re.match(r"^\s*[\[\【]\s*([^\]】]+?)\s*[\]】]\s*(.*)$", line)
    if not m:
        return None
    directive = m.group(1).strip()
    body = m.group(2).strip()
    # (指令词, 说话人, 消息标记)
    for d, speaker, marker in (
        ("我方发链接", "我", "[链接] "), ("发链接", "我", "[链接] "),
        ("发送链接", "我", "[链接] "), ("分享链接", "我", "[链接] "),
        ("发文章", "我", "[链接] "), ("发送文章", "我", "[链接] "),
        ("发卡片", "我", "[链接] "), ("发送卡片", "我", "[链接] "),
        ("对方发链接", "对方", "[链接] "), ("对面发链接", "对方", "[链接] "),
        ("对方发送链接", "对方", "[链接] "), ("对方发文章", "对方", "[链接] "),
        ("我方发图片", "我", "[图片] "), ("发图片", "我", "[图片] "),
        ("发送图片", "我", "[图片] "), ("对方发图片", "对方", "[图片] "),
        ("对面发图片", "对方", "[图片] "),
        ("我方发表情", "我", "[表情] "), ("发一个表情", "我", "[表情] "),
        ("发表情", "我", "[表情] "), ("发贴纸", "我", "[表情] "),
        ("发送表情", "我", "[表情] "), ("发送表情包", "我", "[表情] "),
        ("发个表情", "我", "[表情] "), ("发一张表情", "我", "[表情] "),
        ("表情包", "我", "[表情] "), ("表情", "我", "[表情] "),
        ("对方发表情", "对方", "[表情] "), ("对面发表情", "对方", "[表情] "),
        ("对方表情", "对方", "[表情] "), ("对方表情包", "对方", "[表情] "),
        ("对方发送表情", "对方", "[表情] "), ("对面发来表情", "对方", "[表情] "),
        ("我方发语音", "我", "[语音] "), ("发语音", "我", "[语音] "),
        ("对方发语音", "对方", "[语音] "),
        ("对方发消息", "对方", ""), ("对面发消息", "对方", ""),
    ):
        if directive == d:
            return "%s：%s%s" % (speaker, marker, body)
    return None


def _category_of_name(name: str) -> str:
    """判断一个名字属于哪一类：含学员/学生/粉丝等字样 => 学员，否则 => 美女。"""
    s = (name or "").strip().lower()
    for hint in STUDENT_HINTS:
        if hint in s:
            return "学员"
    return "美女"


def _load_people_groups() -> dict:
    """读取人物库 people.json，返回规范化的 {组名: {人名: 头像路径}}。

    兼容两种已存在的写法：
      1. 分组写法  {"学员": {"学员-小康": "..."}, "美女": {"香儿": "..."}}；
      2. 扁平写法  {"学员-小康": "...", "香儿": "...", ...}，此时按名字关键字自动归组。

    组名固定为 CATEGORIES（学员 / 美女）；不存在或损坏时返回两个空组。
    """
    try:
        with open(PEOPLE_PATH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = None
    groups = {c: {} for c in CATEGORIES}
    if not isinstance(d, dict):
        return groups
    if any(k in d for k in CATEGORIES):
        # 分组写法：取各组里「值应为 dict」的部分
        for c in CATEGORIES:
            sub = d.get(c)
            if isinstance(sub, dict):
                groups[c] = {str(k): str(v) for k, v in sub.items() if isinstance(v, str)}
        return groups
    # 扁平写法：按名字关键字归组
    for name, avatar in d.items():
        if isinstance(avatar, str):
            groups[_category_of_name(str(name))][str(name)] = avatar
    return groups


def _people_flat() -> dict:
    """把分组人物库拍平成 {人名: {avatar, group}}，用于快速查找。"""
    out = {}
    for g, sub in _load_people_groups().items():
        for name, avatar in sub.items():
            out[name] = {"avatar": avatar, "group": g}
    return out


# 联系人名尾部的「关系/状态注释」：`懒猫不懒（暧昧期）`、`苏苏(学员)`、`香儿【新加】`。
_NAME_ANNOT_RE = re.compile(r"[\(（\[【][^\)）\]】]{0,24}[\)）\]】]\s*$")


def _normalize_people_name(name: str, people_flat: dict = None) -> str:
    """把带括号注释的联系人名还原成人物库里的名字；库里有原名（含括号）时原样保留。

    剧本常写成 `懒猫不懒（暧昧期）`（括号里是关系阶段备注），而人物库里登记的是
    `懒猫不懒`。若不做还原，这个名字会被当成「库里没有的陌生人」随机换成另一个人，
    导致主角被顶替。这里只在「剥掉注释后能命中人物库」时才剥，避免把库里真名
    （如 `熙熙（酒吧）`）误剥成不存在的人。
    """
    name = (name or "").strip()
    if not name:
        return name
    people_flat = people_flat if people_flat is not None else _people_flat()
    if name in people_flat:
        return name
    stripped = name
    for _ in range(3):                       # 允许多层注释（（暧昧期）（新加））
        m = _NAME_ANNOT_RE.search(stripped)
        if not m:
            break
        stripped = stripped[:m.start()].strip()
        if not stripped:
            return name
        if stripped in people_flat:
            return stripped
    return name


def _pick_replacement(source_name: str, used_names: set, people_flat: dict) -> dict:
    """为库中不存在的人找一条「同类别人名 + 头像」的替换。

    - source_name: 剧本里的原名（用于判断它属于学员还是美女）。
    - used_names: 本轮转译里已占用的人名集合（避免同一面孔重复出现）。
    - 从人物库里挑一个同类、且尚未被占用的；同类都已占用时退而求其次，
      挑同类里没被源名占用的另一个（因为源名本身不在库中）。

    每次调用都会把同类的候选【随机打乱】再挑，这样不同剧本、不同次运行会
    轮换到不同的人——避免"主角总是人物库里的前几个人"；但仍严格限定在同类，
    且在 used_names 里已出现的（含剧本里已存在的库中原名）绝不会被选中，
    保证替换结果不会与剧本里其它真实角色撞名、也不会跨类。

    返回 {name, avatar, group}；若人物库该类别为空则返回 {}。
    """
    group = _category_of_name(source_name)
    pool = [n for n, info in people_flat.items() if info["group"] == group]
    if not pool:
        return {}
    order = list(pool)
    random.shuffle(order)
    # 优先选同类里还没用过的
    for n in order:
        if n not in used_names:
            return {"name": n, "avatar": people_flat[n]["avatar"], "group": group}
    # 同类全部被占用：再允许复用一个（保证替代可用性，但尽量避开源名）
    for n in order:
        if n != source_name:
            return {"name": n, "avatar": people_flat[n]["avatar"], "group": group}
    return {}


def _library_prompt_block() -> str:
    """把人物库格式化成一屏可读文本，供 AI 转译提示词参考。

    人物库就是系统的唯一人物来源（与场景编辑器「保存到人物库」同步）。
    只列出库里真有的人名 + 头像路径；不在库里的人名一律视为"没有"。
    """
    groups = _load_people_groups()
    lines = ["【人物库】（这是唯一可用的人物名单，名字与头像都从这里取，不要编造其它名字或头像）"]
    for c in CATEGORIES:
        names = list(groups[c].keys())
        if not names:
            lines.append(f"- {c}：（暂无）")
            continue
        bits = [f"{n}({groups[c][n]})" for n in names]
        lines.append(f"- {c}：{'、'.join(bits)}")
    return "\n".join(lines)


def _apply_name_mapping(text: str, mapping: dict) -> str:
    r"""把文本里 `mapping` 的 key（原名）整体替换成 value（替换后的人名）。

    用于把「历史会话块」里已经发生的人名替换同步到历史块之外的剧本文本上，
    让后面 [打开聊天] / [编辑会话] 等步骤引用的是同一个替换后的人名，
    避免"同一人两个名字"导致视频聊天对象与历史对不上、信息错乱。

    按名字长度降序排列再匹配，防止短名被长名包含时替换出错；re.sub 单趟替换，
    替换结果不会再被当作 key 二次替换。

    ★ 关键防护：只对「像人名的」原名做回写，并用词边界匹配。
    历史块里若有一个联系人名是「.」这类纯符号（人物库没有时会被替换），若整串替换
    会把「0.1」里的小数点也换成替换名，导致所有时长数字失效、运行期回落到固定默认值。
    因此这里只回写含中文或字母数字的名字，且用 (?<!\w)…(?!\w) 边界避免误伤「0.1」这类
    被数字夹住的小数点。
    """
    if not text or not mapping:
        return text

    def _is_wordlike(name: str) -> bool:
        # 含中文汉字或字母数字才认为「像人名」；纯符号（如「.」「？」）不参与回写，
        # 防止污染剧本里的时长/标点。
        return any(ch.isalnum() for ch in name)

    keys = sorted((k for k in mapping if _is_wordlike(k)), key=len, reverse=True)
    if not keys:
        return text
    pattern = re.compile("|".join(f"(?<!\\w){re.escape(k)}(?!\\w)" for k in keys))
    return pattern.sub(lambda m: mapping[m.group(0)], text)


def _collect_text_person_names(text: str) -> list:
    """从「原始剧本文本」里收集全部人物名，按出现顺序去重。

    只收集用户自己写出来代表「人」的名字，两类：
      1. 历史会话头的联系人：[会话] X
      2. 动作指令里的联系人：[打开聊天] X
    这两个来源正是把「历史会话卡片」和「下面要点开的聊天」绑定在一起的关键。
    收集全量后再统一做一次替换，就能保证同一旧名在全剧本里永远映射到同一个人，
    从而让主页会话列表与 [打开聊天] 严格对齐，不会出现「主页没有这个人却点了进去」。
    """
    names, seen = [], set()
    open_re = re.compile(r"^\s*[\[【]\s*打开聊天\s*[\]】]\s*(.+?)\s*$")
    people_flat = _people_flat()
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        m = _CONV_HEAD_RE.match(s)          # [会话] X
        if m:
            n = (m.group(1) or "").strip()
        else:
            m2 = open_re.match(s)           # [打开聊天] X
            n = (m2.group(1) or "").strip() if m2 else ""
        # `懒猫不懒（暧昧期）` 这类带关系注释的名字先还原成库里的 `懒猫不懒`，
        # 否则同一个人的「会话头写法」和「打开聊天写法」会被当成两个陌生人分别随机替换。
        if n:
            n = _normalize_people_name(n, people_flat)
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    return names


def build_name_replacement_map(names: list, pre_mapping: dict = None) -> dict:
    """为一批人名一次性确定「唯一的同一人替换」映射。

    对每个【不在人物库】里的名字，调用 _pick_replacement 从同类里随机挑一个
    尚未被占用的库中人作为替换；并保证：
      - 同一个原名【只】映射到同一个替换人（返回的 dict 本身就是唯一来源）；
      - 已被选中的库人不会再被别的原名选走（避免撞面）；
      - pre_mapping（如历史会话块已经确定的替换）优先沿用，不再重复随机。
    返回 {原名: 替换后的人名}。人物库为空时返回 pre_mapping 的拷贝。
    """
    people_flat = _people_flat()
    mapping = dict(pre_mapping or {})
    if not people_flat:
        return mapping
    used = set(mapping.values())            # 已占用的库人名
    for n in names:
        if not n:
            continue
        if n in people_flat:
            used.add(n)                     # 库中原名被用到，后续不再把它当候选
            continue
        if n in mapping:                    # 已有映射（含 pre_mapping），沿用不重选
            continue
        repl = _pick_replacement(n, used, people_flat)
        if repl and repl["name"] != n:
            mapping[n] = repl["name"]
            used.add(repl["name"])
    return mapping


def split_history_block(text: str, pre_mapping: dict = None):
    """从剧本文本里提取「历史会话块」，转成一条 [编辑主页] 步骤。

    pre_mapping：{原名: 替换后的人名}，用于延续同一剧本人名已确定的替换（避免重复随机导致
    主页与 [打开聊天] 用不同的人）。传入后本函数优先沿用 pre_mapping，不再对这些名字重新随机。

    返回 (history_steps, cleaned_text, warnings, replacement_map)：
      - history_steps: 含 [编辑主页]（数据=各会话的 name+messages+avatar），无历史块则为 []。
      - cleaned_text: 历史块之外剩下的剧本文本（供 translate / 离线解析继续）。
      - warnings: 人名被替换 / 库中无此人等提示。
      - replacement_map: 原名 -> 替换后的人名（供后续「打开聊天」等步骤保持一致），
        无历史块时为空 dict。
    多会话由 [会话] 联系人名 切分；每条对白按 [说话人：内容] 识别，支持 [图片]/[语音] 标记；
    块结束于 [历史会话结束] 行，或下一条以 [ 开头的动作指令行。
    """
    # 没出现历史块标记时直接原样返回，避免改动纯动作剧本
    if not text or "[历史会话" not in text.replace("【", "[").replace("】", "]"):
        return [], text, [], {}

    lines = text.splitlines()
    people_flat = _people_flat()    # 会话名归一 + 头像套用共用同一份人物库快照
    conversations = []          # [{"name":..., "messages":[...]}]
    cur_name = None             # 当前正在收集的会话名
    cur_messages = []
    in_block = False
    block_start = None          # [历史会话] 起始行号
    clean_start = len(lines)    # 历史块结束后剧本从哪一行继续
    warnings = []               # 历史块内：人名替换、表情图缺失等提示

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not in_block:
            if _HISTORY_START_RE.match(line):
                in_block = True
                block_start = i
            continue
        # 下面都已在历史块内
        if _HISTORY_END_RE.match(line):
            clean_start = i + 1             # 去掉块结束标记行
            break
        head = _CONV_HEAD_RE.match(line)
        if head:
            # 上一个会话落盘，切换到新会话
            if cur_name is not None:
                conversations.append({"name": cur_name, "messages": cur_messages})
            cur_name = _normalize_people_name((head.group(1) or "").strip(), people_flat)
            cur_messages = []
            continue
        if _TIME_STAMP_RE.match(line):
            # [时间戳] HH:MM 属于会话内的时间标注（时间分隔条占位），不是动作指令；
            # 忽略它并继续收集本会话，避免历史块被提前截断、后续会话与消息丢失。
            continue
        if _BRACKET_LEAD_RE.match(line):
            hist_msg_line = _history_directive_msg(line)
            if hist_msg_line is not None:
                # 行首是「消息型指令」（如 [我方发链接]）：当作当前会话的一条历史消息，
                # 不要结束历史块（否则该行会变成剧本里独立的动作，执行时不在聊天页而报错）。
                msg = _line_to_message(hist_msg_line, warnings)
                if msg is not None and cur_name is not None:
                    cur_messages.append(msg)
                continue
            # 行首是真正的动作指令（导航/流程类）：历史块到此结束，该行保留给剧本
            clean_start = i
            break
        # 普通对白行
        msg = _line_to_message(raw, warnings)
        if msg is not None and cur_name is not None:
            cur_messages.append(msg)

    # 落盘最后一个会话
    if cur_name is not None:
        conversations.append({"name": cur_name, "messages": cur_messages})

    if not conversations or block_start is None:
        return [], text, [], {}

    # cleaned = 历史块之前（若存在） + 历史块之后（含后续动作指令）
    cleaned_lines = lines[:block_start] + lines[clean_start:]
    cleaned = "\n".join(cleaned_lines).strip("\n")
    # 头像自动从人物库套用：查得到就带上 avatar；查不到就用「同类别人名」替换并保留整段对话。
    home = []
    # 沿用上层给定的同剧本人名替换（如全局映射），并据此初始化「已占用」集合，
    # 避免本块（或后续步骤）再把已选中的库中人当作替换候选，保证全剧同一人名同一张脸。
    used_names = set(pre_mapping.values()) if pre_mapping else set()   # 本轮已占用的人名
    replacement_map = dict(pre_mapping or {})                           # 原名 -> 替换后的人名
    # 先收集本块所有会话里"已存在于人物库"的真名，并标记为已占用：
    # 这样后续给未知人挑选替换对象时，绝不会换成库里这些真实角色，避免撞名/张冠李戴。
    for c in conversations:
        if c["name"] in people_flat:
            used_names.add(c["name"])
    for c in conversations:
        original_name = c["name"]
        info = people_flat.get(original_name)
        if info:
            # 库里就有：直接用，头像带上（上面已把该名字加入 used_names）
            home.append({"name": original_name, "messages": c["messages"], "avatar": info["avatar"]})
            continue
        # 本块里同一个原名可能出现在多个会话：若已经替换过，就沿用同一个人，保证前后一致
        mapped_name = replacement_map.get(original_name)
        if mapped_name:
            m_info = people_flat.get(mapped_name)
            if m_info:
                used_names.add(mapped_name)
            home.append({"name": mapped_name, "messages": c["messages"],
                         "avatar": m_info["avatar"] if m_info else None})
            if not (pre_mapping and original_name in pre_mapping):
                warnings.append(
                    f"人物库没有「{original_name}」，已按同类替换为「{mapped_name}」，"
                    f"以与剧本其它处保持一致。")
            continue
        # 库中没有：从同类别人里随机挑一个未用过的替换，对话内容原样保留
        repl = _pick_replacement(original_name, used_names, people_flat)
        if repl and repl["name"] != original_name:
            home.append({"name": repl["name"], "messages": c["messages"], "avatar": repl["avatar"]})
            used_names.add(repl["name"])
            replacement_map[original_name] = repl["name"]
            warnings.append(
                f"人物库没有「{original_name}」，已按同类替换为「{repl['name']}」（{repl['group']}类）。"
                f"若不想替换，可把该名字加入人物库（在场景编辑器人物库添加，或点「保存到人物库」）。")
        else:
            # 人物库里连同类都没有，只能保留原名并提示
            home.append({"name": original_name, "messages": c["messages"]})
            warnings.append(
                f"人物库没有「{original_name}」，且库里也没有同类别（{_category_of_name(original_name)}类）的人可选，"
                f"将保留原名并使用默认头像。可在场景编辑器给该联系人选头像后点「保存到人物库」。")
    # 把历史块里发生的人名替换同步到 cleaned 文本里（如下方 [打开聊天] 的联系人），
    # 保证它们与 [编辑主页] 历史联系人用同一个名字，避免"同一人两个名字"造成视频信息错乱。
    if replacement_map:
        cleaned = _apply_name_mapping(cleaned, replacement_map)
    return [{"action": "编辑主页", "params": {"数据": home}}], cleaned, warnings, replacement_map


if __name__ == "__main__":
    import sys
    demo = """
[回到聊天主页]
[等待] 0.5
[打开聊天] 小明
[等待] 0.8
[我方打字] 在吗，晚上的方案改好了发你
[等待] 0.5
[对方正在输入] 1.2
[对方发消息] 好的，辛苦啦
"""
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            demo = fh.read()
    result = translate(demo)
    print("source:", result["source"])
    for w in result["warnings"]:
        print("[warn]", w)
    print(json.dumps(result["steps"], ensure_ascii=False, indent=2))
