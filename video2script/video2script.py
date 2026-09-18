#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video2script — 对标博主微信聊天录屏 → 剧本 txt 草稿（v1）

用法（在 video2script 目录下，或直接把视频拖到 2-视频转脚本.bat 上）:
    .venv\\Scripts\\python.exe video2script.py <视频路径或文件夹> [选项]

选项:
    --fps-low N     全扫采样帧率（默认 2，用于找页面切换点）
    --fps-high N    切换点精扫帧率（默认 8，用于还原消息）
    --probe         校准模式：只输出页面分类结果+抽样帧+OCR，不生成草稿
    --no-emoji      跳过表情模板匹配
    --debug-dump    把每个精扫帧的 OCR 结果存成 json（排查用）

输出（output/<视频名>/）:
    <视频名>.draft.txt   剧本草稿（翻译器兼容格式，[?] 行=待人工确认）
    report.md            不确定点报告（人工只看这个，5 分钟确认代替 30 分钟手打）
    frames/              关键帧截图

可移植性：全部路径基于脚本自身位置推导；换电脑/换盘符后先双击 1-安装依赖.bat。
"""

import re
import sys
import json
import shutil
import tempfile
import argparse
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent          # video2script/
PROJECT = ROOT.parent                            # 项目根（U 盘）
IMG_DIR = PROJECT / "vue-WeChat" / "public" / "images"
OUTPUT_DIR = ROOT / "output"

TS_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
ALLOWED_STAY = (0.3, 0.5, 1.0, 1.5)
WATERMARK_RE = re.compile(r"剧情演绎|纯属娱乐|如有雷同|纯属巧合|仅供娱乐|不良引导")

# ================================================================ 工具

def imread_u(path):
    """cv2.imread 的中文路径安全版。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_u(path, img):
    """cv2.imwrite 的中文路径安全版。"""
    ext = Path(path).suffix or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        return False
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(path))
    return True


def resolve_openable(path):
    """OpenCV 在 Windows 上不认中文路径：必要时把视频复制到 ASCII 临时目录。
    返回 (可打开的路径, 临时目录或 None)。"""
    p = Path(path)
    cap = cv2.VideoCapture(str(p))
    ok = cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0
    cap.release()
    if ok:
        return p, None
    tmp = Path(tempfile.mkdtemp(prefix="v2s_"))
    dst = tmp / ("v" + p.suffix.lower() or ".mp4")
    shutil.copy2(p, dst)
    cap = cv2.VideoCapture(str(dst))
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"打不开视频: {path}")
    cap.release()
    return dst, tmp

def snap_stay(seconds):
    """时长吸附到规范允许的停留档位。"""
    return min(ALLOWED_STAY, key=lambda s: abs(s - seconds))


def dhash(img, size=8):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (size + 1, size))
    d = g[:, 1:] > g[:, :-1]
    return sum(1 << (i * size + j) for i, row in enumerate(d) for j, v in enumerate(row) if v)


def hamming(a, b):
    return bin(a ^ b).count("1")


def load_emoji_templates():
    """wxemoji3d（e01.png→中文名，映射在 wxemoji3d_map.js）+ sticker 目录。"""
    templates = []
    map_js = IMG_DIR / "wxemoji3d_map.js"
    name_map = {}
    if map_js.exists():
        js = map_js.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(
                r'["\']?([\u4e00-\u9fa5A-Za-z0-9_]{1,10})["\']?\s*[:=]\s*["\']?(e\d{1,3})["\']?', js):
            name_map[m.group(2)] = m.group(1)
    d3 = IMG_DIR / "wxemoji3d"
    if d3.exists():
        for f in sorted(d3.glob("*.png")):
            img = imread_u(f)
            if img is not None:
                templates.append((dhash(img), name_map.get(f.stem, f.stem), "3d"))
    st = IMG_DIR / "sticker"
    if st.exists():
        for f in sorted(st.glob("*.*")):
            img = imread_u(f)
            if img is not None:
                templates.append((dhash(img), f.stem, "sticker"))
    return templates


def match_emoji(crop, templates, max_dist=16):
    if not templates or crop.size == 0:
        return None, 99
    h = dhash(crop)
    best, bd = None, 99
    for th, name, _k in templates:
        d = hamming(h, th)
        if d < bd:
            best, bd = name, d
    return (best, bd) if bd <= max_dist else (None, bd)


# ================================================================ 页面分类

