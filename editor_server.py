# -*- coding: utf-8 -*-
"""
影刀式工作流编辑器 —— 本地服务端
================================
用 Python 标准库起一个本地 Web 服务：
  - 托管 editor/index.html（编辑器界面）
  - 提供 API：动作清单 / 保存 / 加载工作流 / 运行 / 停止 / 日志 / 视频列表

用法：
    py editor_server.py            # 默认 http://localhost:8000
    py editor_server.py --port 9000
"""
import argparse
import base64
import datetime as _dt
import http.client
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import signal
import zlib
import threading
import time
import urllib.error
import urllib.parse
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import script_translator
import script_generator
import create_store as store

# Pillow 可选依赖：用于把上传图片按真实字节归一化重编码，修复「上传后全黑」。
# 缺失时自动回退到原逻辑（按 MIME 推断扩展名、原样保存），保证上传不失败。
try:
    from PIL import Image, ImageOps
    # 放宽解压炸弹限制（仍受下方 10MB 大小上限约束），避免大图触发误判
    Image.MAX_IMAGE_PIXELS = None
    _PIL_OK = True
except Exception:                                # noqa: BLE001
    _PIL_OK = False

# 项目根目录（本文件所在目录）
ROOT = os.path.dirname(os.path.abspath(__file__))
EDITOR_DIR = os.path.join(ROOT, "editor")
WORKFLOW_PATH = os.path.join(ROOT, "workflow.json")
RUN_LOG = os.path.join(ROOT, "editor_run.log")
VIDEO_DIR = os.path.join(ROOT, "videos")
# 判定「疑似残缺 mp4」的最小字节数：合成失败时 ffmpeg 残留的容器头文件通常只有几百字节，
# 而任何一帧真实画面至少上万字节（本项目成品普遍 >1MB）。低于此阈值一律视为残缺，不再上报。
MIN_VIDEO_BYTES = 32 * 1024
LIVE_PORT = 8001  # 运行子进程的「实时手机画面」服务端口（编辑器通过 /api/live 转发）
SCENE_PATH = os.path.join(ROOT, "scene.json")  # 独立场景编辑器读写的数据文件
PEER_PRESETS_PATH = os.path.join(ROOT, "peer_presets.json")  # 「对方主页」女性人设预设库
ENHANCE_DIR = os.path.join(ROOT, "enhance")   # 前端增强层（对方主页样式等），供场景编辑器预览复用
PEOPLE_PATH = os.path.join(ROOT, "people.json")  # 人物库：人名 -> 头像路径（供脚本历史会话自动套用）
FRONTEND_PUBLIC = os.path.join(ROOT, "vue-WeChat", "public", "images")  # 图片库根目录
IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
GALLERY_META_PATH = os.path.join(FRONTEND_PUBLIC, "_gallery_meta.json")  # 图片库「自定义命名」元数据

# 前端静态资源根（vite 的 publicDir）。视频必须放在 public/videos 下，
# 因为录屏时页面由 vue-WeChat dev server 提供，只有 public 里的文件才能用
# /videos/xxx.mp4 这样的 URL 被 <video> 加载。
FRONTEND_PUBLIC_ROOT = os.path.join(ROOT, "vue-WeChat", "public")
SOURCE_VIDEO_DIR = os.path.join(FRONTEND_PUBLIC_ROOT, "videos")   # 朋友圈可点开的源视频目录
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v")
MAX_VIDEO_BYTES = 200 * 1024 * 1024   # 单个源视频上传上限（200MB，够放一段随手拍）

# ============================================================
# 图片库分类：按子目录把图片归入分类，供选图器/图片库筛选与「按分类上传」。
# 分类只是展示层概念，不强制改动磁盘文件；旧目录里的图照样能被选到。
# 上传时可指定分类，新图直接落进对应目录（见 _CATEGORY_DIRS）。
# ============================================================
GALLERY_CATEGORIES = [
    {"key": "avatar",  "label": "头像",     "folders": ["avatar"]},
    {"key": "sticker", "label": "表情包",   "folders": ["sticker"]},
    {"key": "emoji",   "label": "emoji",   "folders": ["emoji", "emoji_panel", "wxemoji"]},
    {"key": "bg",      "label": "背景",     "folders": ["bg"]},
    {"key": "asset",   "label": "配图素材", "folders": ["asset", "album", "peer", "gif"]},
    {"key": "icon",    "label": "系统图标", "folders": ["/", "wxic", "chatbar", "wxpanel",
                                                    "sendpreview", "disc", "chat", "header",
                                                    "link", "transfer", "OfficialAccount",
                                                    "ref", "screenshot"]},
]
_GALLERY_CAT_INDEX = {c["key"]: c for c in GALLERY_CATEGORIES}
# 可上传分类 -> 落盘子目录（public/images/<dir>/）。系统图标不允许上传。
_CATEGORY_DIRS = {"avatar": "avatar", "sticker": "sticker", "emoji": "emoji",
                  "bg": "bg", "asset": "asset"}
_FOLDER_CATEGORY = {}
for _c in GALLERY_CATEGORIES:
    for _f in _c["folders"]:
        _FOLDER_CATEGORY[_f] = _c["key"]

# 兼容旧字段：type 仍按「icon/image」二分（系统图标 vs 其它）
ICON_FOLDERS = {"", "/", "wxic", "chatbar", "wxpanel", "sendpreview"}
_GALLERY_TYPE_ICON = "icon"   # 图标
_GALLERY_TYPE_IMAGE = "image"  # 图像

# 当前运行中的 runner 进程
_run_lock = threading.Lock()
_run_proc = None

# 当前运行中的「编辑模式」进程
_edit_lock = threading.Lock()
_edit_proc = None
EDIT_LOG = os.path.join(ROOT, "editor_edit.log")

