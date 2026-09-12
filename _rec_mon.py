# -*- coding: utf-8 -*-
"""录制监控启动器：跑同款录制，另起线程每 2s 打印 _FRAMES 数量与最新时间戳"""
import sys, threading, time

sys.argv = ["main.py", "--script", "_peer_nav_demo.txt",
            "--headless", "--scene", "_scene_peer.json", "--no-bgm"]
sys.path.insert(0, r"G:\weixin-auto")
import main  # noqa: E402

def mon():
    while True:
        time.sleep(2)
        with main._FRAME_LOCK:
            n = len(main._FRAMES)
            last = main._FRAMES[-1][0] if n else 0.0
            first = main._FRAMES[0][0] if n else 0.0
        print(f"[MON] frames={n} span={(last-first):.2f}s", flush=True)

threading.Thread(target=mon, daemon=True).start()
main.main()