def _green_bubble_like(frame_bgr):
    """统计"微信绿气泡形状"的连通域个数。
    气泡签名：高度占屏 1.5%~13%、宽高比>=1.8、宽度占屏>=10%。
    真机标定（xunuo_01）：聊天页绿块 h≈0.049H 宽高比>=4；实拍绿块 h=0.157H 宽高比0.75。"""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 50, 110), (72, 255, 255))
    h, w = mask.shape[:2]
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    cnt = 0
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        if area < w * h * 0.0004:
            continue
        hr = hh / h
        aspect = ww / max(hh, 1)
        if 0.015 < hr < 0.13 and aspect >= 1.8 and ww / w >= 0.10:
            cnt += 1
    return cnt


def classify_page(frame_bgr):
    """v2：支持微信深色模式录屏 + 排除实拍画面。
    返回 (kind, conf)：chat / list / viewer / unknown"""
    h, w = frame_bgr.shape[:2]
    small = cv2.resize(frame_bgr, (240, int(240 * h / w)))
    sh, sw = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    dark = float((gray < 45).mean())

    green = _green_bubble_like(frame_bgr)
    if green >= 1:
        return "chat", 0.85

    if dark > 0.55:
        # 深底无绿泡：实拍夜景 / 深色列表页 → 交人工（probe 可看帧）
        if 0.02 < float((gray[int(sh * 0.945):, :] < 140).mean()) < 0.6:
            return "list", 0.5
        return "unknown", 0.0
    if dark > 0.18:
        # 半暗 + 无绿 → 朋友圈图片查看页（中央大图，标定 dark≈0.33-0.38）
        return "viewer", 0.7

    # 浅色页面（编辑器渲染 / 浅色模式）
    input_band = gray[int(sh * 0.84):int(sh * 0.94), :]
    input_light = float((input_band > 243).mean())
    tab_band = gray[int(sh * 0.945):, :]
    tab_dark = float((tab_band < 140).mean())

    if 0.02 < tab_dark < 0.6:
        return "list", 0.7
    if input_light > 0.30:
        return "chat", min(1.0, input_light * 2)
    return "unknown", 0.0


# ================================================================ OCR

class Ocr:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR()

    def __call__(self, bgr):
        """→ [(cx, cy, w, h, text, score)] 原图坐标。"""
        result, _ = self.engine(bgr)
        out = []
        if not result:
            return out
        for box, text, score in result:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append(dict(cx=float(np.mean(xs)), cy=float(np.mean(ys)),
                            w=float(max(xs) - min(xs)), h=float(max(ys) - min(ys)),
                            text=str(text), score=float(score)))
        return out


# ================================================================ 气泡分组

def group_bubbles(items, W, H):
    """把 OCR 行按侧别+垂直邻近聚成气泡。
    返回 [(side, text, top, bottom, cx, w_max, items)]，top/bottom 为原图 y。"""
    msgs = []
    for it in items:
        if it["cy"] > H * 0.86:            # 输入区（无锚点兜底）
            continue
        if it["cy"] < H * 0.085:           # 状态栏/标题区
            continue
        t = it["text"].strip()
        if not t or TS_RE.match(t) or WATERMARK_RE.search(t):
            continue                        # 居中时间戳/水印是页面装饰，不是消息
        msgs.append(it)
    msgs.sort(key=lambda i: i["cy"])
    groups = []
    for it in msgs:
        t = it["text"].strip()          # 当前条目文字（勿用过滤循环残留的 t）
        placed = False
        for g in groups:
            if g["side"] == it["side"] and abs(it["cy"] - g["last_cy"]) < max(it["h"], g["last_h"]) * 1.4:
                g["text"] += t
                g["last_cy"] = it["cy"]
                g["last_h"] = it["h"]
                g["bottom"] = max(g["bottom"], it["cy"] + it["h"] / 2)
                g["w_max"] = max(g["w_max"], it["w"])
                g["items"].append(it)
                placed = True
                break
        if not placed:
            groups.append(dict(side=it["side"], text=t, top=it["cy"] - it["h"] / 2,
                               bottom=it["cy"] + it["h"] / 2, cx=it["cx"], w_max=it["w"],
                               last_cy=it["cy"], last_h=it["h"], items=[it]))
    return groups


