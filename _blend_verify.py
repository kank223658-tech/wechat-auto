# -*- coding: utf-8 -*-
"""验证 _assemble_vfr_mp4 的长间隔过渡：构造「10 帧深色 + 0.4s 大间隙 + 4 帧浅色」，
调用合成并核对输出时长（理论 36 帧 ≈ 0.60s）与是否成功。"""
import sys, os, io, subprocess, shutil
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M
from PIL import Image

def jpeg(rgb):
    im = Image.new("RGB", (600, 1300), rgb)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()

dark = jpeg((30, 30, 40))
light = jpeg((220, 200, 180))

frames = []
t = 0.0
for _ in range(10):          # 深色 0..0.15s
    frames.append((t, dark)); t += 1.0/60
t = 0.55                       # 0.4s 大间隙
for _ in range(4):           # 浅色 0.55..0.6167s
    frames.append((t, light)); t += 1.0/60

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe as bnd
        ffmpeg = bnd()
    except Exception:
        ffmpeg = None
print("ffmpeg:", ffmpeg)
if not ffmpeg:
    sys.exit("无 ffmpeg")

out = r"F:\weixin-auto\_blend_test.mp4"
M.WeChatAuto._assemble_vfr_mp4(ffmpeg, frames, out, trim_sec=0.0)
print("合成成功:", os.path.exists(out), os.path.getsize(out) if os.path.exists(out) else "-")

# 用 ffprobe 或 ffmpeg 读时长
try:
    p = subprocess.run([ffmpeg, "-i", out], capture_output=True, text=True, errors="replace")
    import re
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
    if m:
        h, mi, s = m.groups()
        dur = int(h)*3600 + int(mi)*60 + float(s)
    else:
        dur = None
    fm = re.search(r"(\d+) frames", p.stderr)
    print(f"输出时长: {dur}s (理论 ≈0.62s)  编码器帧数报告: {fm.group(1) if fm else '?'}")
except Exception as e:
    print("读时长失败:", e)