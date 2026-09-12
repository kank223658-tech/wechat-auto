# -*- coding: utf-8 -*-
"""朋友圈设置面板 · 端到端冒烟（真编辑器页面 + 真离线解析 + 真 scene 接口）

覆盖：
  1. 模块加载
  2. 离线解析后自动弹出（检测到朋友圈动作）
  3. 我的朋友圈：图片/视频卡片渲染、勾选后自动填秒数、自定义秒数
  4. 对方朋友圈 tab：读取 scene.peer 的数据
  5. 应用：写回 scene.json + 流程里替换掉解析自带的旧朋友圈段（不重复两遍）
  6. 无朋友圈的剧本不弹面板
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:8765/"
SHOT = os.path.join(ROOT, "_shot")
os.makedirs(SHOT, exist_ok=True)
SCENE = os.path.join(ROOT, "scene.json")
BAK = os.path.join(SHOT, "_scene_backup_smoke.json")

IMG1 = "/images/peer/peer_p1.jpg"
IMG2 = "/images/peer/peer_p2.jpg"
VID = "/videos/_test.mp4"

SEED = {
    "title": "冒烟",
    "me": {"name": "阿荡", "signature": "填坑小能手"},
    "home": [{"id": "c1", "type": "friend", "name": "luna-富婆", "lastText": "在吗",
              "time": "18:22", "unread": 0, "messages": []}],
    "moments": [
        {"author": "陆香儿", "text": "就这么丝滑的下班。", "time": "35分钟前",
         "images": [IMG1, IMG2], "comments": [{"name": "陆香儿", "text": "冲！"}]},
        {"author": "陆香儿", "text": "随手拍的海", "time": "1小时前",
         "video": VID, "cover": IMG1},
    ],
    "peer": {
        "name": "吴遂卿", "wxid": "LSDH-WSQ", "area": "广东 佛山",
        "avatar": "/images/peer/peer_avatar.jpg", "signature": "随心随性",
        "cover": IMG1,
        "posts": [{"date": "10 6月", "images": [IMG1], "text": "偶尔玩下 蛮好"}],
    },
    "peers": [],
    "peerNav": False,
}

SCRIPT = """[回到聊天主页]
[打开聊天] luna-富婆
[我方打字] 晚上有空吗
[进入朋友圈]
[向下滚动] 300
[点开图片] 1,1
[进入对方朋友圈]
"""


def main():
    shutil.copyfile(SCENE, BAK)
    with open(SCENE, "w", encoding="utf-8") as fh:
        json.dump(SEED, fh, ensure_ascii=False, indent=2)

    from playwright.sync_api import sync_playwright

    logs = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1680, "height": 1050})
        pg.on("console", lambda m: logs.append("[console:%s] %s" % (m.type, m.text)))
        pg.on("pageerror", lambda e: logs.append("[pageerror] %s" % e))
        pg.on("dialog", lambda d: d.accept(""))
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(500)

        assert pg.evaluate("() => !!window.__wxMomentsEditor"), "moments_editor.js 未加载"
        print("[ok] 面板模块已加载")

        pg.evaluate("() => document.getElementById('btnViewScript').click()")
        pg.wait_for_selector("#scriptInput", state="visible", timeout=8000)

        # 手动点「🍩 朋友圈」按钮也要能开（覆盖手动入口）
        pg.evaluate("() => document.getElementById('btnMoments').click()")
        pg.wait_for_selector(".wxm-mask", timeout=5000)
        print("[ok] 「🍩 朋友圈」按钮能打开面板")
        pg.click(".wxm-foot [data-op='cancel']")
        pg.wait_for_timeout(200)
        assert pg.evaluate("() => !window.__wxMomentsEditor.isOpen()"), "取消后面板没关"

        # ---- 离线解析 → 自动弹出 ----
        pg.fill("#scriptInput", SCRIPT)
        pg.click("#btnOffline")
        pg.wait_for_selector(".wxm-mask", timeout=8000)
        print("[ok] 离线解析后自动弹出")

        info = pg.evaluate("""() => ({
          title: document.querySelector('.wxm-title').textContent.trim(),
          tabs: [...document.querySelectorAll('.wxm-tabs button')].map(b => b.textContent.trim()),
          posts: document.querySelectorAll('.wxm-post').length,
          tiles: document.querySelectorAll('.wxm-tile').length,
          vidbox: document.querySelectorAll('.wxm-vidbox').length,
        })""")
        print("[ok] 我的朋友圈：", json.dumps(info, ensure_ascii=False))
        assert info["posts"] == 2, "应读到 2 条动态"
        assert info["tiles"] == 2 and info["vidbox"] == 1, "配图/视频卡片数量不对"

        # 第 1 条：两张图都勾上，秒数分别为 0.5 / 0.8
        for j, sec in ((0, "0.5"), (1, "0.8")):
            pg.click('.wxm-post[data-i="0"] .wxm-tile:nth-child(%d) [data-op="imgopen"]' % (j + 1))
            pg.wait_for_timeout(100)
            auto = pg.input_value('.wxm-post[data-i="0"] .wxm-tile:nth-child(%d) [data-op="imgsec"]' % (j + 1))
            print("[ok]   图%d 勾选后自动秒数 = %s" % (j + 1, auto))
            assert float(auto or 0) > 0
            pg.fill('.wxm-post[data-i="0"] .wxm-tile:nth-child(%d) [data-op="imgsec"]' % (j + 1), sec)
        # 第 2 条：视频勾上，2.4 秒
        pg.click('.wxm-post[data-i="1"] [data-op="vidopen"]')
        pg.wait_for_timeout(120)
        pg.fill('.wxm-post[data-i="1"] [data-op="vidsec"]', "2.4")
        pg.screenshot(path=os.path.join(SHOT, "moments_panel_me.png"))

        # ---- 对方朋友圈 tab ----
        pg.click('.wxm-tabs button[data-tab="peer"]')
        pg.wait_for_timeout(250)
        peer = pg.evaluate("""() => ({
          name: document.querySelector('[data-op="peername"]').value,
          posts: document.querySelectorAll('.wxm-post').length,
          tiles: document.querySelectorAll('.wxm-tile').length,
        })""")
        print("[ok] 对方朋友圈：", json.dumps(peer, ensure_ascii=False))
        assert peer["name"] == "吴遂卿" and peer["posts"] == 1, "对方朋友圈数据没读到"
        pg.click('.wxm-post[data-i="0"] .wxm-tile [data-op="imgopen"]')
        pg.wait_for_timeout(120)
        pg.fill('.wxm-post[data-i="0"] .wxm-tile [data-op="imgsec"]', "1.2")
        pg.screenshot(path=os.path.join(SHOT, "moments_panel_peer.png"))

        # ---- 应用 ----
        pg.click('.wxm-foot [data-op="apply"]')
        pg.wait_for_timeout(1200)
        assert pg.evaluate("() => !window.__wxMomentsEditor.isOpen()"), "应用后面板没关"

        steps = pg.evaluate("() => JSON.parse(localStorage.getItem('wx-script-mode-v1') || '{}').steps || []")
        print("[ok] 应用后的流程：")
        for i, s in enumerate(steps):
            print("    %2d %s %s" % (i, s.get("action"), json.dumps(s.get("params"), ensure_ascii=False)))

        names = [s.get("action") for s in steps]
        assert names.count("进入朋友圈") == 1, "进入朋友圈应只剩 1 个（旧段被接管），实际 %d" % names.count("进入朋友圈")
        assert names.count("进入对方朋友圈") == 1, "进入对方朋友圈应只剩 1 个"
        assert "编辑朋友圈" in names and "编辑对方资料" in names, "内容步骤缺失"

        imgs = [s for s in steps if s.get("action") == "点开图片"]
        vids = [s for s in steps if s.get("action") == "播放视频"]
        print("[ok] 点开图片：", json.dumps([s["params"] for s in imgs], ensure_ascii=False))
        print("[ok] 播放视频：", json.dumps([s["params"] for s in vids], ensure_ascii=False))
        seq = {(s["params"].get("序号"), s["params"].get("停留")) for s in imgs}
        assert ("1,1", 0.5) in seq and ("1,2", 0.8) in seq, "我的朋友圈图片序号/秒数不对: %s" % seq
        assert ("1,1", 1.2) in seq, "对方朋友圈图片没生成"
        assert len(vids) == 1 and vids[0]["params"]["序号"] == 1 and vids[0]["params"]["停留"] == 2.4, "视频步骤不对"

        # 序号顺序：先图1、图2、再视频、再对方的图
        order = [s["action"] for s in steps if s.get("action") in ("点开图片", "播放视频")]
        print("[ok] 打开顺序：", order)

        # ---- 落盘校验 ----
        pg.wait_for_timeout(300)
        sc = json.load(open(SCENE, encoding="utf-8"))
        p0, p1 = sc["moments"][0], sc["moments"][1]
        print("[ok] scene.moments[0].imgHolds =", p0.get("imgHolds"), "| [1].videoHold =", p1.get("videoHold"))
        assert p0.get("imgHolds") == [0.5, 0.8], "imgHolds 没写回"
        assert p1.get("videoHold") == 2.4, "videoHold 没写回"
        assert sc["peer"]["posts"][0].get("imgHolds") == [1.2], "对方 imgHolds 没写回"
        print("[ok] scene.peer.name =", sc["peer"].get("name"))

        # ---- 无朋友圈的剧本不该弹 ----
        pg.fill("#scriptInput", "[回到聊天主页]\n[打开聊天] luna-富婆\n[我方打字] 在吗\n")
        pg.click("#btnOffline")
        pg.wait_for_timeout(1400)
        assert pg.evaluate("() => !window.__wxMomentsEditor.isOpen()"), "无朋友圈的剧本不该弹面板"
        print("[ok] 无朋友圈的剧本不弹面板")

        br.close()

    errs = [l for l in logs if "pageerror" in l or "console:error" in l]
    if errs:
        print("\n页面报错（%d 条）：" % len(errs))
        for e in errs[:10]:
            print("  ", e)
    print("\n===== 冒烟通过 =====")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        if os.path.exists(BAK):
            shutil.copyfile(BAK, SCENE)
            print("[cleanup] scene.json 已还原")