def detect_side(frame, it):
    """取文字框右缘外侧色块：微信绿=我方，否则对方。"""
    h, w = frame.shape[:2]
    x0 = min(w - 1, int(it["cx"] + it["w"] / 2) + 4)
    x1 = min(w, x0 + 14)
    y0 = max(0, int(it["cy"] - it["h"]))
    y1 = min(h, int(it["cy"] + it["h"]))
    patch = frame[y0:y1, x0:x1]
    if patch.size == 0:
        return "peer"
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 50, 110), (72, 255, 255))   # 微信绿 #95EC69 ≈H50，留余量
    return "me" if mask.mean() > 60 else "peer"


# ================================================================ 单段聊天重建

class ChatRebuild:
    def __init__(self, templates, use_emoji=True, debug=False):
        self.templates = templates
        self.use_emoji = use_emoji
        self.debug = debug
        self.lines = []          # 剧本行
        self.notes = []          # 报告条目
        self.emitted = []        # 已发出的气泡 [(text, cy)]（侧别由多数投票定）
        self.emitted_texts = []  # 最近发出的文本（回滚去重用）
        self.pending = {}        # text -> [count, bubble, {side: votes}]；连续 ≥2 帧才发
        self.input_active_since = None
        self.input_candidate = ""
        self.interjections = []  # 打字期间对方插入的话
        self.fps_high = 8.0

    # ---- 去重辅助 ----
    def _already(self, b):
        return any(t == b["text"] and abs(cy - b["bottom"]) < 80 for (t, cy) in self.emitted)

    def _recent(self, text, n=60):
        return text in self.emitted_texts[-n:]

    # ---- 输入区切分（真机深色模式：键盘弹出时输入框在中部，锚点=发送/确定按钮） ----
    def _split_items(self, ocr_items, H, W):
        """返回 (气泡items, 输入框texts, (zone_top, zone_bot))。
        有「发送/确定」按钮 → 以按钮垂直锚定；否则兜底底部输入带。
        zone 以下（键盘/候选词）直接丢弃。"""
        anchor = None
        for it in ocr_items:
            t = it["text"].strip()
            if it["cy"] > H * 0.35 and it["cx"] > W * 0.70 and it["score"] > 0.4 \
                    and t in ("发送", "确定"):
                anchor = it
                break
        if anchor is not None:
            top = anchor["cy"] - H * 0.055
            bot = anchor["cy"] + H * 0.045
        else:
            top, bot = H * 0.85, H * 0.95
        bubbles, ins = [], []
        for it in ocr_items:
            cy = it["cy"]
            t = it["text"].strip()
            if not t or TS_RE.match(t) or WATERMARK_RE.search(t):
                continue
            if top < cy < bot and it["cx"] < W * 0.80:
                if t not in ("发送", "确定"):
                    ins.append(it)
            elif cy <= top:
                bubbles.append(it)
            # cy >= bot：候选词/键盘上方残留，丢弃
        return bubbles, ins, (top, bot)

    # ---- 输入框状态机 ----
    def _feed_input(self, input_texts, confirmed_new, frame_idx, fps):
        text = "".join(t["text"].strip() for t in sorted(input_texts, key=lambda i: i["cy"]))
        me_new = [b for b in confirmed_new if b["side"] == "me"]
        if text:
            if self.input_active_since is None:
                self.input_active_since = frame_idx
                self.interjections = []
            self.input_candidate = text
        else:
            # 输入框从有到空
            if self.input_active_since is not None:
                dur = (frame_idx - self.input_active_since) / self.fps_high
                if self.input_candidate and not me_new:
                    # 没发出去 → 打字不发
                    stay = snap_stay(max(0.3, dur * 0.6))
                    line = f"[打字不发] {self.input_candidate} | {stay}"
                    if self.interjections:
                        line += " | " + "；".join(self.interjections)
                    self.lines.append(line)
                    self.lines.append("[删除文字] -1")
                # 有我方新气泡 → 打完发出去了，消息本身由气泡确认机制发出
                self.input_active_since = None
                self.input_candidate = ""
                self.interjections = []
        if self.input_active_since is not None:
            # 打字期间对方插话（只记插话，不再重复发独立消息行）
            for b in confirmed_new:
                if b["side"] == "peer" and b["text"] not in self.interjections:
                    self.interjections.append(b["text"])

    # ---- 每帧 ----
    def feed(self, frame, frame_idx, ocr_items, W, H, fps):
        bubbles_items, input_texts, zone = self._split_items(ocr_items, H, W)
        for it in bubbles_items:
            it["side"] = detect_side(frame, it)
        bubbles = group_bubbles(bubbles_items, W, H)

        # 两帧确认 + 文本级去重（侧别按多数投票，防色块判定帧间抖动）
        current_texts = set()
        for b in bubbles:
            if self._already(b):
                continue
            key = b["text"]
            current_texts.add(key)
            if key in self.pending:
                self.pending[key][0] += 1
                self.pending[key][2][b["side"]] = self.pending[key][2].get(b["side"], 0) + 1
            else:
                self.pending[key] = [1, b, {b["side"]: 1}]
        confirmed_new = []
        # 回滚去重：本帧所有可见气泡都已发过 → 是历史回滚/翻看，不再重复发
        scrolling_back = bool(current_texts) and all(self._recent(t) for t in current_texts)
        for key in list(self.pending):
            if key not in current_texts:
                del self.pending[key]           # 稍纵即逝＝OCR 噪声，丢弃
                continue
            if self.pending[key][0] >= 2:
                cnt, b, votes = self.pending[key]
                b = dict(b)
                b["side"] = max(votes, key=votes.get)
                del self.pending[key]
                if scrolling_back and self._recent(key):
                    self.emitted.append((key, b["bottom"]))   # 更新位置，不再出行
                    continue
                self.emitted.append((key, b["bottom"]))
                self.emitted_texts.append(key)
                if len(self.emitted_texts) > 200:
                    del self.emitted_texts[:100]
                self._emit_bubble(frame, b, frame_idx)
                confirmed_new.append(b)
        self._feed_input(input_texts, confirmed_new, frame_idx, fps)

    def _emit_bubble(self, frame, b, frame_idx):
        text = b["text"]
        # 纯符号/极短 且开表情匹配
        if self.use_emoji and len(text) <= 4:
            h, w = frame.shape[:2]
            y0 = max(0, int(b["top"]) - 8)
            y1 = min(h, int(b["bottom"]) + 8)
            x0 = max(0, int(b["cx"] - b["w_max"] / 2) - 10)
            x1 = min(w, int(b["cx"] + b["w_max"] / 2) + 10)
            name, dist = match_emoji(frame[y0:y1, x0:x1], self.templates)
            if name and dist < 12:
                tag = "[发送emoji]" if b["side"] == "me" else "[对方emoji]"
                self.lines.append(f"{tag} {name}")
                return
        if b["side"] == "me":
            self.lines.append(f"[我方打字] {text}")
        else:
            # 打字期间对方的发言已在 _feed_input 记为插话，不重复出独立行
            if self.input_active_since is not None:
                return
            self.lines.append(f"[对方发消息] {text}")

    # ---- 联系人名 ----
    def detect_name(self, frame, ocr_items, H, W=None):
        if W is None:
            W = H
        cands = [i for i in ocr_items if i["cy"] < H * 0.10
                 and W * 0.25 < i["cx"] < W * 0.75 and not TS_RE.match(i["text"])]
        if cands:
            best = max(cands, key=lambda i: len(i["text"]))
            if len(best["text"]) >= 1 and best["score"] > 0.5:
                return best["text"].strip(), True
        return None, False


