# -*- coding: utf-8 -*-
"""把「真实前端」同源嵌进场景编辑器：服务端反代 + 注入，前端换视图。

背景：scene.html 里那台手机是手写复刻，永远追不上 vue-WeChat 的真实 UI。
方案：editor_server 反代 8080（vue-WeChat dev server，publicPath './' 全是相对路径，
可整体挂到任意前缀），HTML 里注入 /enhance/_embed_boot.js 在浏览器内跑
main.py inject_overlays() 的同一套注入。实测与真机帧逐像素平均差 1.44/255。
"""
import io
import sys

ROOT = r"G:\weixin-auto"
SERVER = ROOT + r"\editor_server.py"
SCENE = ROOT + r"\editor\scene.html"

hits = []


def patch(path, pairs, allow=1):
    s = io.open(path, encoding="utf-8").read()
    out = s
    for old, new in pairs:
        n = out.count(old)
        if n != allow:
            print("!! 锚点命中 %d 次（期望 %d）：%s" % (n, allow, old[:90].replace("\n", "\\n")))
            sys.exit(1)
        out = out.replace(old, new, 1)
        hits.append(old[:60].replace("\n", "\\n"))
    io.open(path, "w", encoding="utf-8", newline="").write(out)
    print("OK %s（%d 处）" % (path, len(pairs)))


# ============================================================
# 一、editor_server.py
# ============================================================

SRV_HELPERS = '''
# ---- 实时预览渲染器（vue-WeChat dev server）-----------------------------
# 编辑器左栏的「实时预览」直接同源嵌真实前端，不再手写复刻。
# vue-WeChat/vue.config.js 里 publicPath: './'，所有资源都是相对路径，
# 因此可以把 8080 整体挂到 /wxpv/ 前缀下（hash 路由 base 为 /vue-wechat/ 时
# 也不会乱跳，已实测）。HTML 里注入 /enhance/_embed_boot.js，在浏览器内按
# main.py::inject_overlays() 的同一顺序注入 enhance 层，得到与成片逐像素同源的画面。
FRONTEND_PORT = 8080
FRONTEND_DIR = os.path.join(ROOT, "vue-WeChat")
BUNDLED_NODE_DIR = os.path.join(ROOT, "tools", "node-v20.19.4-win-x64")
PV_PREFIX = "/wxpv/"
PV_BOOT_TAG = '<script src="/enhance/_embed_boot.js"></script>'
_frontend_proc = None
_frontend_lock = threading.Lock()


def _frontend_ready(timeout=1.5):
    """预览渲染器是否真的能出页面（仅端口开着不算：编译中会返回错误页）。"""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", FRONTEND_PORT, timeout=timeout)
        conn.request("GET", "/", headers={"Accept-Encoding": "identity"})
        resp = conn.getresponse()
        ok = resp.status == 200 and "text/html" in (resp.getheader("Content-Type") or "")
        resp.read()
        return ok
    except OSError:
        return False
    except Exception:                            # noqa: BLE001
        return False


def _start_frontend():
    """启动 vue-WeChat dev server（后台，不阻塞请求）。返回 (ok, msg)。"""
    global _frontend_proc
    with _frontend_lock:
        if _frontend_ready():
            return False, "预览渲染器已在运行。"
        if _frontend_proc and _frontend_proc.poll() is None:
            return False, "预览渲染器正在启动中，请稍候……"
        if not os.path.isdir(FRONTEND_DIR):
            return False, "找不到前端项目目录：%s" % FRONTEND_DIR
        node_dir = BUNDLED_NODE_DIR if os.path.isfile(
            os.path.join(BUNDLED_NODE_DIR, "npm.cmd")) else None
        env = os.environ.copy()
        if node_dir:
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
            npm_cmd = os.path.join(node_dir, "npm.cmd")
        else:
            npm_cmd = ""
            for d in env.get("PATH", "").split(os.pathsep):
                cand = os.path.join(d, "npm.cmd")
                if os.path.isfile(cand):
                    npm_cmd = cand
                    break
            if not npm_cmd:
                return False, "未找到可用的 npm / node，无法启动预览渲染器。"
        env["NODE_OPTIONS"] = "--openssl-legacy-provider"
        try:
            log_fh = open(os.path.join(FRONTEND_DIR, "dev-server.log"), "a",
                          encoding="utf-8", errors="replace")
            _frontend_proc = subprocess.Popen(
                [npm_cmd, "run", "dev"], cwd=FRONTEND_DIR, env=env,
                stdout=log_fh, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            return False, "启动失败：%s" % exc
        return True, "正在启动预览渲染器（首次编译约 20~60 秒）……"

'''

