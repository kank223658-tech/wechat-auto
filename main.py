# -*- coding: utf-8 -*-
"""
仿微信界面全自动操作 + 录屏脚本（键盘模拟版）
================================================
基于 Playwright（同步 API）驱动本机运行的 vue-WeChat 前端项目。

两大升级：
1. 真实键盘打字：页面注入手机 QWERTY 键盘覆盖层（enhance/keyboard.js），
   中文按"拼音逐键高亮 → 候选词条 → 点击上屏"流程，英文逐键高亮，
   录出来的视频和手机录屏一致。
2. 工作流模式：支持 workflow.json（影刀式动作序列），也兼容旧 script.txt 文本剧本。

用法：
    python main.py                          # 读取 ./script.txt
    python main.py --workflow work.json     # 读取 JSON 工作流
    python main.py --headless               # 无头模式
"""

import argparse
import datetime as _dt
import faulthandler
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

# Windows 控制台默认 GBK，打印含 ¥ 等字符的 JSON 参数会崩溃，这里强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time
import urllib.parse
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

import sound_engine   # 苹果微信音效引擎（numpy 合成 + winsound 实时播放 + ffmpeg 混流）

try:
    # imageio-ffmpeg 提供内置 ffmpeg，系统没装 ffmpeg 时自动回退使用
    from imageio_ffmpeg import get_ffmpeg_exe as _bundled_ffmpeg
except ImportError:
    _bundled_ffmpeg = None

try:
    from pypinyin import lazy_pinyin
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# 把文本切成「纯中文段」与「非中文段」的正则
_CJK_RUN = re.compile(r"([\u4e00-\u9fff\u3400-\u4dbf]+)|([^\u4e00-\u9fff\u3400-\u4dbf]+)")

# 匹配页面静态资源路径（图片/图标/背景图），用于预热时预载
_ASSET_URL_RE = re.compile(r"/(?:images|fonts)/[A-Za-z0-9_\-./\\]+\.(?:png|jpe?g|gif|webp|svg)")


def _collect_asset_paths(obj):
    """递归提取一个(嵌套)数据结构里所有形如 /images|/fonts/... 的静态资源路径。

    用于运行中切换场景/会话后，把新场景里会渲染的头像/图片一并预载，避免首帧闪现。
    """
    _out = []
    if isinstance(obj, str):
        _out += _ASSET_URL_RE.findall(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _out += _collect_asset_paths(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _out += _collect_asset_paths(v)
    return _out

# ============================================================
# 一、常量区（所有可调参数集中在此）
# ============================================================

BASE_URL = "http://localhost:8080/#/"          # 前端项目地址
DEFAULT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script.txt")
DEFAULT_WORKFLOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow.json")
VIDEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos")
ENHANCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enhance")

# 视口 / 设备（600×1300 固定画布，像素级规格复刻）
VIEWPORT_W, VIEWPORT_H = 600, 1300
DEVICE_SCALE_FACTOR = 3
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1")

# 打字节奏（毫秒）
TYPE_DELAY_MIN_MS = 10          # 单字符最小间隔（打拼音较快）
TYPE_DELAY_MAX_MS = 24          # 单字符最大间隔
# 中文分段长度权重：段长 1~5 按权重随机，大多 1-2 字、偶尔 3-5 字，像真人一段段上屏。
# 元组为 (段长, 权重)；段长指每次「敲完拼音→上屏」的字数。
TYPE_CHUNK_LEN_WEIGHTS = [(1, 0.15), (2, 0.40), (3, 0.20), (4, 0.15), (5, 0.10)]
# 标点 → 手机键盘按键映射（对应「123」数字符号布局里的按键）
PUNCT_KEY = {"，": ",", "。": ".", "！": "!", "？": "?", "；": ";", "：": ":"}
AFTER_TYPING_PAUSE_MS = (160, 320)   # 输完到按下回车之间的停顿区间（原 220~460，提速后更利落）

# 全局倍速：>1 表示更快（缩短视频时长），1 = 正常真人节奏，<1 更慢。
# 可通过命令行 --speed 覆盖（如 --speed 2 把片长几乎减半）。
SPEED = 1.0

# 输出文件名标签：并发跑批时给每条任务的视频前缀一个唯一标识（如任务 id），
# 避免多条任务在同一秒完成时互相覆盖输出文件。留空则保持旧命名（wx_时间戳.mp4）。
OUT_TAG = ""

# 聊天背景：本次运行给聊天页消息区用的背景 URL 路径（如 /images/bg/bg01.jpg）。
# None = 默认深色 #101010（不改变任何现有行为）。
CHAT_BG = None
# 聊天背景自动挑选的随机种子（None = 真随机）。同一 seed 会稳定得到同一张图，
# 便于并发跑批里按任务 id 固定背景（同一条视频复跑背景一致，不同视频背景不同）。
CHAT_BG_SEED = None

# 聊天背景图片扩展名（用于 --chat-bg-dir 自动挑选）
_BG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _list_bg_images(bg_dir: str) -> list:
    """列出背景目录下的图片，返回可被前端引用的 /images/bg/... URL 路径列表（按文件名排序）。"""
    if not bg_dir or not os.path.isdir(bg_dir):
        return []
    names = sorted(f for f in os.listdir(bg_dir) if f.lower().endswith(_BG_EXTS))
    return ["/images/bg/" + f for f in names]


def _pick_chat_bg(path=None, bg_dir=None, mode="random", seed=None):
    """解析并挑出一条视频使用的聊天背景 URL 路径。

    path   : 显式指定（--chat-bg）。支持 /images/... 或相对 vue-WeChat/public 的路径；
             最优先，给了就不再看目录。
    bg_dir : 背景图片所在目录（--chat-bg-dir）。按 mode（random/sequential）+ seed 从中挑一张。
    两者都为空 → 返回 None（默认深色背景，不改现有行为）。
    """
    if path:
        p = str(path or "").strip()
        if not p:
            return None
        if p.startswith("/images/"):
            return p
        # 相对/绝对路径 → 若落在 vue-WeChat/public 内，换算成 /images/... URL
        base = os.path.normpath(os.path.join(FRONTEND_DIR, "public"))
        norm = os.path.normpath(p if os.path.isabs(p) else os.path.join(os.getcwd(), p))
        if os.path.commonpath([base, norm]) == base:
            rel = os.path.relpath(norm, os.path.join(base, "images")).replace(os.sep, "/")
            if not rel.startswith(".."):
                return "/images/" + rel
        print(f"[背景] --chat-bg 不在前端 public 目录内，无法作为背景：{p}")
        return None
    if bg_dir:
        shots = _list_bg_images(bg_dir)
        if not shots:
            print(f"[背景] 目录 {bg_dir} 下没有可用图片，回退默认深色背景。")
            return None
        if mode == "sequential":
            idx = int(seed or 0) % len(shots)
            return shots[idx]
        rng = random.Random(seed) if seed is not None else None
        return (rng.choice(shots) if rng else random.choice(shots))
    return None


def _list_wxemoji_urls() -> list:
    """列出候选条微信小表情图集里的所有静态资源 URL（/images/wxemoji/...）。

    build_wxemoji.py 把「微信图标/小表情」复制到 vue-WeChat/public/images/wxemoji/，
    供 keyboard.js 候选条装饰以真实 <img> 挂入。这里返回全部 URL，用于主流程预热时
    一并预载解码，避免候选条首帧闪图/卡顿。
    """
    d = os.path.join(FRONTEND_DIR, "public", "images", "wxemoji")
    if not os.path.isdir(d):
        return []
    return sorted("/images/wxemoji/" + f
                  for f in os.listdir(d)
                  if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")))

# 打字倍速：>1 时**只**加快打字动画（按键节奏/拼音选字停顿/删除回删），
# 不影响翻页/滚动/等待/看图片等其它动作（那些只受 --speed 影响）。
# 可通过命令行 --typing-speed 覆盖。默认 30：已把打字合并成单次 API 往返（pressType）。
# 说明：30 倍是"速度档位"（按键节奏/停顿按此缩放）；实际吞吐还会受单次 Playwright 往返
# 约 3ms 的下限影响，因此 30 与 40 的单帧观感接近、调高一档更多是心理上的"更快"，
# 调低档位（如 20 以下）才能明显拉出人手的"稍慢连打"节奏。高于 ~10 主要靠
# 减小 KEY_HOLD_MS/TYPE_SPEED 的停顿与更强的按压可见性（keyboard.css 近白按压）来体现。
# 拼音选字（commitByPhrase 前后的停顿）与删除（delete_chars）同样按此倍速缩放，
# 因此调大它就能让「咔咔咔」式连续打字 & 快速退格一起生效。
TYPE_SPEED = 30.0

# 苹果 iPhone + 微信音效（打字哒哒声 / 删除声 / 发送声）
# ------------------------------------------------------------
# 音效挂载在 _kb_press 每次按键/回删/发送上：打字被 TYPE_SPEED 加速后，
# 按键间隔本身变短，音效自然就是加速后的节奏，无需单独做变速。
# 音效来源：type/delete（打字/删除声）必须来自 sounds/ 目录下的真实音效文件
#   （type.wav/delete.wav 或 .mp3，正确苹果音效，旧的 numpy 合成已删除）；
#   发送声 send 同样优先读真实文件，缺文件时才用 numpy 合成近似音效。
# 持续打字声：TYPE_SPEED ≥ CONTINUOUS_TYPE_MIN_SPEED(20) 时，把一段连打合并成一条
#   「持续打字声」——取 sounds/连续打字声.mp4 的原生音轨按敲击时长裁剪（不足循环），
#   不再逐键叠加单个打字音效；低于 20 倍速保留逐键打字声。
SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
ENABLE_AUDIO = True      # 总开关：False 则完全不生成/播放音效（成品视频无声）
LIVE_AUDIO = True        # 运行过程中是否实时播放（演示/录屏时能听到，与成品音轨独立）
AUDIO_VOLUME = 1.0       # 合进成品视频的音轨音量（0~1）

# 背景音乐（成品视频铺底；默认用 苹果音效/背景音乐.mp3，可用命令行 --bgm 指定其它文件）
# ------------------------------------------------------------
# 每次生成都会用 sound_engine.process_bgm 对音乐做一次随机化「去重」处理（参考
# AudioDeDupTool 但大幅精简，听感不变、字节/频谱特征每次不同），随后循环/裁剪到
# 视频时长、按 BGM_VOLUME 音量铺在打字/发送音效之下。--no-bgm 可关闭。
BGM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "苹果音效", "背景音乐.mp3")
BGM_VOLUME = 0.35        # 背景音乐相对音量（低音量铺底，避免盖过打字/发送音效）
ENABLE_BGM = True        # 总开关：False 则成品视频不混背景音乐


# 当前正在录制的 WeChatAuto 实例（供 _pump_wait / _sd_minmax 派发 screencast 帧）
_PUMP_BOT = None
# 脚本累计播放时钟（秒）：_pump_wait 实际等待时累加。旧式「后台消息队列」秒级触发的基准，
# 后台消息队列现已改为「装载即投递」，该时钟仅保留给兼容逻辑使用。
_RUN_CLOCK = 0.0


def _pump_wait(seconds: float):
    """集中等待泵：把等待拆成小片，用 page.wait_for_timeout 等待。

    同步 Playwright 的 CDP 事件（screencast 帧）只在调用 Playwright 方法时派发，
    time.sleep 不会派发。因此所有「需要录进动画」的等待都必须走这里，用分片
    wait_for_timeout 在等待期间同时派发 screencast 帧，避免动画漏帧。
    无录制实例或页面已关闭时退化为普通 time.sleep。
    """
    if seconds <= 0:
        return
    global _RUN_CLOCK
    _RUN_CLOCK += seconds
    bot = _PUMP_BOT
    page = getattr(bot, "page", None) if bot is not None else None
    if page is None or page.is_closed():
        time.sleep(seconds)
        return
    piece = 0.02
    while seconds > 0:
        wait = min(piece, seconds)
        try:
            page.wait_for_timeout(max(1, int(wait * 1000)))
        except Exception:                       # noqa: BLE001
            time.sleep(wait)
        seconds -= wait


def _sd_minmax(lo: float, hi: float):
    """按全局倍速缩放一个毫秒区间，并随机延时后进入等待（SPEED>1 时更快）。

    所有「真人动作」类的随机停顿都走这里，保证 --speed 能整体加速。
    """
    _pump_wait(random.uniform(lo, hi) / 1000.0 / max(0.05, SPEED))


def _type_minmax(lo: float, hi: float):
    """打字专属随机停顿：同时受全局倍速 SPEED 与打字倍速 TYPE_SPEED 影响。

    与 _sd_minmax 的区别：它额外除以 TYPE_SPEED，使「打字动画」能单独加速
    而不影响翻页/滚动/等待等其它动作。TYPE_SPEED=10 即打字部分放 10 倍。
    """
    _pump_wait(random.uniform(lo, hi) / 1000.0 / max(0.05, SPEED)
               / max(0.05, TYPE_SPEED))


def _type_wait(seconds: float):
    """打字专属等待（秒）：按 TYPE_SPEED 缩放，仅用于打字流程内的停顿。"""
    _pump_wait(seconds / max(0.05, TYPE_SPEED))

# 打错回删效果（对英文/数字生效；拼音流程中概率已降低）
TYPO_PROBABILITY = 0.12         # 每个字符触发打错的概率
TYPO_WRONG_CHARS = "jkl你好哈"   # 打错时随机敲入的字符池
TYPO_WRONG_COUNT = 2            # 每次打错敲几个错误字符
TYPO_DELETE_PAUSE_MS = (200, 500)  # 删完后重新输入前的停顿区间

# 键盘按压动画保持时长（毫秒），保证录屏里能看清按键按下。
# 参考真机每次按键约 90~165ms；太短(60ms)在 30fps 下只占 2 帧，观感像鬼影不像按压。
# 注意：该值会再被 TYPE_SPEED 缩放（_kb_press 里 hold_ms/TYPE_SPEED），默认 TYPE_SPEED=30
# 时实际保持即 2.7~4ms（60fps 下不足 1 帧，观感偏快、逐键不明显）。进一步调低会更"鬼影"，
# 所以这一处是"提速与按压可见性"的平衡点；若要再快请优先走 --typing-speed 或 --speed。
KEY_HOLD_MS = (80, 120)

# 按键高亮的"可视下限"（毫秒）：即使高倍速把"键与键的推进节奏"压到几毫秒，
# 每个键高亮仍至少停留这么多毫秒，保证在 60fps 录屏里被约 1.8 帧（≥16.7ms/帧）捕捉到，
# 让人能看到键被按、而不至于动画全消失。这个值只影响高亮的可见时长，
# 不影响打字速度（速度由 KEY_HOLD_MS / TYPE_SPEED 的节奏决定）。调大 → 更明显但连打重叠略多；
# 调小(如 14) → 动画更薄但更"快进"感。
KEY_HOLD_MIN_MS = 30

# 字符浮层气泡的最高打字倍速：TYPE_SPEED ≥ 此值时关闭"每键弹泡"，只保留很轻的按键高亮，
# 避免高倍速下满屏气泡高速跳动、眼花缭乱（配合 keyboard.js 的 setPopupEnabled）。
# 低速(<15)仍保留 iOS 字符浮层，观感更自然。
KEY_POPUP_MAX_TYPING_SPEED = 15.0

# 连续打字声的最低打字倍速：TYPE_SPEED ≥ 此值时，把一段「连续打」合并成一条持续打字声
# （用 sounds/连续打字声.mp4 的原生音轨按敲击时长裁剪），不再逐键叠加单个打字音效。
# 低于此值（低速真人人手感）仍保留逐键打字声。
CONTINUOUS_TYPE_MIN_SPEED = 20.0

# 连续打字声的「断段」间隔：相邻两次打字事件间隔超过此值（秒）即视为一段新连打，
# 上一段先收口、再开新段，避免把跨动作/跨「等待」的长停顿也包进同一条持续声。
# 远大于 20 倍速下 4~6ms 的逐键间隔，仅在对方插话(约 0.26~0.44s)或动作切换时断开。
CONTINUOUS_TYPE_MAX_GAP = 0.25

VIEW_IMAGE_HOLD_DEFAULT = 0.3 # 点开图片放大后默认停留查看时长（秒）。原来为随机 0.9~1.6s，
# 与用户显式设定的短停留（如 0.1s）冲突，故改为固定默认 0.3s，显式设定时严格按设定值停。
# 图片「点开放大」的默认放大倍率：>1 放大、1=保持原大。默认 1.6（比旧版 1.7~2.8 温和，
# 避免「放得太大」）。每张图可在编辑器里单独覆盖（放大倍率），这里只作全局兜底默认。
IMAGE_ZOOM_DEFAULT = 1.6

# 导航 / 操作节奏（秒）
WELCOME_WAIT = 1.2              # 首页欢迎图停留时间
NAV_WAIT = 0.8                  # 页面切换后的自然等待
BACK_HOME_HOLD_DEFAULT = 0.3    # 「返回主页」默认停留在主页等待时长（秒），可被步骤「停留」覆盖
CHAT_ENTER_WAIT = 0.35          # 进入聊天转场（滑入动画 .34s）后的自然等待，紧贴动画结束即可继续
SEND_AFTER_WAIT = 0.4           # 发送消息后的短暂停顿（我方发送还会再按打字倍速缩放，高倍速下几乎无缝接下一段）
TYPING_BANNER_PREFIX = "对方正在输入"
KB_OPEN_WAIT = 0.26             # 键盘弹出动画时长（CSS 过渡 .22s + 少量余量；到位即开始打字，不过度干等）

PAGE_TIMEOUT_MS = 10_000        # 元素查找默认超时
STEP_WATCHDOG_SEC = 90          # 单条指令看门狗：超时导出堆栈并终止，防止永久挂起
FFMPEG_VIDEO_TIMEOUT = 1800     # 视频合成 ffmpeg 超时（秒）：编码阶段不在看门狗内，
                                # 必须给 ffmpeg 单独兜底，防止 ffmpeg 卡死导致永久挂起

# MP4 转码（输出画质 / 流畅度）
# ------------------------------------------------------------
# 经验修正：Playwright 的录屏固定约 25fps，且「按 CSS 像素」抓帧（约 368x800）。
# 旧版用 record_video_size=1170x2532 想要 3x 高清，结果只是把画布拉大、内容仍只占
# 左上角 1/3，其余全是大片灰边，观感「错乱且不清晰」。正确做法：
#   1) 录制时不设 record_video_size，让内容全屏铺满（无灰边）；
#   2) 转码时用 lanczos 把全屏内容放大到 1170x2532，并叠加轻微锐化，让文字够锐；
#   3) 不要用运动补偿插值(mci)：它在动画/过渡处会错误合成「整屏放大」的坏帧，
#      观感就是「一两帧被放大很大」（闪烁）。无插值最稳、最锐。
# ------------------------------------------------------------
VIDEO_CRF = 15                  # 越小越清晰（UI 文字要锐，用 15）
VIDEO_PRESET = "medium"         # 编码速度/质量权衡（veryfast 快但糊，slow 最清晰）
TRIM_HEAD_SEC = 5.5             # 跳过视频开头加载期（欢迎页/白屏 / vue 旧种子 / 列表停留），设为 0 关闭

# ============================================================
# 逐帧 60fps 采集（CDP screencast 真 60fps）
# ------------------------------------------------------------
# 原理：同步 Playwright 的 CDP 事件只在调用 Playwright 方法时派发。因此这里
# 放弃慢速 page.screenshot() 采样（实测轻页 30fps、真实页约 8.7fps），改用
# Page.startScreencast 让浏览器每个合成帧主动推送（实测 headless/headed 均真 60fps），
# 并用集中泵 _pump_wait 把脚本所有等待改成 page.wait_for_timeout 以派发帧。
# 收尾按各帧真实交换时间戳合成 VFR MP4，保留真实帧时长，消除 CFR 网格重排的卡顿。
# 旧版 "screenshot" 截图采样 + 原生 record_video_dir(25fps) 方案已删除，固定走 screencast。
# ============================================================
RECORD_MODE = "screencast"      # 固定为 CDP 推帧真 60fps（旧 "screenshot" 方案已删除）。
FRAME_CAPTURE_ENABLED = True    # True=采集并合成 VFR 视频；False=不做逐帧合成
FRAME_CAPTURE_FPS = 60          # 输出时间基点：每帧按其真实停留时长复制到 1/FRAME_CAPTURE_FPS 整数倍
                                # （60fps），从而贴合真实帧交换节奏
# screencast 按 CSS 像素输出约 600x1300 的帧（不受 device_scale_factor 放大），体积可控。
FRAME_JPEG_QUALITY = 92         # screencast 推帧画质：UI 文字要锐，92 进一步减少文字边缘的 JPEG 块状噪点
# 转场「子页收回/推入」时，.sub-page(translate3d(±100%)) 与 .outter.hideLeft(translate3d(-30%)) 会把
# 合成器表面撑宽到约 1380px。screencast 的 maxWidth 若只给 600，会把这块更宽的表面整幅下采样，
# 导致内容被压到左 40%、右侧大片黑边（即「缩左+黑边」闪帧）。这里把采集上限放宽，让超宽帧
# 以原始尺寸完整推入，再在合成阶段 crop=600:1300:0:0 裁回手机屏（消除下采样闪帧）。
FRAME_SURFACE_MAX_W = 2600      # screencast 采集宽上限：容纳转场时被 transform 撑宽的表面
FRAME_SURFACE_MAX_H = 3900      # screencast 采集高上限：容纳「被撑大」的合成器表面（高度超过视口 1300）
# 60fps 合成输出尺寸：
#   0          = 直接输出采集帧的原始尺寸（600x1300，体积最小、合成最快、最适合手机屏）
#   正数（如 1080）= 把采集帧按比例缩放到该宽度（更贴近主流手机屏，但会略增合成耗时）
# 说明：screencast 源真实上限就是 600x1300，这里放大属「lanczos 插值 + unsharp 重锐化」，
#       不新增真实细节，但会输出贴近手机原生像素网格 1080x2340，手机端播放不再靠播放器粗缩放放大，
#       对「纯 UI + 文字」类内容观感提升明显。
FRAME_OUT_W = 1080              # 0=不高清放大，直接输出采集分辨率；>0 则缩放目标宽度（默认 1080x2340）

# 长间隔视觉过渡（消除偶发断帧造成的成片「硬跳」）
# ------------------------------------------------------------
# 实测采集链路本身约 60fps 稳定，但录屏偶有「~0.5s 无帧断流」（JS 侧零长任务、
# 帧尺寸正常，指向合成器被系统级节流的一次性停顿，非脚本/渲染瓶颈）。若断帧期间
# 画面在动，成片会（按真实时间戳）把前一帧硬停 0.2s+ 再跳到后一帧，观感即"卡一下"。
# 这里在合成阶段对这类长间隔做有界处理：间隔足够长（>=MIN_FRAMES×1/60s）且前后两帧
# 画面差异明显时，把「整段硬停留」改为「短暂停留 + 若干淡入淡出混合帧」，观感从
# 「硬跳」变成自然的「转场」。关键不变量：每帧输出复制总数仍为 round(dur*fps)，
# 混合帧只替换本帧停留份额，后续帧的绝对输出位置不变 —— 与 _mux_audio 的量化
# 时间轴完全一致，音画不错位；混合只发生在差异明显的长间隔，静止等待不受影响。
GAP_BLEND_MIN_FRAMES = 12       # 间隔 >= 12 帧（约 0.2s）才考虑过渡
GAP_BLEND_HOLD_FRAC = 0.30      # 过渡中「前一帧完整停留」占该间隔的比例（其余为混合帧）
GAP_BLEND_DIFF_EPS = 0.018      # 下采样灰度归一化差异阈值：低于它视为静止等待（不混合）
# 帧缓存：[ (timestamp_seconds, jpeg_bytes), ... ]   timestamp=CDP 真实帧交换时刻
_FRAMES = []
_FRAME_LOCK = threading.Lock()

# 前端服务自动启动
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat")
PORT = 8080                     # 前端 dev server 端口
# 项目自带便携版 Node.js（系统没装 node 时使用；为空则直接用 PATH 里的 npm）
BUNDLED_NODE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tools", "node-v20.19.4-win-x64")
AUTO_START_FRONTEND = True      # 检测到 8080 未监听时自动启动前端
FRONTEND_START_TIMEOUT_SEC = 120  # 等待前端启动成功的最长时间

# ============================================================
# 实时画面服务（编辑器页面轮询截图，看到手机实况）
# ============================================================

# 保存当前自动化实例的引用：后台服务线程只读取主线程写好的截图缓存
_LIVE_BOT = {"bot": None}
_LIVE_LOCK = threading.Lock()     # 保护实时画面帧缓存 / 命令队列
_LIVE_FRAME = {"ts": 0.0, "data": None}   # 主线程定期写入的 JPEG 帧缓存（节流 0.4s）

# 元素编辑命令队列：HTTP 线程只入队，主线程（Playwright 安全）执行
_LIVE_QUEUE = []                       # [(cid, cmd, args)]
_LIVE_QUEUE_EVENT = threading.Event()  # 队列非空事件
_LIVE_RESULTS = {}                     # cid -> 结果 dict
_LIVE_NEXT_ID = [0]                    # 命令自增 id
_STOP_EDIT = threading.Event()         # 编辑模式退出信号


def _live_enqueue(cmd: str, args: dict) -> int:
    """把一条编辑器命令放入队列，返回命令 id（HTTP 线程调用，安全）。"""
    with _LIVE_LOCK:
        _LIVE_NEXT_ID[0] += 1
        cid = _LIVE_NEXT_ID[0]
        _LIVE_QUEUE.append((cid, cmd, args))
        _LIVE_QUEUE_EVENT.set()
    return cid


def _live_wait_result(cid: int, timeout: float = 8.0) -> dict:
    """等待主线程处理完命令并返回结果（HTTP 线程调用，安全）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _LIVE_LOCK:
            if cid in _LIVE_RESULTS:
                return _LIVE_RESULTS.pop(cid)
        time.sleep(0.05)
    return {"ok": False, "msg": "处理超时，预览进程可能已退出"}


def _live_dispatch(cmd: str, args: dict) -> dict:
    """入口：检查预览进程存活后入队并等待结果。"""
    bot = _LIVE_BOT.get("bot")
    if bot is None or not getattr(bot, "page_open", False):
        return {"ok": False, "msg": "预览进程未运行，请先点击顶部「编辑模式」"}
    return _live_wait_result(_live_enqueue(cmd, args))


class _LivePreviewHandler(BaseHTTPRequestHandler):
    """实时画面 HTTP 服务：
       GET  /shot.jpeg             -> 返回主线程抓好的最后一帧 JPEG
       GET  /api/pick?x=..&y=..    -> 拾取该坐标下的可编辑元素
       POST /api/edit              -> 修改某个元素（文字/头像/背景等）
       POST /api/tap               -> 把点击转发到真实页面（编辑模式导航用）
       POST /api/type              -> 向当前聚焦输入框打字
       POST /api/quit              -> 让编辑模式进程退出

    注意：这里只读取缓存 / 入队命令，绝不在后台线程里调用 Playwright，
    避免 sync API 跨线程访问引发 greenlet 错误。
    """

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                       # noqa: N802
        if self.path.startswith("/shot"):
            with _LIVE_LOCK:
                data = _LIVE_FRAME.get("data")
            if not data:
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/api/pick"):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                x = float(query.get("x", ["0"])[0])
                y = float(query.get("y", ["0"])[0])
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "msg": "坐标参数错误"})
            return self._json(200, _live_dispatch("pick", {"x": x, "y": y}))
        return self._json(404, {"ok": False, "msg": "not found"})

    def do_POST(self):                      # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        path = self.path.split("?", 1)[0]
        if path == "/api/edit":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return self._json(400, {"ok": False, "msg": "JSON 解析失败"})
            if not payload.get("id") or not payload.get("prop"):
                return self._json(400, {"ok": False, "msg": "缺少 id 或 prop"})
            return self._json(200, _live_dispatch("edit", payload))
        if path == "/api/tap":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                payload["x"] = float(payload.get("x", 0))
                payload["y"] = float(payload.get("y", 0))
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "msg": "坐标参数错误"})
            return self._json(200, _live_dispatch("tap", payload))
        if path == "/api/type":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return self._json(400, {"ok": False, "msg": "JSON 解析失败"})
            return self._json(200, _live_dispatch("type", payload))
        if path == "/api/pick":
            # 防御性支持 POST 拾取（编辑器默认走 GET /api/pick，但代理可能转发 POST）
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                x = float(payload.get("x", 0))
                y = float(payload.get("y", 0))
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "msg": "坐标参数错误"})
            return self._json(200, _live_dispatch("pick", {"x": x, "y": y}))
        if path == "/api/quit":
            _STOP_EDIT.set()
            return self._json(200, {"ok": True})
        return self._json(404, {"ok": False, "msg": "not found"})

    def log_message(self, fmt, *args):      # noqa: A003
        pass  # 静默截图服务日志


def start_live_preview(port: int):
    """启动实时画面服务（后台守护线程）。port<=0 表示不启动。"""
    if not port:
        return None
    server = ThreadingHTTPServer(("127.0.0.1", port), _LivePreviewHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[实时画面] 已开启：http://127.0.0.1:{port}/shot.jpeg")
    return server


def _start_live_guarded(port: int):
    """启动实时画面服务，端口被占时打印友好提示而不是让子进程直接崩溃。"""
    if not port:
        return None
    try:
        return start_live_preview(port)
    except OSError as exc:
        print(f"[警告] 实时画面服务端口 {port} 启动失败：{exc}")
        print("      请确认没有残留的 main.py 进程占用该端口，或先停止旧的运行/编辑进程。")
        return None

# ============================================================
# 二、拼音候选词
# ============================================================

# 常用汉字池，用于生成"看起来真实"的同音/干扰候选字
_COMMON_CHARS = ("的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主"
                 "发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里"
                 "如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些"
                 "然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或"
                 "但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展"
                 "五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将"
                 "组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门"
                 "即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改"
                 "清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类"
                 "八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究"
                 "观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响"
                 "约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候毛亲快效斯院"
                 "查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严龙飞")


@lru_cache(maxsize=None)
def _pinyin_of(char: str) -> str:
    """单个汉字 -> 拼音（无音调）。非汉字返回空串。"""
    if not _HAS_PYPINYIN:
        return ""
    try:
        if '\u4e00' <= char <= '\u9fff' or '\u3400' <= char <= '\u4dbf':
            return lazy_pinyin(char)[0]
    except Exception:                                   # noqa: BLE001
        pass
    return ""


@lru_cache(maxsize=None)
def _candidates_for(char: str):
    """生成候选字列表：目标字排第一，其余为同音字 + 兜底常用字。"""
    py = _pinyin_of(char)
    if not py:
        return [char]
    same = [c for c in _COMMON_CHARS if c != char and _pinyin_of(c) == py][:3]
    if len(same) < 3:
        fill = [c for c in _COMMON_CHARS if c != char and c not in same][:3 - len(same)]
        same += fill
    return [char] + same


# ============================================================
# 三、注入式脚本（键盘 / 配置 / 朋友圈 / 页面增强）
# ============================================================

def _read_enhance(name: str) -> str:
    """读取 enhance/ 目录下的注入脚本文件"""
    path = os.path.join(ENHANCE_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# 页面增强：回车发送 / 对方消息 / 正在输入 / 评论条（内容来自输入框真实输入）
ENHANCE_JS = r"""
(() => {
    if (window.__wxEnhanced) return;
    window.__wxEnhanced = true;

    const css = document.createElement('style');
    css.textContent = `
      .dialogue-section .row.self { float: right; }
      .dialogue-section .row.self .header { float: right; }
      .dialogue-section .row.self .text {
        float: right; margin-left: 0; margin-right: 10px;
        background: #98e165;
      }
      .dialogue-section .row.self .text:before {
        left: auto; right: -12px;
        border-right-color: transparent; border-left-color: #98e165;
      }
      .dialogue-section .row { overflow: hidden; }
      .peer-typing {
        display:inline-block; margin-left:6px; font-size:12px; color:#7d7e83;
        animation: peerBlink 1.2s infinite;
      }
      @keyframes peerBlink { 0%,100%{opacity:.35} 50%{opacity:1} }
      /* 评论输入条：位置/过渡与 iphone_frame 的键盘同步节奏(.32s iOS)对齐，
         不再用旧的 bottom:0/.28s 覆盖外层皮肤。进出动画用 .in/.out 类：
         打开时从底部滑入淡入（与键盘弹出同节奏），关闭时滑回并淡出后移除。 */
      #commentBar {
        position: fixed; left:0; right:0; bottom:34px; height:52px;
        background:#fdfdfd; border-top:1px solid #b7b7b7; z-index:9999;
        display:flex; align-items:center; padding:0 10px;
        transform: translateY(115%);
        opacity: 0;
        visibility: hidden;
        transition: bottom .32s cubic-bezier(.32,.72,0,1),
                    transform .32s cubic-bezier(.32,.72,0,1),
                    opacity .24s ease, visibility .32s ease;
      }
      #commentBar.in { transform: translateY(0); opacity: 1; visibility: visible; }
      #commentBar.out { transform: translateY(115%); opacity: 0; visibility: hidden; }
      #commentBar input {
        flex:1; height:34px; border-radius:6px; border:1px solid #7d7e83;
        padding:0 10px; font-size:15px;
      }
      .comment-entry { font-size:13px; color:#576b95; margin-top:6px; }
      .comment-entry b { color:#576b95; font-weight:normal; }
      /* 评论条目入场：轻微上滑 + 淡入，与真机朋友圈评论出现一致 */
      @keyframes commentPop {
        from { transform: translateY(9px); opacity: 0; }
        to   { transform: translateY(0); opacity: 1; }
      }
      .comment-entry.comment-pop { animation: commentPop .26s cubic-bezier(.25,.75,.3,1) both; }
    `;
    document.head.appendChild(css);

    const scrollBottom = () => {
      const sec = document.querySelector('.dialogue-section');
      /* 统一走 chat_extra.js 挂载的 __wxSmoothScrollBottom：
         未满(不可滚动)瞬间出现、已满极快平滑滚到底、连续多条防抖合并。
         无该函数(注入异常)时退回直接贴底。不再 window.scrollTo——页面级
         滚动由 __wxScrollGuard 钳回，这里滚 document 只会引发跳动。 */
      if (window.__wxSmoothScrollBottom) window.__wxSmoothScrollBottom(sec);
      else if (sec) sec.scrollTop = sec.scrollHeight;
    };

    const meAvatar = () => (window.__wxConfig && window.__wxConfig.get().me.avatar) || '/images/header/header01.png';
    const meName = () => (window.__wxConfig && window.__wxConfig.get().me.name) || '阿荡';

    /* 持久化：把新上屏的消息也写进 vuex store 当前会话的 .msg，保证切走再回来不丢失。
       dialogue.vue 用 v-for 渲染 store 里当前会话的 .msg，因此这里只写 store、
       不再手动 append DOM 气泡——否则同一条消息会被渲染两次（连续两句）。
       Vue 渲染是异步的，写完后在 nextTick 里滚动到底部。 */
    const pushMsgToStore = (text, isMe, peerAvatar, timeSpec) => {
      try {
        const vm = document.getElementById('app') && document.getElementById('app').__vue__;
        if (!vm || !vm.$store || !vm.$route) return false;
        const list = vm.$store.state.msgList.baseMsg;
        const mid = vm.$route.query.mid;
        const cur = (list || []).find(it => String(it.mid) === String(mid));
        if (!cur || !Array.isArray(cur.msg)) return false;
        const name = isMe ? meName() : ((cur.user && cur.user[0] && cur.user[0].nickname) || '对方');
        const headerUrl = isMe ? meAvatar() : (peerAvatar || (window.__wxConfig && window.__wxConfig.get().me.peerAvatar) || '/images/header/yehua.jpg');
        /* 记录推送前消息区已有的气泡行，用于在渲染后定位「刚上屏」的那一行。 */
        const _sec = document.querySelector('.dialogue-section');
        const _before = new Set(_sec ? Array.from(_sec.querySelectorAll('.row')) : []);
        const entry = { text, name, headerUrl };
        /* 时间标注（时间分隔条占位）：把标注时刻换算成 date + timeText + forceTime，
           让 dialogue.vue 的 showTime 在「标注了时间」这条消息前强制显示一条分隔条。 */
        if (timeSpec) {
          const parsed = (window.__wxConfig && window.__wxConfig.parseTimeSpec)
            ? window.__wxConfig.parseTimeSpec(timeSpec) : null;
          if (parsed) {
            entry.date = parsed.ts;
            entry.timeText = parsed.text;
          } else {
            entry.date = Date.now();
            entry.timeText = timeSpec;
          }
          entry.forceTime = true;
        }
        cur.msg.push(entry);
        if (vm.$forceUpdate) vm.$forceUpdate();
        if (vm.$nextTick) vm.$nextTick(() => {
          /* 我方发送：气泡已由 Vue 渲染进 DOM —— 记录「气泡真正出现」的墙钟时刻
             （ms），供 main.py 把发送声锚定到这里，避免发送声早于气泡。 */
          if (isMe) window.__wxLastSelfBubbleWall = Date.now();
          /* 修复「图片/表情贴纸卡在底部、不随新消息上滑」：
             appendRow 直插 DOM 的气泡（图片/表情/语音/转账/转发）不进 store，
             而 Vue 渲染 store 新消息时会把新行插到「最后一条 Vue 行」之后，
             却落在 DOM 直插气泡之前 —— 于是 DOM 直插气泡被永远压在底部。
             这里把刚上屏的这条 store 消息行移到消息区最末（回到所有既有气泡之下），
             使其与直插气泡的先后顺序符合真实时序（最新消息在底部、旧的被顶上去）。 */
          const sec = document.querySelector('.dialogue-section');
          if (sec) {
            const rows = Array.from(sec.querySelectorAll('.row'));
            let fresh = null;
            for (let i = rows.length - 1; i >= 0; i--) {
              if (!_before.has(rows[i])) { fresh = rows[i]; break; }
            }
            if (fresh) sec.appendChild(fresh);   // 未满/无直插气泡时为原地 no-op，不影响既有行为
          }
          scrollBottom();
        });
        return true;
      } catch (e) { return false; }
    };

    const sendSelfFromInput = (input) => {
      const text = (input.value || '').trim();
      if (!text) return false;
      /* 时间标注：human_type 发送前把标注时刻放进 __wxNextSendTime 临时变量。 */
      const timeSpec = window.__wxNextSendTime || '';
      window.__wxNextSendTime = '';
      input.value = '';
      /* 发送后立刻触发增高控制器重算（否则 input.value='' 不派发 input 事件，
         --chat-grow 不归零，输入框会一直停留在长高态）。 */
      input.dispatchEvent(new Event('input', { bubbles: true }));
      return pushMsgToStore(text, true, undefined, timeSpec);   /* 只写 store，由 Vue 渲染气泡，避免重复 */
    };

    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.keyCode !== 13) return;
      const t = e.target;
      if (!t) return;
      if (t.classList && t.classList.contains('chat-txt')) {
        if (sendSelfFromInput(t)) {
          e.preventDefault();
          /* 我方气泡已推入 store，Vue 渲染在 nextTick 里完成；
             这里先记一个近似锚点，真正的渲染完成时刻由 pushMsgToStore 的
             nextTick 回调覆盖（见上方 __wxLastSelfBubbleWall）。 */
          window.__wxBubbleShownAt = Date.now();
        }
      } else if (t.id === 'commentInput') {
        const text = (t.value || '').trim();
        if (text) window.__wxSubmitComment(text);
        t.value = '';
        e.preventDefault();
      }
    }, true);

    window.__wxPeerMsg = (text, avatar, timeSpec) => {
      const pa = avatar || (window.__wxConfig && window.__wxConfig.get().me.peerAvatar) || '/images/header/yehua.jpg';
      return pushMsgToStore(text, false, pa, timeSpec);   /* 只写 store，由 Vue 渲染气泡，避免重复 */
    };

    /* ---- 后台对方消息：给「未打开的会话」投递一条对方消息，并刷新主页预览/角标 ----
       匹配会话：好友按 user[0].remark/nickname，群按 group_name。若目标恰是当前打开的
       会话，退化为 __wxPeerMsg 直接上屏。投递后：该项 read=false、newMsgCount++，
       可置顶(真机来消息会置顶)，并重算 store.state.newMsgCount 刷新「微信 (N)」与底部角标。 */
    const resolveSessionByName = (list, name) => {
      const n = String(name || '').trim();
      if (!n) return null;
      return (list || []).find(it => {
        if (it.type === 'group') return String(it.group_name || '') === n;
        const u = it.user && it.user[0];
        return u && (String(u.remark || '') === n || String(u.nickname || '') === n);
      }) || (list || []).find(it => {
        const u = it.user && it.user[0];
        return u && (String(u.remark || '') === n || String(u.nickname || '') === n
                     || String(it.group_name || '') === n);
      }) || null;
    };
    const moveSessionToTop = (list, item) => {
      const i = (list || []).indexOf(item);
      if (i > 0) {
        list.splice(i, 1);
        list.unshift(item);
      }
    };
    const recomputeNewMsgCount = (vm) => {
      let total = 0;
      (vm.$store.state.msgList.baseMsg || []).forEach(it => {
        if (it.read === false && !it.quiet) total += (Number(it.newMsgCount) || 1);
      });
      vm.$store.state.newMsgCount = total;
    };
    /* 构造一条后台消息 entry：o.image 为真时是图片气泡（主页预览/气泡统一显示 [图片]），
       否则是文本气泡；o.time（如 "18:22"）给该消息前加时间分隔条。 */
    const _bgMsgEntry = (o, sender, headerUrl, text) => {
      const entry = { name: sender, headerUrl, date: Date.now() };
      if (o.image && String(o.image).trim()) {
        entry.text = '[图片]';
        entry.image = o.image;
      } else {
        entry.text = text;
      }
      if (o.time) {
        const parsed = (window.__wxConfig && window.__wxConfig.parseTimeSpec)
          ? window.__wxConfig.parseTimeSpec(o.time) : null;
        if (parsed) {
          entry.date = parsed.ts;
          entry.timeText = parsed.text;
        } else {
          entry.timeText = o.time;
        }
        entry.forceTime = true;
      }
      return entry;
    };
    window.__wxPeerMsgBg = (contactName, text, opts) => {
      const o = opts || {};
      const vm = document.getElementById('app') && document.getElementById('app').__vue__;
      if (!vm || !vm.$store) return false;
      const list = vm.$store.state.msgList.baseMsg || [];
      const item = resolveSessionByName(list, contactName);
      if (!item) return false;
      const mid = vm.$route && vm.$route.query && vm.$route.query.mid;
      const curByMid = (list || []).find(it => String(it.mid) === String(mid));
      const sender = item.type === 'group'
        ? (o.sender || item.group_name) : (item.user && item.user[0] && (item.user[0].remark || item.user[0].nickname)) || '对方';
      const headerUrl = o.avatar || (item.type === 'group'
        ? '/images/header/yehua.jpg' : (item.user && item.user[0] && item.user[0].headerUrl) || '/images/header/yehua.jpg');
      const hasImage = !!(o.image && String(o.image).trim());
      if (curByMid && item === curByMid) {
        /* 正在看 TA → 走即时上屏（气泡动画） */
        if (hasImage) {
          /* 图片后台消息在「正在看的会话」上屏：直接入 store，Vue 渲染图片气泡 */
          curByMid.msg.push(_bgMsgEntry(o, sender, headerUrl, text));
          item.read = false;
          item.newMsgCount = (Number(item.newMsgCount) || 0) + 1;
          recomputeNewMsgCount(vm);
          if (vm.$forceUpdate) vm.$forceUpdate();
          if (vm.$nextTick) vm.$nextTick(() => {
            const sec = document.querySelector('.dialogue-section');
            if (sec) sec.scrollTop = sec.scrollHeight;
          });
          if (window.__wxConfig && window.__wxConfig.apply) window.__wxConfig.apply();
          return true;
        }
        return pushMsgToStore(text, false, headerUrl, o.time);
      }
      const entry = _bgMsgEntry(o, sender, headerUrl, text);
      item.msg.push(entry);
      item.read = false;
      item.newMsgCount = (Number(item.newMsgCount) || 0) + 1;
      if (o.moveTop !== false) moveSessionToTop(list, item);
      recomputeNewMsgCount(vm);
      if (vm.$forceUpdate) vm.$forceUpdate();
      if (window.__wxConfig && window.__wxConfig.apply) window.__wxConfig.apply();   // 刷新「微信 (N)」
      return true;
    };

    window.__wxTypingOn = () => {
      const center = document.querySelector('#wx-header .center');
      if (!center || center.querySelector('.peer-typing')) return;
      const tip = document.createElement('span');
      tip.className = 'peer-typing';
      tip.textContent = '对方正在输入...';
      center.appendChild(tip);
    };
    window.__wxTypingOff = () => {
      const tip = document.querySelector('.peer-typing');
      if (tip) tip.remove();
    };

    let commentTargetPost = null;
    window.__wxOpenCommentBox = () => {
      closeCommentBar();
      const posts = document.querySelectorAll('.moments__post');
      if (!posts.length) return false;
      commentTargetPost = posts[posts.length - 1];
      const bar = document.createElement('div');
      bar.id = 'commentBar';
      bar.innerHTML = '<input id="commentInput" type="text" placeholder="评论">';
      document.body.appendChild(bar);
      // 下一帧加 .in，触发从底部滑入+淡入（与键盘弹出同节奏）
      requestAnimationFrame(() => { requestAnimationFrame(() => bar.classList.add('in')); });
      return true;
    };
    const closeCommentBar = () => {
      const old = document.getElementById('commentBar');
      if (!old) return;
      // 先切到 .out 滑出淡出，等动画结束后再移除 DOM，避免瞬时消失
      if (!old.classList.contains('out')) {
        old.classList.remove('in');
        old.classList.add('out');
      }
      setTimeout(() => { if (old.parentNode) old.parentNode.removeChild(old); }, 360);
    };
    window.__wxSubmitComment = (text) => {
      if (!commentTargetPost) return;
      const bd = commentTargetPost.querySelector('.weui-cell__bd') || commentTargetPost;
      const p = document.createElement('p');
      p.className = 'comment-entry comment-pop';
      p.innerHTML = '<b>' + meName() + '</b>：';
      p.appendChild(document.createTextNode(text));
      bd.appendChild(p);
      commentTargetPost = null;
      closeCommentBar();
    };

    /* 给最后一条朋友圈点赞：显示操作菜单 + 追加我的昵称 + 按钮高亮 */
    window.__wxLikePost = () => {
      const posts = document.querySelectorAll('.moments__post');
      if (!posts.length) return false;
      const post = posts[posts.length - 1];
      const menu = post.querySelector('.action-menu, #actionMenu');
      if (menu) {
        menu.classList.add('open');
        // 模拟真机：点完「赞」后菜单自动收起（配合 open 弹出动画）
        setTimeout(() => menu.classList.remove('open'), 520);
      }
      const like = post.querySelector('.liketext');
      const nm = meName();
      if (like && !like.textContent.includes(nm)) {
        const s = document.createElement('span');
        s.className = 'nickname';
        s.textContent = (like.textContent.trim() ? ',' : '') + nm;
        like.appendChild(s);
      }
      const btn = post.querySelector('.btn-like, #btnLike');
      if (btn) btn.classList.add('liked');
      return true;
    };
})();
"""

# ============================================================
# 真 Rime WASM 引擎（雾凇）引导注入
# ============================================================
# 手动部署雾凇：仅依赖 @libreservice/my-worker（自包含），动态 import 即可，无需 import map/micro-plum。
# 引擎文件放在 vue-WeChat/public/engine/，worker_local.js 同源加载，rime.js/wasm/data 从 /engine/ 本地拉取（不依赖外网 CDN）。
# 预编译产物在 /engine/rime-ice/build/，每次录屏写回 /rime/build/ 让 deploy() 跳过重编译。
RIME_ENGINE_DIR = "/engine"
RIME_WUSONG_FILES = [
    "rime_ice.schema.yaml", "default.yaml", "symbols_v.yaml", "rime_ice.dict.yaml",
    "cn_dicts/8105.dict.yaml", "cn_dicts/base.dict.yaml", "cn_dicts/ext.dict.yaml",
    "cn_dicts/tencent.dict.yaml", "cn_dicts/others.dict.yaml",
    "lua/select_character.lua", "lua/date_translator.lua", "lua/lunar.lua", "lua/uuid.lua",
    "lua/unicode.lua", "lua/number_translator.lua", "lua/calc_translator.lua", "lua/force_gc.lua",
    "lua/corrector.lua", "lua/autocap_filter.lua", "lua/v_filter.lua", "lua/pin_cand_filter.lua",
    "lua/long_word_filter.lua", "lua/reduce_english_filter.lua", "lua/search.lua",
    "lua/convert_ar_num_to_zh.lua",
]
RIME_WUSONG_RAW = "/engine/rime-ice/"   # 本地缓存（vue-WeChat/public/engine/rime-ice），避免每次从 GitHub 慢拉

# 预编译产物：deploy() 一次的 /rime/build 输出，静态缓存于 vue-WeChat/public/engine/rime-ice/build/。
# 每次录屏前把这些 .bin 写回 /rime/build/，能让 deploy() 检测到产物已最新而跳过重编译，
# 省掉冷部署的几十秒（本机实测 deploy 从 ~16s 降到 ~3s，引擎整体就绪约 6s）。
# 需与 _capture_build.py 捕获的文件名保持一致。
RIME_WUSONG_BUILD_FILES = [
    "default.yaml", "rime_ice.schema.yaml", "rime_ice.table.bin",
    "rime_ice.reverse.bin", "rime_ice.prism.bin",
]
RIME_WUSONG_BUILD_RAW = "/engine/rime-ice/build/"   # 预编译产物本地缓存目录


def _rime_bootstrap_js() -> str:
    """返回注入到录屏页的 <script type=module> 内容：加载 my-worker，部署雾凇，暴露 window.__rimeEngine。"""
    files = json.dumps(RIME_WUSONG_FILES)
    build_files = json.dumps(RIME_WUSONG_BUILD_FILES)
    base = json.dumps(RIME_WUSONG_RAW)
    build_base = json.dumps(RIME_WUSONG_BUILD_RAW)
    eng = json.dumps(RIME_ENGINE_DIR)
    return f"""
