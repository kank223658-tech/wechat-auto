"""原型验证服务器：把真实前端（8080 dev server）同源代理进 8002，并注入 enhance 层。

验证目标（不碰项目代码）：
  1) 真实前端的资源都是相对路径（publicPath './'），能否在任意路径前缀下正常工作；
  2) hash 路由 base='/vue-wechat/' 在 /vue-wechat/ 前缀下是否还会乱跳；
  3) 浏览器内注入 enhance 层后，画面是否与 main.py 出的真机帧一致。

跑法：py editor/_redesign/_proto_wxapp.py   然后访问 http://127.0.0.1:8002/
"""
import http.server
import io
import os
import re
import socketserver
import urllib.error
import urllib.parse
import urllib.request

UPSTREAM = "http://127.0.0.1:8080"
ROOT = r"G:\weixin-auto"
ENHANCE_DIR = os.path.join(ROOT, "enhance")
PUBLIC_IMAGES = os.path.join(ROOT, "vue-WeChat", "public", "images")
PREFIX = "/vue-wechat/"

CTYPE = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".mp4": "video/mp4",
    ".wasm": "application/wasm",
}

BOOT_TAG = '<script src="/enhance/_embed_boot.js"></script>'


def ctype_for(path):
    return CTYPE.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def read_file(fp):
    with open(fp, "rb") as fh:
        return fh.read()


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "sockjs" in self.path or "hot-update" in self.path:
            return
        print("[proto]", self.path, args[1] if len(args) > 1 else "")

    def send_bytes(self, data, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            body = (
                "<!doctype html><meta charset=utf-8><title>proto</title>"
                "<style>html,body{margin:0;background:#333;display:flex;"
                "align-items:center;justify-content:center;height:100%}"
                "iframe{width:600px;height:1300px;border:0;background:#000}"
                "</style><iframe src='/vue-wechat/#/'></iframe>"
            ).encode("utf-8")
            return self.send_bytes(body, "text/html; charset=utf-8")

        if path.startswith("/enhance/"):
            rel = os.path.basename(path)
            fp = os.path.join(ENHANCE_DIR, rel)
            if os.path.isfile(fp):
                return self.send_bytes(read_file(fp), ctype_for(fp))
            return self.send_bytes(b"not found", "text/plain")

        if path.startswith("/images/"):
            rel = urllib.parse.unquote(path[len("/images/"):])
            fp = os.path.join(PUBLIC_IMAGES, rel.replace("/", os.sep))
            if os.path.isfile(fp):
                return self.send_bytes(read_file(fp), ctype_for(fp))
            return self.send_bytes(b"not found", "text/plain")

        if path.startswith(PREFIX):
            rel = path[len(PREFIX):] or ""
            url = UPSTREAM + "/" + rel + (("?" + self.path.split("?", 1)[1]) if "?" in self.path else "")
            try:
                req = urllib.request.Request(url, headers={
                    "Accept-Encoding": "identity",
                    "User-Agent": "proto-embed",
                })
                with urllib.request.urlopen(req, timeout=25) as r:
                    data = r.read()
                    ctype = r.headers.get("Content-Type", "")
                    final = r.geturl()
            except urllib.error.HTTPError as e:
                data = e.read()
                ctype = e.headers.get("Content-Type", "")
            except Exception as e:  # noqa: BLE001
                return self.send_bytes(("proxy error: %s" % e).encode(), "text/plain")

            if "text/html" in ctype:
                html = data.decode("utf-8", "replace")
                if BOOT_TAG not in html:
                    if "</body>" in html:
                        html = html.replace("</body>", BOOT_TAG + "</body>", 1)
                    else:
                        html += BOOT_TAG
                data = html.encode("utf-8")
                ctype = "text/html; charset=utf-8"
            return self.send_bytes(data, ctype or "application/octet-stream")

        # 其它（sockjs / favicon 等）直接原样代理，失败就算了
        url = UPSTREAM + path
        try:
            req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return self.send_bytes(r.read(), r.headers.get("Content-Type", "application/octet-stream"))
        except Exception:  # noqa: BLE001
            return self.send_bytes(b"not found", "text/plain")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("127.0.0.1", 8002), H) as httpd:
        print("[proto] http://127.0.0.1:8002/  (iframe -> %s)" % UPSTREAM)
        httpd.serve_forever()