SRV_METHOD = '''    def _proxy_frontend(self):
        """把 /wxpv/* 反代到 vue-WeChat dev server，并在 HTML 里注入 enhance 引导层。

        真实前端的资源都是相对路径，因此整体挂到 /wxpv/ 前缀下即可正常工作；
        注入 _embed_boot.js 后，页面上呈现的就是与成片同一套 UI（逐像素同源）。
        """
        raw = self.path.split("?", 1)
        rel = unquote(raw[0][len(PV_PREFIX):])
        upstream = "/" + rel + (("?" + raw[1]) if len(raw) > 1 else "")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", FRONTEND_PORT, timeout=25)
            conn.request("GET", upstream, headers={"Accept-Encoding": "identity",
                                                   "User-Agent": "editor-preview"})
            resp = conn.getresponse()
            status = resp.status
            ctype = resp.getheader("Content-Type", "") or ""
            cache = resp.getheader("Cache-Control", "")
            data = resp.read()
        except Exception as exc:                 # noqa: BLE001
            return _json_reply(self, 503, {"ok": False,
                                           "msg": "预览渲染器未运行：%s" % exc})
        if status == 200 and "text/html" in ctype:
            html = data.decode("utf-8", "replace")
            if "_embed_boot.js" not in html:
                if "</body>" in html:
                    html = html.replace("</body>", PV_BOOT_TAG + "</body>", 1)
                else:
                    html += PV_BOOT_TAG
            data = html.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

'''

patch(SERVER, [
    # 1) 常量 + 启动助手（紧跟 LIVE_PORT 之后）
    ("LIVE_PORT = 8001  # 运行子进程的「实时手机画面」服务端口（编辑器通过 /api/live 转发）\n",
     "LIVE_PORT = 8001  # 运行子进程的「实时手机画面」服务端口（编辑器通过 /api/live 转发）\n"
     + SRV_HELPERS),
    # 2) 反代方法（放在 _proxy_live 之前）
    ('    def _proxy_live(self, body: bytes = b""):',
     SRV_METHOD + '    def _proxy_live(self, body: bytes = b""):'),
    # 3) GET 路由
    ('''        if self.path.startswith("/api/live"):
            # 转发到运行子进程/编辑模式的实时画面服务
            return self._proxy_live()
''',
     '''        if self.path.startswith("/api/live"):
            # 转发到运行子进程/编辑模式的实时画面服务
            return self._proxy_live()
        if self.path.startswith(PV_PREFIX):
            # 实时预览：同源反代真实前端并注入 enhance 引导层
            return self._proxy_frontend()
        if self.path == "/api/wxapp/status":
            return _json_reply(self, 200, {
                "ok": True,
                "up": _frontend_ready(),
                "starting": bool(_frontend_proc and _frontend_proc.poll() is None)})
'''),
    # 4) POST 路由
    ('''    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.path == "/api/workflow":''',
     '''    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.path == "/api/wxapp/start":
            ok, msg = _start_frontend()
            return _json_reply(self, 200, {"ok": ok, "msg": msg, "up": _frontend_ready()})
        if self.path == "/api/workflow":'''),
])

print("服务端 %d 处锚点全部命中" % len(hits))