const __FILES={files};
const __BUILD_FILES={build_files};
const __BASE={base};
const __BUILD_BASE={build_base};
const __ENG={eng};
async function __ensureDir(FS, path){{let i=1;while((i=path.indexOf('/',i)+1)>0){{const d=path.slice(0,i);try{{await FS.lstat(d)}}catch{{await FS.mkdir(d)}}}}}}
(async()=>{{
  try {{
    // 引擎文件（worker_local.js / rime.js / rime.wasm / rime.data）从 /engine/ 同源本地加载，不依赖外网 CDN
    const mw = await import(__ENG + '/my-worker.js');
    const worker = new mw.LambdaWorker(__ENG + '/worker_local.js');
    const FS = mw.asyncFS(worker);
    const setIME=worker.register('setIME'), setPageSize=worker.register('setPageSize'), deploy=worker.register('deploy');
    const processFn=worker.register('process');
    window.__rimeEngine={{ ready:false, process:(i)=>processFn(String(i)).then(r=>JSON.stringify(r)) }};
    let wrote=0;
    for (const f of __FILES) {{
      const p='/rime/'+f;
      try {{ const r=await fetch(__BASE+f); if(r.ok){{ await __ensureDir(FS,p); await FS.writeFile(p,new Uint8Array(await r.arrayBuffer())); wrote++; }} }} catch(e){{}}
    }}
    try {{ await __ensureDir(FS,'/rime/default.custom.yaml'); await FS.writeFile('/rime/default.custom.yaml','patch:\\n  schema_list:\\n    - schema: rime_ice\\n'); }} catch(e){{}}
    // 预编译产物：把静态缓存的 /engine/rime-ice/build/* 写回 /rime/build/，
    // 使 deploy() 检测到 build 已最新而跳过重编译（冷部署几十秒 → 秒级）。
    // 缺文件时静默跳过，deploy() 会回退到冷编译（慢但可用）。
    let wroteBuild=0;
    for (const f of __BUILD_FILES) {{
      const p='/rime/build/'+f;
      try {{ const r=await fetch(__BUILD_BASE+f); if(r.ok){{ await __ensureDir(FS,p); await FS.writeFile(p,new Uint8Array(await r.arrayBuffer())); wroteBuild++; }} }} catch(e){{}}
    }}
    if (wroteBuild>0) console.log('[rime] prebuilt build files written:', wroteBuild+'/'+__BUILD_FILES.length);
    try {{ await deploy(); await setIME('rime_ice'); setPageSize(10); window.__rimeEngine.ready=true; }} catch(e){{ console.error('rime deploy err', e); }}
  }} catch(e) {{ console.error('rime engine boot err', e); window.__rimeEngine = window.__rimeEngine || {{ready:false}}; }}
}})();
"""


def _inject_rime_engine(page) -> None:
    """向录屏页注入 Rime 引擎引导模块脚本（雾凇部署为异步，用 wait_for_function 等 ready）。"""
    if not os.path.isdir(os.path.join(FRONTEND_DIR, "public", "engine")):
        return  # 未部署引擎目录，跳过（不作废，走离线词库）
    try:
        page.evaluate(
            "(js) => { const s=document.createElement('script'); s.type='module'; s.textContent=js; document.head.appendChild(s); }",
            _rime_bootstrap_js())
        print("[引擎] 已注入 Rime WASM 引擎引导，等待雾凇就绪……")
        try:
            page.wait_for_function("() => window.__rimeEngine && window.__rimeEngine.ready === true",
                                   timeout=90_000)
            print("[引擎] 雾凇引擎就绪（真实候选可用）。")
        except Exception:                     # noqa: BLE001
            print("[引擎] 雾凇未在超时内就绪，回退离线词库。")
    except Exception as exc:                  # noqa: BLE001
        print(f"[引擎] 注入失败（回退离线词库）：{exc}")


def inject_overlays(page) -> None:
    """注入全部前端增强：字体 / iPhone 仿真层 / 现代皮肤 / 键盘 / 配置 / 朋友圈 / 页面增强 / 真人行为。幂等。"""
    # 关键：用 !important 永久隐藏欢迎页（不要用 .remove()——Vue 的 $forceUpdate 会把它再建回来，
    # 导致录制里欢迎页持续出现，这就是「开头一两秒老界面」的根源）。隐藏即可露出下方会话列表。
    page.add_style_tag(content=".welcome { display: none !important; }")
    # 微信风格字体（HarmonyOS Sans SC）先于皮肤注入，供全局字体栈使用
    page.add_style_tag(content=_read_enhance("harmony_font.css"))
    page.add_style_tag(content=_read_enhance("keyboard.css"))
    page.add_style_tag(content=_read_enhance("iphone_frame.css"))
    page.add_style_tag(content=_read_enhance("weui_tokens.css"))
    page.add_style_tag(content=_read_enhance("wechat_modern.css"))
    page.add_style_tag(content=_read_enhance("human_actions.css"))
    page.add_style_tag(content=_read_enhance("transfer_ui.css"))
    page.add_style_tag(content=_read_enhance("send_image_ui.css"))
    # 首页像素级规格覆盖（600×1300 固定画布）需最后注入，压在其它皮肤之上
    page.add_style_tag(content=_read_enhance("homepage_exact.css"))
    for name in ("config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
                 "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js"):
        page.evaluate(_read_enhance(name))
    # pinyin_data.js 体积大（候选词库，几 MB~十几 MB），用 <script> 内联注入让浏览器原生解析，
    # 比 page.evaluate(大字符串) 快得多（实测 10MB 词库从 ~11s 降到 ~2s），避免录屏/截图启动卡顿。
    page.add_script_tag(content=_read_enhance("pinyin_data.js"))
    page.evaluate(_read_enhance("keyboard.js"))
    page.evaluate(ENHANCE_JS)
    # 真 Rime WASM 引擎（雾凇）引导：注入并预热，供 keyboard.js 取真实候选。
    _inject_rime_engine(page)
    # 高速打字(按倍速)时关闭字符浮层气泡，避免高倍速下满屏弹泡、眼花缭乱；低速保留。
    page.evaluate("window.__wxKeyboard && window.__wxKeyboard.setPopupEnabled(%s)"
                  % ("true" if TYPE_SPEED < KEY_POPUP_MAX_TYPING_SPEED else "false"))
    # 真人行为层：图片查看器 / 对方逐字打字（需在 ENHANCE_JS 之后注入，复用 __wxPeerMsg）
    page.evaluate(_read_enhance("human_actions.js"))
    # 把全局默认放大倍率推给 JS（手动点图兜底 / 未单独设倍率的图都按它放大）
    page.evaluate("(z) => window.__wxHuman && window.__wxHuman.setZoomDefault(z)",
                  IMAGE_ZOOM_DEFAULT)
    # 首页像素级覆盖层的 DOM 结构（状态栏静音 / 加号 / 悬浮胶囊），需在 iphone_frame.js 之后注入
    page.evaluate(_read_enhance("homepage.js"))
    # 聊天页像素级规格覆盖（600×1300 固定画布）必须最后注入：
    # chat_extra.js 等 JS 注入的 <style> 出现在文档后部，chat_exact.css 需在其之后才可覆盖。
    page.add_style_tag(content=_read_enhance("chat_exact.css"))
    # 微信真实 SVG 图标（mask 替换 iconfont/自绘），置于最末确保覆盖所有皮肤
    page.add_style_tag(content=_read_enhance("wx_icons.css"))
    # 修复转场闪帧（此处用 add_style_tag，实测生效；放 init script 不生效）：
    # 根因（已用捕获帧实锤）：vue 路由子页用 translateX(±100%) 做左右滑动转场，转场瞬间
    # 子页 `.sub-page`（宽 100%，translate3d(100%) 后右缘到 1200px）与底页 `.outter`
    # (translate3d(-30%) 后左缘到 -180px) 同时存在，把**合成器表面**撑宽到约 1380px。
    # screencast 的 maxWidth:600 会把这块更宽的表面整幅下采样到 600px，于是 600px 宽的
    # 页面内容被压到左边约 40%、右侧出现大片黑边 —— 这就是「缩左+黑边」的闪帧。
    # 旧的 `#app{overflow-x:hidden}` 只锁住了**布局**（实测 documentElement.scrollWidth 恒为
    # 600、visualViewport.scale 恒为 1），却管不住 transform 层在**合成器**里的越界绘制。
    # 
    # 正确修复：给 `#app` 加 `contain: paint`（绘制包含）+ `overflow: clip`，强制把
    # `#app` 内所有后代（含被 transform 的子页/底页）的绘制裁剪在 #app 的 600×1300 盒内，
    # 合成器表面于是恒为 600 宽，screencap 不再下采样 → 不再闪帧。同时给 html/body 也设
    # overflow: clip，避免任何挂在 document.body 上的覆盖层（键盘/手机框/图片查看器等）
    # 撑宽合成器表面。
    #
    # 为什么是 overflow: clip 而不是 overflow: hidden：hidden 仍允许**程序性滚动**——
    # 聚焦输入框时 dialogue.vue 的 focusIpt() 写 document.body.scrollTop = scrollHeight，
    # 会被钳到 (scrollHeight−clientHeight)=278（正是键盘高）。返回主页瞬间 body.wx-chat 被
    # 移除、chat_extra.js 里那段每 50ms「把 html/body 滚动钳回 0」的滚动护栏随之停摆，
    # 于是 body.scrollTop 残留在 278，整屏上移 278px（#app top=-278）的错乱就定在主页。
    # overflow: clip 让 html/body/#app 根本**不是滚动容器**，scrollTop/scrollTo 一律无效，
    # 从源头杜绝这条 278 的错乱；且它不改变 contain:paint 带来的「fixed 键盘包含块」，
    # 键盘/评论条等 fixed 覆盖层与之前完全一致。
    #
    # 注意：`#app` 加 position:relative 会让绝对定位的 .outter 以 #app 为包含块；
    #      homepage_exact.css 中 .outter 的高度是 calc(100% - 83px)，若 html/body/#app
    #      没有确定高度（#app 高度塌陷为 0），calc(100% - 83px) 会按 100%=0 计算而被钳到 0，
    #      导致整页内容区高度为 0、会话列表不可点（Playwright 报 "<html> intercepts pointer events"
    #      / "element is outside of the viewport"）。因此必须同时给 html/body/#app 确定高度。
    page.add_style_tag(
        content=(
            "html, body { height: 100% !important; overflow: clip !important;"
            " contain: paint !important; width: 600px !important; max-width: 600px !important; }"
            "#app { overflow: clip !important; position: relative !important;"
            " contain: paint !important;"
            " width: 600px !important; max-width: 600px !important;"
            " height: 100% !important; min-height: 100% !important; }"))
    # 修复「收起(子页收回)」的「缩左+黑边」闪帧：vue 转场里底页 .outter.hideLeft 用了
    # translate3d(-30%) scale(.95) 做视差，转场瞬间底页盒子只盖到约 405px（右缘留 ~195px），
    # 当子页 .sub-page 滑出速度快于底页「收回」时，右侧会短暂露出 #app 的深色背景，
    # 观感即「内容被压到左 40%、右侧大片黑边」的闪帧。
    # 修复：让底页在子页 push/pop 期间保持整屏、不透明（取消左移缩小视差）。
    # 真机上前一页其实基本静止、只是被新页滑过覆盖，因此取消视差不会改观感，
    # 反而让子页滑出时是「整屏主页原样显露」，不再有露底黑边。
    page.add_style_tag(
        content=(
            ".outter.hideLeft { transform: none !important;"
            " opacity: 1 !important; transition: opacity .3s ease !important; }"))
    # 修复「收起键盘 + 返回主页」的「输入栏悬空错乱」闪帧：返回时 vue 路由给子页
    # .sub-page 加 transform: translateX(±100%) 做水平滑出，而聊天输入栏 .dialogue-footer
    # 一直是 position: fixed。CSS 规则里「最近的被 transform 的祖先会变成 fixed 子元素的
    # 定位包含块」，于是滑出瞬间（body.wx-chat 类已先被移除、只剩基础 fixed 规则生效）这个
    # fixed 输入栏被拖进「被 transform 的子页」坐标系，跟着页面乱飞——出现输入栏悬空在
    # 屏幕中部、聊天头部/消息消失的整画面错乱。
    # 修复：把基础 .dialogue-footer 改为 position: absolute（锚定 .dialogue 子页底部）。
    #   · 稳定聊天态：body.wx-chat .dialogue-footer 那条 specificity 更高的
    #     position: fixed !important 仍然生效，位置完全不变（.dialogue 底边=视口底边）；
    #   · 转场态：wx-chat 类被移除，只剩基础规则，absolute 让输入栏作为子页的一部分
    #     跟着卡片整体水平滑出并被 contain:paint 裁掉，不再被乱拖。
    page.add_style_tag(content=(
        ".dialogue-footer { position: absolute !important; left: 0 !important;"
        " right: 0 !important; width: 100% !important; }"))
    # 应用配置（DEFAULT_HOME/现代数据）。vue 实例可能尚未完全挂载，失败时忽略，
    # start() 会在等 store 就绪后再 apply 一次。
    try:
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    except Exception:                    # noqa: BLE001
        pass
    # 每次运行随机一个电量（60~100%），电量图标固定为白色（贴合 iPhone 15 非充电状态）
    page.evaluate(
        "window.__wxPhoneFrame && window.__wxPhoneFrame.setBattery(%d)"
        % random.randint(60, 100))
    page.evaluate(
        "window.__wxPhoneFrame && window.__wxPhoneFrame.setCharging(false)")


# ============================================================
# 四、元素拾取 / 编辑（编辑器「编辑模式」用）
# ============================================================

# 拾取坐标下的可编辑元素：返回 kind/text/src 描述，并给元素打 data-wx-edit-id 标记。
# kind 取值：text 文字 / image 图片 / bg 背景图 / me_avatar 我的头像 / me_name 我的昵称 / me_bg 朋友圈封面
PICK_JS = r"""
(({x, y}) => {
    const el = document.elementFromPoint(x, y);
    if (!el) return { ok: false, msg: '该位置没有元素' };
    const skipSel = '#ios-statusbar, #ios-home, #ios-screen-mask, #wxkb, .kb-pop, #momentCompose';
    if (el.closest(skipSel)) return { ok: false, msg: '键盘/状态栏区域不可编辑，请点击聊天内容区' };
    const toPath = (u) => {
        if (!u) return '';
        try { const a = new URL(u, location.origin); return a.pathname + a.search; } catch (e) { return u; }
    };
    const ownText = (n) => {
        let t = '';
        n.childNodes.forEach(c => { if (c.nodeType === 3) t += c.nodeValue; });
        return t.replace(/\s+/g, ' ').trim();
    };
    const bgUrl = (n) => {
        const m = /url\(["']?(.*?)["']?\)/i.exec(getComputedStyle(n).backgroundImage);
        return m ? toPath(m[1]) : '';
    };
    const ensureId = (n) => {
        if (!n.dataset.wxEditId) {
            window.__wxEditSeq = (window.__wxEditSeq || 0) + 1;
            n.dataset.wxEditId = 'wxedit_' + window.__wxEditSeq;
        }
        return n.dataset.wxEditId;
    };
    /* 聊天列表最后一条消息：.desc-msg 里是 <span>结构，把最后一段文字当作可编辑文本 */
    const dm = el.closest ? el.closest('.desc-msg') : null;
    if (dm) {
        const spans = dm.querySelectorAll('span');
        const target = spans.length ? spans[spans.length - 1] : dm;
        const t = (target.textContent || '').replace(/\s+/g, ' ').trim();
        if (t.length <= 200) {
            return { ok: true, kind: 'text', id: ensureId(target), text: t, src: '' };
        }
    }
    let node = el;
    for (let i = 0; i < 12 && node && node !== document.body && node !== document.documentElement; i++) {
        if (node.tagName === 'IMG') {
            return { ok: true, kind: node.hasAttribute('data-me-avatar') ? 'me_avatar' : 'image',
                     id: ensureId(node), text: '', src: toPath(node.currentSrc || node.src) };
        }
        if (node.hasAttribute && node.hasAttribute('data-me-name')) {
            return { ok: true, kind: 'me_name', id: ensureId(node), text: (node.textContent || '').trim(), src: '' };
        }
        if (node.hasAttribute && node.hasAttribute('data-me-bg')) {
            return { ok: true, kind: 'me_bg', id: ensureId(node), text: '', src: bgUrl(node) };
        }
        const bg = bgUrl(node);
        if (bg) return { ok: true, kind: 'bg', id: ensureId(node), text: '', src: bg };
        const t = ownText(node);
        if (t && t.length <= 200) return { ok: true, kind: 'text', id: ensureId(node), text: t, src: '' };
        node = node.parentElement;
    }
    return { ok: false, msg: '该位置没有可编辑的文字或图片' };
})
"""

# 应用元素修改。优先处理我的头像/昵称/封面（全局同步），普通文字/图片直接改 DOM；
# 主页聊天列表 / 对话气泡是 Vue 数据驱动的，同步补丁进 vuex store，避免切页后被重新渲染还原。
EDIT_JS = r"""
((p) => {
    const id = p.id, prop = p.prop;
    const value = String(p.value == null ? '' : p.value);

    if (prop === 'me_avatar') { if (window.__wxConfig) { window.__wxConfig.setAvatar(value); return { ok: true }; } }
    if (prop === 'me_name')   { if (window.__wxConfig) { window.__wxConfig.setName(value); return { ok: true }; } }
    if (prop === 'me_bg')     { if (window.__wxConfig) { window.__wxConfig.setBg(value); return { ok: true }; } }

    const el = document.querySelector('[data-wx-edit-id="' + id + '"]');
    if (!el) return { ok: false, msg: '元素已失效（页面可能刷新过），请重新点击选择' };

    /* ---- 先把改动同步进 vuex store（尽量让切页后仍保留） ---- */
    const vm = document.getElementById('app') && document.getElementById('app').__vue__;
    if (vm && vm.$store) {
        try {
            const list = vm.$store.state.msgList && vm.$store.state.msgList.baseMsg;
            /* 主页聊天列表 */
            const li = el.closest('li.list-row');
            if (li && Array.isArray(list)) {
                const all = Array.from(document.querySelectorAll('li.list-row'));
                const idx = all.indexOf(li);
                const item = list[idx];
                if (item) {
                    if (prop === 'text') {
                        if (el.classList.contains('desc-author')) {
                            if (item.type === 'group') item.group_name = value;
                            else if (item.user && item.user[0]) { item.user[0].remark = value; item.user[0].nickname = value; }
                        } else {
                            const dm = el.closest('.desc-msg');
                            const last = item.msg && item.msg[item.msg.length - 1];
                            if (dm && last) {
                                const spans = dm.querySelectorAll('span');
                                if (spans.length && el === spans[0]) last.name = value.replace(/:$/, '');
                                else last.text = value;
                            }
                        }
                    } else if (prop === 'src') {
                        const imgs = li.querySelectorAll('.header img');
                        const imgIdx = Array.prototype.indexOf.call(imgs, el);
                        if (imgIdx >= 0 && item.user && item.user[imgIdx]) item.user[imgIdx].headerUrl = value;
                    }
                }
            }
            /* 对话气泡 */
            const row = el.closest('.dialogue-section .row');
            if (row && vm.$route && list) {
                const mid = vm.$route.query && vm.$route.query.mid;
                const cur = (list || []).find(it => String(it.mid) === String(mid));
                if (cur && Array.isArray(cur.msg)) {
                    const rows = Array.from(document.querySelectorAll('.dialogue-section .row'));
                    const ridx = rows.indexOf(row);
                    if (ridx >= 0 && ridx < cur.msg.length) {
                        if (prop === 'text') cur.msg[ridx].text = value;
                        else if (prop === 'src') cur.msg[ridx].headerUrl = value;
                    }
                }
            }
            if (vm.$forceUpdate) vm.$forceUpdate();
        } catch (e) { /* store 补丁失败不影响直接改 DOM */ }
    }

    /* ---- 直接修改 DOM ---- */
    if (prop === 'text') { el.textContent = value; }
    else if (prop === 'src') { el.src = value; }
    else if (prop === 'bg') { el.style.backgroundImage = "url('" + value + "')"; }
    else { return { ok: false, msg: '不支持的修改类型：' + prop }; }
    return { ok: true };
})
"""


# ============================================================
# 四、前端服务自动启动
# ============================================================

def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    """检测端口是否已有服务在监听"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def ensure_frontend_running() -> None:
    """确保 vue-WeChat 前端已在 http://localhost:8080 运行。"""
    if not AUTO_START_FRONTEND or _port_open(PORT):
        return
    if not os.path.isdir(FRONTEND_DIR):
        raise RuntimeError(f"找不到前端项目目录：{FRONTEND_DIR}")

    node_dir = BUNDLED_NODE_DIR if (os.path.isdir(BUNDLED_NODE_DIR)
                                    and os.path.isfile(os.path.join(BUNDLED_NODE_DIR, "npm.cmd"))) else None
    if node_dir:
        env = {**os.environ, "PATH": node_dir + os.pathsep + os.environ.get("PATH", "")}
        npm_cmd = os.path.join(node_dir, "npm.cmd")
    else:
        env = os.environ.copy()
        # 便携版 Node 目录缺失/不完整(缺 npm.cmd)时回退到系统 PATH 里的 npm；
        # 连系统 npm 都没有则直接给出明确中文提示，避免掉进 WinError 2。
        npm_cmd = shutil.which("npm") or ""
        if not npm_cmd:
            raise RuntimeError(
                "未找到可用的 npm / node：便携版目录缺少 npm.cmd，且系统 PATH 中也找不到 npm。"
                "请安装 Node.js（https://nodejs.org）后重试，或把 tools/node-v20.19.4-win-x64 补齐。")

    print(f"[前端] 检测到端口 {PORT} 无服务，正在自动启动 vue-WeChat……")
    log_fh = open(os.path.join(FRONTEND_DIR, "dev-server.log"), "w", encoding="utf-8")
    proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR, env=env,
        stdout=log_fh, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    deadline = time.time() + FRONTEND_START_TIMEOUT_SEC
    while time.time() < deadline:
        if _port_open(PORT):
            print(f"[前端] 启动成功：http://localhost:{PORT}")
            time.sleep(1)
            return
        if proc.poll() is not None:
            log_fh.close()
            with open(os.path.join(FRONTEND_DIR, "dev-server.log"),
                      encoding="utf-8", errors="replace") as fh:
                tail = fh.read()[-1500:]
            raise RuntimeError(
                f"前端 dev server 启动失败（exit={proc.returncode}），日志尾部：\n{tail}")
        time.sleep(0.5)
    raise RuntimeError(
        f"等待前端启动超时（{FRONTEND_START_TIMEOUT_SEC}s）。"
        f"详情见日志：{os.path.join(FRONTEND_DIR, 'dev-server.log')}")


# ============================================================
# 五、自动化主体
# ============================================================

# ---- 雾凇拼音词表（用于打字按"真实词"分段，让候选与上屏对得上） ----
_WUSONG_WORDS = None


def _wusong_words():
    """懒加载雾凇词表（enhance/rime-ice/wusong_data.json 的 word_weight 键）。

    返回一个 set（含词频阈值≥60 的 72 万+ 词）。加载失败/缺失时回退空集（退回逐字/随机分段）。
    """
    global _WUSONG_WORDS
    if _WUSONG_WORDS is not None:
        return _WUSONG_WORDS
    words = set()
    try:
        with open(os.path.join(ENHANCE_DIR, "rime-ice", "wusong_data.json"),
                  encoding="utf-8") as fh:
            words = set(json.load(fh).get("word_weight", {}).keys())
    except (OSError, ValueError):
        words = set()
    _WUSONG_WORDS = words
    return words


def _wusong_word_len(run: str, i: int, max_len: int = 6) -> int:
    """在 run[i:] 处找最长的雾凇真实词（最长匹配），返回其字符长度；无匹配返回 0。

    用于打字分段：命中雾凇真实词时整词上屏，候选与上屏文字一致（更像真输入法）。
    """
    words = _wusong_words()
    if not words:
        return 0
    n = len(run)
    hi = min(max_len, n - i)
    for L in range(hi, 0, -1):
        if run[i:i + L] in words:
            return L
    return 0


class WeChatAuto:
    """驱动 vue-WeChat 页面的自动化封装（含手机键盘模拟）"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None
        self._cdp = None           # CDP 会话（screencast 真 60fps 采集用）
        self._start_ts = None      # 本轮运行计时起点（monotonic），用于报告耗时
        self.last_mp4 = None       # 兼容旧字段：旧 25fps 录屏已删除，恒为 None
        self.last_mp4_60 = None    # 当前唯一输出：按真实时间戳合成的 VFR MP4（stop 后可用）
        self.wall_seconds = None   # 本轮运行总耗时（含 60fps 密集采集开销）
        self.trim_head_sec = TRIM_HEAD_SEC   # 视频开头跳过时长（预热后调小，仅去首帧抖动）
        # 音效状态（由 start() 初始化，stop() 用事件时间戳合成音轨混进成品视频）
        self._sounds = {}          # name -> int16 单声道数组（type/delete/send/continuous_type）
        self._audio_events = []    # [(wall_ts, name[, dur]), ...] 每次按键/回删/发送都记录一条
        self._audio_offset = 0.0   # CDP 视频时间戳 - 进程墙钟时间戳 的常数偏移（时钟校准）
        self._audio_calibrated = False
        # 连续打字声状态：TYPE_SPEED ≥ CONTINUOUS_TYPE_MIN_SPEED 时，把一段连打合并成一条
        # 「持续打字声」事件（记录起止）；_ct_open 表示当前连打段是否正在收集中。
        self._ct_open = False
        self._ct_start = 0.0       # 连打段起始墙钟时间
        self._ct_last = 0.0        # 连打段最后一次按键的墙钟时间
        self._ct_live_played = False
        self._ct_first_commit_wall = None
        self._pending_send_wall = None   # 发送键待定墙钟：气泡渲染后由 _finalize_send_sound 锚定
        self._mute_sound = False   # 预热等「不进成品」的敲键临时静音（不记录音效/不实时播放）
        # 后台消息队列（[对方后台发消息] / [后台消息队列]）：由 load_bg_queue 装载并投递
        self._bg_queue = []
        self._bg_base_clock = 0.0  # 装载队列时的 _RUN_CLOCK 基准，供「秒」触发使用

    # ---------- 启动 / 收尾 ----------

    # ---------- 启动前静默预热（让录屏第一帧就资源齐备） ----------

    def collect_step_texts(self, steps) -> str:
        """收集工作流/剧本所有动作参数里的文字，用于预热时按实际用到的字形加载字体。"""
        texts = []
        for step in steps or []:
            for v in (step.get("params") or {}).values():
                if isinstance(v, str) and v.strip():
                    texts.append(v)
        return "".join(texts)

    def warmup(self, texts: str = None, urls: list = None):
        """开录屏（真正开始动作采集）之前，静默预热页面资源：
           - 预载当前页面所有 <img> 与背景图，及外部传入的 /images|/fonts 静态资源路径；
           - 用剧本实际文案强制 document.fonts.load，只拉取会用到的 HarmonyOS 字形子集；
           - 停留一小段让字体/图片真正落盘（favicon/首帧不再闪变）。

        texts: 剧本/工作流所有文案拼成的字符串（用于按字形加载字体子集）。
        urls:  额外要预载的静态资源路径列表（相对 '/'）。
        预热期间采集到的帧由调用方随后 reset_frames() 丢弃。
        """
        self._ensure_enhance()
        urls = list(urls or [])
        try:
            self.page.evaluate(
                """(extra) => {
                    const urls = new Set();
                    const abs = (u) => { try { return new URL(u, location.origin).href; } catch (e) { return u; } };
                    // 1) 当前 DOM 里所有 <img> 的 src / currentSrc
                    document.querySelectorAll('img').forEach(im => {
                        const s = im.getAttribute('src') || im.currentSrc;
                        if (s && !s.startsWith('data:')) urls.add(abs(s));
                    });
                    // 2) 所有元素计算样式里的背景图
                    document.querySelectorAll('*').forEach(el => {
                        const bg = getComputedStyle(el).backgroundImage;
                        const m = /url\\(["']?([^"')]+)["']?\\)/.exec(bg || '');
                        if (m && m[1] && !m[1].startsWith('data:')) urls.add(abs(m[1]));
                    });
                    // 3) 调用方额外指定的静态资源（如场景/剧本里引用的图片）
                    (extra || []).forEach(u => { if (u) urls.add(abs(u)); });
                    // 4) 「我方」资料图（头像/朋友圈封面/对方默认头像）：预热时首页未渲染我方头像，
                    //    必须显式取 window.__wxConfig，否则进入聊天后我方头像会闪一下才出来。
                    try {
                        const cfg = window.__wxConfig && window.__wxConfig.get();
                        if (cfg && cfg.me) {
                            const add = (u) => { if (u && !String(u).startsWith('data:')) urls.add(abs(u)); };
                            add(cfg.me.avatar); add(cfg.me.bg); add(cfg.me.peerAvatar);
                        }
                    } catch (e) {}
                    // 5) vuex store 里之后才会渲染的头像/消息图（会话历史 + 通讯录），一并预载。
                    try {
                        const vm = document.getElementById('app') && document.getElementById('app').__vue__;
                        const st = vm && vm.$store && vm.$store.state;
                        const add2 = (u) => { if (u && !String(u).startsWith('data:')) urls.add(abs(u)); };
                        if (st) {
                            const base = (st.msgList && st.msgList.baseMsg) || [];
                            base.forEach(it => {
                                (it.user || []).forEach(u => add2(u && u.headerUrl));
                                (it.msg || []).forEach(m => { if (m) { add2(m.headerUrl); add2(m.image); } });
                            });
                            (st.allContacts || []).forEach(u => add2(u && u.headerUrl));
                        }
                    } catch (e) {}
                    // 逐张预载：触发浏览器图片解码与缓存
                    urls.forEach(u => { const im = new Image(); im.src = u; });
                    return urls.size;
                }""",
                urls)
        except Exception as exc:                                    # noqa: BLE001
            print(f"[预热] 图片预载失败（跳过）：{exc}")

        if texts:
            try:
                self.page.evaluate(
                    """(t) => {
                        const p = [];
                        p.push(document.fonts.ready);
                        // 按剧本实际用到的字形触发 HarmonyOS 子集加载（400/500 两级）
                        ['400', '500'].forEach(w => {
                            try { p.push(document.fonts.load(w + ' 16px "HarmonyOS Sans SC"', t)); } catch (e) {}
                        });
                        return Promise.all(p).then(() => true);
                    }""",
                    texts)
            except Exception as exc:                                # noqa: BLE001
                print(f"[预热] 字体预载失败（跳过）：{exc}")

        # 给字体/图片一点落盘时间（不计入正式视频，因为接下来会 reset_frames）
        _pump_wait(0.9)

    def reset_frames(self):
        """丢弃预热期已采集的帧，让视频从「资源齐备的主页」开始（配合 warmup）。"""
        with _FRAME_LOCK:
            _FRAMES.clear()

    def _prewarm_workflow(self, steps):
        """在开录前，把整条工作流里「冷启动链」提前预热一遍（只求资源/管线变热，不还原时序）：

        - 每个会被 [打开聊天] 的会话：预打开一次，载入其历史消息、头像、对方资料图与封面，
          并顺带读取 vuex store 里的会话历史/通讯录头像，全部进浏览器解码缓存。
        - 每条 [我方打字]/[打字不发] 的真实文案：静默敲一次「拼音→候选→合成渲染→引擎回填→
          上屏」整条输入管线（音效静音、不发送、不注入对方插话），随后清空输入框，
          让每句文案各自的引擎候选与字形子集即时可用——而不止第一条。
        - 每张 [查看图片]/[发送图片]/[对方发图片] 的图片：预载解码缓存。

        所有预热帧会被调用方随后 reset_frames() 丢弃；每个会话预热完立即带回主页，
        不影响后续步骤；任一环节失败只跳过该会话，不影响录屏。预热期间 _mute_sound=True，
        敲键音不进入成品音轨。

        相比只预热第一条消息，这里把「第二次打开键盘/第二个会话/后续文案」全部提前变热，
        消除剧本后续每一步第一次碰到时的冷加载卡顿（正是「某个时刻像被放慢动作」的来源）。
        """
        # ---- 第一步：按剧本顺序收集「会话 → 该会话里要打的文案」和「要预载的图片」 ----
        chat_messages = {}      # 会话名 -> [文案]（按出现顺序去重）
        chat_order = []         # 会话首现顺序
        cur_chat = None
        img_urls = []
        for s in steps or []:
            if not isinstance(s, dict):
                continue
            action = s.get("action")
            p = s.get("params") or {}
            if action == "打开聊天":
                c = p.get("联系人", p.get("name"))
                if c:
                    if c not in chat_messages:
                        chat_messages[c] = []
                        chat_order.append(c)
                    cur_chat = c
            elif action in ("我方打字", "打字不发"):
                t = p.get("内容", p.get("text"))
                if isinstance(t, str) and t.strip() and cur_chat and cur_chat in chat_messages:
                    if t not in chat_messages[cur_chat]:
                        chat_messages[cur_chat].append(t)
            elif action in ("回到聊天主页", "返回聊天主页", "返回主页"):
                cur_chat = None
            elif action in ("查看图片", "发送图片", "对方发图片"):
                u = p.get("图片", "")
                if isinstance(u, str) and u.strip():
                    img_urls.append(u)

        self._mute_sound = True          # 预热敲键不进成品音轨（也不实时播放）
        warmed_ok = []
        try:
            self._ensure_enhance()
            # 图片预载：与 warmup() 的静态资源预载互补，这里额外触发「查看/发送图片」的解码缓存
            if img_urls:
                try:
                    self._preload_images(img_urls)
                except Exception as exc:                    # noqa: BLE001
                    print(f"[预热] 查看/发送图片预载失败（跳过）：{exc}")
            # 逐个会话预热：打开 → 逐条文案敲一遍输入管线再清空 → 回主页
            for c in chat_order:
                msgs = chat_messages[c]
                try:
                    self.open_chat(str(c))
                    if not msgs:
                        # 该会话不涉及我方打字：仍打开一次键盘，避免该会话首次开键盘冷启动动画
                        try:
                            box = self.page.locator(".chat-txt")
                            if box.count():
                                box.first.click()
                                _pump_wait(0.12 / SPEED / max(0.05, TYPE_SPEED))
                                self._kb_show()
                                self._set_input_value(box, "")
                                _pump_wait(0.05)
                        except Exception:                    # noqa: BLE001
                            pass
                        self.go_back_home()
                        warmed_ok.append(c)
                        continue
                    box = self.page.locator(".chat-txt")
                    for m in msgs:
                        try:
                            self.human_type(".chat-txt", m, send=False,
                                            show_keyboard=True, interjections=None)
                            if box.count():
                                self._set_input_value(box, "")   # 清空，避免串到下一条文案
                            _pump_wait(0.08)
                        except Exception as exc:                # noqa: BLE001
                            print(f"[预热] 文案「{str(m)[:12]}…」预热失败（跳过该会话剩余文案）：{exc}")
                            break
                    self.go_back_home()
                    warmed_ok.append(c)
                except Exception as exc:                    # noqa: BLE001
                    print(f"[预热] 会话「{c}」预热失败（跳过）：{exc}")
                    try:
                        self.go_back_home()
                    except Exception:                    # noqa: BLE001
                        pass
        except Exception as exc:                            # noqa: BLE001
            print(f"[预热] 输入管线预热失败（忽略）：{exc}")
        finally:
            self._mute_sound = False
            try:
                self.go_back_home()      # 无论成败都带回主页，避免影响后续步骤
            except Exception:                    # noqa: BLE001
                pass
        if warmed_ok:
            print(f"[预热] 已预热 {len(warmed_ok)} 个会话 + "
                  f"{sum(len(v) for v in chat_messages.values())} 条文案的输入管线，"
                  f"首个字符及后续每一步打字都将即时渲染。")

    def _prewarm_input(self, steps):
        """向后兼容：旧调试/探针脚本（_probe_*.py）仍调用 _prewarm_input，现统一走
        _prewarm_workflow（把整条工作流每个会话+每条文案都预热），不再只预热第一条。"""
        return self._prewarm_workflow(steps)

    def _preload_images(self, urls):
        """在页面里立即预载一组静态资源路径（相对 '/'），触发浏览器解码与缓存。

        用于预热阶段之外、运行中动态更换头像/封面之后调用，确保新图在首帧渲染前已就绪，
        避免切换后我方头像闪一下才出来。
        """
        urls = [u for u in (urls or []) if u and isinstance(u, str)]
        if not urls:
            return
        try:
            self.page.evaluate(
                """(us) => {
                    const abs = (u) => { try { return new URL(u, location.origin).href; } catch (e) { return u; } };
                    us.forEach(u => { const im = new Image(); im.src = abs(u); });
                }""",
                list(dict.fromkeys(urls)))
        except Exception as exc:                                    # noqa: BLE001
            print(f"[预热] 图片追加预载失败（跳过）：{exc}")

    def start(self):
        """启动浏览器并打开首页（单 context 全程录制，保证一镜到底）"""
        global _PUMP_BOT
        _PUMP_BOT = self          # 让模块级 _pump_wait / _sd_minmax 能派发 screencast 帧
        # 初始化音效：加载/合成三种音效，重置事件日志（供 stop() 合成成品音轨）
        self._audio_events = []
        self._audio_calibrated = False
        self._audio_offset = 0.0
        self._ct_open = False
        self._ct_start = 0.0
        self._ct_last = 0.0
        self._ct_live_played = False
        self._ct_first_commit_wall = None
        self._pending_send_wall = None
        self._mute_sound = False
        if ENABLE_AUDIO:
            self._sounds = sound_engine.load_or_synth(SOUNDS_DIR)
            if self._sounds:
                kinds = "、".join(sorted(self._sounds))
                print(f"[音效] 已就绪（{kinds}），实时播放={LIVE_AUDIO}")
            else:
                print("[音效] 未初始化（缺失 numpy 或无音源），成品视频将无声")
        else:
            self._sounds = {}
        self._pw = sync_playwright().start()
        os.makedirs(VIDEO_DIR, exist_ok=True)
        # 用系统已安装的 Chrome 作为浏览器内核（避免 headless chromium 下载失败/缺失）
        _chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        _exe = _chrome if os.path.isfile(_chrome) else None
        # 防「偶发断帧」启动参数（实测 Windows headed 下录屏偶有 ~0.5s 无帧断流，
        # 复现与否不稳定、JS 侧零长任务——指向合成器被系统级节流，而非脚本/渲染瓶颈）：
        #   · --disable-background-timer-throttling / --disable-renderer-backgrounding：
        #     禁止页面失活时定时器/渲染降频；
        #   · --disable-backgrounding-occluded-windows + 关闭 CalculateNativeWinOcclusion：
        #     Windows 窗口被其它窗口遮挡/最小化时按"命中遮挡检测"节流合成器，
        #     是录制中途随机顿一下的已知来源；录屏期间 Chrome 窗口常被编辑器盖住，
        #     关闭该项后合成器不再因遮蔽降帧。
        # 这些开关只影响调度/节流，不改画面渲染，headed/headless 均安全。
        _launch_args = [
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=CalculateNativeWinOcclusion",
        ]
        self.browser = self._pw.chromium.launch(headless=self.headless,
                                                executable_path=_exe,
                                                args=_launch_args)
        # 关键：**不要**传 record_video_size。它只是把视频画布拉大到 1170x2532，
        # 但页面内容仍按 390x844 渲染，于是画面只在左上角 1/3，其余全是大片灰边
        # （实测右上角像素为纯灰，这就是「画面错乱」的根源）。
        # 视频以内容实际尺寸(约 368x800)全屏铺满录制，由转码阶段用 lanczos 放大到
        # 目标视网膜分辨率，保证「无灰边 + 高清」。device_scale_factor 仅用于给
        # 编辑器实时截图提供 3x 高清帧，不影响视频。
        # 已放弃 Playwright 原生 record_video_dir 录屏：它把视频画布拉大导致灰边，
        # 且会与自建 screencast 抢占合成器、重复调度。统一走 CDP screencast 逐帧采集。
        _ctx_kwargs = dict(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=DEVICE_SCALE_FACTOR,
            user_agent=MOBILE_UA,
            is_mobile=True,
            has_touch=True,
            locale="zh-CN",
        )
        self.context = self.browser.new_context(**_ctx_kwargs)
        self.context.set_default_timeout(PAGE_TIMEOUT_MS)
        # 文档级深色基样式：页面一渲染即为深色，屏蔽注入前明亮的旧版 vue 界面，
        # 避免录屏开头出现「旧版界面」闪烁（新版微信深色皮肤由 wechat_modern.css 等注入）。
        # 注意：这里只做「早期压暗」，不要在 document_start 里设 #app 的 overflow——该注入时机
        # 在真实页面里不会生效（实测 #app computed 仍是 visible/static）。真正生效的
        # 「裁剪子页滑动溢出」修复放在 inject_overlays() 末尾用 add_style_tag 注入。
        self.context.add_init_script("""
            () => {
                const s = document.createElement('style');
                s.textContent = 'html, body, #app { background: #111 !important; color: #fff; }'
                    + '.welcome { display: none !important; }';
                (document.head || document.documentElement).appendChild(s);
            }
        """)
        self.page = self.context.new_page()
        self.page_open = True          # Python 层面的存活标记（供后台线程判断，不触碰 Playwright）
        # screencast 真 60fps 采集：浏览器每个合成帧主动推送（固定走此方案）
        self._start_screencast()
        self.page.goto(BASE_URL, wait_until="domcontentloaded")
        # 等 Vue 根应用真正渲染出会话列表，避免视频开头出现白屏/黑屏
        try:
            self.page.wait_for_selector(".wechat-list li, #wx-nav, .welcome",
                                        state="attached", timeout=PAGE_TIMEOUT_MS)
        except PWTimeoutError:
            pass  # 渲染过慢也不阻断，继续注入增强脚本
        inject_overlays(self.page)
        # 性能探针开关：WX_PERF=1 时开启 __wxPerf，让 keyboard.js 采集首键/开键盘各阶段耗时，
        # 录制结束后在 main() 里 dump window.__wxPerfLog，用于定位「键盘打开后前 2s 打不出字」。
        if os.environ.get("WX_PERF") == "1":
            try:
                self.page.evaluate("window.__wxPerf = true")
            except Exception:                    # noqa: BLE001
                pass
        # 等 Vue 根应用 + store 就绪，避免「编辑主页」等第一步在 store 未就绪时
        # setHomeList 静默失败、首页一直显示旧版默认联系人（孙权等）。
        try:
            self.page.wait_for_function(
                "() => { const vm = document.getElementById('app') && document.getElementById('app').__vue__;"
                " return !!(vm && vm.$store && window.__wxConfig); }",
                timeout=10_000)
        except Exception:                    # noqa: BLE001
            pass
        # store 就绪后立刻应用一次配置（DEFAULT_HOME/现代数据），
        # 避免主页长时间停留在 vue 自带旧种子联系人（孙权等）。
        try:
            self.page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        except Exception:                    # noqa: BLE001
            pass
        # 聊天背景：整片一致的背景。在增强注入完成后应用，覆盖 chat_exact.css 默认深色。
        # 用 window.__wxConfig.setChatBg 写入 --wx-chat-bg，与前端挑选入口走同一套逻辑。
        if CHAT_BG:
            try:
                self.page.evaluate(
                    "(u) => window.__wxConfig && window.__wxConfig.setChatBg"
                    " && window.__wxConfig.setChatBg(u)", CHAT_BG)
                print(f"[背景] 已应用聊天背景：{CHAT_BG}")
            except Exception as exc:                 # noqa: BLE001
                print(f"[背景] 应用聊天背景失败（忽略）：{exc}")
        # 立刻强制移除欢迎页，并滚动到会话列表，确保录屏第一帧就是「微信会话列表」
        # 而非欢迎图（旧版是等 1s 自动隐藏，期间录屏会一直拍到欢迎页，造成开头错误界面）。
        try:
            self.page.evaluate(
                "() => { const w = document.querySelector('.welcome');"
                " if (w) w.remove();"
                " const sec = document.querySelector('.app-content, .wechat-list');"
                " if (sec) sec.scrollTop = 0; }")
        except Exception:                    # noqa: BLE001
            pass
        self._start_ts = time.monotonic()   # 计时起点（含启动等待，如实报告总耗时）
        self._sleep_with_capture(WELCOME_WAIT)
        self.live_snapshot()   # 首帧：让编辑器立刻看到手机画面
        print("[启动] 页面已打开，开始执行剧本……")

    def stop(self):
        """关闭录制并合成按真实时间戳输出的 VFR MP4。"""
        global _PUMP_BOT
        self.page_open = False
        mp4_vfr_path = None
        # 先停止 screencast，避免合成期间继续往 _FRAMES 追加帧
        try:
            if getattr(self, "_cdp", None) is not None:
                self._cdp.send("Page.stopScreencast")
        except Exception:                    # noqa: BLE001
            pass
        try:
            if self.context:
                self.live_snapshot()   # 关闭前抓最后一帧，供编辑器显示
                self.context.close()
        except Exception as exc:                    # noqa: BLE001
            print(f"[警告] 视频收尾出现问题：{exc}")
        # 逐帧采集：按各帧真实交换时间戳合成 VFR 视频（保留真实帧时长）
        try:
            with _FRAME_LOCK:
                frames = list(_FRAMES)
                _FRAMES.clear()
            if FRAME_CAPTURE_ENABLED and frames:
                stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                prefix = f"wx_{OUT_TAG}_" if OUT_TAG else "wx_"
                mp4_vfr_path = os.path.join(VIDEO_DIR, prefix + stamp + ".mp4")
                ffmpeg = shutil.which("ffmpeg") or (_bundled_ffmpeg() if _bundled_ffmpeg else None)
                if ffmpeg:
                    WeChatAuto._assemble_vfr_mp4(ffmpeg, frames, mp4_vfr_path,
                                                 trim_sec=self.trim_head_sec)
                    # 把按键音效按视频时间轴混流进成品（实时播放弃用不影响这里）
                    mp4_vfr_path = self._mux_audio(ffmpeg, frames, mp4_vfr_path)
                else:
                    mp4_vfr_path = None
                    print("[提示] 未检测到 ffmpeg，跳过逐帧合成")
        except Exception as exc:                    # noqa: BLE001
            print(f"[警告] 逐帧合成出现问题：{exc}")
            mp4_vfr_path = None
        finally:
            _PUMP_BOT = None
            if self.browser:
                self.browser.close()
            if self._pw:
                self._pw.stop()
        # 记录结果到实例属性；last_mp4 为兼容旧字段（旧 25fps 录屏已删除，恒为 None）
        self.last_mp4 = None
        self.last_mp4_60 = mp4_vfr_path
        self.wall_seconds = (time.monotonic() - self._start_ts) if self._start_ts else None
        return mp4_vfr_path

    @staticmethod
    def _assemble_vfr_mp4(ffmpeg: str, frames, mp4_path: str, trim_sec: float = None) -> None:
        """把带真实交换时间戳的 JPEG 帧按真实停留时长合成视频。

        frames: [(timestamp_seconds, jpeg_bytes), ...]
        timestamp 是 CDP metadata.timestamp（浏览器合成器真实帧交换时刻，秒）。
        相邻两帧的时间差即该帧在屏幕上停留的真实时长。

        说明：ffmpeg 的 concat/image2 对「图片帧」会把时长量化到 1/25s 网格
        （每帧至少 0.04s，无法表达 60fps 的 ~0.0167s 间隔，会导致慢放）。因此这里
        以 FRAME_CAPTURE_FPS 作为时间基点：每帧按其真实停留时长复制到最接近的
        1/FRAME_CAPTURE_FPS 整数倍，使每帧在时间轴上停留时长贴合真实帧交换节奏，
        从而消除「CFR 网格重排」强制匀化造成的时间量化卡顿。
        开头按 TRIM_HEAD_SEC 跳过加载期。仅当 FRAME_OUT_W>0 时按该宽度缩放。
        """
        if not frames:
            raise ValueError("没有采集到任何帧")
        frames = sorted(frames, key=lambda f: f[0])
        t0 = frames[0][0]
        trim = TRIM_HEAD_SEC if trim_sec is None else float(trim_sec)
        # 跳过开头加载期（欢迎页/白屏/旧种子/列表停留）
        keep = [(ts, jpeg) for ts, jpeg in frames if ts >= t0 + trim]
        if not keep:
            raise ValueError("跳过加载期后没有帧")
        fps = float(FRAME_CAPTURE_FPS)
        # 平均帧间隔：作为最后一帧的兜底时长
        gaps = [keep[i + 1][0] - keep[i][0] for i in range(len(keep) - 1)]
        gaps = [g for g in gaps if g > 0]
        last_dur = (sum(gaps) / len(gaps)) if gaps else (1.0 / fps)
        # —— 消除「放大到左上角」闪帧：逐帧把尺寸归一化到 600x1300 ——
        # 根因：某些转场瞬间（键盘收起/消息进出/滚动）合成器表面被短暂「等比放大」，screencast
        # 以 maxWidth=2600 把这块更大的表面原尺寸抓入，合成阶段 crop:0:0 便只露出放大后的左上角，
        # 产生「整页放大＋右侧被裁、只有左上角可见」的错位帧。
        # 修复：写帧前逐帧归一化。用纵横比区分两类「非 600x1300」帧——
        #   · 等比帧（宽高比≈600:1300，尺寸更大）= 整页被等比放大 → 整幅缩回 600×1300，显示完整页面；
        #   · 非等比帧（如转场时底页+滑入子页并排撑宽）= 真实转场 → 仍裁左上 600×1300 见底页。
        # 放大帧不会再被裁到左上角，转场帧行为与原来一致；直接由尺寸判定，不依赖脆弱的内容检测。
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="wxvfr_")
        _PIL = None
        try:
            from PIL import Image as _PIL_IMPORT      # noqa: N813
            _PIL = _PIL_IMPORT
        except Exception:                            # noqa: BLE001
            _PIL = None
        try:
            import io as _io
            out_idx = 0

            def _out_write(jpeg_bytes):
                nonlocal out_idx
                with open(os.path.join(tmpdir, "f%06d.jpg" % out_idx), "wb") as _fh:
                    _fh.write(jpeg_bytes)
                out_idx += 1

            def _norm(jpeg_bytes):
                """单帧归一化：尺寸非 600x1300 的按等比缩放/裁切回规整尺寸，失败回退原字节。"""
                if _PIL is None:
                    return jpeg_bytes
                try:
                    _im = _PIL.open(_io.BytesIO(jpeg_bytes))
                    _w, _h = _im.size
                    if (_w, _h) == (VIEWPORT_W, VIEWPORT_H):
                        return jpeg_bytes
                    _app_ar = VIEWPORT_W / float(VIEWPORT_H)
                    _ar = _w / float(_h)
                    if abs(_ar - _app_ar) <= 0.06:
                        # 等比放大/缩小帧 → 缩到 600x1300（显示完整页面，消除左上角错位）
                        _im2 = _im.convert("RGB").resize(
                            (VIEWPORT_W, VIEWPORT_H), _PIL.LANCZOS)
                    else:
                        # 非等比转场帧 → 裁左上 600x1300，不足补黑（保持原有转场视觉）
                        _cw = min(VIEWPORT_W, _w); _ch = min(VIEWPORT_H, _h)
                        _im2 = _im.convert("RGB").crop((0, 0, _cw, _ch))
                        if (_cw, _ch) != (VIEWPORT_W, VIEWPORT_H):
                            _canvas = _PIL.new("RGB", (VIEWPORT_W, VIEWPORT_H), (0, 0, 0))
                            _canvas.paste(_im2, (0, 0))
                            _im2 = _canvas
                    _buf = _io.BytesIO()
                    _im2.save(_buf, "JPEG", quality=FRAME_JPEG_QUALITY)
                    return _buf.getvalue()
                except Exception:             # noqa: BLE001
                    return jpeg_bytes          # 单帧归一化失败则以原尺寸写入

            def _visual_diff(jpeg_a, jpeg_b):
                """下采样灰度归一化差异（0~1）。只在长间隔且 PIL 可用时触发两次解码。
                缩略图到 32x70，判定「前后画面是否明显不同」不需要全分辨率。"""
                if _PIL is None:
                    return 0.0
                try:
                    _a = _PIL.open(_io.BytesIO(jpeg_a)).convert("L").resize((32, 70))
                    _b = _PIL.open(_io.BytesIO(jpeg_b)).convert("L").resize((32, 70))
                    _pa = _a.load(); _pb = _b.load()
                    _s = 0.0; _n = 0
                    for _x in range(32):
                        for _y in range(70):
                            _s += abs(_pa[_x, _y] - _pb[_x, _y]); _n += 1
                    return _s / (_n * 255.0)
                except Exception:             # noqa: BLE001
                    return 0.0

            for i, (ts, jpeg) in enumerate(keep):
                dur = (keep[i + 1][0] - ts) if i + 1 < len(keep) else last_dur
                n = max(1, int(round(dur * fps)))
                # —— 长间隔视觉过渡 ——
                # 复制总数仍为 n：混合帧只替换「本帧停留份额」，后续帧绝对输出位置不变，
                # 与 _mux_audio 的量化时间轴保持一致（音画不错位）。
                hold = n
                blend = 0
                if (n >= GAP_BLEND_MIN_FRAMES and i + 1 < len(keep)
                        and _PIL is not None):
                    _d = _visual_diff(jpeg, keep[i + 1][1])
                    if _d >= GAP_BLEND_DIFF_EPS:
                        hold = max(2, int(round(n * GAP_BLEND_HOLD_FRAC)))
                        blend = n - hold
                if blend <= 0:
                    for _ in range(hold):
                        _out_write(_norm(jpeg))
                    continue
                for _ in range(hold):
                    _out_write(_norm(jpeg))
                _im_a = _PIL.open(_io.BytesIO(_norm(jpeg))).convert("RGB")
                _im_b = _PIL.open(_io.BytesIO(_norm(keep[i + 1][1]))).convert("RGB")
                _alphas = [(_k / float(blend)) for _k in range(1, blend + 1)]
                for _alpha in _alphas:
                    _mix = _PIL.blend(_im_a, _im_b, _alpha)
                    _buf = _io.BytesIO()
                    _mix.save(_buf, "JPEG", quality=FRAME_JPEG_QUALITY)
                    _out_write(_buf.getvalue())
            if not out_idx:
                raise ValueError("按真实时长扩展后没有帧")
            vf_parts = []
            if FRAME_OUT_W and FRAME_OUT_W != VIEWPORT_W:
                # 按手机屏目标宽度缩放到 css 分辨率（保持 600:1300 纵横比）
                out_h = int(round(FRAME_OUT_W * VIEWPORT_H / VIEWPORT_W))
                vf_parts.append("scale=%d:%d:flags=lanczos" % (FRAME_OUT_W, out_h))
                vf_parts.append("unsharp=5:5:%.2f:5:5:0" % 0.45)
            vf = ",".join(vf_parts)
            cmd = [ffmpeg, "-y", "-loglevel", "error",
                   "-framerate", "%.4f" % fps,
                   "-i", os.path.join(tmpdir, "f%06d.jpg")]
            if vf:
                cmd += ["-vf", vf]
            fps_flag = WeChatAuto._ffmpeg_fps_mode_flag(ffmpeg)
            cmd += ["-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    fps_flag, "cfr", mp4_path]
            # capture_output 拿到 ffmpeg 的 stderr，失败时能报出真正原因（而不是只有一个退出码）；
            # 失败时 ffmpeg 往往已写下一个只有容器头、没有流数据的残缺 mp4，务必删掉它，
            # 否则编辑器 _latest_video() 会把这 261 字节的残缺文件当「最新视频」上报成「已生成」。
            try:
                _proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                                       timeout=FFMPEG_VIDEO_TIMEOUT)
            except subprocess.TimeoutExpired:
                # ffmpeg 超时：subprocess.run 已杀掉 ffmpeg，但可能留下残缺成品，删掉以免被误报
                try:
                    if os.path.exists(mp4_path):
                        os.remove(mp4_path)
                except OSError:                    # noqa: BLE001
                    pass
                raise RuntimeError(
                    "ffmpeg 合成超时（超过 %d 秒），已删除残缺成品" % FFMPEG_VIDEO_TIMEOUT)
            if _proc.returncode != 0:
                try:
                    if os.path.exists(mp4_path):
                        os.remove(mp4_path)
                except OSError:                    # noqa: BLE001
                    pass
                raise RuntimeError(
                    "ffmpeg 合成失败（退出码 %s），已删除残缺成品：\n%s"
                    % (_proc.returncode, (_proc.stderr or "").strip())
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    def _ffmpeg_fps_mode_flag(ffmpeg: str) -> str:
        """返回当前 ffmpeg 版本应使用的帧率控制选项。

        FFmpeg 5.1 起用 `-fps_mode` 取代旧的 `-vsync`（7.0 后 `-vsync` 已移除）。
        <5.1 的老版本仍只能用 `-vsync`。这里按主版本号二选一，保证新老 ffmpeg 都能出片。
        """
        try:
            out = subprocess.run([ffmpeg, "-version"], capture_output=True,
                                 text=True, timeout=10).stdout or ""
            m = re.search(r"ffmpeg version (\d+)\.", out)
            if m and int(m.group(1)) >= 5:
                return "-fps_mode"
        except Exception:                    # noqa: BLE001
            pass
        return "-vsync"

    # ---------- 基础工具 ----------

    def _wait(self, seconds: float):
        """自然等待（加一点随机抖动，避免机械感）"""
        jitter = random.uniform(-0.08, 0.15) if seconds > 0.3 else 0
        self._sleep_with_capture(max(0.05, (seconds + jitter) / SPEED))
        self.live_snapshot()

    def _start_screencast(self):
        """开启 CDP screencast：浏览器每个合成帧主动推 JPEG，写入 _FRAMES。

        固定走此方案（旧版 page.screenshot() 采样已删除）。同步 API 事件只能在
        Playwright 调用期间派发，故配合 _pump_wait 分片 wait_for_timeout 来收帧。
        """
        if getattr(self, "_cdp", None) is not None:
            return
        self._cdp = self.context.new_cdp_session(self.page)
        self._cdp.on("Page.screencastFrame", self._on_screencast_frame)
        self._cdp.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": FRAME_JPEG_QUALITY,
            "everyNthFrame": 1,          # 每个合成帧都推，不隔帧
            "maxWidth": FRAME_SURFACE_MAX_W,   # 放宽采集宽上限，容纳转场被 transform 撑宽的合成器表面，避免整幅下采样成「缩左+黑边」
            "maxHeight": FRAME_SURFACE_MAX_H,  # 放宽采集高上限：高度也被撑大的表面（如键盘/覆盖层顶出视口）若只给 1300 会被整幅下采样，
                                               # 导致内容被缩到左上角、其余大片黑（即「被撑大→缩左上角」闪帧）。放宽后全尺寸传入，
                                               # 再由合成阶段 crop=600:1300:0:0 裁回手机屏，内容保持原始大小。
        })

    def _on_screencast_frame(self, params):
        """screencast 推送帧：解码后写入 _FRAMES，并 ack 让浏览器继续推。

        帧时间直接用 CDP metadata.timestamp（浏览器合成器真实帧交换时刻，秒）。
        VFR 合成时相邻两帧的时间差就是该帧在屏幕上停留的真实时长，按这个节奏
        输出即可消除「CFR 网格重排」造成的时间量化卡顿。
        """
        import base64
        # 关键：先 ACK 再解码。CDP screencast 是「每帧等 ack 才推下一帧」，
        # base64 解码 + 写缓存是较慢的一步；若放在 ack 前，浏览器会被这一帧的解码
        # 时间卡住、下一帧晚到，动画段（键盘弹/收、快打字）就会出现连续掉帧。
        # 这里先回 ack 让浏览器立刻继续推帧，解码/写缓存放在其后，避免拖慢推帧节奏。
        try:
            self._cdp.send("Page.screencastFrameAck",
                           {"sessionId": params["sessionId"]})
        except Exception:                    # noqa: BLE001
            pass
        try:
            jpeg = base64.b64decode(params["data"])
            meta = params.get("metadata") or {}
            ts = meta.get("timestamp", time.monotonic())
            # 时钟校准：用「CDP 视频时间戳 - 本地墙钟」推算二者常数偏移。
            # 音效事件用 time.time()（墙钟）记录时间，混流时靠这个偏移精确对齐视频时间轴。
            # —— 关键：不能只用首帧校准。screencast 帧从「浏览器捕获」到「Python 收到」
            #    存在推送延迟；用首帧（冷启动延迟往往最大）会把这个延迟烘进偏移，
            #    导致所有音效整体偏早。因 cdp_ts - time.time() = 真实偏移 K - 延迟，
            #    延迟越小该项越大，故对逐帧取「最大」即逼近真实 K，且永不越过 K（不会偏晚）。
            _cdp_wall = float(ts) - time.time()
            if not self._audio_calibrated:
                self._audio_offset = _cdp_wall
                self._audio_calibrated = True
            elif self._audio_offset < _cdp_wall:
                self._audio_offset = _cdp_wall
            with _FRAME_LOCK:
                _FRAMES.append((float(ts), jpeg))
        except Exception:                    # noqa: BLE001
            pass

    def _sleep_with_capture(self, seconds: float):
        """等待 + 派发采集帧：把等待拆成小片，期间派发 screencast 帧。

        键盘弹出/按键按压/页面切换等动画过渡发生在等待期间，
        用 _pump_wait 分片 wait_for_timeout 才能让这些动画帧被推入 _FRAMES
        （否则动画段只有 1~2 帧，VFR 合成后这些帧停留时长会失真，观感仍跳）。
        关闭采集时退化为纯 time.sleep。
        """
        if FRAME_CAPTURE_ENABLED and seconds > 0:
            _pump_wait(seconds)
        else:
            time.sleep(seconds)

    def live_snapshot(self, force: bool = False):
        """主线程抓取一帧手机页面 JPEG 存入共享缓存，供实时画面服务返回。

        顺带处理编辑器发来的元素编辑 / 点击命令（同样必须在主线程执行）。
        必须在主线程（自动化线程）调用；截图节流到最多每 0.4 秒一张，
        避免截图拖慢打字等精细动作。screencast 帧由 _on_screencast_frame
        独立推入 _FRAMES，与此处 live 预览截图相互独立。
        """
        self._process_live_commands()
        self._grab_frame(force)

    def _grab_frame(self, force: bool = False):
        """更新实时预览缓存帧（force=True 跳过节流，用于编辑/点击后立即刷新）。

        关键：不再默认调 page.screenshot() —— 它在 CDP screencast 逐帧采集的同时
        会再让浏览器强制截一整张图，抢占合成器导致 screencast 掉帧/闪帧。
        改为优先复用已经采到的 screencast 帧（_FRAMES 最后一帧，与成片一致），
        既彻底消除闪帧，又保证编辑器实时看到的画面和最终视频一致。
        仅当 _FRAMES 还没有任何帧（如编辑模式刚启动、尚未泵帧）时才回退 page.screenshot()。
        """
        if not getattr(self, "_live_enabled", False):
            return
        now = time.time()
        with _LIVE_LOCK:
            if not force and now - _LIVE_FRAME["ts"] < 0.4:
                return
        jpeg = None
        with _FRAME_LOCK:
            if _FRAMES:
                jpeg = _FRAMES[-1][1]
        if jpeg is None:
            # 无已采帧：回退到一次轻量截图（主要覆盖编辑模式初始/静止期）
            page = getattr(self, "page", None)
            if page is None or page.is_closed():
                return
            try:
                jpeg = page.screenshot(type="jpeg", quality=60)
            except Exception:                       # noqa: BLE001
                return
        with _LIVE_LOCK:
            _LIVE_FRAME["data"] = jpeg
            _LIVE_FRAME["ts"] = now

    def _process_live_commands(self):
        """逐条执行编辑器命令队列（仅主线程调用，Playwright 安全）。"""
        global _LIVE_QUEUE, _LIVE_RESULTS
        while True:
            with _LIVE_LOCK:
                if not _LIVE_QUEUE:
                    _LIVE_QUEUE_EVENT.clear()
                    return
                cid, cmd, args = _LIVE_QUEUE.pop(0)
            try:
                if cmd == "pick":
                    result = self.pick_at(float(args.get("x", 0)), float(args.get("y", 0)))
                elif cmd == "edit":
                    result = self.apply_edit(args)
                elif cmd == "tap":
                    self.page.mouse.click(float(args.get("x", 0)), float(args.get("y", 0)))
                    _pump_wait(0.35)
                    result = {"ok": True}
                elif cmd == "type":
                    self.page.keyboard.type(str(args.get("text", "")))
                    result = {"ok": True}
                else:
                    result = {"ok": False, "msg": "未知命令：" + str(cmd)}
            except Exception as exc:                # noqa: BLE001
                result = {"ok": False, "msg": str(exc)}
            with _LIVE_LOCK:
                _LIVE_RESULTS[cid] = result
            if cmd in ("edit", "tap", "type"):
                self._grab_frame(True)

    def pick_at(self, x: float, y: float) -> dict:
        """拾取视口坐标 (x, y) 下的可编辑元素，返回描述信息。"""
        self._ensure_enhance()
        return self.page.evaluate(PICK_JS, {"x": x, "y": y})

    def apply_edit(self, payload: dict) -> dict:
        """按拾取到的元素 id 修改内容（文字 / 图片 / 背景 / 我的资料）。"""
        self._ensure_enhance()
        return self.page.evaluate(EDIT_JS, payload)

    def _ensure_enhance(self):
        """确保页面增强脚本已注入（幂等）"""
        try:
            self.page.evaluate("window.__wxEnhanced === true")
        except Exception:                           # noqa: BLE001
            inject_overlays(self.page)

    # ---------- 键盘模拟 ----------

    def _kb_is_open(self) -> bool:
        """查询当前键盘是否已弹出（读 JS 侧 __wxKeyboard.visible）。

        用于 _kb_show/_kb_hide 判断是否真的发生了「开合过渡」。过渡动画只需在真正的
        弹出/收起瞬间等待；若键盘状态本就如此（例如连续 [我方打字] 之间键盘一直开着），
        就不必再睡固定时长——既能消掉每一句之间的多余停顿，又不会打断动画过渡造成画面错乱。
        """
        try:
            return bool(self.page.evaluate(
                "window.__wxKeyboard && window.__wxKeyboard.visible === true"))
        except Exception:                    # noqa: BLE001
            return False

    def _kb_show(self):
        """弹出手机键盘（带动画），并让聊天内容滚到最新消息（信息多时底部可见）"""
        already = self._kb_is_open()
        self.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.show()")
        self._scroll_chat_bottom()
        # 仅当键盘从「收起」过渡到「弹出」才等待动画；已开着则不再空等
        if not already:
            self._sleep_with_capture(KB_OPEN_WAIT)

    def _kb_hide(self):
        """收起手机键盘（带动画），并复置聊天区留白"""
        already = self._kb_is_open()
        self.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.hide()")
        self._scroll_chat_bottom()
        # 仅当键盘从「弹出」过渡到「收起」才等待动画；已收起则不再空等
        if already:
            self._sleep_with_capture(0.3)

    def _scroll_chat_bottom(self, pad_bottom: int = None):
        """让聊天区滚动到最新消息（配合键盘/输入栏，信息多时底部内容不会被遮住）。

        消息区 .dialogue-section 高度已随键盘弹出自动扣除键盘高（见 chat_extra.js 的
        body.wxkb-open 规则），这里只需滚它自身的 scrollTop 到底，最新消息即停在输入栏上方。
        不碰 .dialogue.sub-page（那是 vue 滑动子页，直接滚会触发子页收回、误返回主页）。
        """
        self._ensure_enhance()
        try:
            self.page.evaluate("""(pb) => {
                const sec = document.querySelector('.dialogue-section');
                if (!sec) return;
                if (pb !== null) sec.style.paddingBottom = pb + 'px';
                // 仅当消息区内容溢出(历史铺满)才滚到底，贴住输入栏；
                // 未溢出时保持顶部锚定：键盘弹出只压缩空区，不把消息/头部往上顶。
                if (sec.scrollHeight > sec.clientHeight) sec.scrollTop = sec.scrollHeight;
            }""", pad_bottom)
        except Exception:                    # noqa: BLE001
            pass

    def _kb_hold_values(self, base_ms: int = None):
        """返回 (cadence_ms, display_ms)：解耦「速度」与「按压可见性」。

        cadence_ms：键与键之间的实际推进间隔（决定打字速度快慢）。被 TYPE_SPEED 缩放，
                    30 倍时约 3~4ms，速度照旧极快。
        display_ms：按键高亮的可视保持时长。有 KEY_HOLD_MIN_MS 下限，即使 30 倍速
                    也至少保留约 1.5 帧(24ms)的高亮，让人看得到在敲键、不会动画全消失。
            - TYPE_SPEED 较大时 display>cadence：多个键高亮会在同一帧重叠、像"快速连打"；
            - TYPE_SPEED=1 时两者相等（维持原真人节奏，不受影响）。
        """
        base_ms = base_ms if base_ms is not None else random.randint(*KEY_HOLD_MS)
        if TYPE_SPEED > 1.05:
            cadence = max(1, int(round(base_ms / TYPE_SPEED)))
        else:
            cadence = base_ms
        display = max(int(round(KEY_HOLD_MIN_MS)), cadence)
        return cadence, display

    def _kb_press(self, label: str, hold_ms: int = None, shift: str = None):
        """按键高亮动画；hold_ms 为按下保持时长（录屏需可见）。
        shift: 'on' 单次大写 / 'caps' 大写锁定 / 'off' 小写 / None 由 label 自动判断"""
        cadence, display = self._kb_hold_values(hold_ms)
        if shift is None and isinstance(label, str) and len(label) == 1 and label.isupper():
            shift = 'on'
        if shift:
            self.page.evaluate(
                "window.__wxKeyboard && window.__wxKeyboard.setShift(%r)" % shift)
        press_label = label.lower() if isinstance(label, str) else label
        # 传给 JS 的是"可视保持时长"(display)，保证高亮能被录到；但实际推进速度用
        # cadence（更快），二者解耦后既能保持快、又保留部分键盘动画。
        ret = self.page.evaluate(
            "window.__wxKeyboard && window.__wxKeyboard.pressKey(%r, %d)"
            % (press_label, max(1, display)))
        self._sleep_with_capture(cadence / 1000.0)
        # 挂音效：键盘每按一次键（打字/回删/发送）就记录并播放一次。
        # 打字被 TYPE_SPEED 加速后按键间隔已变短，音效天然就是加速后的节奏。
        # 时间戳优先用 JS 报告的「按键高亮真正发生」时刻（视觉锚点）。
        name = self._sound_name_for_label(label)
        if name:
            if name == "send":
                # 发送声不锚定按键时刻：气泡要等 Enter + Vue nextTick 渲染，
                # 由 human_type 发送后调用 _finalize_send_sound 锚定到气泡出现时刻。
                if isinstance(ret, (int, float)) and ret > 0:
                    self._pending_send_wall = ret / 1000.0
                else:
                    self._pending_send_wall = None
            else:
                self._emit_sound(name, ret)

    def _kb_type(self, label: str, hold_ms: int = None, shift: str = None):
        """一次调用完成「插入字符 + 按键高亮」（配合 keyboard.js 的 pressType）。

        旧的打字流程是 page.keyboard.type(letter) + _kb_press(letter) 两次浏览器往返，
        这部分不随 TYPE_SPEED 缩放，开到 20~30 倍后被 CDP 延迟卡在 ~15x。
        改用 pressType 把「写入字符 + 按下高亮」合并成一次 evaluate/往返，
        高倍速下速度才能如实翻倍（用户所需的"真实 30 倍"）。
        """
        cadence, display = self._kb_hold_values(hold_ms)
        if shift is None and isinstance(label, str) and len(label) == 1 and label.isupper():
            shift = 'on'
        if shift:
            self.page.evaluate(
                "window.__wxKeyboard && window.__wxKeyboard.setShift(%r)" % shift)
        press_label = label.lower() if isinstance(label, str) else label
        ret = self.page.evaluate(
            "window.__wxKeyboard && window.__wxKeyboard.pressType(%r, %d)"
            % (press_label, max(1, display)))
        self._sleep_with_capture(cadence / 1000.0)
        name = self._sound_name_for_label(label)
        if name:
            # 时间戳优先用 JS 报告的「写入+高亮完成」时刻（视觉锚点）。
            self._emit_sound(name, ret)
        return ret

    def _type_run(self, letters, hint_word, hint_py):
        """一次往返敲完一整段拼音：调用 keyboard.js 的 pressRun 批量打字。

        逐键的「按键高亮 + 写入字符」由浏览器按节奏推进，Python 不再每字母一趟
        page.evaluate。高倍速(≥20x)下逐键往返会把高亮与候选刷新切成错位帧、观感一顿一顿
        （正是「打一半卡一下」的来源）；改为浏览器内自驱动后节奏均匀、无往返抖动。
        顺带把本段目标词预告(hint)随批传入，省一次 setTopHint 往返。
        等逐键推进完成后，读回每键墙钟时刻作为打字声锚点（≥20x 按连打段合并）。
        """
        letters = list(letters)
        if not letters:
            return
        cadence, display = self._kb_hold_values(random.randint(*KEY_HOLD_MS))
        self.page.evaluate(
            "(args) => { const kb = window.__wxKeyboard; if (!kb || !kb.pressRun) "
            "return { ok: false }; return kb.pressRun(args[0], args[1], args[2], "
            "args[3], args[4]); }",
            [letters, cadence, display, hint_word, hint_py])
        # 等浏览器逐键推进完成；wait_for_function 默认在页内 rAF 上轮询，
        # 这次等待同时就是 screencast 帧的派发泵——动画帧不会漏。
        try:
            self.page.wait_for_function(
                "() => { const kb = window.__wxKeyboard; return !kb || kb.typingBusy !== true; }",
                timeout=max(1500, int(len(letters) * 120)))
        except Exception:                  # noqa: BLE001
            return   # 超时/异常不阻断：连打段未收口，后续会自然推进
        # 每键墙钟（视觉锚点）→ 打字声；≥20x 下 _emit_sound 按连打段合并，逐键近乎零成本
        try:
            walls = self.page.evaluate("window.__typeWalls || []")
        except Exception:                  # noqa: BLE001
            walls = []
        for w in walls:
            if isinstance(w, (int, float)) and w > 0:
                self._emit_sound("type", w)

    # ---------- 音效：按键映射 / 实时播放 / 成品音轨合成 ----------

    @staticmethod
    def _sound_name_for_label(label):
        """键盘按键 label → 音效名：backspace→删除、send→发送，其余实体键→打字。
        布局切换/Shift/语音/表情等无实体敲击的功能键返回 None（不出声）。"""
        if not label:
            return None
        low = str(label).lower()
        if low == "backspace":
            return "delete"
        if low == "send":
            return "send"
        if low in ("shift", "globe", "mic", "123", "abc", "#+="):
            return None
        # 字母/数字/标点/空格 → 打字声
        return "type"

    def _emit_sound(self, name: str, wall_ms=None):
        """记录一次音效事件（供 stop() 合成成品音轨），并按需实时播放。

        wall_ms：JS 侧 Date.now() 报告的「视觉动作真正发生的墙钟毫秒」。
        传入时用它作为事件时间（声音锚定到画面动作，而非 Python 发命令时刻，
        消除 CDP 往返+Vue 渲染+合成帧带来的「先有声音后出字」系统性延迟）。
        缺省回退 time.time()。
        """
        if not ENABLE_AUDIO or not self._sounds or name not in self._sounds:
            return
        if self._mute_sound:
            return   # 预热等「不进成品」的敲键：不记录音效，也不实时播放
        now = (wall_ms / 1000.0) if isinstance(wall_ms, (int, float)) and wall_ms > 0 \
            else time.time()
        # —— 高速打字：把一段连续的打字合并成一条「持续打字声」，用原生音轨按敲击
        #    时长裁剪，不再逐键叠加单个「哒哒哒」。降低速(TYPE_SPEED<阈值)仍逐键。
        if (name == "type" and TYPE_SPEED >= CONTINUOUS_TYPE_MIN_SPEED
                and "continuous_type" in self._sounds):
            # 关键：若与上一次打字间隔过久（对方插话/动作切换/跨等待），先把上一段
            # 连打收口成一条持续声，再开启新一段，避免把长时间停顿也包进同一条音轨。
            if self._ct_open and (now - self._ct_last) > CONTINUOUS_TYPE_MAX_GAP:
                self._seal_continuous_type()
            if not self._ct_open:
                self._ct_open = True
                self._ct_start = now
                self._ct_last = now
                self._ct_first_commit_wall = None   # 新连打段：重置上屏锚点
                # 实时播放（若有）：连打发一条持续打字声，替代逐键点击
                if LIVE_AUDIO and not self._ct_live_played:
                    self._play_live("continuous_type")
                    self._ct_live_played = True
            else:
                self._ct_last = now
            return   # 不逐键记录/播放打字音
        # 其它音效（delete/send，或低速打字的逐键声）：先闭合未收口的连打段
        self._seal_continuous_type()
        self._audio_events.append((now, name))
        if LIVE_AUDIO:
            self._play_live(name)

    def _note_commit_wall(self, wall_ms):
        """记录本连打段第一次「字真正上屏」的墙钟时刻（来自 commitByPhrase 的 JS 返回值）。

        _seal_continuous_type 收口时若存在该锚点，持续打字声起点就从「第一键」
        改为「首次上屏」——字出现的声音才响起，彻底消除第一段「先有打字声、后出字」。
        若一段连打从未上屏（如纯英文直输），退回用第一键时刻，视觉本就逐键同步。
        """
        if isinstance(wall_ms, (int, float)) and wall_ms > 0:
            if self._ct_open and self._ct_first_commit_wall is None:
                self._ct_first_commit_wall = wall_ms / 1000.0

    def _seal_continuous_type(self):
        """把当前「连打段」收口成一条持续音效事件；无则忽略。

        只在高速打字(TYPE_SPEED ≥ 阈值)时由 _emit_sound 触发，低速打字本就不存在该状态。
        收口时额外追加一小段收尾(0.06s)，避免连续打字声在最后一键后戛然而止。
        连打至视频结尾仍未收口时，_mux_audio 开头会补调一次，保证事件不被遗漏。
        若段内曾 commit 上屏（中文），起点对齐到首次上屏时刻，避免声音先于字。
        """
        if not self._ct_open:
            return
        start = self._ct_start
        if self._ct_first_commit_wall is not None:
            # 声音从「第一次字上屏」开始（字先出现、声音跟上），而不是从第一键开始。
            # 仅当上屏发生在连打段起点之后才生效（防止乱序把起点扯到段外）。
            if self._ct_first_commit_wall > start:
                start = self._ct_first_commit_wall
        dur = max(0.0, self._ct_last - start)
        self._audio_events.append((start, "continuous_type", dur + 0.06))
        self._ct_open = False
        self._ct_live_played = False
        self._ct_first_commit_wall = None

    def _finalize_send_sound(self):
        """把发送声锚定到「我方气泡真正渲染」的视觉时刻，而不是按键/回车命令时刻。

        发送链路：按 send 键高亮 → Enter 回车触发 keydown → pushMsgToStore 推 store
        → Vue nextTick 渲染气泡。声音若记在按键时刻，会比气泡早几十~几百毫秒。
        这里在 Enter 后等待 JS 侧 nextTick 记录 __wxLastSelfBubbleWall（ms），
        用该时刻放置 send 音效；等不到（渲染失败/超时）才回退按键时刻或当前时刻。
        """
        # 发送声属于「非打字音效」：无论是否放音，都先闭合未收口的连打段，
        # 保证事件顺序与真实节奏一致（打字声收口在前、发送声在后）。
        self._seal_continuous_type()
        if not ENABLE_AUDIO or not self._sounds or "send" not in self._sounds:
            self._pending_send_wall = None
            return
        if self._mute_sound:
            self._pending_send_wall = None
            return
        anchor = self._pending_send_wall
        self._pending_send_wall = None
        bubble_ms = None
        try:
            for _ in range(10):            # 最多等 ~200ms，覆盖 Vue nextTick 渲染
                v = self.page.evaluate("window.__wxLastSelfBubbleWall || 0")
                # 防串：只接受「本轮的」气泡时刻——必须晚于 send 键高亮时刻
                # （上一次发送残留的旧值会早于本轮 anchor，直接忽略继续等）。
                if isinstance(v, (int, float)) and v > 0:
                    if anchor is None or (v / 1000.0) >= anchor:
                        bubble_ms = v
                        break
                _pump_wait(0.02)
        except Exception:                  # noqa: BLE001
            bubble_ms = None
        if isinstance(bubble_ms, (int, float)) and bubble_ms > 0:
            wall = bubble_ms / 1000.0
        elif anchor is not None:
            wall = anchor                  # 拿不到气泡时刻：退回 send 键高亮时刻
        else:
            wall = time.time()
        self._audio_events.append((wall, "send"))
        if LIVE_AUDIO:
            self._play_live("send")

    def _play_live(self, name: str):
        """用 winsound 异步实时播放一个音效（高速连发时可能截断，属可接受的机械感）。"""
        try:
            import winsound
            winsound.PlaySound(sound_engine.wav_bytes(self._sounds[name]),
                               winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:                    # noqa: BLE001
            pass

    def _mux_audio(self, ffmpeg: str, frames, mp4_path: str) -> str:
        """把按键事件按「视频量化时间轴」合成音轨，用 ffmpeg -c:v copy 混流出有声成品。

        frames: 采集到的 [(cdp_ts, jpeg), ...]（与 _assemble_vfr_mp4 同一批）。

        关键：视频不是按原始 metadata.timestamp 播放的——_assemble_vfr_mp4 用
        round(dur*fps) 把每帧复制到 60fps 网格重新量化，输出视频时间轴与该原始
        时间戳并不一致（会随时间产生漂移）。因此音效不能放在原始时间戳上，而要
        放在「视频真正播放到」的量化时间轴上：先按 _assemble_vfr_mp4 的复制规则算出
        每帧在输出视频里的起始时刻，再让每个事件落在其对应帧的输出时刻上。

        事件用 time.time()（墙钟）记录；经 _audio_offset 映射到 CDP 时间戳，再找出
        该时刻落在哪个「原始帧显示区间」，取其输出起始时刻作为音效位置。
        无事件、无背景音乐或混流失败时原样返回 mp4_path（成品保持无声/无背景音乐）。
        """
        if not frames:
            return mp4_path
        frames = sorted(frames, key=lambda f: f[0])
        t0 = frames[0][0]
        start = t0 + float(self.trim_head_sec)
        fps = float(FRAME_CAPTURE_FPS)
        keep = [(ts, jpeg) for ts, jpeg in frames if ts >= start]
        if not keep:
            return mp4_path
        # 用与 _assemble_vfr_mp4 一致的复制规则，算出每帧在输出视频里的起始时刻，
        # 并记录它对应的「原始时间显示区间 [ts_start, ts_end)」。
        intervals = []                      # (out_start, ts_start, ts_end)
        cum = 0.0
        for i, (ts, _j) in enumerate(keep):
            nxt = keep[i + 1][0] if i + 1 < len(keep) else (ts + 1.0 / fps)
            dur = nxt - ts
            n = max(1, int(round(dur * fps)))
            intervals.append((cum / fps, ts, nxt))
            cum += n
        out_dur = cum / fps                  # 输出视频总时长（秒）
        first_kept_ts = keep[0][0]           # 视频首帧的原始时间戳（trim 之后的第一帧）
        # 若连打段一直打到视频结尾仍没被非打字事件收口，这里补收口，避免事件遗漏
        self._seal_continuous_type()
        # ---- 临时诊断：打印音频时钟与开头若干事件的对齐情况 ----
        if os.environ.get("WX_DEBUG_AUDIO"):
            print(f"[DBG] _audio_offset={self._audio_offset:.4f}  first_kept_ts={first_kept_ts:.4f}  "
                  f"n_frames={len(keep)}  out_dur={out_dur:.3f}")
            print(f"[DBG] intervals[:6]=" + ", ".join(
                f"(o={o:.3f},ts={a:.3f}~{b:.3f})" for o, a, b in intervals[:6]))
            print(f"[DBG] 事件前 6 条（len/type/cdp_ts/qpos）:")
        track = sound_engine.AudioTrack()
        placed = 0
        for ev in self._audio_events:
            if len(ev) == 3:               # 连续打字声：(wall_ts, name, dur_sec)
                wall_ts, name, dur = ev
            else:                           # 普通逐键音：(wall_ts, name)
                wall_ts, name = ev
                dur = None
            if name not in self._sounds:
                continue
            cdp_ts = wall_ts + self._audio_offset
            # 落在被 trim 的加载期（视频开始之前）的事件直接丢弃，避免被误放到视频末尾
            if cdp_ts < first_kept_ts:
                continue
            # 事件须放在「真正显示该动作」的那一帧：帧 i 在 cdp_ts_i 被捕获，
            # 只反映 ts_i 一瞬间的状态；动作发生在 cdp_ts，要到「第一个捕获时刻
            # >= cdp_ts」的帧才可见。取第一个 ts_s >= cdp_ts 的区间起点，
            # 而不是「包含该时刻」的区间（后者是动作之前捕获的帧，声音会早一帧）。
            qpos = None
            for out_s, ts_s, ts_e in intervals:
                if ts_s >= cdp_ts:
                    qpos = out_s
                    break
            if qpos is None:
                qpos = intervals[-1][0]     # 落在末帧之后：放视频末尾，仍不被截断
            if qpos > out_dur:
                qpos = out_dur
            if os.environ.get("WX_DEBUG_AUDIO") and placed < 6:
                _iv = intervals[-1]
                for _o, _a, _b in intervals:
                    if _a <= cdp_ts < _b:
                        _iv = (_o, _a, _b); break
                print(f"[DBG]   #{placed:>2} {name:<16} dur={dur if dur is not None else '-':<6}"
                      f" cdp_ts={cdp_ts:.4f} qpos={qpos:.4f} "
                      f"iv[o={_iv[0]:.4f} ts={_iv[1]:.4f}~{_iv[2]:.4f}]")
            if dur is not None:
                # 持续打字声：用原生音轨按敲击时长裁剪（不够则循环），全程一整条
                n = max(1, int(round(dur * sound_engine.SAMPLE_RATE)))
                arr = sound_engine.loop_to_length(self._sounds[name], n, fade_s=0.01)
                if arr is not None and arr.size:
                    track.add(arr, qpos)
                    placed += 1
            else:
                track.add(self._sounds[name], qpos)
                placed += 1

        # ---- 背景音乐：随机「去重」+ 循环/裁剪到视频时长 + 作为铺底混入 ----
        # 每次运行都用 sound_engine.process_bgm 对音乐做随机化处理，使同一首音乐
        # 在不同视频里的字节/频谱特征都不同（规避平台指纹匹配）；随后循环/裁剪到
        # 视频总长，按 BGM_VOLUME 音量铺在打字/发送音效之下。失败只降级（跳过音乐）。
        bgm_added = False
        if ENABLE_BGM and os.path.isfile(BGM_PATH):
            try:
                bgm_arr = sound_engine.process_bgm(BGM_PATH, max_seconds=out_dur + 5.0)
                if bgm_arr is not None and bgm_arr.size:
                    # 裁掉音乐自带的开头静音前奏（部分背景音乐有 1s+ 静音，导致
                    # 音乐「来得慢」），让背景音乐从视频第 0 秒即可听见。
                    bgm_arr = sound_engine.trim_leading_silence(bgm_arr)
                    n = max(1, int(round(out_dur * sound_engine.SAMPLE_RATE)))
                    bgm_loop = sound_engine.loop_to_length(bgm_arr, n)
                    if bgm_loop is not None and bgm_loop.size:
                        track.set_background(bgm_loop, BGM_VOLUME)
                        bgm_added = True
                        print(f"[BGM] 已铺入背景音乐（视频 {out_dur:.2f}s，去重后音量 {BGM_VOLUME}）")
            except Exception as exc:                    # noqa: BLE001
                print(f"[BGM] 背景音乐处理失败，跳过不混入：{exc}")

        if not placed and not bgm_added:
            return mp4_path
        fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tmp_out = mp4_path + ".audio.mp4"
        try:
            if not track.write_wav(wav_path, duration=out_dur, gain=AUDIO_VOLUME):
                return mp4_path
            sound_engine.ffmpeg_mux_audio(ffmpeg, mp4_path, wav_path, tmp_out)
            if os.path.isfile(tmp_out):
                # Windows 下杀毒/文件索引常会短暂锁定刚写出的成品视频，导致 os.replace
                # 报「拒绝访问」(WinError 5)。这里直接用带重试的原子替换覆盖同名文件
                # （os.replace 本就支持覆盖目标，无需先删旧文件，避免删除后替换失败把
                # 视频弄丢），重试数次仍失败才放弃混流（成品保持无声，但视频不丢失）。
                _replaced = False
                for _attempt in range(6):
                    try:
                        os.replace(tmp_out, mp4_path)
                        _replaced = True
                        break
                    except OSError:
                        time.sleep(0.5)
                if _replaced:
                    print(f"[音频] 已为成品视频混入音效 {placed} 条"
                          + ("与背景音乐" if bgm_added else "") + "。")
                else:
                    raise OSError("视频文件被占用（拒绝访问），重试仍失败")
        except Exception as exc:                    # noqa: BLE001
            print(f"[警告] 音效混流失败（视频保持无声）：{exc}")
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass
        return mp4_path

    def _set_input_value(self, box, new_value: str):
        """直接设置输入框内容（拼音上屏），并派发 input 事件。

        输入框是会自动换行的 <textarea>，不再强制水平滚动（旧 el.scrollLeft 会让
        长文本往右推、看不到前面字）；仅滚到内容底部，让最新一行可见。
        """
        box.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.scrollTop = el.scrollHeight; }",
            new_value)

    # ---------- 核心功能：真人级打字（带手机键盘） ----------

    @staticmethod
    def _is_cjk(ch: str) -> bool:
        return '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf'

    def human_type(self, selector: str, text: str, send: bool = True,
                   show_keyboard: bool = True, typo_prob: float = None,
                   interjections: list = None, avatar: str = None,
                   time_spec: str = None) -> str:
        """
        真人级打字（带手机键盘）：
          - 中文：逐键敲拼音（按键高亮）→ 候选词条弹出 → 点击候选上屏
          - 英文/数字：逐键高亮输入（含小概率打错回删）
          - 标点：额外停顿，视觉上像在思考
        send=True 输完停顿后按「发送」并回车；否则停在输入框（打字不发）。
        interjections：对方插话列表（str 或 str 列表）。打字过程中按「已上屏字符数」进度
          在字组/字符间隙注入对方左侧气泡，实现「我边打字、对面边发」的重叠紧凑节奏。
        avatar：对方插话消息默认头像（缺省用配置里的对方头像）。
        time_spec：时间标注（如 "18:22" / "昨天 23:52"）。send=True 且给出时，
          发送上屏的这条消息前会显示一条该时刻的时间分隔条（时间占位）。
        返回最终输入框内容（不含已发送）。
        """
        typo_prob = typo_prob if typo_prob is not None else TYPO_PROBABILITY
        box = self.page.locator(selector)
        if box.count() == 0:
            raise RuntimeError(f"找不到输入框元素：{selector}")
        box.first.click()
        _pump_wait(random.uniform(0.15, 0.35) / SPEED / max(0.05, TYPE_SPEED))   # 聚焦后的自然反应时间
        # 先切输入法模式再弹键盘：键盘弹出来即为拼音/英文模式，首字无需等键盘弹到位再补一次
        # setImeMode（那段等待正是「键盘已弹出却迟迟不出字」的一部分）。
        has_cjk = any(self._is_cjk(c) for c in text)
        self.page.evaluate(
            "(m) => window.__wxKeyboard && window.__wxKeyboard.setImeMode(m)",
            'pinyin' if has_cjk else 'english')
        if show_keyboard:
            self._kb_show()

        # ---- 对方插话调度：按打字进度(已上屏字符数)触发，实现「边打字边对面发」 ----
        interjections = self._normalize_interjections(interjections)
        ij_i = [0]            # 下一条要触发的插话下标
        typed = [0]           # 已上屏的字符计数
        if interjections:
            total = max(1, len(text))
            # 每条插话在打字进度到达 (i+1)/N 处触发（按字符数折算，落在字组/字符间隙）
            ij_thresh = [int(round(total * (i + 1) / len(interjections)))
                         for i in range(len(interjections))]

            def on_progress(n):
                typed[0] += n
                while ij_i[0] < len(interjections) and typed[0] >= ij_thresh[ij_i[0]]:
                    # 第一条插话前先短显「对方正在输入...」，更接近真机被打断
                    self._inject_peer_msg(interjections[ij_i[0]], avatar,
                                          show_typing=(ij_i[0] == 0))
                    ij_i[0] += 1
        else:
            def on_progress(n):
                typed[0] += n

        committed = ""
        # 按词组分段：纯中文整词用「整词拼音→一次性上屏」，其余字符逐键直输
        for kind, val in self._segment_text(text):
            if kind == "cjk" and _HAS_PYPINYIN:
                committed += self._type_cjk_run(box, val, committed, on_progress)
            else:
                for ci, ch in enumerate(val):
                    next_ch = val[ci + 1] if ci + 1 < len(val) else ""
                    committed += self._type_plain_char(box, ch, typo_prob, next_ch,
                                                       on_progress)

        if send:
            _type_minmax(*AFTER_TYPING_PAUSE_MS)
            # 时间标注（时间分隔条占位）：把标注时刻放进临时变量，sendSelfFromInput
            # 在 Enter 回车触发发送时取出并挂到新上屏的这条消息上。
            self.page.evaluate("(t) => { window.__wxNextSendTime = t || ''; }", time_spec or "")
            self._kb_press("send")
            self.page.keyboard.press("Enter")
            # 发送声锚定到气泡真正渲染的时刻（Enter 后的 Vue nextTick），
            # 避免发送声先于气泡出现。
            self._finalize_send_sound()
            # 发送后的停顿：随打字倍速缩放，高倍速下「发完立马接下一段」，低速保留真人节奏。
            # 下限 0.02s 只保证回车事件/气泡渲染不被下一段打字盖住，避免画面错乱。
            _pump_wait(max(0.02, (SEND_AFTER_WAIT / SPEED) / max(0.05, TYPE_SPEED)))
        else:
            # 打字不发：内容保留在输入框，键盘保持弹出
            _type_minmax(*AFTER_TYPING_PAUSE_MS)
        return committed

    @staticmethod
    def _normalize_interjections(interjections) -> list:
        """把插话参数规范成非空字符串列表；None/空 -> []，单字符串 -> [str]。"""
        if not interjections:
            return []
        if isinstance(interjections, str):
            interjections = [interjections]
        if not isinstance(interjections, (list, tuple)):
            return []
        return [str(x).strip() for x in interjections if str(x).strip()]

    def _inject_peer_msg(self, text: str, avatar: str = None, show_typing: bool = False):
        """在打字过程中注入一条对方气泡（插话），并稍作停顿让气泡可读。

        走主线程 page.evaluate，绝不开新线程（同页并发会触发 greenlet 错误）。
        停顿用 _sd_minmax（只受全局倍速影响，不被 TYPE_SPEED 压成不可见）。
        """
        self._ensure_enhance()
        if show_typing:
            self.page.evaluate("window.__wxTypingOn()")
            _sd_minmax(150, 320)
            self.page.evaluate("window.__wxTypingOff()")
            _sd_minmax(60, 160)
        try:
            self.page.evaluate("([t, a]) => window.__wxPeerMsg(t, a)", [text, avatar])
        except Exception as exc:                    # noqa: BLE001
            print(f"[插话] 对方插话注入失败（跳过）：{text} - {exc}")
            return
        _sd_minmax(260, 440)      # 像真人被对方打断、稍停再继续打字
        self.live_snapshot()

    def _segment_text(self, text: str):
        """把文本切成 [(kind, value)]：kind='cjk' 为一整段连续中文，kind='plain' 为其他段。

        连续中文段整体作为一个 cjk 段（整句输入）：驱动层一次敲完整段拼音、
        候选行持续刷新，最后一次性上屏。不在词与词之间插入任何停顿，
        保证打字过程完全流畅（中间不出现"两字一停选字"的卡顿）。
        """
        tokens = []
        if not text:
            return tokens
        for m in _CJK_RUN.finditer(text):
            cjk = m.group(1)
            if cjk:
                tokens.append(("cjk", cjk))
            else:
                tokens.append(("plain", m.group(2)))
        return tokens

    @staticmethod
    def _pick_chunk_len(run: str, i: int) -> int:
        """返回本段要上屏的字数（1~5），按权重随机（大多 1-2 字，偶尔 3-5 字）。"""
        remain = len(run) - i
        if remain <= 1:
            return remain
        r = random.random()
        acc = 0.0
        n = 2
        for ln, w in TYPE_CHUNK_LEN_WEIGHTS:
            acc += w
            if r <= acc:
                n = ln
                break
        return min(n, remain)

    def _type_cjk_run(self, box, run: str, committed: str, on_progress=None) -> str:
        """一整段中文（可多字）：按可变长度分段（大多 1-2 字、偶尔 3-5 字），敲完该段拼音立即上屏。

        像真机"词组输入"：敲完一段拼音 → 这一段字上屏 → 立刻继续敲下一段，中间不插入停顿。
        段落长度可变（1~5 字），避免每次固定 2 字的呆板感，让动画更像真人一段段上屏。
        上屏由键盘引擎 commitByPhrase 把输入框结尾的组合拼音替换为汉字，打字动画全程连续。
        on_progress：可选回调(on_progress(n))，每打完一段（n=本段字数）回调一次，
        用于「边打字边对面插话」的进度触发。缺省 None。
        """
        py = "".join(_pinyin_of(c) for c in run)
        # 词库拿不到拼音（生僻/非汉字）：直接上屏兜底，保证文字一致
        if not py:
            self._set_input_value(box, committed + run)
            _type_minmax(90, 180)
            if on_progress:
                on_progress(len(run))
            return run

        # 拼音模式下，键盘引擎会在每敲一个字母后自动刷新候选行（打 w 即出预选）
        self.page.evaluate(
            "window.__wxKeyboard && window.__wxKeyboard.setImeMode('pinyin')")
        # 先复位大小写状态：拼音字母必须是小写，避免上一个英文段残留的 Shift/Caps
        # 让 pressType 把小写拼音误打成大写（每个中文段仅多 1 次往返，可忽略）。
        self.page.evaluate(
            "window.__wxKeyboard && window.__wxKeyboard.setShift('off')")
        # 按「雾凇真实词」分段：优先整词上屏（最长匹配，最多 5 字），词长自然 1-2/3-5 变化；
        # 命中真实词时候选与上屏文字一致，更像真输入法。无匹配词则退回 1 字。
        i = 0
        while i < len(run):
            n = _wusong_word_len(run, i, max_len=5) or 1    # 本段字数：整词/1 字
            chunk = run[i:i + n]
            chunk_py = "".join(_pinyin_of(c) for c in chunk)
            # 候选-上屏首位对齐微调：预告本段目标词（整词/单字），
            # 让 keyboard.js 在该词拼音敲全时把候选第一位对准它，避免"候选首位≠上屏"（如 甩/帅、窜出来/猜出来）。
            # 与整段拼音一起随 pressRun 传入（省一次 setTopHint 往返）。
            # 高倍速整段一次性敲入（pressRun 浏览器内逐键推进），不再逐字母 page.evaluate，
            # 消除「打开键盘后第一次打字打一半卡一下」的逐键往返抖动。
            self._type_run(chunk_py, chunk, chunk_py)
            # 这一段字立即上屏：引擎把输入框结尾的组合拼音替换为该段中文
            commit_wall = self.page.evaluate(
                "([w]) => window.__wxKeyboard && window.__wxKeyboard.commitByPhrase(w)", [chunk])
            # 记录「字真正上屏」的视觉时刻（JS Date.now() 毫秒），
            # 供连打段收口时把持续打字声起点对齐到首次上屏，消除先有声音后出字。
            self._note_commit_wall(commit_wall)
            if on_progress:
                on_progress(len(chunk))
            i += n

        self.live_snapshot()
        return run

    def _type_plain_char(self, box, ch: str, typo_prob: float, next_ch: str = "",
                         on_progress=None) -> str:
        """英文 / 数字 / 标点：逐键高亮输入，含小概率打错回删"""
        # 打错回删（仅对字母数字；且输入框非空才执行）
        if ch.isalnum() and random.random() < typo_prob and box.first.input_value():
            wrong_text = "".join(random.choice(TYPO_WRONG_CHARS) for _ in range(TYPO_WRONG_COUNT))
            for w in wrong_text:
                self.page.keyboard.type(w)
                self._kb_press(w if w.isalnum() else None, 90)
            _type_minmax(200, 420)  # 发现打错的停顿（同比压缩）
            # JS 逐字回删（比 Backspace 键盘事件更可靠，不会偶发卡 CDP）
            handle = box.first.element_handle()
            for _ in range(TYPO_WRONG_COUNT):
                handle.evaluate(
                    "(el) => { el.value = el.value.slice(0, -1); }")
                self._kb_press("backspace", 90)
                _type_minmax(45, 90)
            _type_minmax(*TYPO_DELETE_PAUSE_MS)  # 重新输入前停顿

        self.page.keyboard.type(ch, delay=max(1, int(
            random.randint(TYPE_DELAY_MIN_MS, TYPE_DELAY_MAX_MS)
            / SPEED / max(0.05, TYPE_SPEED))))
        # 按键高亮：字母/数字按对应键，空格/常用标点按对应功能键；
        # 大写字母联动键盘 Shift 状态（连续大写用大写锁定，真机手感）。
        # 说明：英文/数字含 Shift/大写锁定状态，需显式 setShift，故保留两步；
        # 单次合并的 pressType 只用于中文拼音路径（小写字母、无 Shift 参与）。
        if ch.isalnum():
            if ch.isupper():
                self._kb_press(ch, shift='caps' if next_ch.isupper() else 'on')
            else:
                self._kb_press(ch, shift='off')
        elif ch == " ":
            self._kb_press("space")
        elif ch in PUNCT_KEY:
            self._kb_press(PUNCT_KEY[ch])
        if on_progress:
            on_progress(1)
        self.live_snapshot()
        return ch

    # ---------- 会话切换 ----------

    def open_chat(self, name: str):
        """在聊天列表主页点击指定联系人进入对话（模糊匹配，自动 trim）"""
        self._ensure_enhance()
        name = str(name).strip()
        if not name:
            raise RuntimeError("[打开聊天] 缺少联系人名称。")
        # 优先精确匹配 .desc-author，找不到再退化为子串模糊匹配
        item = self.page.locator(
            f'.wechat-list li:has(.desc-author:text-is("{name}")) .list-info')
        if item.count() == 0:
            item = self.page.locator(
                f'.wechat-list li:has(.desc-author:text("{name}")) .list-info')
        if item.count() == 0:
            raise RuntimeError(
                f'聊天列表中找不到联系人「{name}」。'
                f'请确认剧本中的名字与首页显示的联系人名称完全一致。')
        # 读取该联系人在首页列表的头像，进入聊天后同步为「对方头像」，
        # 使聊天页追加消息与首页会话列表、聊天历史消息的头像保持一致。
        avatar = self.page.evaluate("""(name) => {
            const lis = Array.from(document.querySelectorAll('.wechat-list li'));
            const li = lis.find(l => {
                const a = l.querySelector('.desc-author');
                return a && a.textContent.trim() === name;
            });
            if (!li) return null;
            const img = li.querySelector('.header-box img, .header img');
            return img ? (img.getAttribute('src') || img.src) : null;
        }""", name)
        # 进入对话：
        # .list-info 是 <router-link tag="div">，点击即触发 vue-router 跳转。首页列表在
        # --speed 加速/重排时，Playwright 命中测试常把相邻/重复的 .list-info 判为
        # 「subtree intercepts pointer events」而 10s 超时（与 go_back_home 的修复同理）。
        # 这里改用 DOM click 直接命中「按名字锁定的那一行」，绕开元素重叠 / Z 序 / 命中测试，
        # 保证点开的一定是当前这个联系人，避免误点相邻行。
        opened = self.page.evaluate("""(name) => {
            const lis = Array.from(document.querySelectorAll('.wechat-list li'));
            // 与上方 locator 保持同一套匹配：先精确匹配，再退化为子串匹配
            let li = lis.find(l => {
                const a = l.querySelector('.desc-author');
                return a && a.textContent.trim() === name;
            });
            if (!li) li = lis.find(l => {
                const a = l.querySelector('.desc-author');
                return a && a.textContent.indexOf(name) !== -1;
            });
            if (!li) return false;
            const info = li.querySelector('.list-info');
            (info || li).click();
            return true;
        }""", name)
        if not opened:
            # 兜底：JS 层面没找到行时退回 Playwright 点击（force 跳过命中检查超时）
            item.first.click(force=True)
        self._wait(CHAT_ENTER_WAIT)   # 转场滑入动画 .34s，紧贴动画结束即可继续
        self._scroll_chat_bottom()   # 进入聊天立即滚到最新消息，避免信息多时底部看不到
        if avatar:
            self.page.evaluate(
                "(u) => window.__wxConfig && window.__wxConfig.setPeerAvatar(u)", avatar)
            _sd_minmax(120, 260)

    def go_back_home(self, hold: float = None):
        """返回聊天列表主页：循环点返回按钮直到落到主 Tab 页，再点底部「微信」Tab。

        修复点：朋友圈/资料等子页面只有一层返回，之前只点一次会停在「发现」，
        导致无法继续开第二个聊天。现在连续点击返回直到导航栏可见。
        点击用 DOM click 直接触发路由返回，避免 Playwright 在路由重渲染期间
        等待元素稳定而出现「元素被 detach」超时（特别在 --speed 加速后更易触发）。

        hold 可选：回到主页并等转场动画播完后，继续停留在主页的秒数（默认 0.3s）。
        即「返回主页后、打开下一个聊天前」的自然停顿，可由步骤「停留」覆盖。
        """
        self._ensure_enhance()
        self._kb_hide()
        settle = BACK_HOME_HOLD_DEFAULT if hold is None else float(hold)
        for _ in range(4):
            has_back = self.page.evaluate(
                "() => { const a = document.querySelector('#wx-header .icon-return-arrow');"
                " if (a) { a.click(); return true; } return false; }")
            if not has_back:
                break
            self._wait(0.45)
        try:
            self.switch_tab("微信", settle=settle)
        except RuntimeError:
            pass  # 已在微信主页时无需切换
        # switch_tab 已按 settle(默认 0.3s) 等待，此处不再叠加 NAV_WAIT。

    # ---------- 对方消息交互 ----------

    def show_typing(self, seconds: float):
        """在聊天头部显示「对方正在输入...」，持续指定秒数后消失"""
        self._ensure_enhance()
        if self.page.locator(".dialogue-section").count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法显示「对方正在输入」。请先 [打开聊天]。")
        self.page.evaluate("window.__wxTypingOn()")
        _pump_wait((seconds + random.uniform(-0.1, 0.3)) / SPEED)
        self.page.evaluate("window.__wxTypingOff()")
        _sd_minmax(100, 300)

    def send_peer_message(self, text: str, avatar: str = None, time_spec: str = None):
        """对方消息：JS 注入左侧白色气泡并自动滚到底部

        time_spec：时间标注（如 "18:22"），给出时该消息前显示一条时间分隔条。
        """
        self._ensure_enhance()
        ok = self.page.evaluate(
            "([t, a, ts]) => window.__wxPeerMsg(t, a, ts)", [text, avatar, time_spec])
        if not ok:
            raise RuntimeError("对方消息注入失败：当前页面不存在聊天容器 .dialogue-section。"
                               "请先 [打开聊天] 进入某个会话。")
        _pump_wait(SEND_AFTER_WAIT / SPEED)

    # ---------- 后台对方消息 ----------

    def send_peer_message_bg(self, contact: str, text: str, avatar: str = None,
                             sender: str = None, move_top: bool = True,
                             time_spec: str = None, image: str = None):
        """后台对方消息：给「未打开的会话」投递一条对方消息，并刷新主页预览/角标。

        在你正看着别的聊天（或主页）时注入，画面本身不变，但目标会话在主页的
        预览、未读角标、底部「微信」角标与标题「微信 (N)」会一起更新；
        之后再 [返回主页] 就能看到这条消息，点进去即可阅读。
        若目标会话恰好就是当前打开的会话，则退化为即时上屏（走 __wxPeerMsg）。
        time_spec：时间标注（如 "18:22"），给出时该消息前显示一条时间分隔条。
        image：图片路径（/images/...），给出时该消息为图片气泡（主页预览显示 [图片]）。
        """
        self._ensure_enhance()
        contact = str(contact or "").strip()
        text = str(text or "")
        if not contact:
            raise RuntimeError("[对方后台发消息] 缺少联系人名称。")
        if not text and not image:
            raise RuntimeError(f"[对方后台发消息] 缺少消息内容（联系人：{contact}）。")
        ok = self.page.evaluate(
            "([c, t, o]) => window.__wxPeerMsgBg && window.__wxPeerMsgBg(c, t, o)",
            [contact, text, {"avatar": avatar, "sender": sender, "moveTop": move_top,
                             "time": time_spec, "image": image}])
        if not ok:
            raise RuntimeError(
                f"[对方后台发消息] 找不到会话「{contact}」（主页列表不存在该联系人）。"
                f"请确认首页会话列表里有此人，或在流程里先用 [编辑主页] 加入。")
        _sd_minmax(200, 420)

    @staticmethod
    def _normalize_bg_trigger(trigger) -> dict:
        """把「触发」规范成 {'immediate':bool,'sec':float|None,'step':int|None}。

        支持：省略/'立即'/0 -> 立即；数字 -> 秒；{'秒':S} / {'sec':S} -> 秒；
        {'步':N} / {'step':N} -> 第 N 步前。未知格式回退为立即。
        """
        if trigger is None:
            return {"immediate": True, "sec": None, "step": None}
        if isinstance(trigger, bool):
            return {"immediate": trigger, "sec": None, "step": None}
        if isinstance(trigger, (int, float)):
            return {"immediate": float(trigger) <= 0, "sec": float(trigger), "step": None}
        if isinstance(trigger, dict):
            if "秒" in trigger or "sec" in trigger:
                s = trigger.get("秒", trigger.get("sec"))
                try:
                    s = float(s)
                except (TypeError, ValueError):
                    s = None
                return {"immediate": s is not None and s <= 0,
                        "sec": s, "step": None}
            if "步" in trigger or "step" in trigger:
                n = trigger.get("步", trigger.get("step"))
                try:
                    n = int(n)
                except (TypeError, ValueError):
                    n = None
                return {"immediate": False, "sec": None, "step": n}
        return {"immediate": True, "sec": None, "step": None}

    def load_bg_queue(self, data, time_spec: str = None):
        """装载「后台消息队列」：data 为 JSON 数组或 .json 文件路径。

        每条形如 {"联系":X,"内容":Y,"头像":Z,"sender":S,"置顶":bool,"触发":...,"时间":T}
        （也兼容 contact/text/avatar/sender/moveTop/trigger/time 键名）。
        time_spec：默认时间标注（如 "18:22"），条目未单独给「时间」时套用。

        ★ 行为：装载即投递。队列里每一条消息都在【当前这一时刻】立刻后台发出去，
          让目标会话的主页预览 + 未读角标马上更新，之后打开该会话即可看到。
          不再依赖「秒/步」触发——那种按时间/步骤延迟投递的方式在短剧本里
          会因时钟/步数到不了而永远不投递（后台消息收不到、视频少了那几句）。
          若确实需要「还没到时刻先不发」，请改用 [对方后台发消息] 逐条控制时机。
        """
        if isinstance(data, str):
            data = data.strip()
            if data.endswith(".json") and os.path.isfile(data):
                data = os.path.join(os.path.dirname(os.path.abspath(__file__)), data)
                with open(data, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = json.loads(data)
        if not isinstance(data, list):
            raise ValueError("[后台消息队列] 数据必须是 JSON 数组。")
        self._bg_queue = []
        self._bg_base_clock = _RUN_CLOCK
        for it in data:
            if not isinstance(it, dict):
                continue
            contact = str(it.get("联系", it.get("contact", ""))).strip()
            text = str(it.get("内容", it.get("text", "")))
            image = it.get("图片", it.get("image"))
            if not contact or (not text and not image):
                continue
            time_s = it.get("时间", it.get("time", time_spec))
            entry = {
                "contact": contact,
                "text": text,
                "image": image,
                "avatar": it.get("头像", it.get("avatar")),
                "sender": it.get("sender", it.get("senderName")),
                "moveTop": it.get("置顶", it.get("moveTop", True)),
                "time": time_s,
                "trigger": self._normalize_bg_trigger(it.get("触发", it.get("trigger"))),
                "_delivered": True,   # 装载即投递，标记已投递，后续 drain_bg_queue 不再重复
            }
            self._bg_queue.append(entry)
            # 装载即投递：立刻在后台发出这条消息（画面不变，仅刷新该会话主页预览+角标）
            self.send_peer_message_bg(contact, text, entry["avatar"],
                                      entry["sender"], bool(entry["moveTop"]),
                                      entry["time"], entry["image"])

    def drain_bg_queue(self, step_index: int = None):
        """结算后台消息队列：投递触发条件已满足的条目。

        在每一条动作执行前调用一次（传入当前 1 基步骤号），实现
        「我正跟别人聊，另一个人的消息在后台陆续到达、角标自然累积」。
        """
        if not getattr(self, "_bg_queue", None):
            return False
        any_delivered = False
        for entry in self._bg_queue:
            if entry.get("_delivered"):
                continue
            trig = entry.get("trigger") or {}
            if trig.get("immediate"):
                fire = True
            elif trig.get("sec") is not None:
                fire = (_RUN_CLOCK - getattr(self, "_bg_base_clock", _RUN_CLOCK)) >= trig["sec"]
            elif trig.get("step") is not None:
                fire = step_index is not None and step_index >= trig["step"]
            else:
                fire = True
            if fire:
                entry["_delivered"] = True
                self.send_peer_message_bg(entry["contact"], entry["text"],
                                          entry.get("avatar"), entry.get("sender"),
                                          bool(entry.get("moveTop", True)),
                                          entry.get("time"), entry.get("image"))
                any_delivered = True
        return any_delivered

    def view_image(self, url: str, hold_seconds: float = None, focus=None,
                   zoom: float = None, no_zoom: bool = False):
        """点开图片放大查看：全屏查看器打开（放大动画）→ 手抖停留 → 关闭。

        模拟真人点开一张图片：识别 → 放大 → 转动手机细看 → 点击关闭。
        hold_seconds 控制停留时长（缺省 0.3s）。
        focus 可选：指定放大聚焦点，可为 {"x":0.3,"y":0.4} 或 "0.3,0.4" 字符串。
        zoom 可选：捏合放大倍率（如 2.0）；缺省用全局默认 IMAGE_ZOOM_DEFAULT。
        no_zoom 为 True 时表示「只点开不放大」：打开到原图完整大小，不做捏合放大。
        """
        self._ensure_enhance()
        url = str(url).strip()
        if not url:
            raise RuntimeError("[查看图片] 缺少图片路径。")
        eff_zoom = _parse_zoom(zoom, IMAGE_ZOOM_DEFAULT)
        ok = self.page.evaluate(
            "(o) => window.__wxHuman && window.__wxHuman.openImage(o.src, null, o.opts)",
            {"src": url, "opts": {"focus": focus, "zoom": eff_zoom, "noZoom": bool(no_zoom)}})
        if not ok:
            raise RuntimeError("查看图片失败：图片查看器未注入，或路径无效。")
        # 放大动画 + 查看停留（快速放大 → 微抖细看期间）
        _sd_minmax(350, 500)
        # 用户显式给定「停留」→ 严格按它停；未给 → 用默认 0.3s。
        # 旧逻辑 wait_real = max(hold/SPEED, 动画时长) 会把用户设的短停留（如 0.1s）
        # 抬到缩放/细看动画时长（约 1~2s），造成「预设 0.1s 却停留很久」；现改为优先尊重设定值，
        # 仅保底极小值，避免等待为 0。SPEED 仍参与缩放，与全局倍速保持一致。
        hold_s = hold_seconds if hold_seconds is not None else VIEW_IMAGE_HOLD_DEFAULT
        wait_real = hold_s / max(0.05, SPEED)
        _pump_wait(max(0.05, wait_real))
        _sd_minmax(100, 250)
        self.page.evaluate("window.__wxHuman && window.__wxHuman.closeImage()")
        # 关闭动画是 JS rAF 固定时长(~0.17~0.26s)，不随 SPEED 缩放；这里如果用被 SPEED 压短的
        # 等待(高倍速下 250~450ms 会缩到 50~90ms)，键盘弹出的 0.22s 动画会撞上还没播完的缩小动画，
        # 两个动画同时抢主线程/合成器 → 开键盘卡顿断帧。故保底等完约 0.32s 真实时长再返回。
        close_wait = random.uniform(250, 450) / 1000.0 / max(0.05, SPEED)
        _pump_wait(max(0.32, close_wait))

    # ---------- Tab 与朋友圈 ----------

    def switch_tab(self, name: str, settle: float = None):
        """点击底部 Tab：微信 / 通讯录 / 发现 / 我

        settle 可选：切完 Tab 后的等待秒数；缺省用 NAV_WAIT。
        """
        valid = {"微信", "通讯录", "发现", "我"}
        if name not in valid:
            raise RuntimeError(f"未知 Tab「{name}」，可用值：{'/'.join(valid)}")
        self._kb_hide()
        tab = self.page.locator(f'#wx-nav nav dl:has(dd:text-is("{name}"))')
        if tab.count() == 0:
            raise RuntimeError(f"底部导航栏中找不到 Tab「{name}」（#wx-nav nav dl）。")
        tab.first.click()
        self._wait(NAV_WAIT if settle is None else settle)

    def enter_moments(self):
        """从发现页进入朋友圈；若当前不在「发现」Tab，自动切过去。"""
        self._kb_hide()
        moment_entry = self.page.locator('.weui-cell:has-text("朋友圈"):visible')
        if moment_entry.count() == 0:
            # 大部分朋友圈入口在「发现」页，自动切过去再找，省去手动插一步 [切换Tab]
            self.switch_tab("发现")
            moment_entry = self.page.locator('.weui-cell:has-text("朋友圈"):visible')
        if moment_entry.count() == 0:
            raise RuntimeError('找不到「朋友圈」入口。请先执行 [切换Tab] 发现。')
        moment_entry.first.click()
        self._wait(NAV_WAIT)

    def scroll_down(self, pixels: int):
        """向下滚动指定像素（鼠标滚轮，视觉更接近真人）"""
        self.page.mouse.move(VIEWPORT_W / 2, VIEWPORT_H / 2)
        _sd_minmax(100, 250)
        steps = max(3, int(pixels / 120))
        per_step = pixels / steps
        for _ in range(steps):
            self.page.mouse.wheel(0, per_step * random.uniform(0.85, 1.15))
            _sd_minmax(80, 200)
        _sd_minmax(200, 450)
        self.live_snapshot()

    def like(self):
        """给当前可见的最后一条朋友圈点赞（JS 统一处理，兼容注入/原生动态）"""
        self._ensure_enhance()
        ok = self.page.evaluate("window.__wxLikePost()")
        if not ok:
            raise RuntimeError("当前页面没有朋友圈动态（.moments__post）。请先 [进入朋友圈]。")
        _sd_minmax(400, 700)

    def comment(self, text: str):
        """展开评论框，走真人键盘打字流程发表评论"""
        self._ensure_enhance()
        opened = self.page.evaluate("window.__wxOpenCommentBox()")
        if not opened:
            raise RuntimeError("无法打开评论框：当前页面没有朋友圈动态。请先 [进入朋友圈]。")
        _sd_minmax(300, 500)
        self.human_type("#commentInput", text)
        _sd_minmax(200, 400)
        self._kb_hide()

    # ---------- 新动作：打字不发 / 删除 / 个人资料 / 朋友圈编辑 ----------

    def type_no_send(self, text: str, hold_seconds: float = 1.5,
                     interjections=None, avatar: str = None) -> str:
        """打出文字但不发送，停留在输入框（键盘弹出），随后对方按顺序插话，供后续删除或展示。

        顺序（用户要求的节奏）：先**完整**打出我的文字（打字动画全程可见，不在输入过程中插话）
        → 短暂停留（文字停在输入框、没发出去）→ 对方按顺序逐条回消息（首条前显示「对方正在输入...」）
        → 结束，由下一步 [删除文字] 清空。

        interjections：对方插话列表，按此顺序出现在我打完字**之后**。
        """
        if self.page.locator(".dialogue-section").count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法打字。请先 [打开聊天]。")
        # 先完整打字、过程中不插话 —— 让「逐键上浮字母」的打字动画从头到尾完整呈现
        committed = self.human_type(".chat-txt", text, send=False,
                                    interjections=None, avatar=avatar)
        # 打完字停留：文字停在输入框，看得到「打完了但没发」
        _pump_wait(max(0.35, hold_seconds))
        # 打完字之后，对方才按顺序逐条回
        for idx, msg in enumerate(self._normalize_interjections(interjections)):
            self._inject_peer_msg(msg, avatar, show_typing=(idx == 0))
        return committed

    def delete_chars(self, count: int):
        """按退格键删除指定数量的字符（count=-1 表示清空输入框）

        改进：
          - 删除前切回字母布局，保证退格键高亮显示在字母布局的退格键上（位置一致，
            不再因输入过中文标点/数字导致停在符号布局、退格动画跑错键位）；
          - 删除期间给 body 加 wx-deleting：输入框光标变蓝、退格键稳定长按高亮
            （模拟真机长按退格，而非"按下即闪"），并加快逐字删除节奏。
        """
        box = self.page.locator(".chat-txt")
        if box.count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法删除。请先 [打开聊天]。")
        self.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.show()")
        # 切回字母布局：退格键始终显示在字母布局的固定位置上（真机手感）
        self.page.evaluate("window.__wxKeyboard && window.__wxKeyboard.switchLayout('letters')")
        _pump_wait(0.25)
        # 确保焦点在输入框：pressType('backspace')/deleteHold 都走 activeElement 截字
        focused = self.page.evaluate(
            "() => { const a = document.activeElement;"
            " return !!(a && a === document.querySelector('.chat-txt')); }")
        if not focused:
            box.first.click()
            _pump_wait(0.05)
        orig_len = len(box.first.input_value())
        n = orig_len if count < 0 else int(count)
        n = max(0, n)
        if n <= 0:
            return
        # 进入"删除中"态：光标变蓝 + 退格键长按高亮（真机长按退格效果）
        self.page.evaluate("() => document.body.classList.add('wx-deleting')")
        if TYPE_SPEED >= 8.0:
            # 高倍速：真实每字间隔不足一帧，Python 逐字往返必然把删除切成错位帧（观感掉帧）。
            # 交给 JS 的 deleteHold：由浏览器 rAF 每显示帧删 1 字，节奏帧对齐、无 CDP 抖动。
            target = max(0, orig_len - n)
            self.page.evaluate(
                "(cnt) => window.__wxKeyboard && window.__wxKeyboard.deleteHold(cnt)", n)
            try:
                self.page.wait_for_function(
                    "(target) => { const el = document.querySelector('.chat-txt');"
                    " return !el || el.value.length <= target; }",
                    arg=target, timeout=2500 + int(n * 40))
            except Exception:                      # noqa: BLE001
                pass   # 等待超时不阻断：下面照常收尾
            self._register_delete_sounds()
        else:
            # 低速：肉眼本就可见逐字节奏，保持 Python 逐字驱动。
            # 每字一趟 pressType：按键高亮 + JS 截字在**同一 JS 任务**完成，
            # 不再 pressKey(高亮)+单独截字两趟 CDP（高亮与删字落不同帧会错位）。
            for _ in range(n):
                self._kb_type("backspace", 110)
                _type_minmax(26, 55)      # 加快删除节奏（原 40~90，删得更快更连贯）
        _type_minmax(120, 240)
        self.page.evaluate("() => document.body.classList.remove('wx-deleting')")

    def _register_delete_sounds(self):
        """高速 rAF 删字：从 JS 读取每字删除的墙钟时刻，直接登记成品音轨。

        删字节奏交给 deleteHold(rAF) 后不再有 Python 逐键往返，因此这里补登记
        window.__delWalls 里每字的视觉时刻作为 delete 音效锚点（逐字删除声依旧保留）。
        """
        if not ENABLE_AUDIO or self._mute_sound or not self._sounds \
                or "delete" not in self._sounds:
            return
        try:
            walls = self.page.evaluate("window.__delWalls || []")
        except Exception:                      # noqa: BLE001
            return
        if not walls:
            return
        self._seal_continuous_type()
        for w in walls:
            if isinstance(w, (int, float)) and w > 0:
                self._audio_events.append((w / 1000.0, "delete"))

    def set_avatar(self, image: str):
        """设置头像：所有标记 data-me-avatar 的元素即时更新"""
        self._ensure_enhance()
        self.page.evaluate("(url) => window.__wxConfig && window.__wxConfig.setAvatar(url)", image)
        # 立即使新头像进入浏览器缓存，避免切换后首帧我方头像闪一下
        self._preload_images([image])
        _pump_wait(0.5)

    def set_bg(self, image: str):
        """设置朋友圈封面/背景：所有标记 data-me-bg 的元素即时更新"""
        self._ensure_enhance()
        self.page.evaluate("(url) => window.__wxConfig && window.__wxConfig.setBg(url)", image)
        # 立即使新封面/背景进入浏览器缓存，避免切换后首帧闪一下
        self._preload_images([image])
        _pump_wait(0.5)

    # ---------- 新增：个人资料 / 主页 ----------

    def set_name(self, name: str):
        """修改我的昵称（主页列表、通讯录、朋友圈同步更新）"""
        self._ensure_enhance()
        self.page.evaluate("(n) => window.__wxConfig && window.__wxConfig.setName(n)", name)
        _pump_wait(0.4)

    def set_signature(self, signature: str):
        """修改我的个性签名（同步到通讯录 / 我的资料）"""
        self._ensure_enhance()
        self.page.evaluate("(s) => window.__wxConfig && window.__wxConfig.setSignature(s)", signature)
        _pump_wait(0.4)

    def set_home_list(self, data):
        """按数据重建「微信」主页会话列表（多会话 / 群聊 / 未读 / 免打扰全可配）"""
        self._ensure_enhance()
        if isinstance(data, str):
            data = json.loads(data)
        self.page.evaluate("(d) => window.__wxConfig && window.__wxConfig.setHomeList(d)", data)
        _pump_wait(0.5)

    def apply_scene(self, scene):
        """应用一整份场景：我的资料 + 主页会话(含消息历史) + 朋友圈动态，一步到位。

        scene 可以是 dict、JSON 字符串，或指向 .json 文件的路径（如 scene.json）。
        """
        self._ensure_enhance()
        if isinstance(scene, str):
            scene = scene.strip()
            if scene.endswith(".json") and os.path.isfile(scene):
                with open(scene, "r", encoding="utf-8") as fh:
                    scene = json.load(fh)
            else:
                scene = json.loads(scene)
        ok = self.page.evaluate(
            "(s) => window.__wxConfig && window.__wxConfig.applyScene(s)", scene)
        # 运行中切场景：把新场景要渲染的头像/图片立即可缓存，避免首帧闪现
        self._preload_images(_collect_asset_paths(scene))
        _pump_wait(0.6)
        return ok

    def edit_conversation(self, data):
        """编辑会话消息历史：data 为场景片段（含 home[].messages）或 JSON 字符串/文件路径。"""
        self._ensure_enhance()
        if isinstance(data, str):
            data = data.strip()
            if data.endswith(".json") and os.path.isfile(data):
                with open(data, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = json.loads(data)
        ok = self.page.evaluate(
            "(s) => window.__wxConfig && window.__wxConfig.applyScene(s)", data)
        # 会话/场景切换后预载新数据里的头像与消息图
        self._preload_images(_collect_asset_paths(data))
        _pump_wait(0.6)
        return ok

    # ---------- 新增：聊天增强（图片 / 语音 / 撤回 / 转发 / @成员） ----------

    def _chat_ext(self, fn: str, *args):
        """调用注入的 __wxChatExt 动作；不在聊天页时报错提示先 [打开聊天]。"""
        self._ensure_enhance()
        ok = self.page.evaluate(
            "([fn, a]) => { const f = window.__wxChatExt && window.__wxChatExt[fn]; "
            "return f ? f.apply(null, a) : false; }",
            [fn, list(args)])
        if not ok:
            raise RuntimeError("当前不在聊天对话页，无法执行该动作。请先 [打开聊天]。")
        _pump_wait(0.5)

    def send_image(self, url: str, time_spec: str = None):
        """我方发送图片消息

        time_spec：时间标注（如 "18:22"），给出时该图片消息前显示一条时间分隔条。
        """
        if not str(url or "").strip():
            raise RuntimeError("[发送图片] 缺少图片路径参数（params.图片）。请在剧本中为该动作配置图片。")
        self._chat_ext("selfImage", url, time_spec)

    def peer_image(self, url: str, time_spec: str = None):
        """对方发送图片消息

        time_spec：时间标注（如 "18:22"），给出时该图片消息前显示一条时间分隔条。
        """
        if not str(url or "").strip():
            raise RuntimeError("[对方发图片] 缺少图片路径参数（params.图片）。请在剧本中为该动作配置图片。")
        self._chat_ext("peerImage", url, time_spec)

    def send_emoji(self, url: str, time_spec: str = None):
        """我方发送表情贴纸（带表情面板弹出 -> 点选 -> 上屏动画）

        time_spec：时间标注（如 "18:22"），给出时该表情消息前显示一条时间分隔条。
        """
        if not str(url or "").strip():
            raise RuntimeError("[发送表情] 缺少表情图片路径。")
        self._chat_ext("selfEmoji", str(url).strip(), time_spec)

    def peer_emoji(self, url: str, time_spec: str = None):
        """对方发送表情贴纸

        time_spec：时间标注（如 "18:22"），给出时该表情消息前显示一条时间分隔条。
        """
        self._chat_ext("peerEmoji", str(url).strip(), time_spec)

    def send_voice(self, seconds: int = 3, time_spec: str = None):
        """我方发送语音消息（时长秒数决定波形长短）

        time_spec：时间标注（如 "18:22"），给出时该语音消息前显示一条时间分隔条。
        """
        self._chat_ext("selfVoice", max(1, int(seconds)), time_spec)

    def peer_voice(self, seconds: int = 3, time_spec: str = None):
        """对方发送语音消息

        time_spec：时间标注（如 "18:22"），给出时该语音消息前显示一条时间分隔条。
        """
        self._chat_ext("peerVoice", max(1, int(seconds)), time_spec)

    def withdraw(self):
        """撤回我方最后一条消息"""
        self._chat_ext("withdraw", True)

    def peer_withdraw(self):
        """对方撤回一条消息"""
        self._chat_ext("withdraw", False)

    def open_transfer_panel(self):
        """打开聊天页「+」功能面板（对齐图片1）。需先 [打开聊天]。"""
        self._ensure_enhance()
        if self.page.locator(".dialogue-section").count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法打开转账面板。请先 [打开聊天]。")
        self._kb_hide()
        ok = self.page.evaluate("window.__wxTransfer && window.__wxTransfer.openPanel()")
        if not ok:
            raise RuntimeError("打开转账面板失败：__wxTransfer 未注入。")
        _pump_wait(0.5)

    def transfer(self, recipient: str, amount: str, note: str = "", password: str = "123456"):
        """我方转账真实流程：打开功能面板 → 转账金额页 → 输金额/说明 → 转账 → 6位密码 → 上屏橙色卡片。"""
        if not str(recipient or "").strip():
            raise RuntimeError("[转账] 缺少接收人（聊天对象名）。")
        self._ensure_enhance()
        if self.page.locator(".dialogue-section").count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法转账。请先 [打开聊天]。")
        # 1) 打开功能面板（图片1）
        self._kb_hide()
        self.page.evaluate("window.__wxTransfer && window.__wxTransfer.openPanel()")
        _pump_wait(0.4)
        # 2) 进入转账金额页（图片2）
        self.page.evaluate("window.__wxTransfer && window.__wxTransfer.openAmount(%r)" % str(recipient).strip())
        # 等金额页布局就绪（等数字键盘渲染，避免按键点空）
        self._wait_js("!!document.querySelector('#taKeyboard .tkr-key[data-key=\"1\"]')", 2.0)
        _pump_wait(0.3)
        # 3) 输入金额（数字键盘逐字）
        self._transfer_type_amount(str(amount))
        # 4) 可选：设置转账说明（转账页是独立覆盖层，直接注入值最稳，避免与人 QWERTY 键盘冲突）
        if str(note or "").strip():
            self.page.evaluate(
                "() => { const n = document.querySelector('#taNote'); if (n) { n.value = %r; n.dispatchEvent(new Event('input', { bubbles: true })); } }" % str(note).strip())
            _pump_wait(0.3)
        # 5) 点「转账」绿色键 → 打开密码页
        self.page.evaluate("() => { const k = document.querySelector('#taKeyboard .tkr-ok'); if (k) k.click(); }")
        # 等密码页数字键盘就绪
        self._wait_js("!!document.querySelector('#pwKeyboard .tkr-key[data-key=\"1\"]')", 2.0)
        _pump_wait(0.2)
        # 6) 逐位输入 6 位密码
        pwd = str(password or "123456").strip()
        for ch in pwd:
            if not ch.isdigit():
                continue
            self.page.evaluate("(d) => { const k = document.querySelector('#pwKeyboard .tkr-key[data-key=\"' + d + '\"]'); if (k) k.click(); }", ch)
            _pump_wait(random.uniform(0.10, 0.22) / SPEED)
        # 密码输满 6 位后前端自动确认并上屏橙色卡片
        _pump_wait(0.8)

    def _transfer_type_amount(self, amount: str):
        """在转账金额页用数字键盘逐字输入金额（含小数点）。"""
        # 先聚焦金额输入框（独立数字输入，不弹 QWERTY 键盘）
        self.page.evaluate("() => { const n = document.querySelector('#taInput'); if (n) n.focus(); }")
        _pump_wait(0.2)
        for ch in str(amount or ""):
            key = ch if (ch == '.' or ch.isdigit()) else '.'
            self.page.evaluate("(d) => { const k = document.querySelector('#taKeyboard .tkr-key[data-key=\"' + d + '\"]'); if (k) k.click(); }", key)
            _pump_wait(random.uniform(0.10, 0.22) / SPEED)

    def _wait_js(self, expr: str, timeout: float = 2.0):
        """轮询等待某段 JS 表达式为真（用于等待前端覆盖层就绪，避免按键点空）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.page.evaluate(expr):
                    return True
            except Exception:          # noqa: BLE001
                pass
            time.sleep(0.05)
        return False

    def peer_transfer(self, recipient: str, amount: str, note: str = ""):
        """对方转账：转账卡片上屏（左侧）"""
        self._chat_ext("peerTransfer", str(recipient).strip(), str(amount), str(note))

    def forward(self, text: str):
        """转发一条消息（我方气泡：转发：内容）"""
        self._chat_ext("forward", text)

    def mention(self, name: str):
        """在输入框 @ 成员（弹出键盘，内容保留供后续发送/删除）"""
        self._ensure_enhance()
        if self.page.locator(".dialogue-section").count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法 @ 成员。请先 [打开聊天]。")
        self._kb_show()
        self.page.evaluate("(n) => window.__wxChatExt && window.__wxChatExt.mention(n)", name)
        _pump_wait(0.6)

    def post_moment(self, text: str, image: str = None):
        """发朋友圈：弹出「发表文字」页 → 键盘打字 → 点击发表 → 动态上屏"""
        self._ensure_enhance()
        opened = self.page.evaluate(
            "(img) => window.__wxMoments && window.__wxMoments.openCompose(img)", image)
        if not opened:
            raise RuntimeError("无法打开发朋友圈编辑页：当前页面没有 #moments 容器。请先 [进入朋友圈]。")
        _pump_wait(0.5)
        self.human_type("#mcText", text, send=False)
        _sd_minmax(400, 800)
        ok = self.page.evaluate("window.__wxMoments.submit()")
        if not ok:
            raise RuntimeError("朋友圈发表失败：正文为空或 #moments 不存在。")
        self._kb_hide()
        _pump_wait(0.8)

    def edit_moments(self, data):
        """编辑朋友圈内容：按 posts 数组重建动态列表（昵称/文案/图片/点赞/评论全可配）"""
        self._ensure_enhance()
        posts = data
        if isinstance(data, str):
            posts = json.loads(data)
        self.page.evaluate("(p) => window.__wxConfig.setMomentsPosts(p)", posts)
        self.page.evaluate("(p) => window.__wxMoments.renderPosts(p)", posts)
        _pump_wait(0.6)


# ============================================================
# 六、工作流解析与调度
# ============================================================

LINE_RE = re.compile(r"^\[(.+?)\]\s*(.*)$")

# ---- 时间标注（时间分隔条占位）：`[动作] 内容 | 18:22` / `说话人：内容 | 昨天 23:52` ----
# 只认「整段匹配时间格式」的 `. | 时间` 尾部标注，避免误伤正文里的时间字样。
_TIME_DETECT_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,2}:\d{2}(?::\d{2})?"                              # 18:22 / 09:05:30
    r"|昨天\s*\d{1,2}:\d{2}(?::\d{2})?"                      # 昨天 23:52
    r"|(?:星期|周)[一二三四五六日天](?:\s*\d{1,2}:\d{2})?"   # 星期三 20:00 / 周日
    r"|\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}"                   # 6月8日 18:22
    r"|\d+\s*分钟前|\d+\s*小时前|\d+\s*天前"                   # 35分钟前
    r"|\d{9,}"                                               # 毫秒时间戳
    r")\s*$"
)