# ============================================================
# 动作清单（与 main.py 的 execute_step 一一对应）
# ============================================================
ACTIONS = [
    {"action": "打开聊天", "category": "聊天", "icon": "💬",
     "desc": "从聊天列表点击进入指定会话",
     "params": [{"key": "联系人", "label": "联系人名称", "type": "text",
                 "placeholder": "如：孙权", "default": ""}]},
    {"action": "我方打字", "category": "聊天", "icon": "⌨️",
     "desc": "手机键盘动画打字 + 回车发送",
     "params": [{"key": "内容", "label": "要输入的内容", "type": "textarea", "default": ""}]},
    {"action": "打字不发", "category": "聊天", "icon": "✍️",
     "desc": "打出文字但不发送（停留展示，可配合删除）",
     "params": [{"key": "内容", "label": "要输入的内容", "type": "textarea", "default": ""},
                {"key": "停留", "label": "停留秒数", "type": "number", "default": "1.5"}]},
    {"action": "删除文字", "category": "聊天", "icon": "⌫",
     "desc": "按退格键删除输入框字符（-1 = 清空）",
     "params": [{"key": "数量", "label": "删除字符数（-1 清空）", "type": "text", "default": "-1"}]},
    {"action": "对方正在输入", "category": "聊天", "icon": "⏳",
     "desc": "聊天头部显示「对方正在输入...」",
     "params": [{"key": "秒数", "label": "显示秒数", "type": "number", "default": "1.2"}]},
    {"action": "对方发消息", "category": "聊天", "icon": "📨",
     "desc": "对方逐字打字（含打错退回）后以左侧白气泡上屏，不再是瞬间复制",
     "params": [{"key": "内容", "label": "消息内容", "type": "textarea", "default": ""},
                {"key": "头像", "label": "对方头像（可空）", "type": "text",
                 "placeholder": "如：/images/header/yehua.jpg", "default": ""}]},
    {"action": "对方后台发消息", "category": "聊天", "icon": "📩",
     "desc": "给当前不在看的会话投递对方消息，画面不变，仅刷新该会话在主页的预览+未读角标（返回主页可看到）；内容以 [图片] 开头时变成图片气泡",
     "params": [{"key": "联系人", "label": "目标会话联系人", "type": "text", "default": ""},
                {"key": "内容", "label": "消息内容（[图片] 开头=图片消息）", "type": "textarea", "default": ""},
                {"key": "图片", "label": "配图路径（图片消息用，可空）", "type": "text", "default": ""},
                {"key": "头像", "label": "对方头像（可空）", "type": "text", "default": ""},
                {"key": "发送者", "label": "群聊发送者名（可空）", "type": "text", "default": ""},
                {"key": "置顶", "label": "来消息置顶", "type": "select",
                 "options": ["是", "否"], "default": "是"}]},
    {"action": "后台消息队列", "category": "聊天", "icon": "📬",
     "desc": "装载一批后台消息并立刻在后台发出去：执行到这一行时，队列里每条消息马上投递给对应会话，刷新主页预览+未读角标，之后打开该会话即可看到（不再按秒/步延迟）",
     "params": [{"key": "数据", "label": "JSON 数组，形如 [{联系,内容,头像,置顶}]", "type": "textarea",
                 "placeholder": '[{"联系":"陆香儿","内容":"图片怎么发您"}]', "default": ""}]},
    {"action": "查看图片", "category": "聊天", "icon": "🔍",
     "desc": "点开一张图片放大查看：全屏放大动画 + 手抖停留 + 自动关闭",
     "params": [{"key": "图片", "label": "图片路径", "type": "text",
                 "placeholder": "如：/images/header/yehua.jpg", "default": ""},
                {"key": "停留", "label": "停留秒数（可空）", "type": "number", "default": "0.3"},
                {"key": "焦点", "label": "放大位置 x,y（可空）", "type": "text",
                 "placeholder": "如 0.35,0.4", "default": ""}]},
    {"action": "返回主页", "category": "导航", "icon": "🏠",
     "desc": "切回聊天列表主页（转场动画结束后默认再停留 0.3s）",
     "params": [{"key": "停留", "label": "转场后主页等待秒数（默认可空）", "type": "number", "default": "0.3"}]},
    {"action": "切换Tab", "category": "导航", "icon": "🧭",
     "desc": "点击底部 Tab",
     "params": [{"key": "Tab", "label": "Tab 名称", "type": "select",
                 "options": ["微信", "通讯录", "发现", "我"], "default": "微信"}]},
    {"action": "隐藏键盘", "category": "导航", "icon": "🙈",
     "desc": "收起手机键盘", "params": []},
    {"action": "进入朋友圈", "category": "朋友圈", "icon": "📖",
     "desc": "从发现页进入朋友圈", "params": []},
    {"action": "打开对方主页", "category": "个人主页", "icon": "👤",
     "desc": "点对方消息头像 → 推入「对方个人资料页」（头像/昵称/微信号/地区/朋友资料/朋友圈缩略图/视频号/发消息）",
     "params": [{"key": "对方", "label": "人设名（可空，留空用场景里配置的对方）", "type": "text",
                 "placeholder": "如：餐车老板娘·吴遂卿", "default": ""}]},
    {"action": "进入对方朋友圈", "category": "个人主页", "icon": "🌅",
     "desc": "点资料页「朋友圈」行 → 右滑推入对方朋友圈（全屏封面 + 昵称头像签名 + 动态列表）",
     "params": []},
    {"action": "打开对方设置", "category": "个人主页", "icon": "⚙️",
     "desc": "点资料页右上角「…」推入联系人设置页（编辑备注/设置权限/推荐给朋友/星标/加入黑名单/投诉/删除联系人，深色样式复刻参考视频）",
     "params": [{"key": "对方", "label": "人设名（可空，留空用场景里配置的对方）", "type": "text",
                 "placeholder": "如：餐车老板娘·吴遂卿", "default": ""}]},
    {"action": "加入黑名单", "category": "个人主页", "icon": "🚫",
     "desc": "拉黑全过程动画：拨「加入黑名单」开关变绿 → 底部弹起确认弹窗（确定/取消）→ 点确定弹窗收起 → 中央「正在加载」加载动画，复刻参考视频全过程",
     "params": [{"key": "确认", "label": "弹窗点哪个按钮", "type": "select",
                 "options": ["确定", "取消"], "default": "确定"},
                {"key": "加载秒", "label": "「正在加载」显示秒数", "type": "number", "default": "1.4"},
                {"key": "停留", "label": "结束停留秒数", "type": "number", "default": "0.8"}]},
    {"action": "移出黑名单", "category": "个人主页", "icon": "✅",
     "desc": "把已拉黑的联系人移出黑名单：开关关掉 → 确认弹窗（文案为移出版本）→ 确定 → 「正在加载」加载动画",
     "params": [{"key": "确认", "label": "弹窗点哪个按钮", "type": "select",
                 "options": ["确定", "取消"], "default": "确定"},
                {"key": "加载秒", "label": "「正在加载」显示秒数", "type": "number", "default": "1.4"},
                {"key": "停留", "label": "结束停留秒数", "type": "number", "default": "0.8"}]},
    {"action": "返回上一页", "category": "个人主页", "icon": "↩️",
     "desc": "对方朋友圈 → 对方资料页 → 聊天页（iOS 推出转场）",
     "params": []},
    {"action": "闪回聊天", "category": "个人主页", "icon": "⚡",
     "desc": "硬切回聊天界面：瞬间隐藏「我的朋友圈」或「对方主页/朋友圈」（不做滑出转场），观感等同视频剪辑的一次切镜，随后可继续录制；「回到」填联系人时，闪回后直接进该会话",
     "params": [{"key": "停留", "label": "切完后停留秒数（可空，默认 0.12）", "type": "number", "default": "0.12"},
                {"key": "回到", "label": "闪回后进入的会话（可空=只回聊天列表）", "type": "text", "default": ""},
                {"key": "闪白", "label": "切镜时闪一帧白（剪辑感更强）", "type": "select",
                 "options": ["否", "是"], "default": "否"}]},
    {"action": "编辑对方资料", "category": "个人主页", "icon": "🧩",
     "desc": "整体替换「对方」的资料与朋友圈（昵称/微信号/地区/头像/封面/签名/朋友圈缩略图/视频号/动态全部可配）；动态里加 video 即为视频动态（朋友圈里显示播放角标，可点开全屏播放）",
     "params": [{"key": "数据", "label": "预设名 / JSON 对象 / .json 路径", "type": "textarea",
                 "placeholder": '{"name":"吴遂卿","wxid":"LSDH-WSQ","area":"广东 佛山","gender":0,'
                                '"avatar":"/images/peer/peer_avatar.jpg","signature":"随心随性",'
                                '"cover":"/images/peer/peer_cover.jpg","posts":[{"date":"10 6月",'
                                '"images":["/images/peer/peer_p1.jpg"],"text":"偶尔玩下 蛮好"},'
                                '{"date":"08 6月","video":"/videos/demo.mp4",'
                                '"cover":"/images/peer/peer_v1.jpg","text":"随手拍的海"}]}',
                 "default": ""}]},
    {"action": "向下滚动", "category": "朋友圈", "icon": "⬇️",
     "desc": "自然滚动指定像素（我的朋友圈 / 对方朋友圈均可）",
     "params": [{"key": "像素", "label": "像素", "type": "number", "default": "300"}]},
    {"action": "向上滚动", "category": "朋友圈", "icon": "⬆️",
     "desc": "向上滚动指定像素（我的朋友圈 / 对方朋友圈均可）",
     "params": [{"key": "像素", "label": "像素", "type": "number", "default": "300"}]},
    {"action": "滚动到", "category": "朋友圈", "icon": "↕️",
     "desc": "把朋友圈滚到顶部或底部（对方朋友圈优先，没开时用我的朋友圈）",
     "params": [{"key": "位置", "label": "位置", "type": "select",
                 "options": ["底部", "顶部"], "default": "底部"}]},
    {"action": "点开图片", "category": "朋友圈", "icon": "🔍",
     "desc": "点开朋友圈动态里的配图全屏查看（对方朋友圈优先，没开时用我的朋友圈）；序号写「2」=第2条第1张，写「2,3」=第2条第3张",
     "params": [{"key": "序号", "label": "第几条动态,第几张图（可空，默认 1,1）", "type": "text",
                 "placeholder": "如：2,3", "default": "1"},
                {"key": "停留", "label": "停留秒数（可空=默认）", "type": "number", "default": ""}]},
    {"action": "播放视频", "category": "朋友圈", "icon": "▶️",
     "desc": "点开朋友圈视频全屏播放（停留后自动关闭）；留空「视频」则点开当前打开的朋友圈里第 N 个视频动态（对方朋友圈优先，没开时用我的朋友圈）",
     "params": [{"key": "视频", "label": "视频地址（可空，留空=点开朋友圈里的视频）", "type": "text",
                 "placeholder": "如：/videos/demo.mp4", "default": ""},
                {"key": "序号", "label": "第几个视频动态（留空视频时生效）", "type": "number", "default": "1"},
                {"key": "停留", "label": "播放停留秒数（可空=按视频时长）", "type": "number", "default": ""}]},
    {"action": "点赞", "category": "朋友圈", "icon": "👍",
     "desc": "复刻真机点赞：弹出「···」两格菜单（♥赞/💬评论）→ 点「赞」→ 菜单收起 + 点赞条弹出；「序号」留空 = 最后一条动态",
     "params": [{"key": "序号", "label": "第几条动态（留空=最后一条）", "type": "number", "default": ""}]},
    {"action": "评论", "category": "朋友圈", "icon": "💬",
     "desc": "复刻真机评论：弹出「···」菜单点「评论」→ 输入条随键盘滑入 → 键盘动画打字 → 点「发送」后评论弹进点赞/评论条",
     "params": [{"key": "内容", "label": "评论内容", "type": "textarea", "default": ""},
                {"key": "序号", "label": "第几条动态（留空=最后一条）", "type": "number", "default": ""}]},
    {"action": "发朋友圈", "category": "朋友圈", "icon": "✏️",
     "desc": "发表文字朋友圈（键盘打字 + 发表上屏）",
     "params": [{"key": "内容", "label": "朋友圈文案", "type": "textarea", "default": ""},
                {"key": "图片", "label": "配图路径（可空）", "type": "text", "default": ""}]},
    {"action": "编辑朋友圈", "category": "朋友圈", "icon": "🖼️",
     "desc": "重建「我的朋友圈」动态（作者/文案/配图/视频/点赞/评论全可配）；也支持对象形式 {me:{...}, posts:[...]} 一次同时改主页资料",
     "params": [{"key": "数据", "label": "JSON 数组、{me,posts} 对象或 .json 文件路径", "type": "textarea",
                 "placeholder": '[{"author":"陆香儿","text":"...","images":["/images/peer/peer_p1.jpg"],"likes":["陆香儿"]},'
                                '{"author":"陆香儿","text":"随手拍的海","video":"/videos/demo.mp4","cover":"/images/peer/peer_v1.jpg"}]',
                 "default": ""}]},
    {"action": "编辑我的资料", "category": "个人资料", "icon": "🧑",
     "desc": "编辑「我」的主页资料：昵称 / 头像 / 朋友圈封面 / 个性签名（主页列表、通讯录、朋友圈同步更新）",
     "params": [{"key": "数据", "label": "JSON 对象或 .json 文件路径", "type": "textarea",
                 "placeholder": '{"name":"阿荡","avatar":"/images/avatar/2_20260831_184618_874.jpg",'
                                '"bg":"/images/peer/peer_cover.jpg","signature":"填坑小能手"}',
                 "default": ""}]},
    {"action": "设置头像", "category": "个人资料", "icon": "🪪",
     "desc": "修改头像（所有位置即时更新）",
     "params": [{"key": "图片", "label": "头像图片路径", "type": "text",
                 "placeholder": "如：/images/header/header02.jpg", "default": ""}]},
    {"action": "设置背景", "category": "个人资料", "icon": "🖼️",
     "desc": "修改朋友圈封面背景",
     "params": [{"key": "图片", "label": "背景图片路径", "type": "text",
                 "placeholder": "如：/images/bg/bg02.jpg", "default": ""}]},
    {"action": "修改昵称", "category": "个人资料", "icon": "🏷️",
     "desc": "修改我的昵称（主页列表、通讯录、朋友圈同步更新）",
     "params": [{"key": "昵称", "label": "新昵称", "type": "text", "default": ""}]},
    {"action": "修改签名", "category": "个人资料", "icon": "✒️",
     "desc": "修改我的个性签名（同步到通讯录 / 我的资料）",
     "params": [{"key": "签名", "label": "个性签名", "type": "text", "default": ""}]},
    {"action": "编辑主页", "category": "主页", "icon": "🏠",
     "desc": "按数据重建聊天列表主页：支持私聊/群聊/未读/免打扰，可一次配多个会话，之后用「打开聊天」逐个进入",
     "params": [{"key": "数据", "label": "JSON 数组或 .json 文件路径", "type": "textarea",
                 "placeholder": '[{"name":"孙权","text":"容我三思","avatar":"/images/header/sunquan.jpg"},{"group":"收购万达讨论群","text":"今晚八点开会","members":["阿荡","夜华"],"newMsgCount":2}]',
                 "default": ""}]},
    {"action": "发送图片", "category": "聊天", "icon": "🖼️",
     "desc": "我方在聊天里发送一张图片（真实气泡）；「打开」为是则发送后自动点开放大查看再关闭",
     "params": [{"key": "图片", "label": "图片路径", "type": "text",
                 "placeholder": "如：/images/header/yehua.jpg", "default": ""},
                {"key": "打开", "label": "是否点开查看", "type": "select",
                 "options": ["否", "是"], "default": "否"},
                {"key": "停留", "label": "查看停留秒数（可空）", "type": "number", "default": "0.3"},
                {"key": "焦点", "label": "放大位置 x,y（可空）", "type": "text",
                 "placeholder": "如 0.35,0.4", "default": ""}]},
    {"action": "对方发图片", "category": "聊天", "icon": "🖼️",
     "desc": "对方发送一张图片；「打开」为是则上屏后自动点开放大查看再关闭",
     "params": [{"key": "图片", "label": "图片路径", "type": "text",
                 "placeholder": "如：/images/header/sunquan.jpg", "default": ""},
                {"key": "打开", "label": "是否点开查看", "type": "select",
                 "options": ["否", "是"], "default": "否"},
                {"key": "停留", "label": "查看停留秒数（可空）", "type": "number", "default": "0.3"},
                {"key": "焦点", "label": "放大位置 x,y（可空）", "type": "text",
                 "placeholder": "如 0.35,0.4", "default": ""}]},
    {"action": "发送表情", "category": "聊天", "icon": "🖼️",
     "desc": "我方发表情贴纸（小尺寸贴纸气泡）；配图选哪张就发哪张",
     "params": [{"key": "表情", "label": "表情图片路径", "type": "text",
                 "placeholder": "如：/images/myemoji/xxx.png", "default": ""}]},
    {"action": "对方表情", "category": "聊天", "icon": "🖼️",
     "desc": "对方发来表情贴纸；配图选哪张就上屏哪张",
     "params": [{"key": "表情", "label": "表情图片路径", "type": "text",
                 "placeholder": "如：/images/myemoji/xxx.png", "default": ""}]},
    {"action": "对方后台发表情", "category": "聊天", "icon": "🖼️",
     "desc": "给未打开的会话投递对方表情，刷新主页预览/角标",
     "params": [{"key": "联系人", "label": "目标会话联系人", "type": "text", "default": ""},
                {"key": "表情", "label": "表情图片路径", "type": "text",
                 "placeholder": "如：/images/myemoji/xxx.png", "default": ""}]},
    {"action": "发送语音", "category": "聊天", "icon": "🎙️",
     "desc": "我方发送语音消息（时长决定波形长短）",
     "params": [{"key": "秒数", "label": "语音秒数", "type": "number", "default": "3"}]},
    {"action": "对方语音", "category": "聊天", "icon": "🎙️",
     "desc": "对方发送语音消息",
     "params": [{"key": "秒数", "label": "语音秒数", "type": "number", "default": "3"}]},
    {"action": "撤回我的消息", "category": "聊天", "icon": "↩️",
     "desc": "撤回我方最后一条消息，显示系统提示", "params": []},
    {"action": "对方撤回消息", "category": "聊天", "icon": "↩️",
     "desc": "对方撤回一条消息，显示系统提示", "params": []},
    {"action": "转发消息", "category": "聊天", "icon": "🔁",
     "desc": "我方转发一条消息（转发：内容）",
     "params": [{"key": "内容", "label": "转发内容", "type": "textarea", "default": ""}]},
    {"action": "打开转账面板", "category": "聊天", "icon": "➕",
     "desc": "点聊天输入栏「+」弹出功能面板（照片/转账/红包等，对齐参考图1）",
     "params": []},
    {"action": "转账金额", "category": "聊天", "icon": "💰",
     "desc": "真实转账流程：功能面板→金额页输金额/说明→转账→6位密码→橙色转账卡片",
     "params": [{"key": "接收人", "label": "接收人（聊天对象名）", "type": "text", "default": ""},
                {"key": "金额", "label": "转账金额", "type": "text", "default": "50.00"},
                {"key": "备注", "label": "备注（可空）", "type": "text", "default": ""},
                {"key": "密码", "label": "支付密码（6位数字）", "type": "text", "default": "123456"}]},
    {"action": "转账", "category": "聊天", "icon": "💰",
     "desc": "我方发送一笔转账（绿色转账卡片：谁 + 金额 + 备注）",
     "params": [{"key": "接收人", "label": "接收人（聊天对象名）", "type": "text", "default": ""},
                {"key": "金额", "label": "转账金额", "type": "text", "default": "50.00"},
                {"key": "备注", "label": "备注（可空）", "type": "text", "default": ""}]},
    {"action": "对方转账", "category": "聊天", "icon": "💰",
     "desc": "对方发来一笔转账（左侧转账卡片）",
     "params": [{"key": "接收人", "label": "接收人", "type": "text", "default": ""},
                {"key": "金额", "label": "转账金额", "type": "text", "default": "50.00"},
                {"key": "备注", "label": "备注（可空）", "type": "text", "default": ""}]},
    {"action": "打开转账详情", "category": "聊天", "icon": "🧾",
     "desc": "点击对方转账卡片，打开转账详情页（右滑推入，深色页面）",
     "params": []},
    {"action": "接收转账", "category": "聊天", "icon": "✅",
     "desc": "在转账详情页点「接收」：瞬时切换为已收款（绿色对勾+已存入零钱）",
     "params": []},
    {"action": "关闭转账详情", "category": "聊天", "icon": "↩️",
     "desc": "点返回箭头，转账详情页右滑退出回聊天页",
     "params": []},
    {"action": "手机状态栏", "category": "聊天", "icon": "📱",
     "desc": "切换状态栏场景：转账=参考视频状态栏（03:14+灵动岛微信绿标+录屏红点），默认=恢复 18:36",
     "params": [{"key": "模式", "label": "模式", "type": "select",
                 "options": ["转账", "默认"], "default": "转账"}]},
    {"action": "@成员", "category": "聊天", "icon": "👥",
     "desc": "在输入框 @ 成员（弹出键盘，内容保留在输入框）",
     "params": [{"key": "昵称", "label": "成员昵称", "type": "text",
                 "placeholder": "如：夜华", "default": ""}]},
    {"action": "等待", "category": "系统", "icon": "⏱️",
     "desc": "自然等待指定秒数",
     "params": [{"key": "秒数", "label": "等待秒数", "type": "number", "default": "1"}]},
]

# action -> 动作定义 索引
ACTIONS_BY_NAME = {a["action"]: a for a in ACTIONS}

def _json_reply(handler, code: int, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

def _read_workflow():
    if not os.path.isfile(WORKFLOW_PATH):
        return {"name": "未命名流程", "steps": []}
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)

