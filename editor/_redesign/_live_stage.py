# -*- coding: utf-8 -*-
"""
场景编辑器「主手机画面 = 真机实时画面」改造（2026-09-11）

背景：scene.html 里那台手机是另写的一份 HTML 静态复刻，既跟不上 vue-WeChat
（真正产出成品视频的那套 UI）的更新，也点不动。真实渲染器其实早就存在：
main.py --editmode 会把真正的页面打开、注入 enhance 层，并通过 8001 端口
暴露 /shot.jpeg（真帧，与成片同源）+ /api/tap（把点击真实打进页面）。

本次改造：
  1) main.py 的实时指令队列新增 scene / scroll / back 三条命令
     —— 让编辑器能把「当前正在编辑的场景」推给真机、能滚动、能返回。
  2) main.py 编辑模式启动时支持 --scene，一进来就是场景编辑器的内容。
  3) editor_server.py 启动编辑模式时自动带上 --scene scene.json。
  4) scene.html 主舞台手机改为「真机画面」为默认视图（可点击操作、
     滚轮滚动真机、可点选改文字），静态复刻降级为「示意稿」兜底。

铁律：全部精确锚点替换，命中次数 != 1 立即中止。
"""
import io
import sys

ROOT = "G:/weixin-auto"


def patch(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for name, old, new in pairs:
        n = s.count(old)
        if n != 1:
            print("!! 锚点命中 %d 次（应为 1）：%s @ %s" % (n, name, path))
            sys.exit(1)
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(s)
    print("OK  %s  (%d 处)" % (path, len(pairs)))


# ============================================================
# 一、main.py —— 实时指令队列 + 编辑模式套用场景
# ============================================================
MAIN_CMD_OLD = """                elif cmd == "type":
                    self.page.keyboard.type(str(args.get("text", "")))
                    result = {"ok": True}
                else:
                    result = {"ok": False, "msg": "未知命令：" + str(cmd)}
            except Exception as exc:                # noqa: BLE001
                result = {"ok": False, "msg": str(exc)}
            with _LIVE_LOCK:
                _LIVE_RESULTS[cid] = result
            if cmd in ("edit", "tap", "type"):
                self._grab_frame(True)"""

MAIN_CMD_NEW = """                elif cmd == "type":
                    self.page.keyboard.type(str(args.get("text", "")))
                    result = {"ok": True}
                elif cmd == "scroll":
                    # 编辑器里在真机画面上滚轮 = 滚动真机页面（朋友圈/会话列表/长图）
                    self.page.mouse.move(float(args.get("x", 300)), float(args.get("y", 650)))
                    self.page.mouse.wheel(int(args.get("dx", 0) or 0),
                                          int(args.get("dy", 0) or 0))
                    _pump_wait(0.12)
                    result = {"ok": True}
                elif cmd == "back":
                    # 真机返回上一页（等价于点左上角返回箭头）
                    try:
                        self.page.go_back()
                    except Exception:                   # noqa: BLE001
                        pass
                    _pump_wait(0.35)
                    result = {"ok": True}
                elif cmd == "scene":
                    # 把场景编辑器里正在编辑的场景整体推给真机画面：
                    # 「我的资料 + 会话列表(含历史消息) + 朋友圈 + 对方主页」一步到位。
                    sc = args.get("scene")
                    if not isinstance(sc, dict):
                        result = {"ok": False, "msg": "场景数据格式不对"}
                    else:
                        result = {"ok": bool(self.apply_scene(sc))}
                else:
                    result = {"ok": False, "msg": "未知命令：" + str(cmd)}
            except Exception as exc:                # noqa: BLE001
                result = {"ok": False, "msg": str(exc)}
            with _LIVE_LOCK:
                _LIVE_RESULTS[cid] = result
            if cmd in ("edit", "tap", "type", "scroll", "back", "scene"):
                self._grab_frame(True)"""

MAIN_ROUTE_OLD = """        if path == "/api/quit":
            _STOP_EDIT.set()
            return self._json(200, {"ok": True})
        return self._json(404, {"ok": False, "msg": "not found"})"""

MAIN_ROUTE_NEW = """        if path == "/api/scene":
            # 场景编辑器把当前场景推给真机画面（body 可以是 {scene:{...}}，也可以是场景本身）
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                return self._json(400, {"ok": False, "msg": "JSON 解析失败"})
            if not isinstance(payload, dict):
                return self._json(400, {"ok": False, "msg": "场景数据格式不对"})
            scene = payload.get("scene") if isinstance(payload.get("scene"), dict) else payload
            return self._json(200, _live_dispatch("scene", {"scene": scene}))
        if path == "/api/scroll":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                payload["x"] = float(payload.get("x", 300))
                payload["y"] = float(payload.get("y", 650))
                payload["dy"] = int(payload.get("dy", 0) or 0)
                payload["dx"] = int(payload.get("dx", 0) or 0)
            except (TypeError, ValueError):
                return self._json(400, {"ok": False, "msg": "滚动参数错误"})
            return self._json(200, _live_dispatch("scroll", payload))
        if path == "/api/back":
            return self._json(200, _live_dispatch("back", {}))
        if path == "/api/quit":
            _STOP_EDIT.set()
            return self._json(200, {"ok": True})
        return self._json(404, {"ok": False, "msg": "not found"})"""

MAIN_DOC_OLD = """       POST /api/type              -> 向当前聚焦输入框打字
       POST /api/quit              -> 让编辑模式进程退出"""

MAIN_DOC_NEW = """       POST /api/type              -> 向当前聚焦输入框打字
       POST /api/scroll            -> 滚动真机页面（编辑器滚轮穿透）
       POST /api/back              -> 真机返回上一页
       POST /api/scene             -> 把场景编辑器当前场景整体推给真机
       POST /api/quit              -> 让编辑模式进程退出"""

MAIN_EDIT_OLD = """            ensure_frontend_running()
            bot.start()
            print("[编辑模式] 已就绪：编辑器里点击画面可导航，切换「编辑」可修改元素。", flush=True)"""

MAIN_EDIT_NEW = """            ensure_frontend_running()
            bot.start()
            # 编辑模式一进来就套用场景编辑器保存的场景，保证「编辑器里看到的 == 最终视频里的」
            if args.scene:
                _sp_edit = args.scene if os.path.isfile(args.scene) else \\
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), args.scene)
                if os.path.isfile(_sp_edit):
                    try:
                        bot.apply_scene(_sp_edit)
                        print(f"[编辑模式] 已套用场景编辑器的场景：{_sp_edit}", flush=True)
                    except Exception as _exc:           # noqa: BLE001
                        print(f"[编辑模式] 套用场景失败（不影响使用）：{_exc}", flush=True)
            print("[编辑模式] 已就绪：编辑器里点击画面可导航，切换「编辑」可修改元素。", flush=True)"""

patch(ROOT + "/main.py", [
    ("live-queue", MAIN_CMD_OLD, MAIN_CMD_NEW),
    ("live-routes", MAIN_ROUTE_OLD, MAIN_ROUTE_NEW),
    ("live-docstring", MAIN_DOC_OLD, MAIN_DOC_NEW),
    ("editmode-scene", MAIN_EDIT_OLD, MAIN_EDIT_NEW),
])

# ============================================================
# 二、editor_server.py —— 编辑模式启动时带上场景
# ============================================================
SRV_OLD = """        cmd = [sys.executable, os.path.join(ROOT, "main.py"),
               "--editmode", "--headless", "--liveport", str(LIVE_PORT)]
        log_fh = open(EDIT_LOG, "w", encoding="utf-8", errors="replace")"""

SRV_NEW = """        cmd = [sys.executable, os.path.join(ROOT, "main.py"),
               "--editmode", "--headless", "--liveport", str(LIVE_PORT)]
        # 真机画面默认套用「场景编辑器」当前保存的场景，
        # 让编辑器左边看到的画面就是最终视频里的画面（我的资料/会话/朋友圈）。
        try:
            _sc_edit = _read_scene()
        except Exception:                           # noqa: BLE001
            _sc_edit = None
        if _sc_edit and (_sc_edit.get("home") or _sc_edit.get("me")
                         or _sc_edit.get("moments") or _sc_edit.get("peer")):
            if os.path.isfile(SCENE_PATH):
                cmd += ["--scene", SCENE_PATH]
                print(f"[编辑模式] 将套用场景：{SCENE_PATH}", flush=True)
        log_fh = open(EDIT_LOG, "w", encoding="utf-8", errors="replace")"""

patch(ROOT + "/editor_server.py", [
    ("editmode-scene-arg", SRV_OLD, SRV_NEW),
])
print("main.py / editor_server.py 完成")