# 能产生「会话内消息占位」、从而可以挂时间分隔条的动作。
# 文本消息走 pushMsgToStore 上屏（store 驱动）；图片走 appendRow 直插 DOM（chat_extra.js 里同步处理时间）。
TIMEABLE_ACTIONS = {
    "我方打字", "对方发消息", "对方后台发消息", "后台消息队列",
    "发送图片", "对方发图片", "我方发送图片", "对方发送图片",
}


def _strip_trailing_time(arg):
    """从动作参数里剥离尾部时间标注，返回 (剥离后的arg, 时间或'')。

    只认「最后一个 `|` 分段整段匹配时间」的情况（`内容 | 18:22`），
    时间必须写在最后；其它 `|` 分段（停留/插话）不受影响。
    """
    if not isinstance(arg, str) or "|" not in arg:
        return arg, ""
    parts = [x.strip() for x in arg.split("|")]
    if len(parts) < 2 or not parts[-1]:
        return arg, ""
    if _TIME_DETECT_RE.match(parts[-1]):
        return " | ".join(parts[:-1]).strip(), parts[-1]
    return arg, ""


# 文本剧本指令 -> (动作id, 参数名)。无参数的动作参数名为 None
TEXT_COMMAND_MAP = {
    "打开聊天": "联系人",
    "我方打字": "内容",
    "打字不发": "内容",
    "删除文字": "数量",
    "对方正在输入": "秒数",
    "对方发消息": "内容",
    "对方后台发消息": "内容",
    "后台消息队列": "数据",
    "查看图片": "图片",
    "切换Tab": "Tab",
    "进入朋友圈": None,
    "向下滚动": "像素",
    "点赞": None,
    "评论": "内容",
    "发朋友圈": "内容",
    "设置头像": "图片",
    "设置背景": "图片",
    "编辑朋友圈": "数据",
    "回到聊天主页": None,
    "返回聊天主页": None,
    "返回主页": None,
    "隐藏键盘": None,
    "等待": "秒数",
    "编辑主页": "数据",
    "应用场景": "场景",
    "编辑会话": "数据",
    "修改昵称": "昵称",
    "修改签名": "签名",
    "发送图片": "图片",
    "对方发图片": "图片",
    "我方发送图片": "图片",
    "对方发送图片": "图片",
    "发送表情": "表情",
    "对方表情": "表情",
    "发送语音": "秒数",
    "对方语音": "秒数",
    "撤回我的消息": None,
    "对方撤回消息": None,
    "转账": "金额",
    "对方转账": "金额",
    "转发消息": "内容",
    "@成员": "昵称",
    # ---- 常用别名（补充容错）----
    "回到主页": None,
    "对方打字": "内容",
    "打开会话": "联系人",
    "进入聊天": "联系人",
    "点赞动态": None,
    "发表评论": "内容",
    "看朋友圈": None,
    "滚屏": "像素",
    "滚动": "像素",
    "切换标签": "Tab",
    "切换tab": "Tab",
}