def _write_workflow(data):
    with open(WORKFLOW_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

def _latest_video():
    if not os.path.isdir(VIDEO_DIR):
        return None
    mp4s = [f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(".mp4")]
    if not mp4s:
        return None
    # 上行合成失败时 ffmpeg 会留下只有容器头、没有流数据的残缺 mp4（通常几 KB 甚至几百字节）。
    # 这些文件不能当「最新视频」上报，否则前端会误报成「视频已生成」。这里按文件大小过滤掉明显残缺的。
    def _valid(f):
        try:
            return os.path.getsize(os.path.join(VIDEO_DIR, f)) >= MIN_VIDEO_BYTES
        except OSError:
            return False
    cands = [f for f in mp4s if _valid(f)]
    mp4s = cands or mp4s          # 全部疑似残缺时退而求其次：仍返回最新的一个（不猜真实性）

    # 取最新时按 mtime 排序。混流临时文件（.mp4.audio.mp4）可能在 listdir 之后、getmtime
    # 之前被 os.replace/清理删除，getmtime 会抛 FileNotFoundError 把整个 /api/scene 请求打挂
    # （编辑器表现为列表/状态刷新失败）。这里对每项单独 try，跳过取不到的。
    def _mtime(f):
        try:
            return os.path.getmtime(os.path.join(VIDEO_DIR, f))
        except OSError:
            return None
    with_mtime = [(t, f) for t, f in ((_mtime(f), f) for f in mp4s) if t is not None]
    if not with_mtime:
        return None
    latest = max(with_mtime, key=lambda p: p[0])[1]
    return latest

def _read_scene():
    """读取场景文件；不存在时返回一个最小可用的空场景。"""
    empty = {"me": {}, "home": [], "moments": [], "peer": None, "peers": [], "peerNav": False}
    if not os.path.isfile(SCENE_PATH):
        return empty
    with open(SCENE_PATH, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except ValueError:
            return empty
    if not isinstance(data, dict):
        return empty
    for k, v in empty.items():
        data.setdefault(k, v)
    return data

def _write_scene(data):
    with open(SCENE_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# 「对方主页」预设库的规范字段：顺序即前端表单顺序，也用于读写时归一化。
PEER_FIELDS = ("name", "wxid", "area", "gender", "avatar", "signature", "cover",
               "momentsThumbs", "video", "posts")


def _read_peer_presets():
    """读取 peer_presets.json（对方主页女性人设预设）。

    返回 {"_note": str, "presets": {名字: {字段...}}}；文件缺失/损坏时返回空库。
    """
    empty = {"_note": "", "presets": {}}
    if not os.path.isfile(PEER_PRESETS_PATH):
        return empty
    try:
        with open(PEER_PRESETS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    presets = data.get("presets")
    if not isinstance(presets, dict):
        presets = {}
    return {"_note": data.get("_note", ""), "presets": presets}


def _write_peer_presets(data):
    payload = {
        "_note": (data or {}).get("_note", ""),
        "presets": (data or {}).get("presets", {}) or {},
    }
    with open(PEER_PRESETS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _read_people():
    """读取人物库 people.json。

    返回规范化的分组结构 {"学员": {人名: 头像}, "美女": {人名: 头像}}。
    兼容两种存储写法：
      1. 分组写法 {"学员": {...}, "美女": {...}}；
      2. 旧扁平写法 {人名: 头像}，此时按名字关键字自动归组。
    不存在/损坏时返回两个空组。
    """
    groups = {c: {} for c in script_translator.CATEGORIES}
    if not os.path.isfile(PEOPLE_PATH):
        return groups
    with open(PEOPLE_PATH, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except ValueError:
            return groups
    if not isinstance(data, dict):
        return groups
    if any(k in data for k in script_translator.CATEGORIES):
        for c in script_translator.CATEGORIES:
            sub = data.get(c)
            if isinstance(sub, dict):
                groups[c] = {str(k): str(v) for k, v in sub.items() if isinstance(v, str)}
        return groups
    # 扁平写法：按名字归组
    for name, avatar in data.items():
        if isinstance(avatar, str):
            groups[script_translator._category_of_name(str(name))][str(name)] = avatar
    return groups


def _write_people(groups):
    with open(PEOPLE_PATH, "w", encoding="utf-8") as fh:
        json.dump(groups, fh, ensure_ascii=False, indent=2)


def _people_flat(groups=None):
    """把分组结构拍平成 {人名: {avatar, group}}，供查找。"""
    groups = groups if groups is not None else _read_people()
    out = {}
    for g, sub in groups.items():
        for name, avatar in sub.items():
            out[name] = {"avatar": avatar, "group": g}
    return out


def _people_lookup(groups, name):
    """在分组结构里找 {name}，返回所属组名，找不到返回 None。"""
    for g, sub in groups.items():
        if name in sub:
            return g
    return None


def _sync_people(payload):
    """把一批 {name, avatar, group?} 合并进人物库（覆盖同名），返回合并后的完整人物库。

    group 缺省时按名字关键字自动归类（学员/美女）。
    """
    groups = _read_people()
    src = (payload or {}).get("people")
    items = src if isinstance(src, list) else (
        [{"name": k, "avatar": v} for k, v in src.items()] if isinstance(src, dict) else [])
    for it in items:
        name = str(it.get("name") or "").strip()
        avatar = str(it.get("avatar") or "").strip()
        if not name:
            continue
        group = str(it.get("group") or "").strip() or script_translator._category_of_name(name)
        if group not in groups:
            group = "美女"  # 兜底：别弄丢，放到默认组
        groups[group][name] = avatar
    _write_people(groups)
    return groups


def _save_people_item(payload):
    """保存/更新单个人物：{name, avatar, group?}。avatar 可空字符串表示「清除头像」。

    返回 (people, err)。group 缺省时按名字自动归类，且同名时保持原组归属。
    """
    groups = _read_people()
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        return None, "人物名不能为空"
    avatar = str((payload or {}).get("avatar") or "").strip()
    group = str((payload or {}).get("group") or "").strip() or _people_lookup(groups, name) \
        or script_translator._category_of_name(name)
    if group not in groups:
        group = "美女"
    groups[group][name] = avatar
    _write_people(groups)
    return groups, None


def _rename_people(payload):
    """把人物库里的 {name} 改名为 {newName}（头像与组归属随 key 迁移）。

    若 newName 已存在且不是同一个 name，直接拒绝，避免静默覆盖已有人物。
    返回 (people, err)。
    """
    groups = _read_people()
    name = str((payload or {}).get("name") or "").strip()
    new_name = str((payload or {}).get("newName") or "").strip()
    if not name or not new_name:
        return None, "原名字与新名字都不能为空"
    group = _people_lookup(groups, name)
    if group is None:
        return None, f"人物库中没有「{name}」"
    if new_name == name:
        return groups, None
    if _people_lookup(groups, new_name) is not None:
        return None, f"人物库已有「{new_name}」，不能改名到已存在的名字"
    groups[group][new_name] = groups[group].pop(name)
    _write_people(groups)
    return groups, None


def _delete_people(payload):
    """从人物库删除 {name} 这一条。返回 (people, err)。"""
    groups = _read_people()
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        return None, "人物名不能为空"
    group = _people_lookup(groups, name)
    if group is None:
        return None, f"人物库中没有「{name}」"
    groups[group].pop(name, None)
    _write_people(groups)
    return groups, None
    return people, None


def _peer_has_data(peer):
    """对方人设是否有实质内容（避免场景里空的 peer 占位对象也生成一步「编辑对方资料」）。"""
    if not isinstance(peer, dict):
        return False
    return any(peer.get(k) for k in ("name", "wxid", "area", "avatar",
                                     "signature", "cover", "momentsThumbs",
                                     "video", "posts"))


def _build_scene_workflow(scene):
    """把 scene 转成一段可运行的工作流 steps（我的资料 + 主页会话 + 朋友圈 + 对方主页）。

    对方主页数据有三种写法（优先级从高到低）：
      scene.peers[]     —— 多人物 × 多方案（场景编辑器新格式）：
                           [{activePlan, plans: {A: {...}}}...]，每个人物取其当前方案，
                           各生成一步「编辑对方资料」；peerNav 为真时逐个人物
                           「打开对方主页 → 进入对方朋友圈」，看完退回聊天页再看下一个。
      scene.peer        —— 单人设完整对象（旧格式，编辑器保存时仍会镜像一份，自包含）
      scene.peerPreset  —— 预设名（引用 peer_presets.json，改预设即跟着变）
    scene.peerNav 为真时追加「打开对方主页 → 进入对方朋友圈」。
    """
    scene = scene or {}
    steps = []
    if scene.get("me"):
        me = scene["me"]
        if me.get("name"):
            steps.append({"action": "修改昵称", "params": {"昵称": me["name"]}})
        if me.get("avatar"):
            steps.append({"action": "设置头像", "params": {"图片": me["avatar"]}})
        if me.get("bg"):
            steps.append({"action": "设置背景", "params": {"图片": me["bg"]}})
        if me.get("signature"):
            steps.append({"action": "修改签名", "params": {"签名": me["signature"]}})
    if scene.get("home"):
        steps.insert(0, {"action": "编辑主页", "params": {"数据": scene["home"]}})
    peer = scene.get("peer")
    peer_preset = scene.get("peerPreset")
    peer_ok = bool(peer and _peer_has_data(peer))
    peers = scene.get("peers") if isinstance(scene.get("peers"), list) else []
    peer_plans = []
    if peers:
        for pp in peers:
            if not isinstance(pp, dict):
                continue
            plans = pp.get("plans") if isinstance(pp.get("plans"), dict) else {}
            plan = plans.get(pp.get("activePlan")) or next(iter(plans.values()), None)
            if plan and _peer_has_data(plan):
                steps.append({"action": "编辑对方资料", "params": {"数据": plan}})
                peer_plans.append(plan)
    elif peer_ok:
        steps.append({"action": "编辑对方资料", "params": {"数据": peer}})
    elif peer_preset:
        steps.append({"action": "编辑对方资料", "params": {"数据": peer_preset}})
    if scene.get("moments"):
        steps.append({"action": "编辑朋友圈", "params": {"数据": scene["moments"]}})
    # 导航放最后：先把所有数据铺好，再进页面，录出来才连贯
    if scene.get("momentsNav"):
        steps.extend(_moments_nav_steps(scene))
    if scene.get("peerNav"):
        if peer_plans:
            # 多人物：逐个「进对方朋友圈」，看完退回聊天页（朋友圈→资料页→聊天）再看下一个
            for idx in range(len(peer_plans)):
                steps.append({"action": "打开对方主页", "params": {}})
                steps.append({"action": "进入对方朋友圈", "params": {}})
                if idx < len(peer_plans) - 1:
                    steps.append({"action": "返回上一页", "params": {}})
                    steps.append({"action": "返回上一页", "params": {}})
        elif (peer_ok or peer_preset):
            steps.append({"action": "打开对方主页", "params": {}})
            steps.append({"action": "进入对方朋友圈", "params": {}})
    return {"name": "场景", "steps": steps}


def _ai_peer_posts(payload: dict):
    """用 DeepSeek 给「对方朋友圈」生成一整套动态文案。

    payload: {name: 人物昵称, keywords: 关键词（职业/性格/语气）, count: 条数(1~12)}
    返回 (posts, err)：posts = [{date, text}]，date 形如 "10 6月"，由模型按倒序错落给。
    """
    data = payload or {}
    name = str(data.get("name") or "").strip()
    keywords = str(data.get("keywords") or "").strip()
    if not keywords and not name:
        return None, "请至少填写关键词或人物昵称"
    try:
        count = max(1, min(12, int(data.get("count") or 6)))
    except (TypeError, ValueError):
        count = 6
    settings = script_translator.load_settings()
    api_key = (settings.get("deepseek_api_key") or "").strip()
    if not api_key or api_key.upper().startswith("REPLACE"):
        return None, "AI 文案需要先配置 DeepSeek API Key（工作流编辑器顶部「配置大模型」）。"
    model = settings.get("deepseek_model") or script_translator.DEFAULT_MODEL
    base_url = settings.get("deepseek_base_url") or script_translator.DEFAULT_BASE_URL

    system_prompt = (
        "你是朋友圈文案写手。根据人设，写一组朋友圈动态文案。"
        "只输出 JSON 数组，不要解释、不要 markdown 代码块。"
        "数组元素形如 {\"date\": \"10 6月\", \"text\": \"文案\"}："
        "date 表示发布日期（日 + 月份，从新到旧错落排列，不要全部同一天）；"
        "text 是动态正文，口语化、符合人设、有生活气息，可少量使用常见 emoji，"
        "单条 10~40 字，可以偶尔两行（用 \\n 分隔）。"
    )
    user_msg = (
        "人物昵称：%s\n人设关键词：%s\n请写 %d 条朋友圈动态，按时间从新到旧输出。"
        % (name or "（未提供，按关键词想象）", keywords, count)
    )
    text, err = _call_generate_deepseek(api_key, system_prompt, user_msg, model, base_url)
    if err:
        return None, "AI 调用失败：%s" % err
    # 容错解析：剥掉 markdown 围栏，截取第一个 [ 到最后一个 ]
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("["):] if "[" in raw else raw
    l, r = raw.find("["), raw.rfind("]")
    if l < 0 or r <= l:
        return None, "AI 返回的内容不是 JSON 数组，请重试。"
    try:
        arr = json.loads(raw[l:r + 1])
    except ValueError:
        return None, "AI 返回的 JSON 解析失败，请重试。"
    posts = []
    for item in arr if isinstance(arr, list) else []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("text") or "").strip()
        if not t:
            continue
        posts.append({"date": str(item.get("date") or "").strip(), "text": t})
    if not posts:
        return None, "AI 返回的动态为空，请重试。"
    return posts, None


def _moments_nav_steps(scene):
    """「我的朋友圈」导航段：进入朋友圈 → 滚动到目标动态 → 点开图片 / 播放视频。

    打开方式 scene.momentsOpen："" = 只进入不打开 / "video" = 播放视频 / "image" = 点开图片
    目标动态   scene.momentsOpenIndex：从 1 开始（缺省 1）

    先说滚动量：视频动态和图片动态的高度不一样，这里按「一条约 300px + 封面可视约 460px」
    粗略估算，让目标动态落进视口中部。点开动作本身（playVideo / openImage）还会再做一次
    scrollIntoView 兜底，所以估算有偏差也不会点空。
    """
    posts = scene.get("moments") or []
    idx = max(1, int(scene.get("momentsOpenIndex") or 1))
    if posts:
        idx = min(idx, len(posts))
    steps = [{"action": "进入朋友圈", "params": {}}]
    # 不进朋友圈则无所谓滚动；只要进了就往下滚一段，复刻参考视频「下滑看动态」的观感
    scroll_px = int(max(240, 300 * (idx - 1) + 240))
    steps.append({"action": "向下滚动", "params": {"像素": scroll_px}})
    mode = str(scene.get("momentsOpen") or "").strip().lower()
    if mode in ("video", "视频", "播放视频"):
        steps.append({"action": "播放视频", "params": {"序号": idx}})
    elif mode in ("image", "图片", "点开图片"):
        steps.append({"action": "点开图片", "params": {"序号": str(idx)}})
    return steps

def _list_images(rel_dir=""):
    """递归列出 public/images 下的可用图片，返回形如 /images/xxx.png 的路径列表。"""
    if not os.path.isdir(FRONTEND_PUBLIC):
        return []
    out = []
    base = FRONTEND_PUBLIC
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if fn.lower().endswith(IMG_EXTS):
                rel = os.path.relpath(os.path.join(dirpath, fn), base).replace(os.sep, "/")
                out.append("/images/" + rel)
    out.sort()
    return out

def _list_chat_bgs():
    """列出聊天背景目录（public/images/bg）下的图片，返回可被前端引用的 /images/bg/... URL。"""
    if not os.path.isdir(CHAT_BG_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(CHAT_BG_DIR)):
        if fn.lower().endswith(IMG_EXTS):
            out.append("/images/bg/" + fn)
    return out

def _category_of(folder):
    """按子目录返回分类 key（avatar/sticker/emoji/bg/asset/icon），未知目录归入 asset。"""
    return _FOLDER_CATEGORY.get(folder, "asset")

def _image_type(folder):
    """按目录判断一张图属于「图标」还是「图像」。

    图标 = 微信界面本身用到的 UI 素材；图像 = 用户可挑选的内容图片（头像/背景/相册等）。
    """
    return _GALLERY_TYPE_ICON if (folder in ICON_FOLDERS) else _GALLERY_TYPE_IMAGE

def _load_gallery_meta():
    """读取图片库「自定义命名」元数据 {相对路径 -> 展示名}。

    只存展示名，不改动磁盘文件路径，因此重命名不会破坏工作流/剧本里对旧路径的引用。
    """
    try:
        with open(GALLERY_META_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def _save_gallery_meta(meta):
    """保存图片库「自定义命名」元数据。"""
    try:
        with open(GALLERY_META_PATH, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False

def _label_of(rel, meta):
    """返回一张图的展示名：优先用自定义命名，否则用文件名（去掉扩展名）。"""
    lab = (meta or {}).get(rel)
    if isinstance(lab, str) and lab.strip():
        return lab.strip()
    name = os.path.splitext(os.path.basename(rel))[0]
    return name or (meta or {}).get(rel, "")

def _list_image_files():
    """列出 public/images 下所有图片，返回带元信息的列表，供「图片库」管理界面使用。

    每项：{path, name, folder, size, mtime, type, label}。
    folder 是该文件的子目录名（如 "avatar"、"/"）；type 为 "icon"(图标)/"image"(图像)；
    label 为展示名（自定义命名或文件名）。
    按创建时间降序排列（最新在前），便于用户快速找到刚上传/新加入的图片。
    """
    if not os.path.isdir(FRONTEND_PUBLIC):
        return []
    out = []
    base = FRONTEND_PUBLIC
    meta = _load_gallery_meta()
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in filenames:
            if not fn.lower().endswith(IMG_EXTS):
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, base).replace(os.sep, "/")
            folder = os.path.dirname(rel) or "/"
            try:
                size = os.path.getsize(fp)
                mtime = int(os.path.getmtime(fp))
                # Windows 上 getctime 就是文件创建时间；取不到时退回 mtime
                ctime = int(os.path.getctime(fp))
            except OSError:
                size, mtime, ctime = 0, 0, 0
            out.append({
                "path": "/images/" + rel,
                "name": fn,
                "folder": folder,
                "size": size,
                "mtime": mtime,
                "ctime": ctime,
                "type": _image_type(folder),
                "category": _category_of(folder),
                "label": _label_of(rel, meta),
            })
    # 按创建时间降序（最新在前）；同秒创建时再用文件名固定顺序
    out.sort(key=lambda d: (-d["ctime"], d["name"]))
    return out

def _gallery_payload():
    """返回图片库数据：{images, files, folders, categories, videos, root}。

    images 保持旧字段（纯路径列表），供现有图片选择器直接用；files/folders 供图片库管理界面用；
    categories 是分类清单（key/label/folders），videos 是 public/videos 下的视频素材列表。
    """
    files = _list_image_files()
    folders = sorted({f["folder"] for f in files})
    videos = [{"path": p, "name": os.path.splitext(os.path.basename(p))[0]}
              for p in _list_source_videos()]
    return {
        "images": [f["path"] for f in files],
        "files": files,
        "folders": folders,
        "categories": GALLERY_CATEGORIES,
        "videos": videos,
    }

def _safe_image_fp(rel):
    """把 /images/ 之后的相对路径解析为 public/images 下的绝对路径。

    返回绝对路径；若为空、越界（路径穿越）或不在图片库内，则返回 None。
    """
    if not rel:
        return None
    base = os.path.normpath(FRONTEND_PUBLIC)
    fp = os.path.normpath(os.path.join(FRONTEND_PUBLIC, rel))
    if fp == base or not fp.startswith(base + os.sep):
        return None
    return fp

AVATAR_DIR_NAME = "avatar"  # 上传头像存放的子目录（public/images/avatar）
CHAT_BG_DIR_NAME = "bg"     # 聊天背景存放的子目录（public/images/bg）
CHAT_BG_DIR = os.path.join(FRONTEND_PUBLIC, CHAT_BG_DIR_NAME)

def _save_upload_image(data_url, name="", folder=AVATAR_DIR_NAME):
    """把 base64 dataURL 图片保存到图片库，返回 (路径, None) 或 (None, 错误)。

    folder: 存放的子目录名（public/images/<folder>）。默认 "avatar"（头像），
    传 "bg" 则保存为聊天背景（public/images/bg/）。

    保存到 vue-WeChat/public/images/<folder>/，与编辑器图库同一来源，
    因而上传后的图片在编辑器预览与真实录屏（vue-WeChat dev server）里都能显示。

    关键修复：不再按「浏览器声明的 MIME/扩展名」直接落盘，而是用 Pillow 读取
    **真实字节**并按真实格式归一化重编码（透明图保 PNG、其余转 RGB JPEG、
    GIF/WebP 动态透传、纠正 EXIF 方向 / CMYK / 16-bit / ICC），避免内容与格式
    不符导致的「上传后全黑」。Pillow 不可用或解码失败时回退到原逻辑。
    """
    if not (data_url and isinstance(data_url, str)):
        return None, "未收到图片数据"
    m = re.match(r"data:([^;]+);base64,(.+)", data_url, re.S)
    if not m:
        return None, "图片数据格式不正确（需要 data:image/...;base64,...）"
    mime, b64 = m.group(1), re.sub(r"\s+", "", m.group(2))
    try:
        data = base64.b64decode(b64)
    except Exception as exc:                      # noqa: BLE001
        return None, "图片解码失败：" + str(exc)
    if not data:
        return None, "图片内容为空"
    if len(data) > 10 * 1024 * 1024:
        return None, "图片不能超过 10MB"

    # 归一化重编码：返回 (保存字节, 扩展名)。任何异常都走兜底，绝不拒绝上传。
    if _PIL_OK:
        try:
            data, ext = _normalize_image(data)
        except Exception:                        # noqa: BLE001
            ext = _mime_ext(mime)
    else:
        ext = _mime_ext(mime)

    if not ext:
        return None, "仅支持 PNG / JPG / GIF / WebP / BMP 图片"

    stem = ""
    if name:
        stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", os.path.splitext(os.path.basename(name))[0])[:40].strip("_")
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    folder = folder or AVATAR_DIR_NAME
    fname = (f"{stem}_{stamp}{ext}" if stem else f"{folder}_{stamp}{ext}")
    subdir = os.path.join(FRONTEND_PUBLIC, folder)
    os.makedirs(subdir, exist_ok=True)
    fp = os.path.join(subdir, fname)
    with open(fp, "wb") as fh:
        fh.write(data)
    return f"/images/{folder}/{fname}", None

def _mime_ext(mime):
    """根据 dataURL 声明的 MIME 推断扩展名（仅作兜底）。"""
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return ext_map.get((mime or "").lower())

# ---------- 源视频上传（朋友圈视频动态） ----------

def _list_source_videos():
    """列出 public/videos 下可被前端引用的视频，返回 /videos/xxx.mp4 路径列表。"""
    if not os.path.isdir(SOURCE_VIDEO_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(SOURCE_VIDEO_DIR)):
        if fn.lower().endswith(VIDEO_EXTS):
            out.append("/videos/" + fn)
    return out

def _video_mime_ext(mime):
    """根据上传声明的 MIME 推断视频扩展名。"""
    return {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "video/x-m4v": ".m4v",
    }.get((mime or "").lower())

def _save_upload_video(raw, name="", mime=""):
    """把上传的视频字节直接落盘到 vue-WeChat/public/videos/。

    返回 (路径, None) 或 (None, 错误)。

    不做转码：项目用系统安装的 Chrome 作为浏览器内核（完整 H.264/AAC），
    mp4 可以直接 <video> 播放；转码既慢又伤画质。这里只做
    大小上限校验 + 扩展名归一 + 文件名净化。
    """
    if not raw:
        return None, "未收到视频数据"
    if len(raw) < 1024:
        return None, "视频内容为空或已损坏"
    if len(raw) > MAX_VIDEO_BYTES:
        return None, "视频不能超过 %d MB" % (MAX_VIDEO_BYTES // (1024 * 1024))
    ext = os.path.splitext(str(name or ""))[1].lower()
    if ext not in VIDEO_EXTS:
        ext = _video_mime_ext(mime) or ""
    if ext not in VIDEO_EXTS:
        return None, "仅支持 MP4 / WebM / MOV / M4V 视频"
    stem = ""
    if name:
        stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "_",
                      os.path.splitext(os.path.basename(str(name)))[0])[:40].strip("_")
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    fname = (f"{stem}_{stamp}{ext}" if stem else f"video_{stamp}{ext}")
    os.makedirs(SOURCE_VIDEO_DIR, exist_ok=True)
    with open(os.path.join(SOURCE_VIDEO_DIR, fname), "wb") as fh:
        fh.write(raw)
    return "/videos/" + fname, None

def _normalize_image(data):
    """用 Pillow 按真实字节归一化图片，返回 (字节, 扩展名)。

    - GIF / WebP：透传原字节（保留动画与透明）。
    - 含透明通道（RGBA/LA/P）或真实格式为 PNG：转 8-bit PNG（ext .png）。
    - 其余（JPEG / BMP / 16-bit / CMYK）：exif_transpose 后转 RGB JPEG（quality 92）。
    """
    import io

    im = Image.open(io.BytesIO(data))
    im.load()
    fmt = (im.format or "").upper()

    # 动态/带透明且可动画的格式原样透传，避免丢动画或透明
    if fmt in ("GIF", "WEBP"):
        return data, ("." + fmt.lower())

    is_png = fmt == "PNG"
    if is_png or im.mode in ("RGBA", "LA", "PA", "P"):
        # 统一纠正 EXIF 方向并规范化像素；带透明保留透明，其余转不透明 RGB
        im = ImageOps.exif_transpose(im)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        rgba = im.convert("RGBA") if has_alpha else im.convert("RGB")
        out = io.BytesIO()
        rgba.save(out, format="PNG")
        return out.getvalue(), ".png"

    # 其余转 RGB JPEG（含 CMYK、16-bit、BMP）
    im = ImageOps.exif_transpose(im)
    rgb = im.convert("RGB")
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=92)
    return out.getvalue(), ".jpg"

def _rename_image(old_path, new_name):
    """重命名图片库中的一张图片。返回 (新的 /images/ 路径, None) 或 (None, 错误消息)。

    仅在原目录内改文件名，不清洗目录；非法目录/文件名/扩展名都会被拒绝。
    """
    if not (old_path or "").startswith("/images/"):
        return None, "路径必须以 /images/ 开头"
    old_fp = _safe_image_fp(unquote(old_path[len("/images/"):]))
    if old_fp is None:
        return None, "非法路径"
    if not os.path.isfile(old_fp):
        return None, "图片不存在"

    new_base = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", os.path.basename(new_name or "")).strip("_.")
    if not new_base:
        return None, "请输入有效的新文件名"
    ext = os.path.splitext(new_base)[1].lower()
    if ext == "":
        ext = os.path.splitext(old_fp)[1].lower()      # 未写扩展名则沿用原扩展名
        new_base += ext
    if ext not in IMG_EXTS:
        return None, "仅支持 " + " / ".join(e.lstrip(".") for e in IMG_EXTS) + " 图片"
    new_fp = os.path.join(os.path.dirname(old_fp), new_base)
    if new_fp == old_fp:
        return None, "新文件名与原文件名相同"
    if os.path.exists(new_fp):
        return None, "已存在同名文件"
    try:
        os.rename(old_fp, new_fp)
    except OSError as exc:
        return None, "重命名失败：" + str(exc)
    rel = os.path.relpath(new_fp, FRONTEND_PUBLIC).replace(os.sep, "/")
    return "/images/" + rel, None

# 「移动分类」时需要同步替换旧路径引用的数据文件（存在才处理）
_MOVE_REF_FILES = ["scene.json", "workflow.json", "people.json", "peer_presets.json",
                   "reference_workflow.json", os.path.join("enhance", "config.js")]

def _update_path_references(old_web, new_web):
    """把项目数据文件里对 old_web 的引用替换成 new_web，返回被修改的文件名列表。"""
    changed = []
    for rel in _MOVE_REF_FILES:
        fp = os.path.join(ROOT, rel)
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        if old_web not in text:
            continue
        try:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(text.replace(old_web, new_web))
        except OSError:
            continue
        changed.append(rel)
    return changed

def _move_image(path, category):
    """把图片移动到指定分类对应的子目录（真正的文件搬移）。

    移动后自动把 scene.json / workflow.json / people.json / enhance/config.js 等
    数据文件里的旧路径引用替换成新路径，并迁移「自定义命名」元数据。
    返回 (新路径, 更新的引用文件列表, None) 或 (None, [], 错误消息)。
    """
    if not (path or "").startswith("/images/"):
        return None, [], "路径必须以 /images/ 开头"
    target_dir = _CATEGORY_DIRS.get(category or "")
    if not target_dir:
        return None, [], "不支持移动到该分类"
    old_fp = _safe_image_fp(unquote(path[len("/images/"):]))
    if old_fp is None:
        return None, [], "非法路径"
    if not os.path.isfile(old_fp):
        return None, [], "图片不存在"
    rel_old = os.path.relpath(old_fp, FRONTEND_PUBLIC).replace(os.sep, "/")
    if os.path.dirname(rel_old) == target_dir:
        return None, [], "这张图已经在该分类里了"
    target_sub = os.path.join(FRONTEND_PUBLIC, target_dir)
    os.makedirs(target_sub, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(old_fp))
    new_fp = os.path.join(target_sub, os.path.basename(old_fp))
    n = 1
    while os.path.exists(new_fp):          # 同名冲突：加序号后缀
        new_fp = os.path.join(target_sub, f"{stem}_{n}{ext}")
        n += 1
    try:
        os.rename(old_fp, new_fp)
    except OSError as exc:
        return None, [], "移动失败：" + str(exc)
    rel_new = os.path.relpath(new_fp, FRONTEND_PUBLIC).replace(os.sep, "/")
    old_web, new_web = "/images/" + rel_old, "/images/" + rel_new
    changed = _update_path_references(old_web, new_web)
    meta = _load_gallery_meta()
    if old_web in meta:                    # 迁移自定义命名
        meta[new_web] = meta.pop(old_web)
        _save_gallery_meta(meta)
    return new_web, changed, None

def _delete_image(path):
    """删除图片库中的一张图片。返回 (True, None) 或 (False, 错误消息)。"""
    if not (path or "").startswith("/images/"):
        return False, "路径必须以 /images/ 开头"
    fp = _safe_image_fp(unquote(path[len("/images/"):]))
    if fp is None:
        return False, "非法路径"
    if not os.path.isfile(fp):
        return False, "图片不存在"
    try:
        os.remove(fp)
    except OSError as exc:
        return False, "删除失败：" + str(exc)
    # 清理该图的展示名元数据
    rel = os.path.relpath(fp, FRONTEND_PUBLIC).replace(os.sep, "/")
    meta = _load_gallery_meta()
    if rel in meta:
        del meta[rel]
        _save_gallery_meta(meta)
    return True, None

def _set_gallery_label(path, label):
    """为一张图设置「自定义命名」（只写展示名元数据，不改磁盘文件）。返回 (True, None)/(False, err)。"""
    if not (path or "").startswith("/images/"):
        return False, "路径必须以 /images/ 开头"
    fp = _safe_image_fp(unquote(path[len("/images/"):]))
    if fp is None:
        return False, "非法路径"
    if not os.path.isfile(fp):
        return False, "图片不存在"
    rel = os.path.relpath(fp, FRONTEND_PUBLIC).replace(os.sep, "/")
    meta = _load_gallery_meta()
    lab = re.sub(r"\s+", " ", (label or "")).strip()[:60]
    if lab:
        meta[rel] = lab
    else:
        meta.pop(rel, None)
    if not _save_gallery_meta(meta):
        return False, "保存命名失败（无法写入元数据文件）"
    return True, None

def _start_run(headless: bool, typing_speed: float = 30.0, intro: bool = False,
               bgm: bool = True, bgm_path: str = "", use_scene: bool = True):
    """启动 runner 子进程（写入日志文件，后台运行）

    use_scene=True（默认）且 scene.json 有内容时，自动追加 --scene，
    让「工作流运行」的聊天主页直接就是场景编辑器里编排好的
    我的资料 + 会话列表（含历史消息）+ 朋友圈，便于在工作流模式下逐项测试功能。
    若工作流自己的首步是「编辑主页 / 应用场景」，仍会按工作流里的数据覆盖，
    语义保持不变（工作流显式指定优先）。
    """
    global _run_proc
    # 加锁顺序与 _start_edit 保持一致（先 _edit_lock 再 _run_lock），
    # 避免「运行」与「编辑模式」并发启动时互持锁等待造成死锁
    with _edit_lock:
        if _edit_proc and _edit_proc.poll() is None:
            return False, "编辑模式正在运行中，请先退出编辑模式。"
        with _run_lock:
            if _run_proc and _run_proc.poll() is None:
                return False, "已有流程在运行中，请先停止。"
        cmd = [sys.executable, os.path.join(ROOT, "main.py"),
               "--workflow", WORKFLOW_PATH]
        if headless:
            cmd.append("--headless")
        # 打字倍速：始终显式传给 main.py（值为编辑器「打字倍速」滑块/默认 30.0），
        # 按键节奏、拼音选字、删除回删都会随此倍速缩放。
        cmd.append("--typing-speed")
        cmd.append(str(typing_speed))
        # 可选：录制完成后在视频开头拼接锁屏收消息开场
        if intro:
            cmd.append("--intro")
        # 背景音乐：默认开启（用 main.py 内置的 苹果音效/背景音乐.mp3）。
        # 关闭时传 --no-bgm；自定义路径时传 --bgm <path>。
        if not bgm:
            cmd.append("--no-bgm")
        elif bgm_path:
            cmd.append("--bgm")
            cmd.append(bgm_path)
        # 聊天背景：单条运行同样自动挑一张（目录为空则回退默认深色）
        if os.path.isdir(CHAT_BG_DIR):
            cmd += ["--chat-bg-dir", CHAT_BG_DIR, "--chat-bg-pick", "random"]
        # 场景：工作流运行默认套用「场景编辑器」当前保存的场景，
        # 让聊天主页直接是编排好的联系人 / 消息 / 我的资料 / 朋友圈。
        # 场景为空（还没在场景编辑器里配过）时不加参数，行为与以前一致。
        if use_scene:
            scene = _read_scene()
            has_scene = bool(scene and (scene.get("home") or scene.get("me")
                                        or scene.get("moments") or scene.get("peer")))
            if has_scene and os.path.isfile(SCENE_PATH):
                cmd += ["--scene", SCENE_PATH]
                _n = len(scene.get("home") or [])
                print(f"[场景] 运行前套用场景编辑器的场景（{_n} 个会话）：{SCENE_PATH}",
                      flush=True)
        log_fh = open(RUN_LOG, "w", encoding="utf-8", errors="replace")
        # 把完整启动命令写入日志，便于确认是否带了 --intro 等参数
        log_fh.write("[启动命令] " + subprocess.list2cmdline(cmd) + "\n")
        log_fh.flush()
        _run_proc = subprocess.Popen(
            cmd, cwd=ROOT, stdout=log_fh, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True, "运行已启动"

def _stop_run():
    global _run_proc
    with _run_lock:
        if _run_proc and _run_proc.poll() is None:
            _run_proc.terminate()
            try:
                _run_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _run_proc.kill()
            _run_proc = None
            return True
    return False

def _start_edit():
    """启动「编辑模式」子进程：打开手机画面后空闲待命，供编辑器点击/修改元素。"""
    global _edit_proc
    with _edit_lock:
        if _edit_proc and _edit_proc.poll() is None:
            return False, "编辑模式已在运行中。"
        with _run_lock:
            if _run_proc and _run_proc.poll() is None:
                return False, "有流程正在运行，请先停止再进入编辑模式。"
        cmd = [sys.executable, os.path.join(ROOT, "main.py"),
               "--editmode", "--headless", "--liveport", str(LIVE_PORT)]
        log_fh = open(EDIT_LOG, "w", encoding="utf-8", errors="replace")
        _edit_proc = subprocess.Popen(
            cmd, cwd=ROOT, stdout=log_fh, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True, "编辑模式已启动"

def _stop_edit():
    """停止编辑模式：先通知进程自行退出，等 3 秒后强杀兜底。"""
    global _edit_proc
    with _edit_lock:
        if not _edit_proc or _edit_proc.poll() is not None:
            _edit_proc = None
            return False
        try:
            conn = http.client.HTTPConnection("127.0.0.1", LIVE_PORT, timeout=2)
            conn.request("POST", "/api/quit")
            resp = conn.getresponse()
            resp.read()
            conn.close()
            try:
                _edit_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _edit_proc.terminate()
                try:
                    _edit_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _edit_proc.kill()
        except Exception:                           # noqa: BLE001
            _edit_proc.terminate()
            try:
                _edit_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _edit_proc.kill()
        _edit_proc = None
        return True

def _run_log_tail(offset: int):
    if not os.path.isfile(RUN_LOG):
        return {"text": "", "offset": 0, "running": False}
    with open(RUN_LOG, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        text = fh.read()
        new_offset = fh.tell()
    running = bool(_run_proc) and _run_proc.poll() is None
    return {"text": text, "offset": new_offset, "running": running}

def _capture_screenshot():
    """用 Playwright headless 打开首页并注入 iPhone 仿真层，截图 PNG 存 videos/。

    返回 (文件路径, None) 成功 / (None, 错误信息) 失败。
    """
    try:
        sys.path.insert(0, ROOT)
        import main as _wx
        from playwright.sync_api import sync_playwright
    except Exception as exc:                      # noqa: BLE001
        return None, f"缺少依赖：{exc}（请先 pip install playwright）"

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(VIDEO_DIR, f"shot_{stamp}.png")
    try:
        _wx.ensure_frontend_running()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(
                viewport={"width": _wx.VIEWPORT_W, "height": _wx.VIEWPORT_H},
                device_scale_factor=2,
                user_agent=_wx.MOBILE_UA,
                is_mobile=True,
                has_touch=True,
                locale="zh-CN",
            )
            page = ctx.new_page()
            page.goto(_wx.BASE_URL, wait_until="domcontentloaded")
            _wx.inject_overlays(page)
            page.wait_for_timeout(2000)
            page.screenshot(path=path)
            browser.close()
        return path, None
    except Exception as exc:                      # noqa: BLE001
        return None, f"截图失败：{exc}"


def _parse_script_to_steps(text, offline=False):
    """把一段剧本文本解析成步骤列表，返回 (steps, warnings, source)。

    供 /api/translate 与并发跑批的任务解析共用同一套逻辑：先剥离「历史会话块」，
    再做 AI 转译（或离线解析），最后把历史块拼回结果并做人物归一。

    人物一致性：先把【全剧】人物名（历史会话头 + 所有「打开聊天」联系人）收齐，
    一次性生成同一份替换映射（同一旧名 -> 同一库中人），再同时喂给历史块、AI/离线
    转译与归一，确保「主页会话卡片」和「下面点开的聊天」永远用同一个人，不换错人。
    """
    text = str(text or "")
    all_names = script_translator._collect_text_person_names(text)
    global_map = script_translator.build_name_replacement_map(all_names)
    history_steps, cleaned_text, hist_warnings, repl_map = script_translator.split_history_block(
        text, pre_mapping=global_map)
    # 合并成一份最终映射：全局映射优先，历史块自身补充的映射次之。
    full_map = {**global_map, **repl_map}
    if offline:
        steps, warnings = script_translator.translate_offline(cleaned_text)
        steps = script_translator.merge_typing_waits(steps, cleaned_text)
        if not steps:
            warnings = list(warnings) + [
                "未识别出任何有效指令。离线解析只支持标准格式（[指令] 参数）；"
                "松散自然语言请先配置 API Key 后使用「AI 转译剧本」。"]
        result = {"steps": steps, "warnings": warnings, "source": "offline"}
    else:
        result = script_translator.translate(cleaned_text, actions=ACTIONS, pre_mapping=full_map)
    if history_steps:
        # 历史会话块自带完整的 [编辑主页]；剔掉 AI 自动补的那条占位版，避免覆盖清空历史。
        translated = [s for s in (result["steps"] or []) if s.get("action") != "编辑主页"]
        result["steps"] = history_steps + translated
        result["warnings"] = list(hist_warnings) + list(result.get("warnings") or [])
    # 用同一份映射统一收尾归一，保证主页卡片与 [打开聊天] 严格对齐、不换错人。
    script_translator.normalize_step_people(result["steps"], pre_mapping=full_map)
    # 主页一屏最多 9 个会话：只保留前 9 个历史会话、丢弃后续；
    # [打开聊天] 联系人不在前 9 里时按顺序对齐到主页可见人物，避免追加新人导致前后对不上
    # （离线 / LLM 都走一遍，防止 LLM 结果仍引用了被丢弃的第 10 个及以后的联系人）。
    script_translator.cap_home_and_align_contacts(result["steps"], result["warnings"])
    # 兜底：确保 [编辑主页] 覆盖所有 [打开聊天] 引用的联系人，避免"聊天列表找不到联系人"。
    # 历史块 [编辑主页] 只含块内联系人，剧本其余部分（如 LLM 结果）引用的联系人需补进列表。
    script_translator.ensure_all_contacts_in_home(result["steps"])
    # 把「内容以 [图片]/[配图] 开头」的消息步骤统一转成图片动作（对方发图片/发送图片），
    # 与脚本模式一致，避免并发界面的运行器把 [图片] 前缀当成纯文字发出。
    script_translator.convert_image_marker_steps(result["steps"])
    # 把「内容以 [链接] 开头」的消息步骤统一转成链接卡片动作（我方发链接/对方发链接）：
    # 让链接的封面/来源参数被正确拆出、并进入链接图库预载，而不是当普通文字发出。
    script_translator.convert_link_marker_steps(result["steps"])
    return result["steps"], result["warnings"], result["source"]


# ============================================================
# 剧本创作生成器（男追女聊天教学）：主题 + 参考剧本 -> 完整 [指令] 剧本
# ============================================================

# 创作生成单次调用大模型的超时与重试参数。DeepSeek 处理长文本（含参考剧本/人物库/
# 偏好块的大 prompt + 可达 8000 tokens 的输出）在高峰期容易超过请求超时，此处：
#   - 单次超时放宽到 300s；
#   - 对「瞬时错误（读超时/连接断/服务端 429|5xx）」自动重试，避免用户一次点生成就报错。
_GENERATE_TIMEOUT = 600.0
_GENERATE_RETRIES = 2            # 除首次外的额外重试次数（共最多 3 次尝试）
_GENERATE_MAX_TOKENS = 32000     # 该模型是推理模型：reasoning_tokens 会先吃掉预算，
                                 # 8000 时 reasoning 就占满、正文被截断（finish_reason=length）。
_GENERATE_MAX_TOKENS_CAP = 64000  # 若首轮仍被 reasoning 吃光，自动加倍到这个上限
# 诊断目录：把每轮生成的提示词/模型原始输出/解析结果落盘，便于排查"生成结果解析不出步骤"。
_GEN_DEBUG_DIR = os.path.join(ROOT, "_runtime", "_gen_debug")


def _is_retryable_call_error(exc: Exception) -> bool:
    """判断一次大模型调用失败是否为「可重试的瞬时错误」。

    超时 / 连接类异常，以及 DeepSeek 服务端临时错误（429、5xx）都值得立即重试；
    API 返回 4xx 参数类错误或响应解析失败等则不可重试，直接报错更快。
    """
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return True
    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        return any(code in msg for code in ("返回 429", "返回 500", "返回 502", "返回 503", "返回 504"))
    return False


def _call_generate_deepseek(api_key, system_prompt, user_msg, model, base_url):
    """调用大模型进行创作生成，带自动重试。

    返回 (text, error_msg)：text 为成功时的模型输出；error 为最终失败原因（成功时 None）。

    两类空/失败都要处理：
      1) DeepSeek 对长请求偶发返回「HTTP 正常但内容为空」——视为瞬时失败重试；
      2) 本模型是推理模型，reasoning_tokens 会先占满输出预算，导致正文为空或被截断
         （finish_reason=length）——此时自动加倍 max_tokens 重试，而不是报「模型返回内容为空」。
    """
    last_exc = None
    max_tokens = _GENERATE_MAX_TOKENS
    for attempt in range(_GENERATE_RETRIES + 1):
        text = None
        info = None
        err = None
        try:
            text, info = script_translator.call_deepseek(
                api_key, system_prompt, user_msg, model, base_url,
                timeout=_GENERATE_TIMEOUT, max_tokens=max_tokens, json_mode=False,
                meta=True)
        except Exception as exc:                    # noqa: BLE001
            err = exc
        # 成功且非空：直接返回
        if text is not None and (text or "").strip():
            return text, None
        finish = (info or {}).get("finish_reason")
        if finish == "length":
            # 推理模型把输出预算全用在 reasoning 上，导致正文为空/被截断。
            # 这不是"模型没说话"，加大预算再试，而不是报「模型返回内容为空」。
            last_exc = RuntimeError(
                "模型输出被截断：推理过程用满了 %d 个输出 token（finish_reason=length），"
                "正文没有生成完。" % max_tokens)
            max_tokens = min(max_tokens * 2, _GENERATE_MAX_TOKENS_CAP)
            continue
        # 空文本也算失败；错误是否可重试视类型而定（空文本总是值得重试一次）。
        last_exc = err or RuntimeError("模型返回内容为空")
        retryable = (err is None) or _is_retryable_call_error(err)
        if attempt < _GENERATE_RETRIES and retryable:
            time.sleep(3 + 2 * attempt)
            continue
        return None, last_exc
    return None, last_exc


def _generate_script(payload: dict):
    """执行一次"创作生成"：主题 + 参考剧本 -> 完整 [指令] 文本 + 归一步骤 + 校验报告。

    返回 (result_dict, error_msg)：
      result_dict = {"ok": True, "text": ..., "steps": [...], "warnings": [...],
                     "report": {"issues": [...], "attempts": int, "passed": bool}, "source": "generate"}
    流程：AI 输出 [指令] 文本 -> 完整性检查 -> 离线归一(parse_script_to_steps offline)
          -> 结构化校验 -> 有问题则 critique 重写（最多 2 轮），全程记录问题清单。
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
    best = None  # (评分, 文本, 问题清单, 是否通过)：防止「越改越差」

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
        if attempt > 0 and current_text and len(raw) < len(current_text) * 0.5:
            # 纠错轮把剧本砍掉一半以上：这是「越改越差」，直接保留上一版。
            break
        current_text = raw

        completeness = script_generator.check_completeness(raw)
        # 离线归一（生成结果已是标准 [指令]，避免二次调用大模型）
        steps, warnings, _src = _parse_script_to_steps(raw, offline=True)
        structural, violated_skills = script_generator.validate_generated_steps(steps, skills, raw)
        all_issues = completeness + structural
        # 记录本轮的「好坏」：问题越少越好，同分时文本更完整者优先。
        _score = (len(all_issues), -len(raw))
        if best is None or _score < best[0]:
            best = (_score, raw, list(all_issues), not all_issues)
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
                fh.write("===== system_prompt =====\n" + sys_prompt +
                         "\n\n===== user_msg =====\n" + user_msg +
                         "\n\n===== raw_output =====\n" + (raw or "") +
                         "\n\n===== parsed_steps =====\n" + json.dumps(steps, ensure_ascii=False, indent=2) +
                         "\n\n===== issues =====\n" + "\n".join(all_issues))
        except OSError:
            pass
        if not all_issues:
            passed = True
            break

    # 采用「问题最少的那一轮」，而不是无脑用最后一轮：
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
        },
        "ref_titles": ref_titles,
        "auto_refs": auto_refs,
        "source": "generate",
    }
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
        })
        result["history_id"] = entry.get("id")
    except Exception:  # noqa: BLE001
        pass
    return result, None


# ============================================================
# 并发跑批：任务队列（一次跑多条剧本，各自生成独立视频）
# ============================================================
# 旧编辑器（工作流编辑 / 脚本模式）仍走单条 _run_proc 与 workflow.json；
# 这里另起一套「任务队列」：每条任务 = 一份剧本，可独立解析、独立运行，
# 各自的 workflow 与日志写入 _runtime/<id>.json / <id>.log，视频用 --tag <id>
# 前缀命名，互不冲突，从而支持同时跑多条。

TASKS_PATH = os.path.join(ROOT, "tasks.json")                 # 任务持久化文件
RUNTIME_DIR = os.path.join(ROOT, "_runtime")                  # 每条任务的 workdir（工作流 + 日志）
BATCH_CONF_PATH = os.path.join(ROOT, "_concurrent.json")      # 批量设置（并发上限等）
BATCH_MAX_CONCURRENT = 3                                      # 默认同时跑几条（前端可改）

_task_lock = threading.Lock()     # 保护 _tasks / _task_procs 等
_tasks = {}                       # id -> 任务 dict（可持久化部分）
_task_procs = {}                  # id -> Popen
_task_workflow = {}               # id -> 该任务工作流 json 路径
_task_log = {}                    # id -> 该任务日志路径
_batch_event = threading.Event()  # 批次工人线程的唤醒信号
_batch_started = False            # 批次工人线程是否已启动

TASK_IDLE = "idle"
TASK_QUEUED = "queued"
TASK_RUNNING = "running"
TASK_SUCCESS = "success"
TASK_FAILED = "failed"
TASK_STOPPED = "stopped"

_frontend_lock = threading.Lock()
_frontend_ensured = False


def _ensure_frontend():
    """确保前端 dev server 已启动（仅供批量跑批启动前预热，减少并发启动竞态）。"""
    global _frontend_ensured
    with _frontend_lock:
        if _frontend_ensured:
            return True
        try:
            sys.path.insert(0, ROOT)
            import main as _wx                       # noqa: PLC0415
            _wx.ensure_frontend_running()
            _frontend_ensured = True
            return True
        except Exception as exc:                     # noqa: BLE001
            print(f"[批量] 前端预热失败（子进程会自行处理）：{exc}")
            return False


def _default_task():
    """返回一条空任务的默认结构。"""
    now = _dt.datetime.now().timestamp()
    return {
        "id": "",
        "name": "未命名任务",
        "script": "",
        "steps": [],
        "warnings": [],
        "source": "",
        "options": {"typing_speed": 30.0, "intro": False, "bgm": True, "bgm_path": ""},
        "images": {},                 # 配图槽位 key -> 图片路径（脚本解析时由前端生成 img0/img1...）
        "status": TASK_IDLE,
        "video": None,
        "error": None,
        "created": now,
        "updated": now,
        "log_offset": 0,
    }


def _new_task_id():
    """生成带时间戳的唯一任务 id（也用作视频 --tag 前缀）。"""
    return "t" + _dt.datetime.now().strftime("%y%m%d%H%M%S%f")[:-3]


def _load_tasks():
    """重启后恢复任务表；原先在跑/排队的任务已无对应进程，重置为 idle 并提示。"""
    global _tasks
    data = {}
    if os.path.isfile(TASKS_PATH):
        try:
            with open(TASKS_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
    tasks = {}
    for tid, t in (data or {}).items():
        if not isinstance(t, dict):
            continue
        task = _default_task()
        task.update(t)
        task["id"] = tid
        if task.get("status") in (TASK_RUNNING, TASK_QUEUED):
            task["status"] = TASK_IDLE
            task["error"] = "服务重启，任务已中断。"
        tasks[tid] = task
    _tasks = tasks


def _save_tasks_locked():
    try:
        with open(TASKS_PATH, "w", encoding="utf-8") as fh:
            json.dump(_tasks, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _task_dict_public(task):
    """返回可直接给前端的任务字典（去掉进程内部字段）。"""
    t = dict(task)
    return t


def _batch_ensure_worker():
    """确保批次工人线程已启动（守护线程，常驻轮询）。"""
    global _batch_started
    with _task_lock:
        if _batch_started:
            return
        _batch_started = True
    threading.Thread(target=_batch_worker, daemon=True).start()


def _batch_worker():
    while True:
        _batch_event.wait(1.0)
        _batch_event.clear()
        _batch_pump()


def _batch_pump():
    """收编已完成的任务，并在不超并发上限时启动排队任务。"""
    with _task_lock:
        # 1) 收编已结束的子进程
        for tid, proc in list(_task_procs.items()):
            if proc.poll() is not None:
                _finalize_task_locked(tid, proc)
                del _task_procs[tid]
        running = len(_task_procs)
        need_launch = running < BATCH_MAX_CONCURRENT and \
            any(t.get("status") == TASK_QUEUED for t in _tasks.values())

    # 2) 仅在确实要启动新任务时预热前端（可能较慢，放在锁外避免阻塞 API）
    if need_launch:
        _ensure_frontend()
        with _task_lock:
            running = len(_task_procs)
            if running < BATCH_MAX_CONCURRENT:
                queued = [tid for tid, t in _tasks.items() if t.get("status") == TASK_QUEUED]
                for tid in queued:
                    if running >= BATCH_MAX_CONCURRENT:
                        break
                    if _launch_task_locked(_tasks[tid]):
                        running += 1
            _save_tasks_locked()
    else:
        with _task_lock:
            _save_tasks_locked()


def _launch_task_locked(task):
    """写入该任务的工作流/日志并启动 main.py 子进程。成功返回 True。"""
    tid = task["id"]
    steps = task.get("steps") or []
    if not steps:
        task["status"] = TASK_FAILED
        task["error"] = "没有可运行的步骤，请先解析剧本。"
        return False
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    wf_path = os.path.join(RUNTIME_DIR, f"{tid}.json")
    log_path = os.path.join(RUNTIME_DIR, f"{tid}.log")
    with open(wf_path, "w", encoding="utf-8") as fh:
        json.dump({"name": task.get("name") or tid, "steps": steps}, fh, ensure_ascii=False, indent=2)
    opt = task.get("options") or {}
    typing_speed = min(40.0, max(0.1, float(opt.get("typing_speed", 30.0))))  # 上限 40
    cmd = [sys.executable, os.path.join(ROOT, "main.py"),
           "--workflow", wf_path, "--headless",
           "--typing-speed", str(typing_speed),
           "--tag", tid]
    if opt.get("intro"):
        cmd.append("--intro")
    if not opt.get("bgm", True):
        cmd.append("--no-bgm")
    elif opt.get("bgm_path"):
        cmd.append("--bgm")
        cmd.append(str(opt["bgm_path"]))
    # 聊天背景：每条任务自动从背景库挑一张。seed=tid 的 crc32 保证「同一条视频背景稳定、
    # 不同条视频背景不同、整片一致」。目录为空时 main.py 会回退默认深色，不影响现有行为。
    if os.path.isdir(CHAT_BG_DIR):
        cmd += ["--chat-bg-dir", CHAT_BG_DIR, "--chat-bg-pick", "random",
                "--chat-bg-seed", str(zlib.crc32(tid.encode("utf-8")) & 0xffffffff)]
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    log_fh.write("[启动命令] " + subprocess.list2cmdline(cmd) + "\n")
    log_fh.flush()
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log_fh, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as exc:
        log_fh.close()
        task["status"] = TASK_FAILED
        task["error"] = "启动失败：" + str(exc)
        return False
    _task_procs[tid] = proc
    _task_workflow[tid] = wf_path
    _task_log[tid] = log_path
    task["status"] = TASK_RUNNING
    task["video"] = None
    task["error"] = None
    task["log_offset"] = 0
    task["updated"] = _dt.datetime.now().timestamp()
    return True


def _finalize_task_locked(tid, proc):
    """任务子进程结束：判定成功（有产出视频）或失败，并记录日志尾部。"""
    task = _tasks.get(tid)
    if not task:
        return
    code = proc.poll()
    log_path = _task_log.get(tid)
    tail = ""
    if log_path and os.path.isfile(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                tail = fh.read()[-800:]
        except OSError:
            pass
    # 找该任务产出的视频：wx_<tid>_*.mp4 最新一张（文件名含毫秒时间戳，字典序即时间序）
    vids = []
    if os.path.isdir(VIDEO_DIR):
        vids = [f for f in os.listdir(VIDEO_DIR)
                if f.lower().endswith(".mp4") and f.startswith(f"wx_{tid}_")]
        vids.sort(reverse=True)
    if vids:
        task["status"] = TASK_SUCCESS
        task["video"] = vids[0]
        task["error"] = None
    else:
        task["status"] = TASK_FAILED
        reason = f"进程退出码 {code}" if code is not None else "进程已退出"
        lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        if lines:
            reason += " · " + lines[-1][:120]
        task["error"] = reason
    task["updated"] = _dt.datetime.now().timestamp()


def _kill_tree(pid: int) -> None:
    """强制结束一个进程及其整棵子进程树（含它派生的 ffmpeg / playwright 等）。

    历史问题：Windows 上 Popen.terminate() 只结束直接子进程，不会级联杀掉其派生的
    ffmpeg 子进程——这会导致「停止任务后视频仍在生成」（孤儿 ffmpeg 继续把
    wx_<tag>_*.mp4 写完），任务状态对不上、流程无法收尾。
    这里改用 taskkill /PID <pid> /T /F（连同子进程树一并终止）；非 Windows 回退到
    进程组 kill，再兜底直接 kill 进程本身。
    """
    if pid is None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _stop_task_proc(tid):
    """停止单条任务的子进程（若在跑），返回是否真的停掉。"""
    with _task_lock:
        proc = _task_procs.get(tid)
        if proc and proc.poll() is None:
            _kill_tree(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            _finalize_task_locked(tid, proc)
            task = _tasks.get(tid)
            if task:
                task["status"] = TASK_STOPPED
                task["error"] = "已手动停止。"
                task["updated"] = _dt.datetime.now().timestamp()
            del _task_procs[tid]
            _save_tasks_locked()
            return True
    return False


def _log_tail(path, offset):
    if not path or not os.path.isfile(path):
        return {"text": "", "offset": 0, "running": False}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        text = fh.read()
        new_offset = fh.tell()
    return {"text": text, "offset": new_offset, "running": False}


def _batch_status_locked():
    running = len([t for t in _tasks.values() if t.get("status") == TASK_RUNNING])
    queued = len([t for t in _tasks.values() if t.get("status") == TASK_QUEUED])
    return {"running": running, "queued": queued, "max_concurrent": BATCH_MAX_CONCURRENT}


def _read_batch_conf():
    if os.path.isfile(BATCH_CONF_PATH):
        try:
            with open(BATCH_CONF_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
    return {}


def _write_batch_conf(conf):
    try:
        with open(BATCH_CONF_PATH, "w", encoding="utf-8") as fh:
            json.dump(conf, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _set_batch_max_concurrent(value):
    global BATCH_MAX_CONCURRENT
    try:
        n = int(value)
    except (TypeError, ValueError):
        return BATCH_MAX_CONCURRENT, "并发数必须是整数"
    if not (1 <= n <= 8):
        return BATCH_MAX_CONCURRENT, "并发数需在 1~8 之间"
    BATCH_MAX_CONCURRENT = n
    conf = _read_batch_conf()
    conf["max_concurrent"] = n
    _write_batch_conf(conf)
    _batch_pump()   # 上限提高时立即多启动几条
    return n, None


class Handler(SimpleHTTPRequestHandler):
    """静态文件 + JSON API"""

    def end_headers(self):
        # 允许前端(Vite 8080)跨域调用编辑器的 JSON API（上传/列出聊天背景等），
        # 使「换聊天背景」面板能直接向编辑器上传图片。同源访问不受影响。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):  # noqa: N802
        # 跨域预检：直接返回 204 + CORS 头，放行后续真正请求
        self.send_response(204)
        self.end_headers()

    def _send_file(self, fp):
        """返回一个二进制文件，Content-Type 按扩展名推断。"""
        try:
            ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        except Exception:                        # noqa: BLE001
            ctype = "application/octet-stream"
        with open(fp, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/images/"):
            # 图片库静态文件：映射到 vue-WeChat/public/images，供编辑器预览头像/图片
            # 注意：self.path 是 HTTP 请求行里的原始路径，可能是百分号编码的（如中文文件名
            # 会被浏览器编码成 %E6%88%91...）。必须先 unquote 再拼接，否则中文名图片会 404。
            rel = unquote(self.path.split("?", 1)[0][len("/images/"):])
            fp = _safe_image_fp(rel)
            if fp is None:
                return _json_reply(self, 403, {"ok": False, "msg": "禁止访问"})
            if os.path.isfile(fp):
                self._send_file(fp)
                return
            return _json_reply(self, 404, {"ok": False, "msg": "图片不存在"})
        if self.path == "/scene":
            fp = os.path.join(EDITOR_DIR, "scene.html")
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8") as fh:
                    html = fh.read()
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return _json_reply(self, 404, {"ok": False, "msg": "scene.html 不存在"})
        if self.path in ("/concurrent", "/concurrent/"):
            fp = os.path.join(EDITOR_DIR, "concurrent.html")
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8") as fh:
                    html = fh.read()
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return _json_reply(self, 404, {"ok": False, "msg": "concurrent.html 不存在"})
        if self.path == "/api/scene":
            return _json_reply(self, 200, _read_scene())
        if self.path == "/api/peer-presets":
            return _json_reply(self, 200, _read_peer_presets())
        if self.path.startswith("/enhance/"):
            # 供场景编辑器预览复用真实前端增强层（对方主页/朋友圈样式），只允许读 enhance 目录
            rel = unquote(self.path.split("?", 1)[0][len("/enhance/"):])
            fp = os.path.normpath(os.path.join(ENHANCE_DIR, rel))
            if fp.startswith(ENHANCE_DIR + os.sep) and os.path.isfile(fp):
                self._send_file(fp)
                return
            return _json_reply(self, 404, {"ok": False, "msg": "文件不存在"})
        if self.path == "/api/people":
            return _json_reply(self, 200, _read_people())
        if self.path == "/api/gallery":
            return _json_reply(self, 200, _gallery_payload())
        if self.path == "/api/chat-bgs":
            return _json_reply(self, 200, {"images": _list_chat_bgs(), "dir": "/images/bg/"})
        if self.path == "/api/actions":
            return _json_reply(self, 200, ACTIONS)
        if self.path == "/api/reference-scripts":
            return _json_reply(self, 200, {"scripts": script_generator.load_reference_scripts()})
        if self.path == "/api/generate/history":
            return _json_reply(self, 200, {"ok": True, "items": script_generator.list_generation_history()})
        if self.path == "/api/skills":
            return _json_reply(self, 200, {
                "ok": True,
                "items": store.list_skills(),
                "kinds": store.rule_kind_options(),
            })
        if self.path.startswith("/api/reference-scripts/recommend"):
            from urllib.parse import parse_qs, urlparse
            _q = (parse_qs(urlparse(self.path).query).get("brief") or [""])[0]
            return _json_reply(self, 200, {"ok": True, "items": store.search_references(_q, 3)})
        _m = re.match(r"^/api/generate/history/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            item = script_generator.get_generation_history(_m.group(1))
            if not item:
                return _json_reply(self, 404, {"ok": False, "msg": "历史记录不存在"})
            return _json_reply(self, 200, {"ok": True, "item": item})
        if self.path == "/api/preferences":
            return _json_reply(self, 200, {"preferences": script_generator.load_preferences_block()})
        if self.path == "/api/feedback":
            _fb = script_generator.load_feedback().get("feedback", [])
            _items = [x for x in _fb if isinstance(x, dict)][-20:]
            _items.reverse()
            return _json_reply(self, 200, {"ok": True, "items": _items, "total": len(_fb)})
        if self.path == "/api/workflow":
            return _json_reply(self, 200, _read_workflow())
        if self.path == "/api/status":
            running = bool(_run_proc) and _run_proc.poll() is None
            return _json_reply(self, 200, {
                "running": running,
                "video": _latest_video(),
                "workflow": os.path.basename(WORKFLOW_PATH),
            })
        if self.path == "/api/llm/config":
            # 不回显密钥，只告诉前端是否已配置 + 当前模型
            settings = script_translator.load_settings()
            return _json_reply(self, 200, {
                "configured": bool((settings.get("deepseek_api_key") or "").strip()),
                "model": settings.get("deepseek_model") or script_translator.DEFAULT_MODEL,
                "base_url": settings.get("deepseek_base_url") or script_translator.DEFAULT_BASE_URL,
            })
        if self.path.startswith("/api/runlog"):
            offset = int(self.path.split("?", 1)[1].split("=")[1]) if "=" in self.path else 0
            return _json_reply(self, 200, _run_log_tail(offset))
        if self.path == "/api/videos":
            files = sorted(os.listdir(VIDEO_DIR), reverse=True) if os.path.isdir(VIDEO_DIR) else []
            vids = [f for f in files if f.lower().endswith((".mp4", ".webm"))][:20]
            return _json_reply(self, 200, {"videos": vids})
        if self.path == "/api/source-videos":
            # 场景编辑器的「源视频库」：public/videos 下可被朋友圈动态引用的视频
            return _json_reply(self, 200, {"videos": _list_source_videos(),
                                           "dir": os.path.relpath(SOURCE_VIDEO_DIR, ROOT).replace(os.sep, "/")})
        if self.path == "/api/screenshot":
            path, err = _capture_screenshot()
            if err:
                return _json_reply(self, 500, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "file": os.path.basename(path)})
        if self.path.startswith("/shot/"):
            # 返回截图 PNG 图片本身
            name = os.path.basename(self.path[len("/shot/"):])
            fp = os.path.join(VIDEO_DIR, name)
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    data = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            return _json_reply(self, 404, {"ok": False, "msg": "文件不存在"})
        if self.path.startswith("/api/live"):
            # 转发到运行子进程/编辑模式的实时画面服务
            return self._proxy_live()
        if self.path.startswith("/api/editstatus"):
            running = bool(_edit_proc) and _edit_proc.poll() is None
            return _json_reply(self, 200, {"ok": True, "running": running})
        if self.path == "/api/openvideos":
            if os.path.isdir(VIDEO_DIR):
                if sys.platform.startswith("win"):
                    os.startfile(VIDEO_DIR)  # noqa: S606
                else:
                    subprocess.Popen(["explorer", VIDEO_DIR] if sys.platform == "win32" else ["xdg-open", VIDEO_DIR])
            return _json_reply(self, 200, {"ok": True})
        if self.path == "/api/tasks" or self.path == "/api/tasks/":
            with _task_lock:
                tasks = [_task_dict_public(_tasks[t]) for t in sorted(_tasks, key=lambda k: _tasks[k].get("created", 0), reverse=True)]
            return _json_reply(self, 200, {"tasks": tasks})
        if self.path == "/api/tasks/status":
            with _task_lock:
                body = _batch_status_locked()
                body["tasks"] = [{k: t.get(k) for k in ("id", "name", "status", "video", "error", "source")}
                                 for t in _tasks.values()]
            return _json_reply(self, 200, body)
        if self.path == "/api/batch/config":
            conf = _read_batch_conf()
            return _json_reply(self, 200, {"max_concurrent": BATCH_MAX_CONCURRENT,
                                           **conf})
        # 任务日志：/api/tasks/<id>/log?offset=N
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)/log$", self.path.split("?", 1)[0])
        if _m:
            tid = _m.group(1)
            offset = 0
            if "?" in self.path:
                try:
                    offset = int(self.path.split("?", 1)[1].split("=")[1])
                except (ValueError, IndexError):
                    offset = 0
            with _task_lock:
                t = _tasks.get(tid)
                log_path = _task_log.get(tid)
                running = bool(t) and t.get("status") == TASK_RUNNING
            return _json_reply(self, 200, _log_tail(log_path, offset) if log_path else
                               {"text": "", "offset": offset, "running": running})
        # 其余按静态文件处理
        return super().do_GET()

    def _proxy_live(self, body: bytes = b""):
        """把实时画面相关请求转发给 127.0.0.1:LIVE_PORT。

        GET  /api/live              -> 截图帧（JPEG）
        GET  /api/live/pick?x=..    -> 拾取元素
        POST /api/live/edit|tap|type|quit -> 修改元素 / 点击 / 打字 / 退出
        """
        sub = self.path[len("/api/live"):]
        # 截图帧仍是 /shot.jpeg，直接转发图片（忽略 ?t= 时间戳查询参数）
        if not sub or sub.split("?", 1)[0] in ("", "/shot.jpeg"):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", LIVE_PORT, timeout=2)
                conn.request("GET", "/shot.jpeg")
                resp = conn.getresponse()
                data = resp.read()
                conn.close()
                if resp.status == 200 and data:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception:                       # noqa: BLE001
                pass
            return _json_reply(self, 503, {"ok": False, "msg": "实时画面暂不可用"})

        # 其余为 JSON API：映射到子进程的 /api/... 路径
        # 注意：前端路径是 /api/live/pick，子进程实际监听 /api/pick，这里要把前缀补回来
        method = self.command
        child_path = "/api" + sub
        try:
            conn = http.client.HTTPConnection("127.0.0.1", LIVE_PORT, timeout=8)
            headers = {"Content-Type": "application/json"} if body else {}
            conn.request(method, child_path, body=body or None, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
        except Exception:                           # noqa: BLE001
            return _json_reply(self, 503, {"ok": False, "msg": "预览进程不可用，请先启动「编辑模式」"})
        try:
            payload = json.loads(data.decode("utf-8") or "{}")
        except ValueError:
            return _json_reply(self, 502, {"ok": False, "msg": "预览进程返回了异常数据"})
        return _json_reply(self, 200, payload)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.path == "/api/workflow":
            try:
                data = json.loads(body.decode("utf-8"))
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            _write_workflow(data)
            return _json_reply(self, 200, {"ok": True})
        if self.path == "/api/scene":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            _write_scene(data)
            return _json_reply(self, 200, {"ok": True, "msg": "场景已保存"})
        if self.path == "/api/peer-presets":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            lib = _read_peer_presets()
            presets = lib["presets"]
            if "presets" in data and isinstance(data["presets"], dict):
                # 整库覆盖（导入/批量编辑）
                lib["_note"] = data.get("_note", lib.get("_note", ""))
                lib["presets"] = data["presets"]
            elif data.get("delete"):
                name = str(data["delete"]).strip()
                if name not in presets:
                    return _json_reply(self, 404, {"ok": False, "msg": "预设不存在：%s" % name})
                presets.pop(name, None)
            else:
                name = str(data.get("preset") or "").strip()
                item = data.get("data")
                if not name:
                    return _json_reply(self, 400, {"ok": False, "msg": "缺少预设名"})
                if not isinstance(item, dict):
                    return _json_reply(self, 400, {"ok": False, "msg": "预设数据必须是 JSON 对象"})
                # 只保留规范字段，避免前端误塞的临时字段（likesText 等）落盘
                presets[name] = {k: item.get(k) for k in PEER_FIELDS if k in item}
            _write_peer_presets(lib)
            return _json_reply(self, 200, {"ok": True, "msg": "预设已保存",
                                           "_note": lib["_note"], "presets": lib["presets"]})
        if self.path == "/api/people/sync":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            people = _sync_people(data)
            return _json_reply(self, 200, {"ok": True, "msg": "已保存到人物库", "people": people})
        if self.path == "/api/people/save":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            people, err = _save_people_item(data)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "msg": "已保存", "people": people})
        if self.path == "/api/people/rename":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            people, err = _rename_people(data)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "msg": "已改名", "people": people})
        if self.path == "/api/people/delete":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            people, err = _delete_people(data)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "msg": "已删除", "people": people})
        if self.path == "/api/scene/to-workflow":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            wf = _build_scene_workflow(data)
            _write_workflow(wf)
            n_peer = sum(1 for s in wf["steps"] if s.get("action") == "编辑对方资料")
            return _json_reply(self, 200, {"ok": True,
                                           "msg": "已生成工作流：编辑主页+朋友圈+我的资料"
                                                  + ("+对方主页×%d" % n_peer if n_peer else ""),
                                           "workflow": wf})
        if self.path == "/api/peer/ai-copy":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            posts, err = _ai_peer_posts(data)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "posts": posts})
        if self.path == "/api/upload-image":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            # category：上传分类（avatar/sticker/emoji/bg/asset），决定落盘子目录；
            # 未指定时保持旧行为（进头像目录），兼容旧前端。
            folder = _CATEGORY_DIRS.get(data.get("category") or "", AVATAR_DIR_NAME)
            path, err = _save_upload_image(data.get("data"), data.get("name"), folder=folder)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "path": path,
                                           "images": _list_images()})
        if self.path == "/api/upload-bg":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            path, err = _save_upload_image(data.get("data"), data.get("name"), folder=CHAT_BG_DIR_NAME)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "path": path,
                                           "images": _list_chat_bgs()})
        if self.path == "/api/upload-video":
            # 两种上传姿势都支持：
            #   1) 原始二进制（推荐，大文件省掉 base64 的 33% 膨胀）：
            #      Content-Type: video/* 或 application/octet-stream，
            #      文件名放在 X-File-Name（前端 encodeURIComponent 编码）
            #   2) JSON dataURL：{"data":"data:video/mp4;base64,...","name":"a.mp4"}
            ctype = (self.headers.get("Content-Type") or "").lower()
            raw_name = self.headers.get("X-File-Name") or ""
            try:
                raw_name = urllib.parse.unquote(raw_name)
            except Exception:                     # noqa: BLE001
                pass
            raw, fname, err = None, raw_name, None
            if "application/json" in ctype:
                try:
                    data = json.loads(body.decode("utf-8") or "{}")
                except ValueError:
                    return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
                fname = data.get("name") or raw_name
                m = re.match(r"data:([^;]+);base64,(.+)", str(data.get("data") or ""), re.S)
                if not m:
                    return _json_reply(self, 400, {"ok": False,
                                                   "msg": "视频数据格式不正确（需要 data:video/...;base64,...）"})
                mime = m.group(1)
                try:
                    raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
                except Exception as exc:           # noqa: BLE001
                    return _json_reply(self, 400, {"ok": False, "msg": "视频解码失败：" + str(exc)})
            else:
                raw, mime = body, ctype
            path, err = _save_upload_video(raw, fname, mime)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "path": path,
                                           "videos": _list_source_videos()})
        if self.path == "/api/gallery/move":
            # 移动分类：把图片真正搬到目标分类的子目录，并同步更新项目里的路径引用
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            new_path, changed, err = _move_image(data.get("path") or "",
                                                 data.get("category") or "")
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "path": new_path,
                                           "changed": changed,
                                           "gallery": _gallery_payload()})
        if self.path == "/api/gallery/rename":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            new_path, err = _rename_image(data.get("path") or "", data.get("name") or "")
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "path": new_path,
                                           "gallery": _gallery_payload()})
        if self.path == "/api/gallery/delete":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            ok, err = _delete_image(data.get("path") or "")
            if not ok:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "gallery": _gallery_payload()})
        if self.path == "/api/gallery/label":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            ok, err = _set_gallery_label(data.get("path") or "", data.get("label") or "")
            if not ok:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "gallery": _gallery_payload()})
        if self.path == "/api/run":
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except ValueError:
                payload = {}
            # 运行前把编辑器里的工作流落盘
            if "workflow" in payload:
                _write_workflow(payload["workflow"])
            ts = payload.get("typing_speed", 30.0)
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                ts = 1.0
            ts = min(40.0, max(0.1, ts))      # 脚本界面打字倍速上限 40
            ok, msg = _start_run(bool(payload.get("headless")), ts,
                                 bool(payload.get("intro")),
                                 bool(payload.get("bgm", True)),
                                 str(payload.get("bgm_path") or ""),
                                 bool(payload.get("use_scene", True)))
            return _json_reply(self, 200 if ok else 409, {"ok": ok, "msg": msg})
        if self.path == "/api/stop":
            return _json_reply(self, 200, {"ok": _stop_run()})
        if self.path == "/api/llm/config":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            patch = {}
            if "api_key" in payload:
                patch["deepseek_api_key"] = str(payload.get("api_key", "")).strip()
            if "model" in payload and str(payload.get("model", "")).strip():
                patch["deepseek_model"] = str(payload.get("model", "")).strip()
            if "base_url" in payload and str(payload.get("base_url", "")).strip():
                patch["deepseek_base_url"] = str(payload.get("base_url", "")).strip()
            script_translator.save_settings(patch)
            return _json_reply(self, 200, {"ok": True, "msg": "配置已保存"})
        if self.path == "/api/translate":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            text = str(payload.get("text") or "")
            if not text.strip():
                return _json_reply(self, 400, {"ok": False, "msg": "剧本内容为空"})
            # 与并发跑批的任务解析共用同一套逻辑（含历史会话块剥离 / AI 转译 / 离线解析 / 人物归一）
            steps, warnings, source = _parse_script_to_steps(text, bool(payload.get("offline")))
            return _json_reply(self, 200, {
                "ok": True,
                "steps": steps,
                "warnings": warnings,
                "source": source,
            })
        if self.path == "/api/scene/script-import":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            text = str(payload.get("text") or "")
            if not text.strip():
                return _json_reply(self, 400, {"ok": False, "msg": "剧本内容为空"})
            if payload.get("offline"):
                # 「不上传剧本给 AI」：强制走确定性逐行解析，不调用大模型
                dialogue, warnings = script_translator._offline_dialogue(text)
                source = "offline"
                if not dialogue:
                    warnings = list(warnings) + [
                        "未能从剧本中提取出对话。请确认每行是「说话人：内容」格式；"
                        "格式有误时可配置 API Key 后用「AI 修正剧本」。"]
            else:
                result = script_translator.build_dialogue(text)
                dialogue, warnings, source = result["dialogue"], result["warnings"], result["source"]
            return _json_reply(self, 200, {
                "ok": True,
                "dialogue": dialogue,
                "warnings": warnings,
                "source": source,
            })
        if self.path == "/api/generate":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            result, err = _generate_script(payload)
            if err:
                return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, result)
        if self.path == "/api/reference-scripts":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            title = str(payload.get("title") or "").strip()
            text = str(payload.get("text") or "").strip()
            if not text:
                return _json_reply(self, 400, {"ok": False, "msg": "参考剧本内容为空"})
            item = script_generator.add_reference_script(title, text, str(payload.get("category") or "").strip())
            return _json_reply(self, 200, {"ok": True, "item": item})
        if self.path == "/api/skills":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            candidates = payload.get("candidates")
            if isinstance(candidates, list):
                src = payload.get("source_feedback")
                if not src and payload.get("history_id"):
                    src = [payload.get("history_id")]
                saved = script_generator.save_skill_candidates(
                    candidates, source_feedback=src,
                    enabled=bool(payload.get("enabled", True)),
                    source_note=str(payload.get("source_note") or "来自评价"))
                return _json_reply(self, 200, {"ok": True, "items": saved})
            item = store.add_skill(
                title=str(payload.get("title") or ""),
                kind=(payload.get("kind") or None),
                value=payload.get("value"),
                skill_type=str(payload.get("type") or "rule"),
                prompt_hint=str(payload.get("prompt_hint") or ""),
                enabled=bool(payload.get("enabled", True)),
                source_feedback=payload.get("source_feedback"),
                source_note=str(payload.get("source_note") or ""))
            return _json_reply(self, 200, {"ok": True, "item": item})
        _m = re.match(r"^/api/skills/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            item = store.update_skill(_m.group(1), payload)
            if not item:
                return _json_reply(self, 404, {"ok": False, "msg": "规则不存在"})
            return _json_reply(self, 200, {"ok": True, "item": item})
        if self.path == "/api/generate/history/clear":
            n = script_generator.clear_generation_history()
            return _json_reply(self, 200, {"ok": True, "cleared": n})
        if self.path == "/api/feedback":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            try:
                score = int(payload.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            score = max(1, min(5, score))
            comment = str(payload.get("comment") or "")
            brief = str(payload.get("brief") or "")
            item = script_generator.add_feedback(
                score, comment, brief, str(payload.get("title") or ""))
            # 评价星级回写到对应历史条目（若有），让历史列表也能看到打分。
            _hid = str(payload.get("history_id") or "").strip()
            if _hid:
                script_generator.set_generation_score(_hid, score)
                # 回填「这次用了哪些参考剧本」的效果分
                try:
                    _hist = script_generator.get_generation_history(_hid) or {}
                    store.rate_references(_hist.get("ref_ids"), score)
                except Exception:  # noqa: BLE001
                    pass
            # 把这条评价拆成规则候选，并【自动生效】：用户写了评价就该立刻影响下次生成，
            # 而不是停在"待确认"面板里（旧版就是没人点确认 → 评价等于没写）。
            settings = script_translator.load_settings()
            _key = (settings.get("deepseek_api_key") or "").strip()
            _model = settings.get("deepseek_model") or script_translator.DEFAULT_MODEL
            _base = settings.get("deepseek_base_url") or script_translator.DEFAULT_BASE_URL
            try:
                candidates = script_generator.extract_skill_candidates(
                    comment, brief=brief,
                    category=str(payload.get("category") or ""),
                    api_key=_key, model=_model, base_url=_base)
            except Exception:  # noqa: BLE001
                candidates = []
            saved = []
            if candidates:
                try:
                    saved = script_generator.save_skill_candidates(
                        candidates, source_feedback=[item.get("id")],
                        enabled=True, source_note="来自评价（自动生效）")
                except Exception:  # noqa: BLE001
                    saved = []
            try:
                enabled_count = len(script_generator.load_enabled_skills())
            except Exception:  # noqa: BLE001
                enabled_count = 0
            return _json_reply(self, 200, {
                "ok": True, "item": item, "candidates": candidates, "saved": saved,
                "enabled_skills": enabled_count, "history_id": _hid})
        if self.path == "/api/preferences":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            settings = script_translator.load_settings()
            api_key = (settings.get("deepseek_api_key") or "").strip()
            model = settings.get("deepseek_model") or script_translator.DEFAULT_MODEL
            base_url = settings.get("deepseek_base_url") or script_translator.DEFAULT_BASE_URL
            pref = script_generator.distill_preferences(api_key, model, base_url)
            return _json_reply(self, 200, {"ok": True, "preferences": pref})
        if self.path == "/api/editmode/start":
            ok, msg = _start_edit()
            return _json_reply(self, 200 if ok else 409, {"ok": ok, "msg": msg})
        if self.path == "/api/editmode/stop":
            return _json_reply(self, 200, {"ok": _stop_edit()})
        if self.path.startswith("/api/live"):
            # 转发给编辑模式/运行进程的实时服务（pick/edit/tap/type 等）
            return self._proxy_live(body)

        # ============ 并发跑批：任务队列 API ============
        if self.path == "/api/tasks":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            task = _default_task()
            task["id"] = _new_task_id()
            task["name"] = str(payload.get("name") or "").strip() or "未命名任务"
            task["script"] = str(payload.get("script") or "")
            if isinstance(payload.get("steps"), list):
                task["steps"] = payload["steps"]
            if isinstance(payload.get("options"), dict):
                task["options"].update(payload["options"])
            task["updated"] = _dt.datetime.now().timestamp()
            with _task_lock:
                _tasks[task["id"]] = task
                _save_tasks_locked()
            _batch_ensure_worker()
            return _json_reply(self, 200, {"ok": True, "task": _task_dict_public(task)})
        if self.path == "/api/tasks/run-selected":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                payload = {}
            ids = payload.get("ids") or []
            if not isinstance(ids, list):
                ids = [ids]
            started = 0
            with _task_lock:
                for tid in ids:
                    t = _tasks.get(str(tid))
                    if not t:
                        continue
                    if t.get("status") in (TASK_RUNNING, TASK_QUEUED):
                        continue
                    if not (t.get("steps") or []):
                        continue
                    t["status"] = TASK_QUEUED
                    t["error"] = None
                    t["updated"] = _dt.datetime.now().timestamp()
                    started += 1
            _batch_ensure_worker()
            _batch_event.set()
            return _json_reply(self, 200, {"ok": True, "started": started})
        if self.path == "/api/tasks/stop":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                payload = {}
            ids = payload.get("ids") or None
            if ids is not None and not isinstance(ids, list):
                ids = [ids]
            with _task_lock:
                targets = [t for t in _tasks.values()
                           if t.get("status") in (TASK_QUEUED, TASK_RUNNING)]
            stopped = 0
            for t in targets:
                tid = t["id"]
                if ids is not None and tid not in ids:
                    continue
                if t.get("status") == TASK_RUNNING:
                    if _stop_task_proc(tid):
                        stopped += 1
                else:  # queued
                    with _task_lock:
                        tt = _tasks.get(tid)
                        if tt:
                            tt["status"] = TASK_STOPPED
                            tt["error"] = "已手动停止。"
                    stopped += 1
            with _task_lock:
                _save_tasks_locked()
            return _json_reply(self, 200, {"ok": True, "stopped": stopped})
        if self.path == "/api/batch/config":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            if "max_concurrent" in payload:
                val, err = _set_batch_max_concurrent(payload.get("max_concurrent"))
                if err:
                    return _json_reply(self, 400, {"ok": False, "msg": err})
            return _json_reply(self, 200, {"ok": True, "max_concurrent": BATCH_MAX_CONCURRENT})
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            tid = _m.group(1)
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            with _task_lock:
                t = _tasks.get(tid)
                if not t:
                    return _json_reply(self, 404, {"ok": False, "msg": "任务不存在"})
                if t.get("status") in (TASK_RUNNING, TASK_QUEUED):
                    return _json_reply(self, 409, {"ok": False, "msg": "任务正在运行，不能修改"})
                if "name" in payload:
                    t["name"] = str(payload["name"] or "").strip() or "未命名任务"
                if "script" in payload:
                    t["script"] = str(payload["script"] or "")
                if isinstance(payload.get("options"), dict):
                    t["options"].update(payload["options"])
                if "steps" in payload:
                    t["steps"] = payload["steps"] if isinstance(payload["steps"], list) else []
                    t["status"] = TASK_IDLE
                    t["error"] = None
                    t["video"] = None
                if isinstance(payload.get("images"), dict):
                    t["images"].update(payload["images"])
                t["updated"] = _dt.datetime.now().timestamp()
                _save_tasks_locked()
                return _json_reply(self, 200, {"ok": True, "task": _task_dict_public(t)})
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)/parse$", self.path)
        if _m:
            tid = _m.group(1)
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return _json_reply(self, 400, {"ok": False, "msg": "JSON 解析失败"})
            with _task_lock:
                t = _tasks.get(tid)
                if not t:
                    return _json_reply(self, 404, {"ok": False, "msg": "任务不存在"})
                if t.get("status") in (TASK_RUNNING, TASK_QUEUED):
                    return _json_reply(self, 409, {"ok": False, "msg": "任务正在运行，不能解析"})
                text = t.get("script") or ""
            if not text.strip():
                return _json_reply(self, 400, {"ok": False, "msg": "剧本内容为空"})
            try:
                steps, warnings, source = _parse_script_to_steps(text, bool(payload.get("offline")))
            except Exception as exc:                    # noqa: BLE001
                return _json_reply(self, 500, {"ok": False, "msg": f"解析失败：{exc}"})
            with _task_lock:
                t = _tasks.get(tid)
                if t:
                    t["steps"] = steps
                    t["warnings"] = warnings
                    t["source"] = source
                    t["status"] = TASK_IDLE
                    t["error"] = None
                    t["video"] = None
                    t["updated"] = _dt.datetime.now().timestamp()
                    _save_tasks_locked()
                    return _json_reply(self, 200, {"ok": True, "task": _task_dict_public(t)})
            return _json_reply(self, 404, {"ok": False, "msg": "任务不存在"})
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)/run$", self.path)
        if _m:
            tid = _m.group(1)
            with _task_lock:
                t = _tasks.get(tid)
                if not t:
                    return _json_reply(self, 404, {"ok": False, "msg": "任务不存在"})
                if t.get("status") in (TASK_RUNNING, TASK_QUEUED):
                    return _json_reply(self, 200, {"ok": True, "status": t["status"], "msg": "任务已在运行/排队"})
                if not (t.get("steps") or []):
                    return _json_reply(self, 400, {"ok": False, "msg": "请先解析剧本"})
                t["status"] = TASK_QUEUED
                t["error"] = None
                t["updated"] = _dt.datetime.now().timestamp()
            _batch_ensure_worker()
            _batch_event.set()
            return _json_reply(self, 200, {"ok": True, "status": TASK_QUEUED})
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)/stop$", self.path)
        if _m:
            tid = _m.group(1)
            ok = _stop_task_proc(tid)
            if not ok:
                with _task_lock:
                    t = _tasks.get(tid)
                    if t and t.get("status") == TASK_QUEUED:
                        t["status"] = TASK_STOPPED
                        t["error"] = "已手动停止。"
                        t["updated"] = _dt.datetime.now().timestamp()
                        _save_tasks_locked()
                        ok = True
            return _json_reply(self, 200, {"ok": ok})
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)/reset$", self.path)
        if _m:
            tid = _m.group(1)
            with _task_lock:
                t = _tasks.get(tid)
                if not t:
                    return _json_reply(self, 404, {"ok": False, "msg": "任务不存在"})
                if t.get("status") in (TASK_RUNNING, TASK_QUEUED):
                    return _json_reply(self, 409, {"ok": False, "msg": "任务正在运行，不能重置"})
                t["status"] = TASK_IDLE
                t["video"] = None
                t["error"] = None
                t["updated"] = _dt.datetime.now().timestamp()
                _save_tasks_locked()
            return _json_reply(self, 200, {"ok": True})

        return _json_reply(self, 404, {"ok": False, "msg": "not found"})

    def do_DELETE(self):                           # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        _m = re.match(r"^/api/tasks/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            tid = _m.group(1)
            with _task_lock:
                t = _tasks.get(tid)
                if not t:
                    return _json_reply(self, 404, {"ok": False, "msg": "任务不存在"})
                if t.get("status") in (TASK_RUNNING, TASK_QUEUED):
                    return _json_reply(self, 409, {"ok": False, "msg": "任务正在运行，请先停止再删除"})
                _tasks.pop(tid, None)
                _task_workflow.pop(tid, None)
                _task_log.pop(tid, None)
                _save_tasks_locked()
            for p in (os.path.join(RUNTIME_DIR, f"{tid}.json"),
                      os.path.join(RUNTIME_DIR, f"{tid}.log")):
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except OSError:
                    pass
            return _json_reply(self, 200, {"ok": True})
        # 删除参考剧本
        _m = re.match(r"^/api/reference-scripts/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            ok = script_generator.delete_reference_script(_m.group(1))
            return _json_reply(self, 200, {"ok": ok, "msg": "已删除" if ok else "未找到该剧本"})
        # 删除规则
        _m = re.match(r"^/api/skills/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            ok = store.delete_skill(_m.group(1))
            return _json_reply(self, 200, {"ok": ok, "msg": "已删除" if ok else "未找到该规则"})
        # 删除某条生成历史
        _m = re.match(r"^/api/generate/history/([A-Za-z0-9_\-]+)$", self.path)
        if _m:
            ok = script_generator.delete_generation_history(_m.group(1))
            return _json_reply(self, 200, {"ok": ok, "msg": "已删除" if ok else "未找到该记录"})
        return _json_reply(self, 404, {"ok": False, "msg": "not found"})

    def log_message(self, fmt, *args):  # noqa: A003
        pass  # 静默访问日志

    def end_headers(self):
        # 禁止浏览器缓存 HTML / JS / CSS / JSON 等所有响应，避免旧版页面被缓存后
        # 出现「界面显示不全、点击无反应」（脚本与 HTML 不匹配或资源缺失）。
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """检测本机端口是否已有服务在监听（用于防止重复启动编辑器）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main():
    parser = argparse.ArgumentParser(description="影刀式工作流编辑器本地服务")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open-scene", action="store_true",
                        help="启动后直接打开独立场景编辑器（/scene），而不是工作流编辑器")
    args = parser.parse_args()

    os.makedirs(EDITOR_DIR, exist_ok=True)
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    if not os.path.isfile(WORKFLOW_PATH):
        _write_workflow({"name": "未命名流程", "steps": []})

    # 并发跑批：恢复任务表并确保批次工人线程在跑（监听任务状态/自动排队启动）
    _load_tasks()
    _batch_ensure_worker()
    conf = _read_batch_conf()
    if conf.get("max_concurrent"):
        _set_batch_max_concurrent(conf["max_concurrent"])

    url = f"http://localhost:{args.port}"
    if _port_in_use(args.port):
        # 端口已被一个仍存活/仍监听的编辑器占用：不再另起服务，避免「Address already in use」
        # 导致本进程崩溃、残留僵尸进程、以及重复启动后页面卡死/不可操作。直接打开浏览器
        # 指向已运行实例即可，符合「一键成功启动」的目标。
        print("=" * 52)
        print("  影刀式微信录屏工作流编辑器")
        print(f"  打开浏览器访问：{url}")
        print("=" * 52)
        print(f"[提示] 端口 {args.port} 已有编辑器在运行，本次不再重复启动，已直接打开浏览器。")
        print("       如需全新实例，请先结束旧的编辑器进程（Ctrl+C 或关闭对应窗口）后再运行。")
        target = url + "/scene" if args.open_scene else url
        threading.Timer(0.5, lambda: webbrowser.open(target)).start()
        return

    handler = lambda *a, **kw: Handler(*a, directory=EDITOR_DIR, **kw)  # noqa: E731
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print("=" * 52)
    print("  影刀式微信录屏工作流编辑器")
    print(f"  打开浏览器访问：{url}")
    print("  Ctrl+C 退出")
    print("=" * 52)
    target = url + "/scene" if args.open_scene else url
    threading.Timer(0.5, lambda: webbrowser.open(target)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _stop_run()
        _stop_edit()
        print("\n已退出。")

if __name__ == "__main__":
    main()