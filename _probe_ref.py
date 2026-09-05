import subprocess
import sys
from imageio_ffmpeg import get_ffmpeg_exe

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ff = get_ffmpeg_exe()
v = r"C:\Users\Administrator\Downloads\真实打字动画和间隔.MP4"
out = subprocess.run([ff, "-i", v], capture_output=True, text=True, errors="replace")
print(out.stderr[-1200:])