# 动作别名 -> 规范动作名（execute_step 开头统一归一，剧本与转译结果都适用）
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
    "后台消息队列": "后台消息队列",
    "打开会话": "打开聊天",
    "进入聊天": "打开聊天",
    "进入聊天会话": "打开聊天",
    "点赞动态": "点赞",
    "给动态点赞": "点赞",
    "发表评论": "评论",
    "评论动态": "评论",
    "看朋友圈": "进入朋友圈",
    "进入朋友圈页面": "进入朋友圈",
    "滚屏": "向下滚动",
    "滚动": "向下滚动",
    "滑动": "向下滚动",
    "切换标签": "切换Tab",
    "切换tab": "切换Tab",
    "发朋友圈动态": "发朋友圈",
    "发语音": "发送语音",
    "转帐": "转账",
    "打钱": "转账",
    "发红包": "转账",
    "打开加号面板": "打开转账面板",
    "打开功能面板": "打开转账面板",
    "点加号": "打开转账面板",
    "发表情": "发送表情",
    "发一个表情": "发送表情",
    "发贴纸": "发送表情",
    "我方发送图片": "发送图片",
    "对方发送图片": "对方发图片",
}


def parse_script_text(text: str):
    """解析文本剧本内容 -> 动作步骤列表 [{"action":..., "params":{...}}]

    兼容：空行 / # 注释行自动跳过；无法识别的行打印警告并跳过。
    """
    steps = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            print(f"[剧本警告] 第 {lineno} 行格式无法识别，已跳过：{line}")
            continue
        cmd, arg = m.group(1).strip(), m.group(2).strip()
        param_name = TEXT_COMMAND_MAP.get(cmd)
        if param_name is None and cmd not in TEXT_COMMAND_MAP:
            print(f"[剧本警告] 第 {lineno} 行未知指令 [{cmd}]，已跳过")
            continue
        # 时间标注（时间分隔条占位）：`[动作] 内容 | 18:22` / `内容 | 昨天 23:52`。
        # 先剥离尾部时间，其余 `|` 分段（停留/插话）不受影响。
        time_annot = None
        if cmd in TIMEABLE_ACTIONS and "|" in arg:
            arg, time_annot = _strip_trailing_time(arg)
        params = {param_name: arg} if param_name else {}
        if time_annot:
            params["时间"] = time_annot
        # [打字不发] 支持内联停顿 + 对方插话：`[打字不发] 内容 | 0.3 | 对方消息；再一条`
        #   -> 内容=「内容」，停留=0.3 秒，插话=[「对方消息」,「再一条」]。
        # 无「| 秒数」时与原来一致（停留缺省）；无「| 插话」时无插话（向后兼容）。
        if cmd == "打字不发" and "|" in arg:
            parts = [x.strip() for x in arg.split("|")]
            params["内容"] = parts[0]
            if len(parts) > 1 and parts[1]:
                params["停留"] = parts[1]
            if len(parts) > 2 and parts[2]:
                params["插话"] = parts[2]
        # [我方打字] 支持内联对方插话：`[我方打字] 内容 | 对方消息；再一条`
        #   -> 内容=「内容」，插话=[「对方消息」,「再一条」]。无「| 插话」时无插话。
        elif cmd == "我方打字" and "|" in arg:
            content, _, ij = arg.partition("|")
            params["内容"] = content.strip()
            ij = ij.strip()
            if ij:
                params["插话"] = ij
        # [对方后台发消息] 支持内联目标会话：`[对方后台发消息] 联系人 | 内容`
        #   -> 联系人=「联系人」，内容=「内容」。无「|」时内容取整行（联系人缺省，运行时报错）。
        elif cmd == "对方后台发消息" and "|" in arg:
            contact, _, content = arg.partition("|")
            params["联系人"] = contact.strip()
            params["内容"] = content.strip()
        # [后台消息队列] 也支持内联目标会话：`[后台消息队列] 联系人 | 内容`
        #   -> 数据=[{"联系":「联系人」,"内容":「内容」}]（装载即投递，之后打开该会话可看到）。
        #   纯 JSON 数组写法仍然支持：`[后台消息队列] [{"联系":X,"内容":Y},...]`。
        elif cmd == "后台消息队列" and "|" in arg:
            contact, _, content = arg.partition("|")
            params["数据"] = [{"联系": contact.strip(), "内容": content.strip()}]
        steps.append({"action": cmd, "params": params})
    return steps


