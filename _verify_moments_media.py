# -*- coding: utf-8 -*-
"""临时验证工具：走 main.py 的真实运行路径，验证「脚本模式」下
   [进入朋友圈] → [向下滚动] → [播放视频] / [点开图片] 是否真的能打开。

关键手法：执行 [播放视频]/[点开图片] 期间，临时把「关闭播放器 / 关闭图片查看器」
替换成空操作（verify patch），这样动作结束后覆盖层仍在，才观测得到真实打开状态；
观测完再还原并真关。

用法:
    py _verify_moments_media.py
产物:
    _shot/verify_*.png      各阶段截图
    控制台 JSON 报告
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import main as M

# 关掉录音/配乐/逐帧合成：只验证交互，不为出片
M.FRAME_CAPTURE_ENABLED = False
M.ENABLE_AUDIO = False
M.ENABLE_BGM = False
M.TRIM_HEAD_SEC = 0
M.SPEED = 3.0            # 加速，验证不等真人节奏

OUT = os.path.join(BASE, "_shot")
os.makedirs(OUT, exist_ok=True)

VIDEO0 = "/videos/_test.mp4"
IMG0 = "/images/avatar/2_20260831_184618_874.jpg"

SCENE = {
    "me": {"name": "小星", "avatar": IMG0, "bg": IMG0},
    "home": [{"name": "文件传输助手", "lastText": "", "unread": 0, "messages": []}],
    "moments": [
        {   # 第 1 条：视频动态（企业来源，验证金色 @公司名 + 视频角标）
            "author": "小星", "avatar": IMG0, "company": "微盛企微管家",
            "text": "随手拍的一段。",
            "video": {"src": VIDEO0, "cover": IMG0},
            "time": "5分钟前", "likes": ["月亮"], "comments": [{"name": "月亮", "text": "不错"}],
        },
        {   # 第 2 条：多图动态
            "author": "铁木君", "avatar": IMG0,
            "text": "今天天气很好，出来走走。\n顺便记录一下。",
            "images": [IMG0, IMG0],
            "time": "1小时前", "likes": [], "comments": [],
        },
    ],
}

report = {"steps": [], "video": {}, "image": {}, "errors": []}

# 冻结「关闭」动作，便于动作结束后观测覆盖层
PATCH_ON = """() => {
    if (window.__wxVideo && !window.__wxVideo._vcFrozen) {
        window.__wxVideo._vcRealClose = window.__wxVideo.close;
        window.__wxVideo.close = function () { return true; };
        window.__wxVideo._vcFrozen = true;
    }
    if (window.__wxMoments && !window.__wxMoments._vcFrozen) {
        window.__wxMoments._vcRealCloseImage = window.__wxMoments.closeImage;
        window.__wxMoments.closeImage = function () { return true; };
        window.__wxMoments._vcFrozen = true;
    }
    if (window.__wxHuman && !window.__wxHuman._vcFrozen) {
        window.__wxHuman._vcRealCloseImage = window.__wxHuman.closeImage;
        window.__wxHuman.closeImage = function () { return true; };
        window.__wxHuman._vcFrozen = true;
    }
}"""

PATCH_OFF = """() => {
    if (window.__wxVideo && window.__wxVideo._vcFrozen) {
        window.__wxVideo.close = window.__wxVideo._vcRealClose;
        window.__wxVideo._vcFrozen = false;
        window.__wxVideo.close();
    }
    if (window.__wxMoments && window.__wxMoments._vcFrozen) {
        window.__wxMoments.closeImage = window.__wxMoments._vcRealCloseImage;
        window.__wxMoments._vcFrozen = false;
        window.__wxMoments.closeImage();
    }
    if (window.__wxHuman && window.__wxHuman._vcFrozen) {
        window.__wxHuman.closeImage = window.__wxHuman._vcRealCloseImage;
        window.__wxHuman._vcFrozen = false;
    }
    const iv = document.getElementById('imageViewer');
    if (iv) { iv.classList.remove('iv-open', 'iv-visible'); iv.style.display = 'none'; }
}"""


def snap(page, name):
    p = os.path.join(OUT, "verify_%s.png" % name)
    try:
        page.screenshot(path=p)
        print("      截图:", os.path.relpath(p, BASE))
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("screenshot %s: %s" % (name, e))
    return p


def do_step(bot, action, params, tag):
    try:
        M.execute_step(bot, action, params)
        report["steps"].append({"action": action, "params": params, "ok": True})
        print("    ✓ %s %s" % (action, params))
        return True
    except Exception as e:                                   # noqa: BLE001
        report["steps"].append({"action": action, "params": params, "ok": False, "err": str(e)})
        report["errors"].append("%s: %s" % (action, e))
        print("    ✗ %s %s -> %s" % (action, params, e))
        snap(bot.page, tag + "_FAIL")
        return False


def main():
    print("[1] 确保前端在跑…")
    M.ensure_frontend_running()

    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        M._pump_wait(1.0)
        page = bot.page

        print("[2] 应用场景（视频动态 + 多图动态）…")
        bot.apply_scene(SCENE)
        M._pump_wait(0.8)

        print("[3] [进入朋友圈]…")
        if not do_step(bot, "进入朋友圈", {}, "0_enter"):
            return 1
        info = page.evaluate("""() => ({
            hasMoments: !!document.getElementById('moments'),
            posts: document.querySelectorAll('#moments .moments__post').length,
            videoThumbs: document.querySelectorAll('#moments [data-wx-video-src]').length,
            imageFigs: document.querySelectorAll('#moments .my-gallery .thumbnail:not(.video-thumb)').length,
            hasPlayer: !!window.__wxVideo,
            company: (() => { const c = document.querySelector('#moments .post-company');
                              return c ? c.textContent : ''; })(),
        })""")
        report["momentsDom"] = info
        print("      DOM:", json.dumps(info, ensure_ascii=False))
        snap(page, "1_moments")

        # 冻结关闭动作，便于观测
        page.evaluate(PATCH_ON)

        print("[4] [向下滚动 240]…")
        do_step(bot, "向下滚动", {"像素": 240}, "1_scroll")

        print("[5] [播放视频 序号=1]（观测播放器真实状态）…")
        if do_step(bot, "播放视频", {"序号": 1}, "2_video"):
            try:
                page.wait_for_function(
                    "() => { const v = document.querySelector('#wxVideoPlayer video');"
                    " return !!(v && v.readyState >= 1 && v.duration > 0); }",
                    timeout=5000)
            except Exception:                                # noqa: BLE001
                pass
            v1 = page.evaluate("""() => {
                const v = document.querySelector('#wxVideoPlayer video');
                const root = document.getElementById('wxVideoPlayer');
                return {
                    open: !!(window.__wxVideo && window.__wxVideo.isOpen()),
                    hasVideoEl: !!v,
                    src: v ? (v.currentSrc || v.src || '') : '',
                    readyState: v ? v.readyState : -1,
                    duration: v ? (v.duration || 0) : 0,
                    currentTime: v ? (v.currentTime || 0) : 0,
                    paused: v ? v.paused : null,
                    errorCode: v && v.error ? v.error.code : 0,
                    errorMsg: v && v.error ? (v.error.message || '') : '',
                    rootOpen: !!root && root.classList.contains('wv-open'),
                    progressWidth: (() => { const f = root && root.querySelector('.wv-fill');
                                            return f ? f.style.width : ''; })(),
                    durLabel: (() => { const d = root && root.querySelector('.wv-dur');
                                       return d ? d.textContent : ''; })(),
                };
            }""")
            snap(page, "3_video_open")
            page.wait_for_timeout(1500)
            v2 = page.evaluate("""() => {
                const v = document.querySelector('#wxVideoPlayer video');
                const root = document.getElementById('wxVideoPlayer');
                return { currentTime: v ? (v.currentTime || 0) : 0,
                         paused: v ? v.paused : null,
                         progressWidth: (() => { const f = root && root.querySelector('.wv-fill');
                                                 return f ? f.style.width : ''; })() };
            }""")
            v1["currentTimeAfter1_5s"] = v2["currentTime"]
            v1["progressAfter1_5s"] = v2["progressWidth"]
            v1["advanced"] = bool(v2["currentTime"] > v1["currentTime"] + 0.05)
            report["video"] = v1
            print("      视频:", json.dumps(v1, ensure_ascii=False))
            snap(page, "4_video_playing")

        # 还原并真关播放器，再验证图片
        page.evaluate(PATCH_OFF)
        page.wait_for_timeout(500)

        print("[6] [点开图片 序号=2]（观测图片查看器真实状态）…")
        page.evaluate(PATCH_ON)
        if do_step(bot, "点开图片", {"序号": "2"}, "5_image"):
            page.wait_for_timeout(900)
            img = page.evaluate("""() => ({
                pswpOpen: !!document.querySelector('.pswp--open'),
                pswpClass: (() => { const p = document.querySelector('.pswp'); return p ? p.className : ''; })(),
                pswpImg: (() => { const i = document.querySelector('.pswp--open img.pswp__img');
                                  return i ? (i.currentSrc || i.src || '') : ''; })(),
                humanOpen: !!(window.__wxHuman && window.__wxHuman.isImageOpen
                              && window.__wxHuman.isImageOpen()),
                anyViewer: !!document.querySelector('#imageViewer.iv-open'),
            })""")
            report["image"] = img
            print("      图片:", json.dumps(img, ensure_ascii=False))
            snap(page, "5_image_open")
        page.evaluate(PATCH_OFF)
        page.wait_for_timeout(400)

        print("[7] [闪回聊天]…")
        try:
            bot.flash_back_to_chat()
            print("    ✓ 闪回聊天 OK")
        except Exception as e:                               # noqa: BLE001
            report["errors"].append("闪回聊天: %s" % e)
            print("    ✗ 闪回聊天 ->", e)

    finally:
        try:
            bot.stop()
        except Exception as e:                               # noqa: BLE001
            report["errors"].append("stop: %s" % e)

    v = report.get("video") or {}
    i = report.get("image") or {}
    d = report.get("momentsDom") or {}
    ok_dom = bool(d.get("posts") == 2 and d.get("videoThumbs") == 1 and d.get("imageFigs") == 2)
    ok_video = bool(v.get("open") and v.get("duration", 0) > 0 and v.get("advanced"))
    ok_image = bool(i.get("pswpOpen") or i.get("humanOpen") or i.get("anyViewer"))

    print("\n=== 结论 ===")
    print("场景铺到朋友圈 DOM:", "✅" if ok_dom else "❌", json.dumps(d, ensure_ascii=False))
    print("视频能在脚本里打开并播放:", "✅" if ok_video else "❌")
    print("图片能在脚本里点开:", "✅" if ok_image else "❌")
    if report["errors"]:
        print("错误:", report["errors"])
    print("\n=== 详细报告 ===")
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return 0 if (ok_dom and ok_video and ok_image) else 1


if __name__ == "__main__":
    sys.exit(main())
