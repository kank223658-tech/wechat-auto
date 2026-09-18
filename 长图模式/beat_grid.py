# -*- coding: utf-8 -*-
"""
长图模式 · 鼓点检测
====================
对 BGM 做谱通量 onset 检测（scipy，无额外依赖），输出「强拍」时间序列。
滚动步进与片头卡点都落在强拍上 —— 与对标的机制一致
（实测对标滚动落点 4.7 / 8.45 / 10.32 … 与其 BGM 强拍逐一重合）。
"""
import os
import subprocess
import tempfile

import numpy as np
from scipy import signal

from sound_engine import load_audio_float

SR = 44100


def audio_to_wav_float(path):
    """任意音频 → float32 单声道 (44100)。支持 wav 直接读，其它走 ffmpeg。"""
    arr = load_audio_float(path)
    if arr is None:
        raise RuntimeError("无法解码音频: %s" % path)
    return arr


def detect_beats(path, min_gap=1.15, strength_q=0.0):
    """返回强拍时间列表（秒，升序）。

    min_gap: 两个强拍的最小间隔（秒）——滚动一步最快也要一拍多。
    strength_q: 峰值强度的分位数门槛，越高拍越少。
    """
    a = audio_to_wav_float(path)
    hop, nfft = 512, 1024
    _, t, S = signal.spectrogram(a, fs=SR, nperseg=nfft, noverlap=nfft - hop,
                                 window="hann")
    S = np.log1p(1000 * S)
    flux = np.maximum(0, np.diff(S, axis=1)).sum(axis=0)
    if flux.max() > 0:
        flux = flux / flux.max()
    smooth = np.convolve(flux, np.ones(5) / 5, mode="same")
    dist = int(min_gap * SR / hop)
    peaks, _ = signal.find_peaks(smooth, distance=dist)
    if not len(peaks):
        return [], t
    heights = smooth[peaks]
    thr = np.quantile(heights, strength_q)
    strong = peaks[heights >= thr]
    beats = t[strong]
    beats = beats[beats >= 0.5]          # 掐头：开头半秒内的点不稳
    return sorted(beats.tolist()), t


def plan_step_beats(beats, n_steps, start_at=None, max_step=3.5, end_at=None):
    """从强拍里挑出 n_steps 个滚动落点。

    - start_at: 从这个时刻之后开始取（默认跳过片头，用第 intro_blocks 个拍之后）
    - 相邻落点间隔超过 max_step 时补拍（等分插入）——音乐空拍也要继续走
    - end_at: 不晚于这个时刻
    返回长度 n_steps 的落点列表。
    """
    pool = [b for b in beats if (start_at is None or b > start_at)
            and (end_at is None or b < end_at)]
    if not pool:
        # 兜底：无有效鼓点就按 1.9s 均匀铺（对标实测平均步距 ≈1.88s）
        t0 = start_at if start_at is not None else 4.6
        return [t0 + 1.9 * (i + 1) for i in range(n_steps)]
    steps = []
    for i, b in enumerate(pool):
        if steps and b - steps[-1] > max_step:
            k = int((b - steps[-1]) // max_step) + 1
            for j in range(1, k + 1):
                steps.append(steps[-1] + (b - steps[-1]) / k * j)
            steps[-1] = b
        else:
            steps.append(b)
        if len(steps) >= n_steps:
            break
    # 鼓点不够：按最后一步距继续补
    last = steps[-1] if steps else (start_at or 4.6)
    gap = min(max_step, np.median(np.diff(steps)).item() if len(steps) > 2 else 1.9)
    while len(steps) < n_steps:
        last += float(gap)
        steps.append(last)
    return steps[:n_steps]


if __name__ == "__main__":
    import sys
    beats, _ = detect_beats(sys.argv[1])
    print("强拍数:", len(beats))
    print(np.round(beats[:24], 2).tolist())