def parse_script(path: str):
    """解析旧文本剧本文件 -> 动作步骤列表 [{"action":..., "params":{...}}]"""
    with open(path, "r", encoding="utf-8") as fh:
        return parse_script_text(fh.read())


def load_workflow(path: str):
    """加载 workflow.json -> 步骤列表"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    steps = data.get("steps", data) if isinstance(data, dict) else data
    if not isinstance(steps, list):
        raise ValueError(f"工作流文件格式错误（应为 {{steps:[...]}} 或数组）：{path}")
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or "action" not in s:
            raise ValueError(f"工作流第 {i + 1} 步缺少 action 字段：{s}")
    return steps


def _load_people_avatars() -> dict:
    """读取人物库 people.json，返回 {人名: 头像路径}（学员/美女两组拍平）。"""
    avatars = {}
    try:
        pp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "people.json")
        with open(pp, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        for grp in ("学员", "美女"):
            sub = d.get(grp) if isinstance(d, dict) else None
            if isinstance(sub, dict):
                avatars.update({str(k): str(v) for k, v in sub.items() if isinstance(v, str)})
    except (OSError, ValueError, TypeError):
        avatars = {}
    return avatars


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


def _reconcile_home_contacts(steps: list) -> list:
    """运行前兜底：确保 [编辑主页] 的「数据」覆盖此后所有 [打开聊天] 引用的联系人。

    历史会话块（或旧转译）生成的 [编辑主页] 通常只含块内的联系人；若剧本其余部分
    又通过 [打开聊天] 引用了列表外的联系人（例如「鱼丸卡莉」被 AI 换成「范思琪」），
    运行期会因「聊天列表中找不到联系人」而失败。本函数在步骤加载后、执行前扫描一遍：
    凡是 [打开聊天] 的联系人不在 [编辑主页] 数据里，就补一条
    {{"name": 联系人名, "text": "", "avatar": 人物库头像}}（人物库没有该名字时 avatar 留空，
    运行时用默认头像）。若步骤里根本没有 [编辑主页]，则在最前面插入一条。

    返回新的步骤列表（原地补齐，返回同一引用）。
    """
    home = None
    home_exists = False
    existing = set()
    for step in steps:
        if isinstance(step, dict) and step.get("action") in ("编辑主页", "应用场景", "编辑会话"):
            home_exists = True
            data = (step.get("params") or {}).get("数据")
            if isinstance(data, list):
                home = data
                existing = {str(it.get("name", "")).strip()
                            for it in home if isinstance(it, dict)}
            break
    contacts, seen = [], set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        act = step.get("action")
        pp = step.get("params") or {}
        if act == "打开聊天":
            n = str(pp.get("联系人", "")).strip()
            if n and n not in seen:
                seen.add(n)
                contacts.append(n)
        elif act == "对方后台发消息":
            n = str(pp.get("联系人", pp.get("会话", ""))).strip()
            if n and n not in seen:
                seen.add(n)
                contacts.append(n)
        elif act in ("后台消息队列", "后台消息"):
            for n in _extract_bg_queue_contacts(pp.get("数据", pp.get("data", pp.get("队列")))):
                if n and n not in seen:
                    seen.add(n)
                    contacts.append(n)
    if not contacts:
        return steps
    if home is None:
        if home_exists:
            # 数据来自 .json 文件路径，无法内联补联系人，贸然插入会与文件版冲突，跳过。
            return steps
        home = []
        steps.insert(0, {"action": "编辑主页", "params": {"数据": home}})
    avatars = _load_people_avatars()
    for n in contacts:
        if n in existing:
            continue
        home.append({"name": n, "text": "", "avatar": avatars.get(n, "")})
        existing.add(n)
    # 与编辑器离线解析保持一致：主页一屏最多 9 个会话，超出的丢弃；
    # [打开聊天] 不在主页前 9 里时对齐到主页可见人物，避免打开屏幕外的人造成前后对不上。
    try:
        import script_translator
        warns = []
        script_translator.cap_home_and_align_contacts(steps, warns)
        for w in warns:
            print(f"[工作流] {w}", flush=True)
    except Exception:
        pass  # 兜底增强失败不影响运行（仍按补齐后的列表执行）
    return steps


def _inject_image_autoopen(steps: list) -> list:
    """把历史会话里「打开动画」标记的图片消息，转成进入会话后的 [查看图片] 步骤。

    [编辑主页]/[应用场景]/[编辑会话] 的「数据」里，kind==image 且 open 为真的消息，
    按其在会话中的顺序，在该会话 [打开聊天] 之后依次插入 [查看图片] 步骤，从而
    进入对话看到那几张图时，手机逐个点开放大再关闭（模拟真人看图）。
    无 [打开聊天] 匹配的会话则跳过（不注入）。
    """
    scene_actions = {"编辑主页", "应用场景", "编辑会话"}
    conf_by_conv = {}                            # 会话名 -> [{图片,停留,焦点}, ...]，按消息顺序
    for step in steps:
        action = ACTION_ALIASES.get(step.get("action"), step.get("action"))
        if action not in scene_actions:
            continue
        params = step.get("params", {}) or {}
        data = params.get("数据", params.get("data"))
        if not isinstance(data, list):
            continue
        for conv in data:
            if not isinstance(conv, dict):
                continue
            name = str(conv.get("name", "")).strip()
            msgs = conv.get("messages")
            if not name or not isinstance(msgs, list):
                continue
            specs = []
            for m in msgs:
                if not isinstance(m, dict) or m.get("kind") != "image":
                    continue
                mode = _parse_open_mode(m.get("open"))
                if mode == "none":
                    continue
                img = str(m.get("image", "")).strip()
                if not img:                      # 还没配图，无法点开，跳过
                    continue
                hold = m.get("openHold")
                if hold in (None, ""):
                    hold = None
                focus = m.get("openFocus")
                if focus in (None, ""):
                    focus = None
                zoom = _parse_zoom(m.get("openZoom"), IMAGE_ZOOM_DEFAULT)
                spec = {"图片": img, "停留": hold, "焦点": focus, "放大倍率": zoom}
                spec["打开"] = "只点开" if mode == "view" else "是"
                specs.append(spec)
            if specs:
                conf_by_conv.setdefault(name, []).extend(specs)
    if not conf_by_conv:
        return steps
    out = []
    for step in steps:
        out.append(step)
        action = ACTION_ALIASES.get(step.get("action"), step.get("action"))
        if action == "打开聊天":
            name = str((step.get("params", {}) or {}).get("联系人", "")).strip()
            if conf_by_conv.get(name):
                for spec in conf_by_conv[name]:
                    out.append({"action": "查看图片", "params": dict(spec)})
                conf_by_conv[name] = []
    return out


def _parse_interjections(value):
    """解析「插话」参数为对方消息列表。

    支持：单条字符串、用「；/;」分隔的多条字符串、或已是列表/元组。
    空/缺省返回 []，每条会 trim。用于「打字不发/我方打字」的边打字边对面插话。
    """
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    parts = re.split(r"[；;]", str(value))
    return [x.strip() for x in parts if x.strip()]


def _typing_hold_default() -> float:
    """读取「打字不发」默认停留时长（秒）；可用 settings.json 的 typing_hold_default 覆盖，缺省 1.5。"""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
        with open(p, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return float(d.get("typing_hold_default", 1.5))
    except (OSError, ValueError, TypeError):
        return 1.5


def _num(value, default, allow_all=False):
    """参数转数字；'全部' 等关键字 -> -1；空/无法解析 -> default。

    秒数类参数需要小数精度（如 0.5 秒），因此带小数的值保留为 float，
    整数类参数（像素/数量）仍返回 int。
    """
    if value is None or value == "":
        return default
    if allow_all and str(value).strip() in ("全部", "all", "-1"):
        return -1
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num == int(num):
        return int(num)
    return num


def _truthy(value):
    """把常见「是/否」表述转成 bool；空 / 缺省一律视为 False。"""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s not in ("", "0", "no", "off", "false", "否", "不", "关闭", "不打开")


def _parse_open_mode(value):
    """解析「打开」为图片点开模式：none / view(只点开不放大) / zoom(点开并放大)。

    「只点开不放大」由这些可读的表述触发：只点开 / 不放大 / 查看 / 只显示 / 不缩放。
    其余真有值时一律视为「点开并放大」（默认行为）。
    """
    if not _truthy(value):
        return "none"
    s = str(value).strip().lower()
    if s in ("只点开", "不放大", "查看", "只显示", "不缩放", "open", "view"):
        return "view"
    return "zoom"

def _parse_move_top(value):
    """解析「置顶」，缺省为 True（后台消息到达时把该会话移到主页顶部，贴合真机）。

    显式置 False / 否 / off / 不置顶 时返回 False，其余真值返回 True。
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s not in ("0", "no", "off", "false", "否", "不", "不置顶", "不顶置", "关闭")


