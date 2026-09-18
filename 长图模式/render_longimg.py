# -*- coding: utf-8 -*-
"""
长图模式 · 渲染主程序
======================
长图 + BGM → 「鼓点卡点 + 步进滚动」的横屏成片。

v2（程序化镜头改造，2026-09-15）：
  - JSON 模式升级为「坐标真值驱动」：chat_canvas 画长图时同步输出每个气泡的
    精确矩形（bx/bw/by0/by1），动态镜头（一句一挪/连发拉远/单句拉近）直接吃
    真值坐标做纯算术，不再做任何像素探测；探测只留给上传的外部截图。
  - 画质：长图支持 2 倍超采样（quality.supersample，带内存上限自动降档）；
    每帧用 AFFINE 变换（BICUBIC）一次性完成取窗+缩放，亚像素移动不再跳帧。

机制（逆向自对标视频《当女生下定决心要跟你分开该怎么回复》）：
  1. 片头：顶部栏淡入 → 前几条消息块按强拍逐条从侧边滑入（卡点钩子）
  2. 主体：镜头按 BGM 强拍逐步下移，每步 0.3~0.4s 缓动滑 + 停到下一拍
  3. 音频：BGM 铺满全片，结尾淡出

用法：
  py render_longimg.py --config 配置.json --out videos/长图_标题.mp4
  py render_longimg.py --longimg 长图.png --bgm 音乐.mp3 --out videos/x.mp4
  py render_longimg.py --config 配置.json --preview-only   # 只出关键帧拼图
"""
import argparse
import json
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chat_canvas as CC          # noqa: E402
from beat_grid import detect_beats, plan_step_beats  # noqa: E402

FF = get_ffmpeg_exe()
OUT_W, OUT_H = 1920, 1080
MAX_SRC_BYTES = 550 * 1024 * 1024      # 长图内存上限（RGB 3 字节/像素）


# ----------------------------------------------------------------------------
# 时间轴
# ----------------------------------------------------------------------------

