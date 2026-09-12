# 扫描视频：逐帧找「事件时刻」（ffmpeg 管道直读 raw gray，无需 imageio）
import subprocess, sys, os
import numpy as np

FF = r"C:/Users/mik/AppData/Local/Programs/Python/Python314/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
VID = sys.argv[1] if len(sys.argv) > 1 else "_snd/numkey_send_demo.mp4"
FPS = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
W, H = 270, 585

cmd = [FF, "-i", VID, "-vf", f"scale={W}:{H}", "-pix_fmt", "gray", "-f", "rawvideo", "-loglevel", "error", "-"]
raw = subprocess.run(cmd, capture_output=True).stdout
n = len(raw) // (W * H)
frames = np.frombuffer(raw[:n*W*H], dtype=np.uint8).reshape(n, H, W).astype(np.int16)
print(f"总帧数 {n}, 时长 {n/FPS:.2f}s")

regions = {"input": (slice(300, 322), slice(20, 200)), "bksp": (slice(412, 432), slice(243, 266)),
           "cand": (slice(355, 375), slice(5, 265)), "kbpage": (slice(400, 560), slice(5, 265))}
last = {}
for i in range(1, n):
    mad = np.abs(frames[i] - frames[i-1]).mean()
    if mad > 1.0:
        msgs = []
        for name, (ys, xs) in regions.items():
            m = np.abs(frames[i][ys, xs] - frames[i-1][ys, xs]).mean()
            if m > 2.0:
                msgs.append(f"{name}={m:.0f}")
        print(f"t={i/FPS:.3f}s 全帧MAD={mad:.1f}  {', '.join(msgs)}")
