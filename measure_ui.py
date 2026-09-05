# -*- coding: utf-8 -*-
"""
measure_ui.py — 微信截图 UI 测量工具
=====================================================
功能：
  1. 读取用户传入的一张微信截图（命令行第一个参数）。
  2. 用 OpenCV Canny 边缘检测 + findContours 轮廓识别，找出所有独立的 UI 元素区域。
  3. 对每个元素记录：位置(x,y)、宽度、高度、主色调(HEX)。
  4. 计算相邻元素之间的水平/垂直间距。
  5. 识别全局参数：聊天背景色、顶部导航栏高度、底部输入栏高度。
  6. 把结果输出为 measure_result.json（同时给出原始像素与 CSS 逻辑像素两套单位）。

用法：
  py measure_ui.py 参考图片/聊天截图.jpg
  py measure_ui.py screenshot.png

说明：
  - CSS 逻辑像素 = 原始像素 ÷ SCALE（本模拟器视口 390x844，device scale 3，
    故默认 SCALE=3，与 main.py 中 DEVICE_SCALE_FACTOR 保持一致）。
  - 输出 JSON 默认写在脚本同级目录 measure_result.json，可用 --out 覆盖。
"""

import argparse
import json
import os
import sys
import statistics

import numpy as np
import cv2

# Windows 控制台默认 GBK，中文打印会乱码；强制 stdout/stderr 使用 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------
# 可调参数
# ---------------------------------------------------------------
SCALE = 3            # 原始像素 → CSS 逻辑像素的缩放比（device_scale_factor）
MIN_AREA = 100       # 低于该面积的轮廓视为噪点，忽略（单位：原始像素）
MIN_ELEMENT_W = 8    # 低于该宽度的元素忽略（过滤文字笔画等碎片）
MIN_ELEMENT_H = 8    # 低于该高度的元素忽略
COLOR_TOL = 40       # 颜色相近判定阈值（RGB 各通道最大差值）
NEAR_TOL = 10        # 判断元素是否“同处一行/列”的容差（原始像素）
SPACING_MAX = 400    # 间距统计上限，大于此视为不相关，忽略
BG_SIM_TOL = 12      # 与背景色几乎相同的区域忽略（避免背景被当成元素）

# -----------------------------------------------
# 工具函数
# -----------------------------------------------


def read_image(path):
    """读取图片。优先 cv2，失败后用 Pillow 解码（兼容中文路径）。返回 BGR ndarray。"""
    # cv2.imread 不支持含中文的路径，先尝试；失败再用 Pillow 转码后给 cv2。
    try:
        img = cv2.imread(path)
        if img is not None:
            return img
    except Exception:
        pass
    try:
        from PIL import Image
        pil = Image.open(path).convert("RGB")
        arr = np.asarray(pil)
        # PIL 是 RGB，转回 OpenCV 的 BGR
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise SystemExit("无法读取图片 %s：%s" % (path, e))


def bgr_to_hex(b, g, r):
    """把 BGR 三元组转成 #RRGGBB 字符串。"""
    return "#%02x%02x%02x" % (int(r), int(g), int(b))


def hex_to_bgr(h):
    """#RRGGBB → (b, g, r) 元组。"""
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)) if len(h) == 6 else (0, 0, 0)


