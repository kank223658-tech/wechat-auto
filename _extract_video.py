# -*- coding: utf-8 -*-
"""从成品 mp4 抽帧到 _video_frames/，供 _scan_highlight.py 复用验证动画是否可见。"""
import os
import sys
import imageio_ffmpeg
import subprocess


def extract(mp4, fps=60):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_video_frames")
    os.makedirs(out, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    pat = os.path.join(out, "vf_%03d.jpg")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", mp4,
                    "-vf", f"fps={fps}", "-q:v", "3", pat], check=True)
    print("抽帧到", out)
    return out


if __name__ == "__main__":
    mp4 = sys.argv[1] if len(sys.argv) > 1 else r"F:\weixin-auto\videos\wx_20260903_214907_372.mp4"
    extract(mp4)
