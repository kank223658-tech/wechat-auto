from imageio_ffmpeg import get_ffmpeg_exe
import subprocess

ff = get_ffmpeg_exe()
v = "videos/wx_opt1_20260904_183234_878.mp4"
for i, t in enumerate(["3.0", "4.5", "7.0"]):
    out = "_opt1_chk_%d.png" % i
    subprocess.run([ff, "-v", "error", "-ss", t, "-i", v, "-frames:v", "1", out, "-y"], check=True)
    print(out)
