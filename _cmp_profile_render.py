# -*- coding: utf-8 -*-
"""渲染「对方个人主页」与参考图对齐用的截图。

用法: py _cmp_profile_render.py
输出: _cmp_ref_home/ours.png (600x1300)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import main as M

M.FRAME_CAPTURE_ENABLED = False
M.ENABLE_AUDIO = False
M.ENABLE_BGM = False
M.SPEED = 2.0

OUT = os.path.join(BASE, "_cmp_ref_home")
os.makedirs(OUT, exist_ok=True)

IMG0 = "/images/avatar/2_20260831_184618_874.jpg"
AVATAR = "/images/avatar/30_女人_1_金善慧Keina_来自小红书网页版_20260831_184614_096.jpg"

SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "月亮", "lastText": "", "unread": 0, "messages": []}],
    "moments": [
        {"author": "月亮🌙", "text": "测试联动", "images": ["/images/peer/peer_p1.jpg", "/images/peer/peer_p2.jpg", "/images/peer/peer_p3.jpg"], "time": "1小时前"},
    ],
    "peer": {
        "name": "月亮🌙",
        "wxid": "David-011231",
        "area": "",
        "nickname": "人事主管张小姐",
        "gender": 0,
        "avatar": AVATAR,
        "momentsThumbs": [
            "/images/peer/peer_m1.jpg",
            "/images/peer/peer_m2.jpg",
            "/images/peer/peer_m3.jpg",
            "/images/peer/peer_m4.jpg",
            "/images/peer/peer_m5.jpg",
        ],
        "video": None,
        "posts": [],
    },
}


def main():
    print("[1] 起真机实例…")
    M.ensure_frontend_running()
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        M._pump_wait(1.0)
        page = bot.page
        bot.apply_scene(SCENE)
        M._pump_wait(0.8)
        # 直接用页面 API 打开对方主页（渲染对比用，与真人点头像后的页面完全一致）
        page.evaluate("""() => {
            document.body.classList.add('wx-peer-no-blur');  // 对照时临时清晰（默认仍模糊）
            window.__wxPeer.openProfile();
        }""")
        M._pump_wait(1.5)  # 等滑入动画彻底结束
        srcs = page.evaluate("() => Array.from(document.querySelectorAll('.wpp-moments-cell .wpp-thumbs img')).map(i => i.getAttribute('src'))")
        print("[thumbs]", srcs)
        page.screenshot(path=os.path.join(OUT, "ours.png"))
        # 默认态（无 wx-peer-no-blur）：验证录制时微信号/昵称/地区自动打码
        page.evaluate("() => document.body.classList.remove('wx-peer-no-blur')")
        M._pump_wait(0.4)
        page.screenshot(path=os.path.join(OUT, "ours_blur.png"))
        print("[2] 已截图 -> ours.png + ours_blur.png")
        return 0
    finally:
        try:
            bot.stop()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