# ================================================================ 列表页（历史会话）

def history_from_frame(ocr_items, W, H):
    """v1：按 y 聚行，每行输出 [会话] 名 + 名：预览 | 时间。"""
    usable = [i for i in ocr_items if H * 0.09 < i["cy"] < H * 0.90 and i["text"].strip()]
    usable.sort(key=lambda i: i["cy"])
    rows = []
    for it in usable:
        if rows and abs(it["cy"] - rows[-1][-1]["cy"]) < it["h"] * 1.6:
            rows[-1].append(it)
        else:
            rows.append([it])
    out = []
    for row in rows:
        # 行内排序：先按行线（y）再按 x——名字在预览上方
        row.sort(key=lambda i: (round(i["cy"] / max(i["h"], 1)), i["cx"]))
        stamp = next((i["text"] for i in row if TS_RE.match(i["text"].strip())), None)
        rest = [i for i in row if not TS_RE.match(i["text"].strip())]
        if not rest:
            continue
        name = rest[0]["text"].strip()
        preview = "".join(i["text"].strip() for i in rest[1:])
        line = f"{name}：{preview}" if preview else f"{name}："
        if stamp:
            line += f" | {stamp}"
        out.append(("[会话]", name, line, len(rest) == 1))
    return out


# ================================================================ 主处理

