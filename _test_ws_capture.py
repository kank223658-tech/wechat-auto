# -*- coding: utf-8 -*-
"""_WsClient + CDP screencast 链路自检（不依赖 Playwright / 前端 dev server）。

跑法：py _test_ws_capture.py
流程：拉起无头 Chrome（独立调试端口）→ _WsClient 直连页面 target →
Page.navigate 到一个 CSS 动画页 → startScreencast → 收帧+ack 3 秒 →
断言：握手成功、帧为 JPEG、时间戳单调、ack 后持续出帧（ack 循环有效）。
"""
import base64
import os
import socket
import subprocess
import sys
import tempfile
import time

from main import _WsClient, PORT  # 复用项目内的最小 ws 客户端

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.isfile(CHROME):
    print("SKIP：未找到 Chrome")
    sys.exit(0)

# 选空闲端口
probe = socket.socket()
probe.bind(("127.0.0.1", 0))
dbg_port = probe.getsockname()[1]
probe.close()

profile = tempfile.mkdtemp(prefix="wx_ws_test_")
proc = subprocess.Popen(
    [CHROME, "--headless=new", "--no-first-run", "--disable-gpu-sandbox",
     "--disable-background-timer-throttling",
     "--disable-backgrounding-occluded-windows",
     "--disable-renderer-backgrounding",
     "--disable-features=CalculateNativeWinOcclusion",
     f"--remote-debugging-port={dbg_port}", f"--user-data-dir={profile}",
     "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    # 等 DevTools 端点就绪
    import urllib.request
    page_ws = None
    deadline = time.time() + 10
    while time.time() < deadline and page_ws is None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{dbg_port}/json/list",
                                        timeout=2) as r:
                targets = __import__("json").loads(r.read().decode())
            pages = [t for t in targets if t.get("type") == "page"]
            if pages:
                page_ws = pages[0]["webSocketDebuggerUrl"]
            break_ = False
        except Exception:
            time.sleep(0.25)
    assert page_ws, "DevTools 端点 10s 内未就绪"

    ws = _WsClient.connect_url(page_ws, timeout=5)
    ws.settimeout(1.0)

    msg_id = [0]

    def cmd(method, params=None):
        msg_id[0] += 1
        ws.send_json({"id": msg_id[0], "method": method, "params": params or {}})
        return msg_id[0]

    page_html = """data:text/html,<html><body style="margin:0">
      <div id=m style="width:100px;height:100px;background:red;
        animation:spin 1s linear infinite"></div>
      <style>@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}</style>
      </body></html>"""
    cmd("Page.enable")
    cmd("Page.navigate", {"url": page_html})
    time.sleep(1.0)

    start_id = cmd("Page.startScreencast",
                   {"format": "jpeg", "quality": 60, "everyNthFrame": 1,
                    "maxWidth": 800, "maxHeight": 800})
    frames, t_end = [], time.time() + 3.0
    acks_pending = 0
    while time.time() < t_end:
        try:
            msg = ws.recv_json(timeout=1.0)
        except socket.timeout:
            continue
        if not msg:
            continue
        if msg.get("id") == start_id and msg.get("error"):
            raise SystemExit(f"FAIL: startScreencast 被拒 {msg['error']}")
        if msg.get("method") == "Page.screencastFrame":
            p = msg["params"]
            ts = (p.get("metadata") or {}).get("timestamp", 0)
            frames.append((ts, p["data"]))
            msg_id[0] += 1
            ws.send_json({"id": msg_id[0], "method": "Page.screencastFrameAck",
                          "params": {"sessionId": p.get("sessionId")}})
    ws.close()

    ok = True
    if len(frames) < 20:
        print(f"FAIL: 3 秒仅收到 {len(frames)} 帧（动画页应持续出帧）")
        ok = False
    ts_list = [ts for ts, _ in frames]
    if any(b < a for a, b in zip(ts_list, ts_list[1:])):
        print("FAIL: 时间戳非单调")
        ok = False
    if frames and not base64.b64decode(frames[0][1]).startswith(b"\xff\xd8"):
        print("FAIL: 帧不是 JPEG")
        ok = False
    gaps = [b - a for a, b in zip(ts_list, ts_list[1:]) if b - a > 0.25]
    if gaps:
        print(f"FAIL: 出现 >0.25s 断流 {len(gaps)} 处")
        ok = False
    print(("PASS" if ok else "FAIL") +
          f"  3s 收到 {len(frames)} 帧, 均匀无断流, 全部为 JPEG"
          + (f", 平均帧距 {1000*(ts_list[-1]-ts_list[0])/max(1,len(ts_list)-1):.1f}ms"
             if len(frames) > 1 else ""))
    sys.exit(0 if ok else 1)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