def ease_in_out_cubic(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def build_timeline(cams, beats, pace, intro_blocks, bgm_len, zvals=None,
                   open_hold_beats=0, open_pan=None):
    """ cams[i] = 第 i 块居中时的相机 y（含初始 0）。

    zvals 可选：与 cams 等长的每步缩放序列，写入 steps 的 zf/zt。
    open_hold_beats: 开场镜头静止撑过的拍数（参考视频方法：撑 2 拍，
    第一步落在第 3 拍）；0 = 不额外停留（旧 JSON/scroll 模式）。
    返回 dict: intro(块入场拍), steps[(beat, from_y, to_y)], total, first_step
    """
    glide = pace.get("glide", 0.36)
    max_step = pace.get("max_step", 3.5)
    tail = pace.get("tail_hold", 2.2)
    min_gap = pace.get("min_gap", 1.15)

    intro_beats = [b for b in beats if b >= pace.get("start_beat_min", 0.8)]
    need = max(intro_blocks + 1, 1)
    if len(intro_beats) < need:
        base = intro_beats[-1] if intro_beats else pace.get("start_beat_min", 0.8)
        intro_beats = list(intro_beats) + [base + 1.6 * (i + 1)
                                           for i in range(need - len(intro_beats))]
    block_beats = intro_beats[:intro_blocks]              # 块滑入拍（可为空）
    step_start = block_beats[-1] if block_beats \
        else pace.get("start_beat_min", 0.8) - 0.01
    if open_hold_beats > 0 and len(intro_beats) > open_hold_beats:
        # 开场停 N 拍：第一步落在第 N+1 拍（intro_beats[N-1] 之后的下一个拍）
        step_start = max(step_start, intro_beats[open_hold_beats - 1])
    step_beats = plan_step_beats(intro_beats, len(cams) - 1,
                                 start_at=step_start, max_step=max_step,
                                 end_at=bgm_len - tail - 0.5) if len(cams) > 1 else []
    # 鼓点不足导致落点超出音乐：整体前移保住结尾淡出
    if step_beats and step_beats[-1] > bgm_len - tail:
        shift = step_beats[-1] - (bgm_len - tail)
        step_beats = [max(0.5, s - shift) for s in step_beats]

    steps = []
    cur = float(cams[0]) if cams else 0.0    # 起点=首帧取景（整图模式=第一条消息），不是图片顶
    for i, b in enumerate(step_beats):
        tgt = cams[i + 1]
        # 缩放用比位移更缓的曲线（1.8 倍时长），且不越过下一步的起点——
        # 移动干脆、缩放像呼吸一样拖尾，两者错开不再「硬邦邦同步变焦」
        nxt = step_beats[i + 1] if i + 1 < len(step_beats) else b + glide + 0.8
        zgl = min(glide * 1.8, max(glide, nxt - b - 0.2))
        st = {"beat": float(b), "from": cur, "to": float(tgt), "glide": glide,
              "zglide": float(zgl)}
        if zvals is not None and len(zvals) > i + 1:
            st["zf"], st["zt"] = float(zvals[i]), float(zvals[i + 1])
        steps.append(st)
        cur = float(tgt)
    last_t = step_beats[-1] if step_beats else (block_beats[-1] if block_beats else 1.0)
    total = min(bgm_len, last_t + tail)
    tl = {"block_beats": block_beats, "steps": steps, "total": float(total),
          "intro_end": block_beats[-1] if block_beats
          else (steps[0]["beat"] if steps else 1.0)}
    # 开场滑现（参考视频定标+用户 0916 定调）：镜头不是一上来就停在首句上，
    # 而是更放大、首句被画面缘切掉的状态，匀速滑/放大到落定——第一句「慢慢出现」。
    # open_pan = (x_from, x_to, z_from, y_from)；z/y 落点取 cams[0]/zvals[0]。
    if open_pan is not None and steps:
        t1 = min(float(step_start), steps[0]["beat"] - steps[0]["glide"] / 2.0)
        if t1 > 0.35 and (abs(float(open_pan[0]) - float(open_pan[1])) > 8
                          or float(open_pan[2]) > float(zvals[0] if zvals else 1.0) * 1.05):
            tl["open_pan"] = {"t0": 0.0, "t1": float(t1),
                              "x0": float(open_pan[0]), "x1": float(open_pan[1]),
                              "z0": float(open_pan[2]),
                              "z1": float(zvals[0]) if zvals else 1.0,
                              "y0": float(open_pan[3]), "y1": float(cams[0])}
    return tl


def cam_at(t, tl):
    """t 时刻的相机 y。开场滑现期（t < open_pan.t1）从 y0 匀速滑到落定 y1。"""
    op = tl.get("open_pan")
    if op and t < op["t1"]:
        p = min(1.0, max(0.0, (t - op["t0"]) / max(1e-6, op["t1"] - op["t0"])))
        return op["y0"] + (op["y1"] - op["y0"]) * p
    for s in tl["steps"]:
        b, gl = s["beat"], s["glide"]
        if t < b - gl / 2:
            return s["from"]
        if t <= b + gl / 2:
            p = (t - (b - gl / 2)) / gl
            return s["from"] + (s["to"] - s["from"]) * ease_in_out_cubic(p)
    return tl["steps"][-1]["to"] if tl["steps"] else 0.0


def block_enter_t(i, tl, intro_blocks):
    """第 i 块的入场时刻。"""
    if i < intro_blocks:
        return tl["block_beats"][i]
    idx = i - intro_blocks
    if idx < len(tl["steps"]):
        return tl["steps"][idx]["beat"] - tl["steps"][idx]["glide"] / 2
    return 1e9


def x_pos_at(t, tl, xt):
    """水平相机位置：与 cam_at 共用同一节拍曲线。

    xt 长度 = len(tl["steps"]) + 1，xt[0] 为初始 x，之后每步一个落点。
    开场若有 tl["open_pan"]，则在 [t0, t1] 内匀速从 x0 滑到 x1（参考视频手法）。
    """
    op = tl.get("open_pan")
    if op and t < op["t1"]:
        p = (t - op["t0"]) / max(1e-6, op["t1"] - op["t0"])
        p = min(1.0, max(0.0, p))
        return op["x0"] + (op["x1"] - op["x0"]) * p
    for i, s in enumerate(tl["steps"]):
        b, gl = s["beat"], s["glide"]
        if t < b - gl / 2:
            return xt[i]
        if t <= b + gl / 2:
            p = (t - (b - gl / 2)) / gl
            return xt[i] + (xt[i + 1] - xt[i]) * ease_in_out_cubic(p)
    return xt[-1] if len(xt) else 0.0


def zoom_at(t, tl):
    """缩放插值：开场滑现期从 z0 匀速放大到落定 z1，之后 steps[i] 的 zf→zt
    用自己的 zglide（比位移更缓），落点同拍。"""
    op = tl.get("open_pan")
    if op and t < op["t1"]:
        p = min(1.0, max(0.0, (t - op["t0"]) / max(1e-6, op["t1"] - op["t0"])))
        return op["z0"] + (op["z1"] - op["z0"]) * p
    for s in tl["steps"]:
        if "zf" not in s:
            return 1.0
        b, gl = s["beat"], s.get("zglide", s["glide"])
        if t < b - gl / 2:
            return s["zf"]
        if t <= b + gl / 2:
            p = (t - (b - gl / 2)) / gl
            return s["zf"] + (s["zt"] - s["zf"]) * ease_in_out_cubic(p)
    last = tl["steps"][-1] if tl["steps"] else None
    return last["zt"] if last and "zt" in last else 1.0


# ----------------------------------------------------------------------------
# 帧渲染
# ----------------------------------------------------------------------------

def grab_frame(base_img, cx, cy, z, src_scale, out_w, out_h):
    """按（缩放 z + 亚像素中心 cx,cy）从长图取一帧输出画面。

    一次 AFFINE 变换完成取窗+缩放，无整数裁切、无二次插值：
    输入坐标 = 相机中心 + 输出坐标 × (src_scale / z)，小数部分由 BICUBIC 插值吸收。
    cx/cy 与长图同坐标系（已含超采样倍率）。
    """
    k = max(1e-6, src_scale / max(1.0, z))
    m = (k, 0.0, float(cx), 0.0, k, float(cy))
    return base_img.transform((out_w, out_h), Image.AFFINE, m,
                              resample=Image.BICUBIC)


def render_frames(long_base, layers, tl, fps, out_w, out_h, intro_blocks,
                  out_path, progress=None):
    """逐帧合成并直接管道喂给 ffmpeg。返回 (ffmpeg 进程, 帧数)。
    （仅 camera=scroll 旧滚动模式使用，长图必须与 out_w 同宽）"""
    H = long_base.height
    base_np = np.asarray(long_base.convert("RGB"))
    layer_np = [np.asarray(L["rgba"]) for L in layers]      # H×W×4

    n_frames = int(round(tl["total"] * fps))
    cmd = [FF, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (out_w, out_h),
           "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    frame = np.empty((out_h, out_w, 3), dtype=np.uint8)
    for fi in range(n_frames):
        t = fi / fps
        cam = int(round(min(max(cam_at(t, tl), 0), H - out_h)))
        frame[:] = base_np[cam:cam + out_h]
        for i, L in enumerate(layers):
            et = block_enter_t(i, tl, intro_blocks)
            if t < et:
                continue
            y0, y1 = L["y0"], L["y1"]
            if y1 < cam or y0 > cam + out_h:
                continue
            arr = layer_np[i]
            if i < intro_blocks and t < et + 0.5:       # 片头滑入动画
                p = min(1.0, (t - et) / 0.5)
                e = ease_out_cubic(p)
                dx = int((1 - e) * (out_w * 0.55) * (-1 if L["side"] == "peer" else 1))
                a = arr[..., 3].astype(np.float32) * e
                m = a.astype(np.uint8)
                tmp = arr[..., :3].copy()
            else:
                dx = 0
                tmp = arr[..., :3]
                m = arr[..., 3]
            yy0, yy1 = max(y0, cam), min(y1, cam + out_h)
            if yy1 <= yy0:
                continue
            sub_f = frame[yy0 - cam:yy1 - cam]
            sub_l = tmp[yy0 - y0:yy1 - y0]
            sub_m = m[yy0 - y0:yy1 - y0]
            x0, x1 = max(0, dx), min(out_w, out_w + dx)
            lx0, lx1 = max(0, -dx), min(arr.shape[1], out_w - dx)
            if x1 <= x0:
                continue
            region = sub_f[:, x0:x1]
            lay = sub_l[:, lx0:lx1]
            msk = sub_m[:, lx0:lx1, None].astype(np.float32) / 255.0
            region[:] = (lay * msk + region * (1 - msk)).astype(np.uint8)
        proc.stdin.write(frame.tobytes())
        if progress and fi % (fps * 5) == 0:
            progress(fi, n_frames)
    proc.stdin.close()
    return proc, n_frames


def render_frames_ext(base_img, tl, fps, out_w, out_h, z_at, x_at,
                      out_path, progress=None, src_scale=1.0):
    """动态缩放平移渲染：每帧按 z_at(t) 取窗口尺寸、x_at/cam_at 取亚像素中心，
    grab_frame 一次 AFFINE（BICUBIC）出帧——连发拉远、单句拉近、慢滑丝滑
    都在同一条节拍曲线上完成。src_scale = 长图相对 1920 基准的超采样倍率。
    """
    n_frames = int(round(tl["total"] * fps))
    cmd = [FF, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (out_w, out_h),
           "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    W_img, H_img = base_img.size
    for fi in range(n_frames):
        t = fi / fps
        z = max(1.0, z_at(t))
        k = src_scale / z
        cy = min(max(cam_at(t, tl), 0.0), max(0.0, H_img - out_h * k))
        cx = min(max(x_at(t), 0.0), max(0.0, W_img - out_w * k))
        frame = grab_frame(base_img, cx, cy, z, src_scale, out_w, out_h)
        proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
        if progress and fi % (fps * 5) == 0:
            progress(fi, n_frames)
    proc.stdin.close()
    return proc, n_frames


# ----------------------------------------------------------------------------
# 音频
# ----------------------------------------------------------------------------

def make_bgm_wav(path, total, fade_out, out_wav):
    a = None
    try:
        import sound_engine as SE
        a = SE.load_audio_float(path)
    except Exception:                                   # noqa: BLE001
        a = None
    if a is None:
        raise RuntimeError("BGM 解码失败: %s" % path)
    n = int(total * 44100)
    if len(a) < n:                                      # 不够就循环补
        reps = int(np.ceil(n / len(a)))
        a = np.tile(a, reps)
    a = a[:n].copy()
    fo = int(fade_out * 44100)
    if fo > 0:
        a[-fo:] *= np.linspace(1, 0, fo)
    a = np.clip(a, -1, 1)
    pcm = (a * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(pcm.tobytes())
    return out_wav


def bgm_duration(path):
    try:
        import sound_engine as SE
        a = SE.load_audio_float(path)
        if a is not None:
            return len(a) / 44100.0
    except Exception:                                   # noqa: BLE001
        pass
    return 0.0


# ----------------------------------------------------------------------------
# 动态镜头规划（坐标真值驱动，探测/JSON 两路共用）
# ----------------------------------------------------------------------------

def plan_dynamic_camera(msgs, sides, W_img, H_img, zoom, pan, out_w, out_h,
                        note_ys=None, ending=None, avatars=None, note_xs=None):
    """动态镜头 v3：句数定标（用户 0916 凌晨定调）。

    规则：镜头逐句下移；窗口「刚好」框住当前同侧连发的最近 N 句——
    第 1 句框 1 句、第 2 句拉远到 2 句同框、第 3 句 3 句同框，
    再多发就滑动窗口（始终最近 3 句）；换人开口立刻平移到另一侧、句数从 1 重数。
    垂直构图（0916 定标）：窗口底边收紧在当前内容底＋小边距，多余高度留给
    上方已读内容——下一条未读气泡最多露个头，绝不整条暴露。
    横向构图（0916 定标）：当前句的「整颗头像」必须入画（参考视频头像完整），
    因此横向按「头像外缘＋小留白」锚定；装不下时自动降倍率（拉远），
    垂直侧由底边收紧兜住，不会因此漏出下面的气泡。

    msgs[i]    = (y0, y1, xlo, xhi)  气泡「本体」矩形（不含头像/点评行）
    sides[i]   = "L"(对方) | "R"(我方)
    note_ys[i] = 点评行底 y（只兜取景下界，不参与句数与宽度计算）
    ending     = (x0, x1, y1) 结尾 CTA 文字矩形（ render 坐标）
    avatars[i] = (x0, x1) 该句头像横向范围（None=未知，退回气泡外缘）
    返回 (zs, ys, xs)——与 msgs 等长的每步缩放/相机 y/相机 x。
    """
    Z_MAX = 4.2
    MAX_N = 3          # 同侧连发最多同框句数（之后滑动窗口）
    OUT_PAD = 0.04     # 当前句一侧的外留白（锚到头像外缘时用）
    if note_ys is None:
        note_ys = [None] * len(msgs)
    if avatars is None:
        avatars = [None] * len(msgs)
    if note_xs is None:
        note_xs = [None] * len(msgs)
    # 每条消息所处「同侧连发」的起点
    run_start = [0] * len(msgs)
    for i in range(1, len(msgs)):
        run_start[i] = run_start[i - 1] if sides[i] == sides[i - 1] else i
    zs, ys, xs = [], [], []
    for i, (y0, y1, xlo, xhi) in enumerate(msgs):
        s = sides[i]
        k = max(run_start[i], i - MAX_N + 1)      # 取景集 = 第 k..i 句
        avg_h = float(np.mean([msgs[m][1] - msgs[m][0]
                               for m in range(i, min(i + 4, len(msgs)))]))
        fy0 = msgs[k][0]                          # 取景集顶（首句泡顶）
        fy1 = max(msgs[i][1], note_ys[i] or 0.0)  # 取景集底（当前句，含点评行）
        is_last = (i == len(msgs) - 1)
        if is_last and ending is not None:
            # 结尾全景（参考视频结尾实测）：前一句+当前句+点评+CTA 完整同框
            fy1 = max(fy1, ending[2] + 0.15 * avg_h)
            if i > 0:
                fy0 = min(fy0, msgs[i - 1][0])
        # 缩放：高度「刚好」框住 N 句 + 呼吸；宽度由这 N 句的气泡范围决定
        h_need = (fy1 - fy0) + avg_h * BREATH * 2
        z_y = out_h / max(out_h / 9.0, h_need)    # 1920 基准下的 120px 下限等比缩放
        xlo_r = min(msgs[m][2] for m in range(k, i + 1))
        xhi_r = max(msgs[m][3] for m in range(k, i + 1))
        # 取景集内点评行文字的横向范围：长蓝字配短泡时泡宽定不出足够倍率，
        # 必须按文字宽拉远装下（拉远窗口变高，多余高度被底边收紧推到顶边
        # ——镜头相对「往上拉」，下方未读内容照样只露个头）
        for m in range(k, i + 1):
            nx = note_xs[m]
            if nx:
                xlo_r = min(xlo_r, nx[0])
                xhi_r = max(xhi_r, nx[1])
        if is_last and ending is not None:
            # 结尾全景：前一句的横向范围 + CTA + 当前句头像，全部招进画面
            if i > 0:
                xlo_r = min(xlo_r, msgs[i - 1][2])
                xhi_r = max(xhi_r, msgs[i - 1][3])
            xlo_r = min(xlo_r, ending[0])
            xhi_r = max(xhi_r, ending[1])
            if avatars[i]:
                xlo_r = min(xlo_r, avatars[i][0])
                xhi_r = max(xhi_r, avatars[i][1])
            req_w = (xhi_r + 0.10 * W_img) - (xlo_r - 0.10 * W_img)
        elif s == "R":
            # 当前句的头像必须整颗入画 → 外侧边界取「头像右缘」（无头像真值退回泡右缘）
            r_edge = max(xhi_r, avatars[i][1]) if avatars[i] else xhi_r
            req_w = (r_edge + OUT_PAD * W_img) - (xlo_r - 0.06 * W_img)
        else:
            l_edge = min(xlo_r, avatars[i][0]) if avatars[i] else xlo_r
            req_w = (xhi_r + 0.03 * W_img) - (l_edge - OUT_PAD * W_img)
        z_x = out_w / max(out_w / 6.0, req_w)     # 1920 基准下的 320px 下限等比缩放
        z = max(zoom, min(Z_MAX, z_y, z_x))       # zoom=滑杆拉远下限
        # （开场 i==0 不再特判：统一走「框当前句+点评+呼吸」与底边收紧，
        #   开场画面里只有第一句自己——比旧「次句泡顶露 93%」更放大、更干净）
        win_h, win_w = out_h / z, out_w / z
        # 垂直（参考视频规律 0916 定标 + 用户同日定调「边边也不要露」）：
        # 窗口底边钉死在当前内容底（泡/点评行的下缘），下方下一条气泡
        # 一个像素都不进画面；多余的窗口高度全部留给上方已读内容
        # （上面的泡被切一半也无妨；宽度约束压低倍率时 surplus 全去顶边）。
        if i + 1 < len(msgs) and (msgs[i + 1][0] - fy1) < 0.6 * avg_h:
            bot_m = 0.0                           # 下面紧贴着下一条：一点不露
        else:
            bot_m = BREATH * avg_h                # 底下没内容了：正常呼吸
        y = fy1 + bot_m - win_h
        y = max(0.0, min(y, H_img - win_h))
        if pan == "center":
            x = (W_img - win_w) / 2.0
        elif is_last and ending is not None:
            # 结尾全景：横向居中于内容整体
            x = (xlo_r + xhi_r) / 2.0 - win_w / 2.0
            x = max(0.0, min(x, W_img - win_w))
        elif s == "R":
            # 锚定「气泡+头像」块：头像右缘（无真值退回泡右缘）对到画面右缘
            r_edge = max(xhi, avatars[i][1]) if avatars[i] else xhi
            x = r_edge + OUT_PAD * W_img - win_w
            x = max(0.0, min(x, W_img - win_w))
        else:                   # 对方：头像左缘对到画面左缘（整颗头像入画）
            l_edge = min(xlo, avatars[i][0]) if avatars[i] else xlo
            x = l_edge - OUT_PAD * W_img
            x = max(0.0, min(x, W_img - win_w))
        zs.append(z)
        ys.append(y)
        xs.append(x)
    return zs, ys, xs


BREATH = 0.38         # 取景集上/下呼吸空间（按句均高比例，模块级供开场复用）


def opening_pan(sides, msgs, note_ys, zs, ys, xs, W_img, H_img, out_w, out_h,
                opener_zoom=1.22, cut=0.30):
    """开场起点状态（用户 0916 定调「第一句话要慢慢出现，别开局就看到」）。

    参考 t=0 实测：首句泡被画面缘切掉（只见「们还是分手吧」），且开场倍率
    比落定更大；约 0.7s 泡才滑完整、2s 头像入画落定。
    返回 (x_from, x_to, z_from, y_from)：
      z_from = 落定倍率 × opener_zoom（更放大）
      x_from = 首句泡被画面缘切掉 cut 比例的位置（L 侧切左缘 / R 侧切右缘）
      y_from = 同底边收紧规则、按放大后的窗口算（画面里只有第一句+点评）
    """
    if not xs:
        return None
    z_to, x_to, y_to = float(zs[0]), float(xs[0]), float(ys[0])
    z_from = min(z_to * opener_zoom, z_to + 2.0)
    win_w0, win_h0 = out_w / max(0.2, z_from), out_h / max(0.2, z_from)
    xlo0, xhi0 = msgs[0][2], msgs[0][3]
    bw0 = max(1.0, xhi0 - xlo0)
    if sides[0] == "L":
        x_from = xlo0 + cut * bw0            # 画面左缘切掉泡左段 → 从右往左滑入
    else:
        x_from = xhi0 - cut * bw0 - win_w0   # 画面右缘切掉泡右段 → 从左往右滑入
    x_from = max(0.0, min(x_from, max(0.0, W_img - win_w0)))
    fy1_0 = max(msgs[0][1], (note_ys[0] if note_ys else None) or 0.0)
    avg_h0 = float(msgs[0][1] - msgs[0][0])
    if len(msgs) > 1 and (msgs[1][0] - fy1_0) < 0.6 * avg_h0:
        bot_m0 = 0.0                          # 与主镜头同口径：下方一点不露
    else:
        bot_m0 = BREATH * avg_h0
    y_from = fy1_0 + bot_m0 - win_h0
    y_from = max(0.0, min(y_from, max(0.0, H_img - win_h0)))
    if z_from <= z_to * 1.05 and abs(x_from - x_to) < 8:
        return None
    return (x_from, x_to, z_from, y_from)


# ----------------------------------------------------------------------------
# 外部长图：自动找内容块（仅用于上传截图，JSON 模式不走这里）
# ----------------------------------------------------------------------------

def bands_from_image(img, min_h=50):
    """在(已缩放到工作宽度)的长图上找内容块。

    用「暗色文字」判据：聊天气泡里的字都是深色的，对彩色渐变背景
    的手机截图鲁棒（白泡/绿泡/背景色都会骗过亮度阈值）。

    返回 [(y0, y1, cx), ...]，cx = 该带文字质心 x（判断气泡在左还是在右）。
    """
    g = np.asarray(img.convert("L"))
    dark = g < 100
    cov = dark.mean(axis=1)
    W = img.width
    thr, merge = 0.015, 90
    bands, inb, y0 = [], False, 0
    for y, v in enumerate(cov):
        if v > thr and not inb:
            inb, y0 = True, y
        elif v <= thr and inb:
            inb = False
            if y - y0 >= min_h:
                bands.append([y0, y])
    if inb and len(cov) - y0 >= min_h:
        bands.append([y0, len(cov)])
    merged = []
    for b in bands:
        if merged and b[0] - merged[-1][1] < merge:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    out = []
    for y0, y1 in merged:
        seg = dark[y0:y1]
        col = seg.sum(axis=0)
        tot = int(col.sum())
        if not tot:
            out.append((y0, y1, W / 2.0, W / 2.0, W / 2.0))
            continue
        xs = np.repeat(np.arange(W), col.astype(np.int64))
        cx = float(np.median(xs))                       # 中位数比均值抗长尾
        x_lo, x_hi = (float(np.percentile(xs, 2)),
                      float(np.percentile(xs, 98)))
        out.append((y0, y1, cx, x_lo, x_hi))
    return out


def side_by_color(img, y0, y1, cx_fallback):
    """用气泡颜色判侧：我方=微信绿泡(#95EC69 系)→R，否则→L(对方白泡)。

    位置中点判定会被短句/时间戳/居中元素骗过；颜色是确定性信号。
    绿色像素不明显（检测不到绿泡）时才回退到 cx 中点判定。
    """
    seg = np.asarray(img.convert("RGB"))[max(0, int(y0)):int(y1)]
    if seg.size == 0:
        return "L" if cx_fallback < img.width / 2.0 else "R"
    r = seg[..., 0].astype(np.int16)
    g = seg[..., 1].astype(np.int16)
    b = seg[..., 2].astype(np.int16)
    green = (g > 150) & (g - r > 25) & (g - b > 30)
    n = int(green.sum())
    if n >= seg.shape[0] * seg.shape[1] * 0.015:      # 绿泡足够明显才信颜色
        mid = img.width // 2
        cols = green.sum(axis=0)
        return "R" if int(cols[mid:].sum()) >= int(cols[:mid].sum()) else "L"
    return "L" if cx_fallback < img.width / 2.0 else "R"


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="JSON 配置（blocks 模式）")
    ap.add_argument("--longimg", help="外部整图模式")
    ap.add_argument("--wxshot", help="微信仿真长图模式（wx_export.py 的产物 PNG）")
    ap.add_argument("--manifest", help="坐标清单（默认 <wxshot>.manifest.json）")
    ap.add_argument("--bgm", help="背景音乐（覆盖 config）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preview-only", action="store_true")
    args = ap.parse_args()

    args.out = os.path.abspath(args.out)       # 统一绝对路径，避免子进程 cwd 歧义
    tmp_out = args.out + ".tmp.mp4"

    cfg = {}
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    # 配置里也可以直接给长图（编辑器 API 走这条通道）
    if not args.longimg and cfg.get("longimg"):
        args.longimg = cfg["longimg"]
    meta = cfg.get("meta", {})
    pace = cfg.get("pace", {})
    intro_blocks = int(cfg.get("intro", {}).get("blocks", 2))
    opts = cfg.get("longimg_opts") or {}
    zoom = max(1.0, float(opts.get("zoom", 1.0)))
    pan = str(opts.get("pan", "side")).lower()
    if pan not in ("side", "center"):
        pan = "side"

    bgm = args.bgm or cfg.get("bgm", {}).get("path") or ""
    if not bgm or not os.path.isfile(bgm):
        print("[错误] BGM 不存在:", bgm)
        return 1
    bgm_len = bgm_duration(bgm)
    print("[BGM] %.2fs  %s" % (bgm_len, bgm))

    # ---- 长图来源 ----
    ext_zoom = False
    src_scale = 1.0
    xt = [0.0]
    zvals = None
    if args.wxshot:
        # ★微信仿真长图：wx_export.py 驱动 vue-WeChat 出正宗微信样式长图，
        # 并导出每条消息的 DOM 坐标真值——零探测，直接动态镜头。
        mpath = args.manifest or os.path.splitext(args.wxshot)[0] + ".manifest.json"
        with open(mpath, "r", encoding="utf-8") as f:
            mf = json.load(f)
        long_img = Image.open(args.wxshot).convert("RGB")
        dsf = float(mf.get("dsf", 1))
        scale = OUT_W / long_img.width
        if abs(scale - 1.0) > 0.01:
            long_img = long_img.resize((OUT_W, int(long_img.height * scale)),
                                       Image.LANCZOS)
        css_f = scale * dsf                  # CSS px → 1920 基准
        W_img, H_img = long_img.size
        msgs, sides, note_ys, avatars, note_xs = [], [], [], [], []
        ending = None
        # 头像真值：清单里有 avatar 就用；老清单没有 → 按微信皮肤常量反推
        # （头像 62.6×62.6、与泡间距 18.3，见 enhance/chat_exact.css）
        AV, GAP = 62.6 * css_f, 18.3 * css_f
        e = mf.get("ending")
        if e and e.get("x1") is not None:
            ending = (e["x0"] * css_f, e["x1"] * css_f, e["y1"] * css_f)
        for it in mf.get("items") or []:
            if it.get("type") != "msg" or not it.get("bubble"):
                continue
            b = it["bubble"]
            nt = it.get("note") or {}
            # 气泡本体矩形（定位/取景全按它算）；点评行底单独传，只兜取景下界
            note_y = nt["y1"] * css_f if nt else None
            # 点评文字横向范围（tx0/tx1=Range 量测的真文字宽；老清单没有则不并入）
            note_x = ((nt["tx0"] * css_f, nt["tx1"] * css_f)
                      if nt.get("tx1") is not None else None)
            side = it.get("side") or "L"
            bx0, bx1 = b["x0"] * css_f, b["x1"] * css_f
            msgs.append((b["y0"] * css_f, b["y1"] * css_f, bx0, bx1))
            note_ys.append(note_y)
            note_xs.append(note_x)
            sides.append(side)
            av = it.get("avatar")
            if av and av.get("x1") is not None:
                avatars.append((av["x0"] * css_f, av["x1"] * css_f))
            elif side == "R":
                avatars.append((bx1 + GAP, bx1 + GAP + AV))
            else:
                avatars.append((bx0 - GAP - AV, bx0 - GAP))
        if not msgs:
            print("[错误] 清单里没有消息坐标")
            return 1
        zs, ys, xs = plan_dynamic_camera(msgs, sides, W_img, H_img,
                                         zoom, pan, OUT_W, OUT_H,
                                         note_ys=note_ys, ending=ending,
                                         avatars=avatars, note_xs=note_xs)
        print("[镜头] %d 条消息（微信仿真 DOM 真值）；zoom %.2f~%.2f（下限 %.2f）"
              % (len(msgs), min(zs), max(zs), zoom))
        open_msgs, open_notes = msgs, note_ys
        # 参考视频方法：开场镜头=msgs[0] 的「页面顶部」构图（plan 内 i==0 特例），
        # 静止撑 2 拍后第一步直接移到 msgs[1]——不再有独立的「拉近第一句」一步
        cams = ys
        xt = xs
        zvals = zs
        ext_zoom = True
        print("[长图] %dx%d（微信仿真），平移 %s，开场 x=%.0f"
              % (W_img, H_img, pan, xt[0]))
        long_base = long_img
        layers = []
        intro_blocks = 0
    elif args.longimg:
        # 外部截图：探测定位（上传图没有真值，只能看图猜）
        long_img = Image.open(args.longimg).convert("RGB")
        scale = OUT_W / long_img.width
        if abs(scale - 1.0) > 0.01:
            long_img = long_img.resize((OUT_W, int(long_img.height * scale)),
                                       Image.LANCZOS)
        bands = bands_from_image(long_img)
        W_img, H_img = long_img.size
        half = W_img / 2.0
        # 过滤非气泡带：太矮（状态栏）或横居中的矮带（时间戳/「对方正在输入」）；
        # 居中但很高的带是真内容（整块图片消息等），保留
        msgs = [b for b in bands
                if b[1] - b[0] >= 100
                and (not (half * 0.84 < b[2] < half * 1.16) or b[1] - b[0] >= 220)]
        if not msgs:
            print("[错误] 没识别到消息块")
            return 1
        sides = [side_by_color(long_img, b[0], b[1], b[2]) for b in msgs]

        # 剔除头像死区：头像照片内的暗像素会污染 xlo/xhi（左头像把 xlo 拉到
        # ~0.04W、右头像把 xhi 拉到 ~0.96W），导致锚定失效、窗口虚宽。
        clean = []
        for (y0, y1, cx, xlo, xhi), s in zip(msgs, sides):
            if s == "R":
                clean.append((y0, y1, xlo, min(xhi, 0.905 * W_img)))
            else:
                clean.append((y0, y1, max(xlo, 0.095 * W_img), xhi))
        zs, ys, xs = plan_dynamic_camera(clean, sides, W_img, H_img,
                                         zoom, pan, OUT_W, OUT_H)
        print("[镜头] %d 条消息（像素探测）；zoom %.2f~%.2f（滑杆下限 %.2f）"
              % (len(clean), min(zs), max(zs), zoom))
        open_msgs, open_notes = clean, None
        # 开场同参考方法：cams[0]=msgs[0] 的页面顶部构图，撑 2 拍后移 msgs[1]
        cams = ys
        xt = xs
        zvals = zs
        ext_zoom = True
        print("[长图] %dx%d，检测到 %d 条消息，平移 %s，开场 x=%.0f"
              % (W_img, H_img, len(clean), pan, xt[0]))
        long_base = long_img
        layers = []
        intro_blocks = 0            # 整图模式不做逐块滑入
    else:
        blocks = cfg.get("blocks") or []
        if not blocks:
            print("[错误] 配置里没有 blocks")
            return 1
        end_note = (cfg.get("ending") or {}).get("note") or ""
        camera_mode = str(cfg.get("camera", "dynamic")).lower()
        eb = 280 if end_note else 0

        if camera_mode == "scroll":
            # 旧滚动模式：只上下滚 + 片头逐块滑入（长图须 1920 宽）
            long_img, layers = CC.render_blocks(blocks, meta, extra_bottom=eb)
            if end_note:
                CC.render_ending(long_img, end_note,
                                 (cfg.get("ending") or {}).get("color", "red"))
            long_base = long_img.convert("RGB")
            cams = [0.0] + [max(0.0, min(L["cy"] - OUT_H / 2, long_img.height - OUT_H))
                            for L in layers]
            if end_note:
                cams.append(max(0.0, long_img.height - OUT_H))   # 最后一滑停在结尾 CTA
            print("[长图] %dx%d，%d 个消息块（scroll 旧模式）"
                  % (long_img.width, long_img.height, len(layers)))
        else:
            # ★程序化动态镜头：画长图时同步拿气泡矩形真值，零探测。
            # 超采样画质：默认 2 倍，超过内存上限自动降档。
            ss_req = max(1.0, float(cfg.get("quality", {}).get("supersample", 2.0)))
            ss = ss_req
            for _ in range(4):
                long_img, layers = CC.render_blocks(blocks, meta,
                                                    extra_bottom=eb, s=ss)
                if long_img.width * long_img.height * 3 <= MAX_SRC_BYTES or ss <= 1.0:
                    break
                ss = max(1.0, round(ss / 2.0, 2))
                if ss == ss_req:
                    break
            if end_note:
                CC.render_ending(long_img, end_note,
                                 (cfg.get("ending") or {}).get("color", "red"),
                                 s=ss)
            long_base = long_img
            src_scale = ss
            W_img, H_img = long_img.size
            OW, OH = OUT_W * ss, OUT_H * ss
            msgs, sides = [], []
            for L in layers:
                if "bx" not in L:
                    continue
                msgs.append((L["by0"], L["by1"], float(L["bx"]),
                             float(L["bx"] + L["bw"])))
                sides.append("R" if L["side"] == "me" else "L")
            if not msgs:
                print("[错误] 坐标清单为空")
                return 1
            zs, ys, xs = plan_dynamic_camera(msgs, sides, W_img, H_img,
                                             zoom, pan, OW, OH)
            cams = ys
            xt = xs
            zvals = zs
            ext_zoom = True
            layers = []
            intro_blocks = 0            # 动态模式开场=页面顶部构图，撑 2 拍再移
            print("[镜头] %d 条消息（坐标真值）；zoom %.2f~%.2f（下限 %.2f）"
                  % (len(msgs), min(zs), max(zs), zoom))
            open_msgs, open_notes = msgs, None
            print("[长图] %dx%d（超采样 %.2fx），平移 %s，开场 x=%.0f"
                  % (W_img, H_img, ss, pan, xt[0]))

    # ---- 鼓点与时间轴 ----
    beats, _ = detect_beats(bgm, min_gap=pace.get("min_gap", 1.15))
    print("[鼓点] 强拍 %d 个，前 8 个: %s" % (len(beats), np.round(beats[:8], 2).tolist()))
    # 动态镜头线（ext_zoom）沿用参考视频方法：开场静止撑 2 拍，第一步落第 3 拍
    open_hold = int(pace.get("open_hold_beats", 2 if ext_zoom else 0))
    # 开场滑现：更放大 + 首句被画面缘切掉，慢慢滑/放大到落定（参考视频手法）
    op_pan = opening_pan(sides, open_msgs, open_notes, zs, ys, xs,
                         W_img, H_img, OUT_W * src_scale, OUT_H * src_scale,
                         ) if ext_zoom else None
    if op_pan:
        print("[开场] 滑现 x %.0f→%.0f  z %.2f→%.2f（首句 %s 侧，%s滑）"
              % (op_pan[0], op_pan[1], op_pan[2], float(zs[0]), sides[0],
                 "右→左" if sides[0] == "L" else "左→右"))
    tl = build_timeline(cams, beats, pace, intro_blocks, bgm_len, zvals=zvals,
                        open_hold_beats=open_hold, open_pan=op_pan)
    if ext_zoom and tl["steps"]:
        # 开场第一滑 = 慢慢移向第一条消息（对标手法），其余步保持快滑
        tl["steps"][0]["glide"] = max(tl["steps"][0]["glide"], 0.9)
    print("[时间轴] 片头块 %d（拍 %s）| 滚动 %d 步 | 成片 %.2fs"
          % (intro_blocks, np.round(tl["block_beats"], 2).tolist(),
             len(tl["steps"]), tl["total"]))

    # ---- 预览模式：抽 6 个关键帧拼图 ----
    if args.preview_only:
        picks = [0.0, tl["intro_end"] - 0.05] + \
            [s["beat"] + 0.4 for s in tl["steps"][::max(1, len(tl["steps"]) // 4)][:4]] + \
            [tl["total"] - 1.0]
        if ext_zoom:
            thumbs = []
            for t in picks:
                z = max(1.0, zoom_at(t, tl))
                k = src_scale / z
                cy = min(max(cam_at(t, tl), 0), max(0.0, long_base.height - OUT_H * k))
                cx = min(max(x_pos_at(t, tl, xt), 0), max(0.0, long_base.width - OUT_W * k))
                thumbs.append(grab_frame(long_base, cx, cy, z, src_scale,
                                         OUT_W, OUT_H))
        else:
            thumbs = []
            for t in picks:
                cam = int(round(min(max(cam_at(t, tl), 0), long_img.height - OUT_H)))
                thumbs.append(long_base.crop((0, cam, OUT_W, cam + OUT_H)))
        sheet = Image.new("RGB", (OUT_W // 2 * 3, OUT_H // 2 * 2), (20, 20, 20))
        for i, th in enumerate(thumbs[:6]):
            sheet.paste(th.resize((OUT_W // 2, OUT_H // 2)),
                        ((i % 3) * OUT_W // 2, (i // 3) * OUT_H // 2))
        prev = args.out + ".preview.jpg"
        sheet.save(prev, quality=88)
        print("[预览]", prev, "关键帧时刻:", np.round(picks, 2).tolist())
        return 0

    # ---- 渲染 ----
    def prog(fi, n):
        print("  帧 %d/%d (%.0f%%)" % (fi, n, 100 * fi / n), flush=True)

    if ext_zoom:
        n_need = len(tl["steps"]) + 1
        if len(xt) < n_need:
            xt = xt + [xt[-1]] * (n_need - len(xt))
        xt = xt[:n_need]
        proc, n_frames = render_frames_ext(
            long_base, tl, args.fps, OUT_W, OUT_H,
            lambda t: zoom_at(t, tl), lambda t: x_pos_at(t, tl, xt),
            tmp_out, progress=prog, src_scale=src_scale)
    else:
        proc, n_frames = render_frames(long_base, layers, tl, args.fps, OUT_W, OUT_H,
                                       intro_blocks, tmp_out, progress=prog)
    rc = proc.wait()
    if rc != 0:
        print("[错误] 视频编码失败 rc=", rc)
        return 1
    print("[视频] %d 帧编码完成" % n_frames)

    # ---- 音频 ----
    print("[调试] tmp 存在=%s 大小=%s" % (os.path.isfile(tmp_out),
          os.path.getsize(tmp_out) if os.path.isfile(tmp_out) else "-"), flush=True)
    if not os.path.isfile(tmp_out):
        print("[错误] 编码产物缺失:", tmp_out)
        return 1
    wav = tmp_out + ".bgm.wav"
    make_bgm_wav(bgm, tl["total"], float(cfg.get("bgm", {}).get("fade_out", 1.2)), wav)
    cmd = [FF, "-y", "-loglevel", "error", "-i", tmp_out, "-i", wav,
           "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", args.out]
    subprocess.run(cmd, check=True)
    for p in (tmp_out, wav):
        try:
            os.remove(p)
        except OSError:
            pass
    print("[完成]", args.out, "%.2fs" % tl["total"],
          "%.1f MB" % (os.path.getsize(args.out) / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())