def open_video(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    return cap, fps, total


def scan_pages(path, fps_low, probe_dir=None, ocr=None):
    """低帧率全扫，返回 [(frame_idx, kind, conf)]。probe_dir 提供时存未知页关键帧。"""
    cap, fps, total = open_video(path)
    step = max(1, int(round(fps / fps_low)))
    marks = []
    idx = 0
    unknown_saved = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            kind, conf = classify_page(frame)
            marks.append((idx, kind, conf))
            if probe_dir is not None and (kind == "unknown" or unknown_saved < 6):
                imwrite_u(probe_dir / f"f{idx:06d}_{kind}.png", frame)
                if ocr is not None:
                    (probe_dir / f"f{idx:06d}_{kind}.ocr.json").write_text(
                        json.dumps(ocr(frame), ensure_ascii=False), encoding="utf-8")
                unknown_saved += 1
        idx += 1
    cap.release()
    return marks, fps, total


def merge_segments(marks, total, gap=90):
    segs = []
    pts = marks + [(total, "end", 0)]
    for (f0, kind, _), (f1, _, _) in zip(pts, pts[1:]):
        if segs and segs[-1]["kind"] == kind:
            segs[-1]["end"] = f1
        else:
            segs.append(dict(kind=kind, start=f0, end=f1))
    # 吸收夹在同类段之间的短 unknown（分类抖动/转场动画）
    merged = []
    i = 0
    while i < len(segs):
        s = segs[i]
        if s["kind"] == "unknown" and (s["end"] - s["start"]) <= gap \
                and merged and i + 1 < len(segs) and merged[-1]["kind"] == segs[i + 1]["kind"]:
            i += 1
            continue
        merged.append(dict(s))
        i += 1
    out = []
    for s in merged:
        if out and out[-1]["kind"] == s["kind"]:
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    return out


def read_frames(path, fps, rate, f_start, f_end):
    """顺序解码取帧——OpenCV 对 mp4v 的按帧 seek 不可靠（落点漂移→混叠帧），禁用 cap.set。"""
    step = max(1, int(round(fps / rate)))
    cap, _, _ = open_video(path)
    out = []
    idx = 0
    while idx < f_end:
        ok, frame = cap.read()
        if not ok:
            break
        if idx >= f_start and (idx - f_start) % step == 0:
            out.append((idx, frame))
        idx += 1
    cap.release()
    return out


def process_chat_segment(path, seg, fps, total, args, ocr, templates, notes, frame_dir, seg_i):
    """一段连续聊天页 → [(联系人名, 剧本行), ...]。
    真机博主会在同一录屏里切聊天对象：标题稳定变化 ≥3 帧 → 拆新会话。"""
    rb = ChatRebuild(templates, not args.no_emoji)
    rb.fps_high = args.fps_high
    blocks = []
    cur_name = None
    pend_name, pend_cnt = None, 0
    frames = read_frames(path, fps, args.fps_high, seg["start"], min(seg["end"] + 1, total))
    for k, (f, frame) in enumerate(frames):
        items = ocr(frame)
        if args.debug_dump:
            (frame_dir / f"seg{seg_i}_f{f:06d}.json").write_text(
                json.dumps(items, ensure_ascii=False), encoding="utf-8")
        h, w = frame.shape[:2]
        t, ok = rb.detect_name(frame, items, h, w)
        if ok and t:
            if t == cur_name:
                pend_name, pend_cnt = None, 0
            else:
                pend_cnt = pend_cnt + 1 if t == pend_name else 1
                pend_name = t
                if cur_name is None and pend_cnt >= 2:
                    cur_name, pend_name, pend_cnt = t, None, 0
                elif cur_name is not None and pend_cnt >= 3:
                    blocks.append((cur_name, rb.lines))
                    rb = ChatRebuild(templates, not args.no_emoji)
                    rb.fps_high = args.fps_high
                    cur_name, pend_name, pend_cnt = t, None, 0
        rb.feed(frame, f, items, w, h, fps)
    blocks.append((cur_name, rb.lines))
    if cur_name is None:
        notes.append(f"- 聊天段{seg_i}（帧 {seg['start']}~{seg['end']}）：联系人名没识别出来，"
                     f"看 frames/ 手动补。")
    return blocks


def process_list_segment(path, seg, fps, total, args, ocr, notes):
    """列表段：取该段最中间的一帧做整页 OCR。"""
    mid = (seg["start"] + seg["end"]) // 2
    frames = read_frames(path, fps, 1.0, mid, mid + 1)
    if not frames:
        return []
    frame = frames[0][1]
    h, w = frame.shape[:2]
    rows = history_from_frame(ocr(frame), w, h)
    out = []
    for tag, name, line, thin in rows:
        out.append(f"[会话] {name}")
        out.append(line)
        if thin:
            notes.append(f"- 列表行「{name}」只 OCR 到名字没读到预览（可能被表情/图片占位），手动核对。")
    return out


def build_draft(parts):
    lines = ["# 由 video2script 自动生成（草稿）", "# 用法：对照 report.md 逐条确认；[?] 行=待确认；确认后删掉本注释块", ""]
    lines.extend(parts)
    return "\n".join(lines) + "\n"


def process_video(v, out_dir, args, ocr, templates):
    frame_dir = out_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    notes = ["# 不确定点报告（人工只看这里）\n"]
    marks, fps, total = scan_pages(v, args.fps_low)
    segs = merge_segments(marks, total)
    parts = []
    seg_i = 0
    in_chat = False
    for seg in segs:
        seg_i += 1
        if seg["kind"] == "chat":
            blocks = process_chat_segment(v, seg, fps, total, args, ocr, templates, notes, frame_dir, seg_i)
            for name, lines in blocks:
                parts.append(f"[打开聊天] {name or '?待确认?'}")
                for ln in lines:
                    if ln.startswith(("[我方打字]", "[对方发消息]", "[打字不发]", "[删除文字]")) \
                            or "[发送emoji]" in ln or "[对方emoji]" in ln:
                        parts.append(ln)
                    else:
                        parts.append(f"[?] {ln}")
                parts.append("[返回主页] 0.3")
            in_chat = False
        elif seg["kind"] == "list":
            if in_chat:
                parts.append("[返回主页] 0.3")
            parts.append("[历史会话]")
            parts.extend(process_list_segment(v, seg, fps, total, args, ocr, notes))
            parts.append("[历史会话结束]")
            in_chat = False
        else:
            if in_chat:
                parts.append("[返回主页] 0.3")
                in_chat = False
            notes.append(f"- {seg['kind']} 段（帧 {seg['start']}~{seg['end']}）：v1 未自动翻译，"
                         f"看 frames/ 下对应截图人工补（朋友圈/图片查看器动作）。")
    if in_chat:
        parts.append("[返回主页] 0.3")
    (out_dir / "report.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    return build_draft(parts)


def probe_main(v, out_dir, args, ocr):
    probe_dir = out_dir / "frames"
    probe_dir.mkdir(parents=True, exist_ok=True)
    marks, fps, total = scan_pages(v, args.fps_low, probe_dir, ocr)
    kinds = {}
    for _, k, _ in marks:
        kinds[k] = kinds.get(k, 0) + 1
    segs = merge_segments(marks, total)
    print(f"[probe] {v.name}  总帧 {total}  fps {fps:.1f}")
    print(f"[probe] 页面分布: " + ", ".join(f"{k}={n}" for k, n in kinds.items()))
    print("[probe] 页面段:")
    for s in segs:
        print(f"    {s['start']:6d}~{s['end']:6d}  {s['kind']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=None)
    ap.add_argument("--fps-low", type=float, default=2.0)
    ap.add_argument("--fps-high", type=float, default=8.0)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--no-emoji", action="store_true")
    ap.add_argument("--debug-dump", action="store_true")
    args = ap.parse_args()

    target = Path(args.target) if args.target else ROOT / "input_videos"
    if target.is_dir():
        videos = [p for p in sorted(target.glob("*"))
                  if p.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".flv", ".webm")]
        if not videos:
            print(f"[提示] {target} 里没有视频。把博主视频放进去后重跑。")
            return 1
    else:
        videos = [target]

    templates = [] if args.no_emoji else load_emoji_templates()
    print(f"[i] 表情模板 {len(templates)} 个")
    ocr = Ocr()
    rc = 0
    for v in videos:
        tmp_dir = None
        try:
            out_dir = OUTPUT_DIR / v.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            if args.probe:
                probe_main(v, out_dir, args, ocr)
                continue
            v_path, tmp_dir = resolve_openable(v)   # 中文路径 → ASCII 临时副本
            draft = process_video(v_path, out_dir, args, ocr, templates)
            (out_dir / f"{v.stem}.draft.txt").write_text(draft, encoding="utf-8")
            print(f"[完成] {v.name} → {out_dir}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[错误] {v.name}: {e}")
            rc = 1
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
