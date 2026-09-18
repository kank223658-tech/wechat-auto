# -*- coding: utf-8 -*-
"""
长图模式 · 聊天画布
====================
把 JSON 对话数据渲染成一张「聊天记录长图」（黑底、大字号、带彩色点评行），
同时返回每个消息块的独立图层与**精确坐标清单**（气泡矩形 bx/bw/by0/by1），
供镜头做零猜测的程序化取景——坐标是画的时候算出来的真值，不需要事后看图探测。

v2（程序化镜头改造）：
  - 全部几何支持 scale（超采样）：s=2 时长图 3840 宽，拉近后文字依然锐利
  - layers[i] 新增 bx/bw/by0/by1（长图坐标系下的气泡/图片矩形真值）

对标样式（来自《当女生下定决心要跟你分开该怎么回复》逐帧测量）：
  - 纯黑背景 #000
  - 对方气泡：深灰 #2D2D2D 圆角 + 左侧圆头像，白字
  - 我方气泡：微信绿 #2FAF5E 圆角 + 右侧圆头像，黑字
  - 每颗气泡正下方一行点评：蓝=点评对方/形势，黄=点评我方操作，红=结尾 CTA
  - 顶部栏（长图的一部分，会随滚动移出画面）：`< 1` 徽标 + 右侧对方头像与名字
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "准备制作界面", "assets")
FRONTEND_PUBLIC = os.path.join(ROOT, "vue-WeChat", "public")

# ---- 样式常量（1920 宽基准；实际渲染乘以 scale s）----
W = 1920
BG = (0, 0, 0)
BUBBLE_PEER = (45, 45, 45)
BUBBLE_ME = (47, 175, 94)
TEXT_ON_PEER = (240, 240, 240)
TEXT_ON_ME = (12, 12, 12)
NOTE_BLUE = (86, 180, 235)
NOTE_YELLOW = (255, 210, 70)
NOTE_ORANGE = (255, 150, 60)
NOTE_RED = (255, 86, 86)
NOTE_COLORS = {"blue": NOTE_BLUE, "yellow": NOTE_YELLOW,
               "orange": NOTE_ORANGE, "red": NOTE_RED}

FONT_TEXT = os.path.join(ASSETS, "PingFang-SC-Bold.ttf")
FONT_SEMI = os.path.join(ASSETS, "PingFangSC-Semibold.ttf")

AVATAR_D = 140          # 头像直径
BUBBLE_X_PEER = 250     # 对方气泡左缘
BUBBLE_X_ME = W - 250   # 我方气泡右缘
BUBBLE_MAX_W = 1330     # 气泡最大宽
PAD_X = 76              # 气泡内左右留白
LINE_H = 140            # 行高
VPAD = 69               # 气泡上下留白（单行泡高 = 140 + 138 = 278，与对标一致）
RADIUS = 46
GAP_BUBBLE_NOTE = 22    # 气泡 → 点评
GAP_BLOCK = 30          # 点评 → 下一颗气泡
NOTE_FONT = 78
NOTE_H = 96

HEADER_H = 560          # 顶栏占据的长图高度（其后内容开始）
BAR_Y0, BAR_Y1 = 130, 490


def _s(v, s):
    """基准值 → 按 scale 缩放后的整数像素。"""
    return int(round(v * s))


def _font(path, size):
    return ImageFont.truetype(path, size)


def _resolve_image(p):
    """支持 /images/... web 路径、项目相对路径、绝对路径（先判 web 再判绝对，
    规避 Windows os.path.isabs('/x') == True 的坑）。"""
    if not p:
        return None
    posix = p.replace("\\", "/")
    if posix.startswith("/") and not posix.startswith("//"):
        for base in (FRONTEND_PUBLIC, ROOT):
            cand = os.path.normpath(os.path.join(base, posix.lstrip("/")))
            if os.path.isfile(cand):
                return cand
        return None
    if os.path.isabs(posix):
        return posix if os.path.isfile(posix) else None
    cand = os.path.normpath(os.path.join(ROOT, posix))
    return cand if os.path.isfile(cand) else None


def _circle_avatar(src, d):
    """把头像图裁成圆形 RGBA。"""
    if src and os.path.isfile(src):
        im = Image.open(src).convert("RGB")
    else:                       # 占位灰底
        im = Image.new("RGB", (d, d), (90, 90, 90))
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                  (im.width + s) // 2, (im.height + s) // 2)).resize((d, d))
    mask = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    mask = mask.resize((d, d))
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def _wrap(draw, text, font, max_w):
    """按像素宽度折行。"""
    lines, cur = [], ""
    for ch in text:
        t = cur + ch
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_header(img, peer_name, peer_avatar, badge="1", s=1.0):
    """顶栏：`<` + 圆形计数徽标 + 右侧头像/名字。画在长图顶部。"""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((_s(40, s), _s(BAR_Y0, s), img.width - _s(40, s),
                         _s(BAR_Y1, s)), radius=_s(28, s), fill=(22, 22, 22))
    y_c = (_s(BAR_Y0, s) + _s(BAR_Y1, s)) // 2
    f_arrow = _font(FONT_SEMI, _s(92, s))
    d.text((_s(150, s), y_c), "<", font=f_arrow, fill=(220, 220, 220),
           anchor="lm")
    # 计数徽标
    r = _s(74, s)
    bx0 = _s(270, s)
    d.ellipse((bx0, y_c - r, bx0 + 2 * r, y_c + r), fill=(58, 58, 58))
    f_badge = _font(FONT_SEMI, _s(78, s))
    d.text((bx0 + r, y_c - _s(4, s)), str(badge), font=f_badge,
           fill=(235, 235, 235), anchor="mm")
    # 右侧：头像 + 名字
    av = _circle_avatar(_resolve_image(peer_avatar), _s(120, s))
    img.paste(av, (_s(1370, s), y_c - _s(60, s)), av)
    f_name = _font(FONT_SEMI, _s(88, s))
    d.text((_s(1530, s), y_c - _s(4, s)), peer_name or "", font=f_name,
           fill=(240, 240, 240), anchor="lm")


def render_blocks(blocks, meta, extra_bottom=0, s=1.0):
    """渲染全部消息块。s = 超采样倍率（2 → 3840 宽长图）。

    返回 (long_image, layers)
      layers[i] = {"y0","y1","side","rgba","cy",
                   "bx","bw","by0","by1"}   # 气泡/图片矩形真值（长图坐标系）
    """
    W2 = _s(W, s)
    AV = _s(AVATAR_D, s)
    XP = _s(BUBBLE_X_PEER, s)          # 对方气泡左缘
    XM = _s(BUBBLE_X_ME, s)            # 我方气泡右缘
    MAXW = _s(BUBBLE_MAX_W, s)
    PX = _s(PAD_X, s)
    LH = _s(LINE_H, s)
    VP = _s(VPAD, s)
    RAD = _s(RADIUS, s)
    GBN = _s(GAP_BUBBLE_NOTE, s)
    GBL = _s(GAP_BLOCK, s)
    NH = _s(NOTE_H, s)

    peer_av = _circle_avatar(_resolve_image(meta.get("peer_avatar")), AV)
    my_av = _circle_avatar(_resolve_image(meta.get("my_avatar")), AV)

    f_text = _font(FONT_TEXT, _s(100, s))
    f_note = _font(FONT_SEMI, _s(NOTE_FONT, s))

    meas = Image.new("RGB", (8, 8))
    md = ImageDraw.Draw(meas)

    layers = []
    y = _s(HEADER_H, s) + _s(20, s)
    for b in blocks:
        side = b.get("side", "peer")
        text = (b.get("text") or "").strip()
        img_path = _resolve_image(b.get("img"))
        note = (b.get("note") or "").strip()
        note_color = NOTE_COLORS.get(b.get("note_color")
                                     or ("yellow" if side == "me" else "blue"))

        parts = []                      # 本块的组成：[(高, 绘制描述)]
        if img_path:                    # 图片/表情块
            im = Image.open(img_path).convert("RGB")
            scale = min(1.0, _s(900, s) / im.width)
            im = im.resize((int(im.width * scale), int(im.height * scale)))
            bw, bh = im.width, im.height
            parts.append((bh, ("img", im, bw)))

        elif text:
            lines = _wrap(md, text, f_text, MAXW - PX * 2)
            bh = len(lines) * LH + VP * 2
            bw = min(MAXW,
                     int(max(md.textlength(ln, font=f_text) for ln in lines)) + PX * 2)
            parts.append((bh, ("bubble", lines, bw)))

        nh = (NH + GBN) if note else 0
        block_h = sum(h for h, _ in parts) + nh
        y1 = y + block_h

        # 画块图层（横向位置由 side 决定）
        layer = Image.new("RGBA", (W2, block_h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        cy_parts = y
        rect = None                     # 本块主体矩形（气泡或图片）
        for h, spec in parts:
            if spec[0] == "img":
                _, im, bw = spec
                bx = XP - _s(10, s) if side == "peer" else XM - bw + _s(10, s)
                layer.paste(im, (bx, cy_parts - y))
                rect = (bx, bw)
                av = peer_av if side == "peer" else my_av
                ax = _s(64, s) if side == "peer" else W2 - _s(64, s) - AV
                layer.paste(av, (ax, cy_parts - y + h // 2 - AV // 2), av)
            else:
                _, lines, bw = spec
                bx = XP if side == "peer" else XM - bw
                ld.rounded_rectangle((bx, cy_parts - y, bx + bw,
                                      cy_parts - y + h), radius=RAD,
                                     fill=BUBBLE_PEER if side == "peer" else BUBBLE_ME)
                # 气泡小尾巴
                ty = cy_parts - y + _s(60, s)
                if side == "peer":
                    ld.polygon([(bx, ty), (bx, ty + _s(56, s)),
                                (bx - _s(34, s), ty + _s(40, s))],
                               fill=BUBBLE_PEER)
                    ax = _s(64, s)
                else:
                    ld.polygon([(bx + bw, ty), (bx + bw, ty + _s(56, s)),
                                (bx + bw + _s(34, s), ty + _s(40, s))],
                               fill=BUBBLE_ME)
                    ax = W2 - _s(64, s) - AV
                av = peer_av if side == "peer" else my_av
                layer.paste(av, (ax, cy_parts - y + h // 2 - AV // 2), av)
                ty2 = cy_parts - y + VP
                for ln in lines:
                    ld.text((bx + PX, ty2), ln, font=f_text,
                            fill=TEXT_ON_PEER if side == "peer" else TEXT_ON_ME)
                    ty2 += LH
                rect = (bx, bw)
            cy_parts += h

        if note:
            ny = cy_parts - y + GBN
            if side == "peer":
                nx = XP + _s(6, s)
                anchor = "la"
            else:
                anchor = "ma"
                nx = XM - _s(380, s)
            ld.text((nx, ny), note, font=f_note, fill=note_color, anchor=anchor)

        L = {"y0": y, "y1": y1, "side": side, "rgba": layer}
        if rect:
            L["bx"], L["bw"] = rect[0], rect[1]
            L["by0"], L["by1"] = y, y + sum(h for h, _ in parts)
        layers.append(L)
        y = y1 + GBL

    total_h = y + _s(80 + extra_bottom, s)
    long_img = Image.new("RGB", (W2, total_h), BG)
    if meta.get("header", True):
        draw_header(long_img, meta.get("peer_name", ""),
                    meta.get("peer_avatar"), meta.get("badge", "1"), s=s)
    for L in layers:
        long_img.paste(L["rgba"], (0, L["y0"]), L["rgba"])
    for L in layers:
        L["cy"] = (L["y0"] + L["y1"]) // 2
    return long_img, layers


def render_ending(img, text, color="red", bottom=150, s=1.0):
    """结尾 CTA：红字大号居中（画在长图底部预留区内，随滚动入场）。"""
    d = ImageDraw.Draw(img)
    f = _font(FONT_SEMI, _s(84, s))
    d.text((img.width // 2, img.height - _s(bottom, s)), text, font=f,
           fill=NOTE_COLORS.get(color, NOTE_RED), anchor="mm")