def _parse_zoom(value, default=IMAGE_ZOOM_DEFAULT):
    """解析「放大倍率」为数字；空 / 非法 / 过小（<=0.5）回退到 default。"""
    if value is None or value == "":
        return default
    try:
        z = float(value)
    except (TypeError, ValueError):
        return default
    return z if z > 0.5 else default


def _open_image_if_requested(bot, p, path):
    """图片上屏后，若动作参数「打开」为真，则点开放大查看再自动关闭。"""
    if not _truthy(p.get("打开")):
        return
    hold = p.get("停留")
    hold = float(hold) if hold not in (None, "") else None
    mode = _parse_open_mode(p.get("打开"))
    zoom = _parse_zoom(p.get("放大倍率"), IMAGE_ZOOM_DEFAULT)
    bot.view_image(path, hold, _parse_focus(p.get("焦点")),
                   zoom=zoom, no_zoom=(mode == "view"))


def _parse_focus(value):
    """解析「焦点」参数为 {x,y} 或 None；支持 {"x","y"} / "x,y" / 直接字符串。"""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    s = str(value).strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) == 2:
        try:
            return {"x": float(parts[0]), "y": float(parts[1])}
        except (TypeError, ValueError):
            return None
    return None


def execute_step(bot: WeChatAuto, action: str, params: dict):
    """执行单个工作流动作（params 为 dict）"""
    action = ACTION_ALIASES.get(action, action)   # 别名统一归一
    p = params or {}
    if action in ("回到聊天主页", "返回聊天主页", "返回主页"):
        _hold = p.get("停留")
        bot.go_back_home(None if _hold in (None, "") else _hold)
    elif action == "打开聊天":
        bot.open_chat(str(p.get("联系人", "")).strip())
    elif action == "我方打字":
        if bot.page.locator(".dialogue-section").count() == 0:
            raise RuntimeError("当前不在聊天对话页，无法打字。请先 [打开聊天]。")
        bot.human_type(".chat-txt", str(p.get("内容", "")),
                       interjections=_parse_interjections(p.get("插话")),
                       time_spec=p.get("时间"))
    elif action == "打字不发":
        bot.type_no_send(str(p.get("内容", "")), _num(p.get("停留"), _typing_hold_default()),
                         interjections=_parse_interjections(p.get("插话")))
    elif action == "删除文字":
        bot.delete_chars(_num(p.get("数量"), -1, allow_all=True))
    elif action == "对方正在输入":
        bot.show_typing(_num(p.get("秒数"), 1.2))
    elif action == "对方发消息":
        # 对方文字一整行上屏（不再逐字打字），更贴近真机一条消息
        bot.send_peer_message(str(p.get("内容", "")), p.get("头像"), p.get("时间"))
    elif action == "对方后台发消息":
        # 对方的会话不在当前画面：给「未打开的会话」投递消息，只更新主页预览/角标
        contact = str(p.get("联系人", p.get("会话", ""))).strip()
        if not contact:
            raise ValueError("[对方后台发消息] 缺少联系人（params.联系人），"
                             "表示要给哪个会话投递后台消息。")
        move_top = _parse_move_top(p.get("置顶"))
        bot.send_peer_message_bg(contact, str(p.get("内容", "")), p.get("头像"),
                                 p.get("发送者"), move_top, p.get("时间"), p.get("图片"))
    elif action == "后台消息队列":
        # 装载后台消息队列：队列里每条消息都在【当前这一时刻】后台发出（不改变当前画面），
        # 刷新对应会话的主页预览+未读角标，之后打开该会话即可看到。
        data = p.get("数据", p.get("data", p.get("队列")))
        if data is None or (isinstance(data, str) and not data.strip()):
            raise ValueError("[后台消息队列] 缺少数据参数（JSON 数组或 .json 文件路径）")
        bot.load_bg_queue(data, p.get("时间"))
    elif action == "查看图片":
        hold = p.get("停留")
        hold = float(hold) if hold not in (None, "") else None
        mode = _parse_open_mode(p.get("打开", "是"))
        zoom = _parse_zoom(p.get("放大倍率"), IMAGE_ZOOM_DEFAULT)
        bot.view_image(str(p.get("图片", "")).strip(), hold, _parse_focus(p.get("焦点")),
                       zoom=zoom, no_zoom=(mode == "view"))
    elif action == "切换Tab":
        bot.switch_tab(str(p.get("Tab", "")))
    elif action == "进入朋友圈":
        bot.enter_moments()
    elif action == "向下滚动":
        bot.scroll_down(_num(p.get("像素"), 300))
    elif action == "点赞":
        bot.like()
    elif action == "评论":
        bot.comment(str(p.get("内容", "")))
    elif action == "发朋友圈":
        bot.post_moment(str(p.get("内容", "")), p.get("图片"))
    elif action == "设置头像":
        bot.set_avatar(str(p.get("图片", "")))
    elif action == "设置背景":
        bot.set_bg(str(p.get("图片", "")))
    elif action == "编辑朋友圈":
        data = p.get("数据", p.get("data"))
        if not data:
            raise ValueError("[编辑朋友圈] 缺少数据参数（JSON 数组或 .json 文件路径）")
        if isinstance(data, str) and data.strip().endswith(".json"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), data.strip())
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        bot.edit_moments(data)
    elif action == "编辑主页":
        data = p.get("数据", p.get("data"))
        if not data:
            raise ValueError("[编辑主页] 缺少数据参数（JSON 数组或 .json 文件路径）")
        if isinstance(data, str) and data.strip().endswith(".json"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), data.strip())
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        bot.set_home_list(data)
    elif action == "应用场景":
        data = p.get("场景", p.get("scene", p.get("数据", p.get("data"))))
        if not data:
            raise ValueError("[应用场景] 缺少场景参数（JSON 对象或 scene.json 文件路径）")
        if isinstance(data, str) and data.strip().endswith(".json"):
            data = os.path.join(os.path.dirname(os.path.abspath(__file__)), data.strip())
        bot.apply_scene(data)
    elif action == "编辑会话":
        data = p.get("数据", p.get("data"))
        if not data:
            raise ValueError("[编辑会话] 缺少数据参数（JSON 数组或 .json 文件路径）")
        if isinstance(data, str) and data.strip().endswith(".json"):
            data = os.path.join(os.path.dirname(os.path.abspath(__file__)), data.strip())
        bot.edit_conversation(data)
    elif action == "修改昵称":
        bot.set_name(str(p.get("昵称", "")).strip())
    elif action == "修改签名":
        bot.set_signature(str(p.get("签名", "")).strip())
    elif action == "发送图片":
        img_path = str(p.get("图片", "")).strip()
        bot.send_image(img_path, p.get("时间"))
        _open_image_if_requested(bot, p, img_path)
    elif action == "对方发图片":
        img_path = str(p.get("图片", "")).strip()
        bot.peer_image(img_path, p.get("时间"))
        _open_image_if_requested(bot, p, img_path)
    elif action == "发送表情":
        bot.send_emoji(str(p.get("表情", p.get("图片", ""))).strip())
    elif action == "对方表情":
        bot.peer_emoji(str(p.get("表情", p.get("图片", ""))).strip())
    elif action == "发送语音":
        bot.send_voice(_num(p.get("秒数"), 3))
    elif action == "对方语音":
        bot.peer_voice(_num(p.get("秒数"), 3))
    elif action == "撤回我的消息":
        bot.withdraw()
    elif action == "对方撤回消息":
        bot.peer_withdraw()
    elif action == "打开转账面板":
        bot.open_transfer_panel()
    elif action == "转账金额":
        bot.transfer(str(p.get("接收人", p.get("联系人", ""))).strip(),
                     str(p.get("金额", "50.00")), str(p.get("备注", "")),
                     str(p.get("密码", "123456")))
    elif action == "转账":
        bot.transfer(str(p.get("接收人", p.get("联系人", ""))).strip(),
                     str(p.get("金额", "50.00")), str(p.get("备注", "")),
                     str(p.get("密码", "123456")))
    elif action == "对方转账":
        bot.peer_transfer(str(p.get("接收人", p.get("联系人", ""))).strip(),
                          str(p.get("金额", "50.00")), str(p.get("备注", "")))
    elif action == "转账上屏":
        # 不经过面板/密码，直接上屏橙色转账卡片（等价于旧行为）
        bot._chat_ext("selfTransfer", str(p.get("接收人", p.get("联系人", ""))).strip(),
                      str(p.get("金额", "1.00")), str(p.get("备注", "")))
    elif action == "转发消息":
        bot.forward(str(p.get("内容", "")).strip())
    elif action == "@成员":
        bot.mention(str(p.get("昵称", "")).strip())
    elif action == "隐藏键盘":
        bot._kb_hide()
    elif action == "等待":
        bot._wait(_num(p.get("秒数"), 1.0))
    else:
        print(f"[剧本警告] 未知动作 [{action}]，已跳过")