def dominant_color(region_bgr):
    """取区域内出现最多的颜色（先量化到 8 档，避免抗锯齿干扰）。返回 (b,g,r)。"""
    if region_bgr is None or region_bgr.size == 0:
        return (0, 0, 0)
    flat = region_bgr.reshape(-1, 3).astype(np.int32)
    # 量化：每个通道压到 0..7 共 8 档，统计众数
    q = (flat // 32).astype(np.int32)
    keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    uniq, counts = np.unique(keys, return_counts=True)
    top = uniq[np.argmax(counts)]
    # 把量化桶中心作为代表色
    r = ((top % 16) * 32 + 16)
    g = (((top // 16) % 16) * 32 + 16)
    b = ((top // 256) * 32 + 16)
    return (min(b, 255), min(g, 255), min(r, 255))


def detect_background(image):
    """自动检测大面积纯色作为背景色。返回 (bgr, hex, 占比)。"""
    flat = image.reshape(-1, 3).astype(np.int32)
    # 量化到 16 档统计
    q = (flat // 16).astype(np.int32)
    keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    uniq, counts = np.unique(keys, return_counts=True)
    idx = np.argmax(counts)
    top = uniq[idx]
    r = (top % 16) * 16 + 8
    g = ((top // 16) % 16) * 16 + 8
    b = ((top // 256) % 16) * 16 + 8
    bgr = (min(b, 255), min(g, 255), min(r, 255))
    ratio = float(counts[idx]) / flat.shape[0]
    return bgr, bgr_to_hex(*bgr), ratio


def detect_horizontal_band(image, from_top=True):
    """
    检测横向纯色色带的高度（用于导航栏/输入栏）。
    from_top=True 从顶部往下找第一条近满宽度的纯色带；False 从底部往上找。
    返回 (起始y, 高度, hex)。找不到返回 (0,0,None)。
    """
    h, w = image.shape[:2]
    # 逐行计算均值与标准差，纯色带的标准差很小
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    row_std = gray.std(axis=1)
    row_mean = gray.mean(axis=1)
    rows = range(h) if from_top else range(h - 1, -1, -1)
    band_start = None
    band_end = None
    for y in rows:
        # 近满宽度（左右各留 10% 判断为贯穿）+ 低方差 = 纯色带
        near_full = True
        if row_std[y] < 14:
            # 再抽查该行两端颜色是否接近整行均值
            if band_start is None:
                band_start = y
                band_end = y
            else:
                band_end = y
        else:
            if band_start is not None:
                # 找到了一个连续纯色段，结束
                break
    if band_start is None:
        return (0, 0, None)
    # 取该段中心行色作为代表色
    mid = (band_start + band_end) // 2
    bgr = tuple(image[mid, w // 2])
    height = abs(band_end - band_start) + 1
    y0 = min(band_start, band_end)
    return (y0, height, bgr_to_hex(*bgr))


def merge_rects(rects, tol):
    """
    把颜色相近且距离接近的区域合并，避免一个 UI 元素被拆成多个。
    rects: [(x,y,w,h,bgr), ...]。返回合并后的同结构列表。
    """
    merged = []
    used = [False] * len(rects)
    for i in range(len(rects)):
        if used[i]:
            continue
        x0, y0, w0, h0, c0 = rects[i]
        changed = True
        while changed:
            changed = False
            for j in range(len(rects)):
                if used[j]:
                    continue
                x1, y1, w1, h1, c1 = rects[j]
                # 颜色相近判断
                color_ok = all(abs(a - b) <= COLOR_TOL for a, b in zip(c0, c1))
                # 相邻判断：水平或垂直方向间距很小
                gap_x = max(0, max(x0, x1) - min(x0 + w0, x1 + w1))
                gap_y = max(0, max(y0, y1) - min(y0 + h0, y1 + h1))
                near = (gap_x <= tol and gap_y <= h1)
                near |= (gap_y <= tol and gap_x <= w1)
                if color_ok and near:
                    # 合并包围盒
                    nx = min(x0, x1)
                    ny = min(y0, y1)
                    nw = max(x0 + w0, x1 + w1) - nx
                    nh = max(y0 + h0, y1 + h1) - ny
                    # 合并后主色取两区域像素占比加权近似：简单用 c0（再后续重算）
                    x0, y0, w0, h0 = nx, ny, nw, nh
                    used[j] = True
                    changed = True
        merged.append((x0, y0, w0, h0, c0))
    return merged


def compute_spacings(elements):
    """
    计算相邻元素的水平/垂直间距。
    elements: [{'x','y','width','height'}, ...]
    返回 {'horizontal': median 或 None, 'vertical': median 或 None}。
    """
    h_gaps = []
    v_gaps = []
    n = len(elements)
    for i in range(n):
        a = elements[i]
        for j in range(i + 1, n):
            b = elements[j]
            ax0, ay0 = a["x"], a["y"]
            ax1, ay1 = ax0 + a["width"], ay0 + a["height"]
            bx0, by0 = b["x"], b["y"]
            bx1, by1 = bx0 + b["width"], by0 + b["height"]
            # 垂直方向重叠（同一行上的两个元素）→ 算水平间距
            if min(ay1, by1) - max(ay0, by0) > 0:
                gap = max(bx0 - ax1, ax0 - bx1)
                if 0 <= gap <= SPACING_MAX:
                    h_gaps.append(gap)
            # 水平方向重叠（同一列上的两个元素）→ 算垂直间距
            if min(ax1, bx1) - max(ax0, bx0) > 0:
                gap = max(by0 - ay1, ay0 - by1)
                if 0 <= gap <= SPACING_MAX:
                    v_gaps.append(gap)

    def median_or_none(lst):
        if not lst:
            return None
        return round(statistics.median(lst), 1)

    return {"horizontal": median_or_none(h_gaps), "vertical": median_or_none(v_gaps)}


def css(px_value):
    """原始像素 → CSS 逻辑像素。"""
    if px_value is None:
        return None
    return round(px_value / SCALE, 1)


def main():
    parser = argparse.ArgumentParser(description="测量微信截图的 UI 元素几何/颜色/间距")
    parser.add_argument("image", help="截图文件路径")
    parser.add_argument("--out", default="measure_result.json", help="输出 JSON 路径")
    parser.add_argument("--scale", type=float, default=SCALE, help="CSS 缩放比（默认3）")
    parser.add_argument("--min-area", type=float, default=MIN_AREA, help="最小噪点面积（默认100）")
    args = parser.parse_args()

    image = read_image(args.image)
    h, w = image.shape[:2]

    # ---- 1. 背景色识别 ----
    bg_bgr, bg_hex, bg_ratio = detect_background(image)

    # ---- 2. 预处理：转灰 + 高斯模糊 + Canny 边缘 ----
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 60, 160)

    # ---- 3. 轮廓检测 ----
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_rects = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < args.min_area:      # 过滤太小噪点
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < MIN_ELEMENT_W or bh < MIN_ELEMENT_H:   # 过滤文字笔画等碎片
            continue
        if bw > w * 0.98 or bh > h * 0.98:
            continue  # 跳过几乎整张的轮廓（多半是背景或遮罩）
        # 区域内主色调
        roi = image[y:y + bh, x:x + bw]
        cb = dominant_color(roi)
        # 与背景几乎相同的区域忽略（避免背景被当元素）
        if all(abs(a - b) <= BG_SIM_TOL for a, b in zip(cb, bg_bgr)):
            continue
        raw_rects.append((x, y, bw, bh, cb))

    # ---- 4. 颜色相近区域合并 ----
    merged_rects = merge_rects(raw_rects, NEAR_TOL * 2)

    # ---- 5. 相邻重叠矩形去重 ----
    # 合并后可能仍有大量重叠，保留更大的那个
    merged_rects.sort(key=lambda r: -(r[2] * r[3]))
    kept = []
    for r in merged_rects:
        x, y, bw, bh, c = r
        dup = False
        for k in kept:
            kx, ky, kw, kh, _ = k
            # IoU 近似：重叠占比很高则视为重复
            ox = max(0, min(x + bw, kx + kw) - max(x, kx))
            oy = max(0, min(y + bh, ky + kh) - max(y, ky))
            inter = ox * oy
            if inter > 0.6 * min(bw * bh, kw * kh):
                dup = True
                break
        if not dup:
            kept.append(r)

    # ---- 6. 生成元素记录 ----
    elements = []
    for x, y, bw, bh, c in kept:
        elements.append({
            "x": int(x),
            "y": int(y),
            "width": int(bw),
            "height": int(bh),
            "color_hex": bgr_to_hex(*c),
            "color_rgb": {"r": int(c[2]), "g": int(c[1]), "b": int(c[0])},
            "css": {
                "x": css(x),
                "y": css(y),
                "width": css(bw),
                "height": css(bh),
            },
        })

    # ---- 7. 间距计算 ----
    spacing_px = compute_spacings(elements)
    spacing_css = {
        "horizontal": css(spacing_px["horizontal"]),
        "vertical": css(spacing_px["vertical"]),
    }

    # ---- 8. 全局参数：导航栏 / 输入栏高度 ----
    nav_y, nav_h, nav_hex = detect_horizontal_band(image, from_top=True)
    # 输入栏：从底部往上找纯色带
    in_y, in_h, in_hex = detect_horizontal_band(image, from_top=False)
    nav_bar = {
        "y": nav_y, "height": nav_h, "color_hex": nav_hex,
        "css": {"y": css(nav_y), "height": css(nav_h)},
    }
    input_bar = {
        "y": in_y, "height": in_h, "color_hex": in_hex,
        "css": {"y": css(in_y), "height": css(in_h)},
    }

    # ---- 9. 组装并输出 JSON ----
    result = {
        "image": os.path.abspath(args.image),
        "size_px": {"width": w, "height": h},
        "size_css": {"width": css(w), "height": css(h)},
        "scale": SCALE,
        "background_color": {
            "hex": bg_hex,
            "rgb": {"r": int(bg_bgr[2]), "g": int(bg_bgr[1]), "b": int(bg_bgr[0])},
            "coverage": round(bg_ratio, 3),
        },
        "nav_bar": nav_bar,
        "input_bar": input_bar,
        "element_count": len(elements),
        "spacing_px": spacing_px,
        "spacing_css": spacing_css,
        "elements": elements,
    }

    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)

    # ---- 10. 控制台摘要 ----
    print("=" * 52)
    print("截面：%s" % os.path.basename(args.image))
    print("尺寸（原始像素）：%d x %d" % (w, h))
    print("尺寸（CSS 逻辑像素）：%s x %s" % (css(w), css(h)))
    print("背景色：%s（覆盖 %.1f%%）" % (bg_hex, bg_ratio * 100))
    print("导航栏：y=%d 高=%dpx(css %s) 颜色=%s" % (nav_y, nav_h, css(nav_h), nav_hex))
    print("输入栏：y=%d 高=%dpx(css %s) 颜色=%s" % (in_y, in_h, css(in_h), in_hex))
    print("检测到元素数：%d" % len(elements))
    print("水平间距(px/css)：%s / %s" % (spacing_px["horizontal"], spacing_css["horizontal"]))
    print("垂直间距(px/css)：%s / %s" % (spacing_px["vertical"], spacing_css["vertical"]))
    print("结果已写入：%s" % os.path.abspath(args.out))
    print("=" * 52)


if __name__ == "__main__":
    main()