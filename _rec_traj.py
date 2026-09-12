# -*- coding: utf-8 -*-
"""视频位移轨迹检查（快速通道）。

用 ffmpeg 直接输出 rawvideo 灰度帧到管道（跳过 PNG 编解码，比抽帧再读快 5~10 倍），
对每帧沿扫描线找最强边缘，得到「边缘位置-时间」轨迹，报告单调性与回跳。

用法: py _rec_traj.py <video> <t0> <t1> <axis:x|y> <line> <a> <b> [fps] [scale_w] [scale_h]
  axis=x：扫第 line 行，在 x∈[a,b]（缩放后坐标）找竖边 → 页面左右滑
  axis=y：扫第 line 列，在 y∈[a,b]（缩放后坐标）找横边 → 面板上下滑
"""
import sys
import subprocess
import numpy as np
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()


def read_frames(video, t0, t1, fps, w, h):
    p = subprocess.run([FF, "-v", "error",
                        "-ss", "%.3f" % t0, "-i", video, "-t", "%.3f" % (t1 - t0),
                        "-vf", "fps=%d,scale=%d:%d,format=gray" % (fps, w, h),
                        "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    buf = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(buf) // (w * h)
    return buf[:n * w * h].reshape(n, h, w).astype(np.float32), 1.0 / fps


def edge_pos(prof, a, b):
    seg = prof[a:b]
    if len(seg) < 4:
        return None
    d = np.abs(np.diff(seg))
    i = int(np.argmax(d))
    if d[i] < 8:
        return None
    if 0 < i < len(d) - 1:
        y0, y1, y2 = d[i - 1], d[i], d[i + 1]
        den = y0 - 2 * y1 + y2
        sub = 0.5 * (y0 - y2) / den if abs(den) > 1e-6 else 0.0
    else:
        sub = 0.0
    return a + i + sub


def main():
    video = sys.argv[1]
    axis = sys.argv[2]
    line = int(sys.argv[3])
    a, b = int(sys.argv[4]), int(sys.argv[5])
    fps = int(sys.argv[6]) if len(sys.argv) > 6 else 60
    w = int(sys.argv[7]) if len(sys.argv) > 7 else 150
    h = int(sys.argv[8]) if len(sys.argv) > 8 else 325

    fs, dt = read_frames(video, fps, w, h)
    print("%s  共 %d 帧 (%.0f fps, 采样标尺 %dx%d)" % (video, len(fs), 1 / dt, w, h))

    traj = []
    for i, f in enumerate(fs):
        prof = f[line, :] if axis == "x" else f[:, line]
        traj.append((i * dt, edge_pos(prof, a, b)))
    good = [(t, p) for t, p in traj if p is not None]
    if len(good) < 4:
        print("  有效边缘太少 %d/%d" % (len(good), len(traj)))
        return
    s = 1000.0 / w if axis == "x" else 1000.0 / h          # 采样标尺 → 全分辨率像素
    print("  轨迹(ms:位置, 已换算回 600x1300 像素):")
    print("   " + " ".join("%.0f:%s" % (t * 1000, "-" if p is None else "%.0f" % (p * s))
                           for t, p in traj[::max(1, len(traj) // 24)]))
    p0, p1 = good[0][1], good[-1][1]
    total = p1 - p0
    sign = 1 if total >= 0 else -1
    print("  首 %.0f → 末 %.0f  总位移 %+.0f px(全分辨率)" % (p0 * s, p1 * s, total * s))

    # 只看"运动中"的帧：与首末值都差 > 1% 总位移
    moving = [(t, p) for t, p in good if abs(p - p0) > abs(total) * 0.01 and abs(p - p1) > abs(total) * 0.01]
    back_frames, back_max = 0, 0.0
    for i in range(1, len(moving)):
        step = (moving[i][1] - moving[i - 1][1]) * sign
        if step < -abs(total) * 0.005:
            back_frames += 1
            back_max = max(back_max, -step)
    # 极值后是否回退（鬼影的典型特征：先冲到终点又弹回再前进）
    peak = max(moving, key=lambda g: (g[1] - p0) * sign) if moving else good[0]
    after = [g for g in moving if g[0] > peak[0]]
    tail = ((peak[1] - min(after, key=lambda g: (g[1] - p0) * sign)[1]) * sign) if after else 0.0
    mx = max(abs(moving[i][1] - moving[i - 1][1]) for i in range(1, len(moving))) if len(moving) > 1 else 0
    print("  运动帧 %d 个；倒退帧 %d 个（最大回跳 %.1fpx）；冲峰后最多回退 %.1fpx；单帧最大步 %.1fpx"
          % (len(moving), back_frames, back_max * s, tail * s, mx * s))
    if back_frames == 0 and tail * s < 4:
        print("  → 单调推进 ✓（无鬼影回跳）")
    elif back_max * s < 6:
        print("  → 轻微抖动（可接受）")
    else:
        print("  → 存在回跳/鬼影 ✗")


main()