def main():
    global BASE_URL, SPEED, TYPE_SPEED, ENABLE_BGM, BGM_PATH, OUT_TAG, CHAT_BG, CHAT_BG_SEED
    parser = argparse.ArgumentParser(description="仿微信界面全自动操作+录屏")
    parser.add_argument("--script", default=None, help="旧文本剧本文件路径")
    parser.add_argument("--workflow", default=None, help="JSON 工作流文件路径")
    parser.add_argument("--headless", action="store_true", help="无头模式运行（默认有头可见）")
    parser.add_argument("--liveport", type=int, default=0,
                        help="实时画面截图服务端口（0 表示关闭，编辑器默认 8001）")
    parser.add_argument("--url", default=BASE_URL, help="前端项目地址")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="倍速：>1 更快（缩短视频时长），如 2 表示 2 倍速")
    parser.add_argument("--typing-speed", type=float, default=30.0,
                        help="打字动画倍速：>1 只加快打字（按键节奏/拼音选字/删除回删，如 30 = 打字放 30 倍），"
                             "已改为单次 API 往返(pressType)实现，且按压高亮有 40ms 可见下限。默认 30.0。")
    parser.add_argument("--scene", default=None,
                        help="启动时先应用的 scene.json 场景文件（我的资料+会话+朋友圈）")
    parser.add_argument("--intro", action="store_true",
                        help="录制完成后在视频开头拼接 1-2 秒锁屏收消息开场（与视频会话对齐）")
    parser.add_argument("--intro-target", default="",
                        help="开场锁屏的发送者/目标会话名字；留空则自动取工作流里第一个 [打开聊天] 的联系人")
    parser.add_argument("--editmode", action="store_true",
                        help="编辑模式：打开手机画面后空闲待命，供编辑器点击画面/修改元素")
    parser.add_argument("--bgm", default=None,
                        help="背景音乐文件路径（默认 苹果音效/背景音乐.mp3；每次生成会随机化去重并铺满视频时长）")
    parser.add_argument("--no-bgm", action="store_true",
                        help="不混入背景音乐（默认开启背景音乐铺底）")
    parser.add_argument("--tag", default="",
                        help="输出视频文件名的前缀标签（如任务 id），用于并发跑批时避免文件名冲突；留空则用默认 wx_时间戳")
    parser.add_argument("--chat-bg", default=None,
                        help="聊天页背景图片（/images/bg/xxx.jpg 或相对 vue-WeChat/public 的路径）；"
                             "不传则在 --chat-bg-dir 里自动挑。整条视频用同一张，保持一致")
    parser.add_argument("--chat-bg-dir", default=None,
                        help="聊天背景图片目录；配合 --chat-bg-seed 可让每条视频自动挑一张且复跑稳定")
    parser.add_argument("--chat-bg-pick", default="random", choices=["random", "sequential"],
                        help="从 --chat-bg-dir 挑选背景的方式（默认 random 随机；sequential 按 seed 取模顺排）")
    parser.add_argument("--chat-bg-seed", type=int, default=None,
                        help="自动挑选背景的随机种子（None=真随机）。并发跑批可传任务 id 的 hash，"
                             "使同一条视频背景稳定")
    args = parser.parse_args()

    SPEED = max(0.1, float(args.speed))
    TYPE_SPEED = max(0.1, float(args.typing_speed))
    OUT_TAG = args.tag
    BASE_URL = args.url.rstrip("/") + "/#/"
    ENABLE_BGM = not args.no_bgm
    if args.bgm:
        BGM_PATH = args.bgm
    # 聊天背景：显式路径优先，否则从目录自动挑；都没给 → 保持默认深色
    CHAT_BG = _pick_chat_bg(args.chat_bg, args.chat_bg_dir, args.chat_bg_pick, args.chat_bg_seed)
    CHAT_BG_SEED = args.chat_bg_seed
    if CHAT_BG:
        print(f"[背景] 本视频聊天背景：{CHAT_BG}（seed={CHAT_BG_SEED}）", flush=True)
    if args.intro:
        print("[开场] 已开启：录制完成后将拼接锁屏入场动画。", flush=True)

    # ============ 编辑模式：画面就绪后一直待命，等编辑器命令 ============
    if args.editmode:
        bot = WeChatAuto(headless=args.headless)
        _LIVE_BOT["bot"] = bot
        live_server = _start_live_guarded(args.liveport)
        bot._live_enabled = live_server is not None
        try:
            ensure_frontend_running()
            bot.start()
            print("[编辑模式] 已就绪：编辑器里点击画面可导航，切换「编辑」可修改元素。", flush=True)
            while not _STOP_EDIT.is_set():
                bot._process_live_commands()
                bot._grab_frame(False)
                time.sleep(0.15)
            print("[编辑模式] 已收到停止信号，正在退出……", flush=True)
        finally:
            if live_server:
                live_server.shutdown()
            bot.stop()
        return

    # ============ 工作流 / 文本剧本运行 ============
    if args.workflow:
        if not os.path.isfile(args.workflow):
            print(f"[错误] 工作流文件不存在：{args.workflow}")
            sys.exit(1)
        steps = load_workflow(args.workflow)
        src_desc = args.workflow
    else:
        script_path = args.script or DEFAULT_SCRIPT
        if not os.path.isfile(script_path):
            print(f"[错误] 剧本文件不存在：{script_path}")
            sys.exit(1)
        steps = parse_script(script_path)
        src_desc = script_path

    if not steps:
        print("[错误] 工作流/剧本为空或没有任何有效指令。")
        sys.exit(1)
    # 运行前兜底：确保 [编辑主页] 覆盖所有 [打开聊天] 引用的联系人，
    # 避免"聊天列表中找不到联系人"（无论工作流来自历史块 / 旧转译 / 陈旧版本都能修复）。
    steps = _reconcile_home_contacts(steps)
    # 把历史会话里标记「打开动画」的图片，注入为进入会话后的 [查看图片] 步骤
    steps = _inject_image_autoopen(steps)
    print(f"[工作流] 共载入 {len(steps)} 条动作（来源：{src_desc}）。")

    bot = WeChatAuto(headless=args.headless)
    # 绑定实时画面服务（后台线程截图用），并启动服务
    _LIVE_BOT["bot"] = bot
    live_server = _start_live_guarded(args.liveport)
    bot._live_enabled = live_server is not None
    mp4 = None
    try:
        ensure_frontend_running()
        bot.start()
        if args.scene:
            scene_path = args.scene if os.path.isfile(args.scene) else \
                os.path.join(os.path.dirname(os.path.abspath(__file__)), args.scene)
            print(f"[场景] 正在应用场景：{scene_path}")
            bot.apply_scene(scene_path)
            _pump_wait(0.8)
        # 开录前静默预热：预载场景/剧本用到的图片 + 按文案加载字体字形，
        # 随后丢弃预热帧，让视频从「资源齐备的主页」开始（消除进画面才加载的卡顿）。
        try:
            _warm_texts = bot.collect_step_texts(steps)
            _warm_urls = []
            for _s in steps:
                for _v in (_s.get("params") or {}).values():
                    if isinstance(_v, str):
                        _warm_urls += _ASSET_URL_RE.findall(_v)
            if args.scene and os.path.isfile(args.scene):
                with open(args.scene, "r", encoding="utf-8") as _fh:
                    _warm_urls += _ASSET_URL_RE.findall(_fh.read())
            # 候选条微信小表情图集：不在页面 DOM，需显式全部预载解码，避免候选条首帧闪图/卡顿
            _warm_urls += _list_wxemoji_urls()
            bot.warmup(texts=_warm_texts, urls=list(dict.fromkeys(_warm_urls)))
            # 首屏即用户主页：在 reset 前应用首个「编辑主页/应用场景」，让 reset 后的
            # 第一帧直接就是剧本编排好的主页（而非默认参考主页闪一下），从而
            # 保证视频第一帧是主页，并停留约 0.5s 再进入第一个会话。
            # 注意：必须先应用主页数据再预热输入管线 —— 预热要预打开首个会话，
            # 若主页还是默认列表（不含剧本联系人），open_chat 会因找不到联系人而失败。
            try:
                if steps:
                    _fp = (steps[0].get("params") or {})
                    if steps[0].get("action") == "编辑主页":
                        bot.set_home_list(_fp.get("数据", _fp.get("data")))
                    elif steps[0].get("action") == "应用场景":
                        bot.apply_scene(_fp.get("场景", _fp.get("scene", _fp.get("数据", _fp.get("data")))))
            except Exception as exc:                  # noqa: BLE001
                print(f"[预热] 首屏主页预应用失败（忽略）：{exc}")
            # 先预热「雾凇词表」：首次 _wusong_word_len 会一次性读+解析 72万 词 JSON（约 0.7s），
            # 这一档正是「键盘弹出后、首字前整个画面卡住 ~1s」的根源（首键分词被硬卡住）。
            # 必须在下面「逐条文案预热打字」之前加载，否则预热敲键本身还会被冷词典卡住，
            # 起不到预热效果（加载后再预热，真实首键只做 set 查询，不再开键盘后迟迟不出字）。
            _wusong_words()
            # 预热整个工作流的冷启动链：预打开每个将被打开的会话、静默敲一遍每条真实文案的
            # 完整输入管线、预载每张要查看/发送的图片，随后带回主页。
            # 相关帧会被下面的 reset_frames() 丢弃，只为了让浏览器端「输入框聚焦+候选刷新+
            # 合成渲染」以及每个会话的历史/头像/图片这条链先热起来——不止第一条消息，
            # 后续每一步第一次碰到的冷加载也一并消除（某时刻像被放慢动作的根源）。
            bot._prewarm_workflow(steps)
            bot.reset_frames()
            # 预热+首屏主页均已就绪：不再裁切开头（此前 1.0s 会把主页整段剪掉，导致
            # 视频第一帧落在「切入第一个会话」的转场中途）。设为 0 保留主页约 0.5s。
            bot.trim_head_sec = 0.0
            print(f"[预热] 已预载 {len(set(_warm_urls))} 个静态资源并预热字体，视频从就绪画面开始。")
        except Exception as exc:                # noqa: BLE001
            print(f"[预热] 跳过（不影响录屏）：{exc}")
        # 兜底再预热一次「雾凇词表」（幂等，已加载则直接返回）：确保即使上面的预热块因
        # 异常被跳过，首个真实首键也不会被 72万 词 JSON 的冷解析卡住（开键盘后迟迟不出字）。
        _wusong_words()
        # 剧本执行时钟清零：供「后台消息队列」旧式「秒」触发的时钟基准保留兼容使用
        # （后台消息队列现已改为「装载即投递」，此处仅为向后兼容不再作为主力）。
        global _RUN_CLOCK
        _RUN_CLOCK = 0.0
        total = len(steps)
        for idx, step in enumerate(steps, start=1):
            action = step["action"]
            params = step.get("params", {}) or {}

            def _on_watchdog_timeout(a=action, pp=params):
                print(f"\n[看门狗] 动作 [{a}] {pp} 超过 {STEP_WATCHDOG_SEC}s 未完成，堆栈如下：", flush=True)
                faulthandler.dump_traceback()
                os._exit(3)

            watchdog = threading.Timer(STEP_WATCHDOG_SEC, _on_watchdog_timeout)
            watchdog.daemon = True
            watchdog.start()
            try:
                print(f"  [执行 {idx:>3}/{total}] [{action}] {params}", flush=True)
                bot.drain_bg_queue(idx)          # 每步前结算后台消息队列（现为向后兼容，队列已装载即投递）
                execute_step(bot, action, params)
                bot.live_snapshot()   # 每完成一步就刷新一次实时画面
            except (PWTimeoutError, RuntimeError, ValueError) as exc:
                raise RuntimeError(
                    f"\n[执行失败] 第 {idx}/{total} 条动作 [{action}] {params}\n原因：{exc}"
                ) from exc
            finally:
                watchdog.cancel()
        # 性能探针 dump：读浏览器端 __wxPerfLog（仅 WX_PERF=1 时有数据），定位开键盘前 2s 卡顿。
        if os.environ.get("WX_PERF") == "1":
            try:
                _plog = bot.page.evaluate("window.__wxPerfLog || []")
            except Exception:                    # noqa: BLE001
                _plog = []
            if _plog:
                print("[perf] __wxPerfLog（label/dt=本阶段ms/total=本轮累计ms）:")
                for _e in _plog:
                    print(f"  [perf] {_e.get('label','?'):<24} dt={_e.get('dt','?'):>5}ms  total={_e.get('total','?'):>6}ms")
        print("[完成] 全部动作执行成功，正在保存视频……")
    except Exception as exc:                        # noqa: BLE001
        print(f"[异常] {exc}")
        raise
    finally:
        mp4 = bot.stop()
        # 与编辑模式分支对齐：显式关闭实时画面服务，避免端口残留
        if live_server:
            try:
                live_server.shutdown()
            except Exception:                   # noqa: BLE001
                pass

    if mp4:
        size_mb = os.path.getsize(mp4) / 1024 / 1024
        print(f"[视频] 已保存：{mp4}（{size_mb:.1f} MB）")
        # ---- 可选：录制完成后在开头拼接 1-2 秒锁屏收消息开场 ----
        if args.intro:
            try:
                _prepend = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "准备制作界面", "prepend_intro.py")
                _cmd = [sys.executable, _prepend, "--main", mp4]
                if args.workflow:
                    _cmd += ["--workflow", args.workflow]
                if args.scene:
                    _cmd += ["--scene", args.scene]
                if args.intro_target.strip():
                    _cmd += ["--target", args.intro_target.strip()]
                print("[开场] 正在合成锁屏入场动画……", flush=True)
                subprocess.run(_cmd, cwd=os.path.dirname(os.path.abspath(__file__)), check=True)
                print("[视频] 已合成锁屏开场。", flush=True)
            except Exception as exc:                        # noqa: BLE001
                print(f"[警告] 开场锁屏合成失败，已保留原视频：{exc}")


if __name__ == "__main__":
    main()