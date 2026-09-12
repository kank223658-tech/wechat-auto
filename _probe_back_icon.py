# -*- coding: utf-8 -*-
"""抓朋友圈头部左上角返回箭头的放大图（修正 y 坐标）+ DOM 信息。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import main as M

M.FRAME_CAPTURE_ENABLED = False
M.ENABLE_AUDIO = False
M.ENABLE_BGM = False
M.SPEED = 3.0

OUT = os.path.join(BASE, "_shot")
os.makedirs(OUT, exist_ok=True)

IMG0 = "/images/avatar/2_20260831_184618_874.jpg"
SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "阿月", "lastText": "", "unread": 0, "messages": []}],
}


def main():
    M.ensure_frontend_running()
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        M._pump_wait(1.0)
        bot.apply_scene(SCENE)
        M._pump_wait(0.8)
        M.execute_step(bot, "切换Tab", {"Tab": "发现"})
        M._pump_wait(0.5)
        M.execute_step(bot, "进入朋友圈", {})
        M._pump_wait(1.0)
        info = bot.page.evaluate(
            """() => {
                const el = document.querySelector('#moments .icon-return-arrow')
                    || document.querySelector('.icon-return-arrow');
                const out = { hash: location.hash };
                if (el) {
                    const r = el.getBoundingClientRect();
                    const cs = getComputedStyle(el);
                    out.rect = { x: r.x, y: r.y, w: r.width, h: r.height };
                    out.font = { family: cs.fontFamily, size: cs.fontSize, color: cs.color };
                    out.outer = el.outerHTML.slice(0, 200);
                }
                const hdr = document.querySelector('#moments #wx-header, #wx-header');
                if (hdr) out.headerHtml = hdr.outerHTML.slice(0, 400);
                return out;
            }""")
        import json as _j
        print(_j.dumps(info, ensure_ascii=False, indent=1))
        bot.page.screenshot(path=os.path.join(OUT, "mom_hdr2.png"),
                            clip={"x": 0, "y": 80, "width": 300, "height": 100})
        bot.page.screenshot(path=os.path.join(OUT, "mom_hdr2_zoom.png"),
                            clip={"x": 10, "y": 90, "width": 80, "height": 60})
        print("saved mom_hdr2.png / mom_hdr2_zoom.png")
        return 0
    finally:
        try:
            bot.stop()
        except Exception:                                    # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
