# -*- coding: utf-8 -*-
"""
截图模式 · 编辑器 API 与静态路由
==================================
「微信聊天截图」生成器的服务端：JSON 对话 → 正宗微信样式截图 PNG。
被 editor_server.py 以两行接入（与 longimg_api 同一挂钩方式）：

    import shot_api
    # do_GET  开头:  if shot_api.handle_get(self): return
    # do_POST 开头:  if shot_api.handle_post(self): return

路由：
  GET  /shot                    截图工作台页面（editor/shot.html）
  GET  /shots/*                 成品截图 / 上传素材（vue-WeChat/public/shots/*）
  GET  /api/shot/people         人物资料：people.json 分组 + peer_presets 人设
  GET  /api/shot/avatars        内置头像库（153 张）
  GET  /api/shot/bgs            聊天背景候选（/images/bg）
  GET  /api/shot/assets         可发素材：sticker|photo|link|emoji（分页）
  GET  /api/shot/sample         示例 JSON（工作台「载入示例」）
  GET  /api/shot/format         格式说明（截图功能设计说明书.md）
  GET  /api/shot/list           截图库（成品 + 对应 source.json）
  POST /api/shot/render         同步出图（JSON → PNG，10~30s）
  POST /api/shot/delete         删除一张成品（连同 source.json）
  POST /api/shot/upload         上传素材（原始二进制 + X-Shot-Kind/X-Shot-Name）

★ 渲染子进程的解释器：必须是装了 playwright 的解释器（系统 Python）。
  编辑器用 启动.bat 起时 sys.executable 就是它；若被 AI 用托管 Python 起过服务，
  这里会自动探测一个能 import playwright 的解释器，避免"跑不出图"。
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DIR = os.path.join(ROOT, "长图模式")
PUBLIC = os.path.join(ROOT, "vue-WeChat", "public")
SHOT_DIR = os.path.join(PUBLIC, "shots")
UPLOAD_DIR = os.path.join(SHOT_DIR, "assets")
PAGE = os.path.join(ROOT, "editor", "shot.html")
FORMAT_DOC = os.path.join(ROOT, "截图功能设计说明书.md")

if MOD_DIR not in sys.path:
    sys.path.insert(0, MOD_DIR)

_render_lock = threading.Lock()
_py_cache = {"path": None}

CATEGORIES = {
    "sticker": ["images/sticker"],
    "emoji": ["images/emoji", "images/wxemoji", "images/wxemoji3d"],
    "photo": ["images/sets2", "images/album", "images/ref"],
    "link": ["images/link"],
    "avatar": ["images/avatar"],
    "bg": ["images/bg"],
}
IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")


# ---------------------------------------------------------------- 基础回复

def _json(handler, code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except OSError:
        pass


def _read_json_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        return None


def _send_file(handler, fp, mime=None):
    if not os.path.isfile(fp):
        return _json(handler, 404, {"ok": False, "msg": "文件不存在"})
    mime = mime or mimetypes.guess_type(fp)[0] or "application/octet-stream"
    with open(fp, "rb") as f:
        data = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    try:
        handler.wfile.write(data)
    except OSError:
        pass


def _in_dir(fp, base):
    """路径必须在 base 之内（禁止 ../ 越权）。"""
    try:
        fp = os.path.abspath(fp)
        return os.path.commonpath([fp, os.path.abspath(base)]) == os.path.abspath(base)
    except ValueError:
        return False


# ---------------------------------------------------------------- 解释器探测

def pick_python():
    """挑一个能 import playwright 的解释器（带缓存）。"""
    if _py_cache["path"]:
        return _py_cache["path"]
    cands = [os.environ.get("SHOT_PYTHON"), sys.executable,
             sys.executable.replace("pythonw.exe", "python.exe")]
    la = os.environ.get("LOCALAPPDATA") or ""
    for pat in ("Programs/Python", "Programs/Python312", "Programs/Python314"):
        d = os.path.join(la, pat.replace("/", os.sep))
        if os.path.isdir(d):
            for sub in sorted(os.listdir(d), reverse=True):
                p = os.path.join(d, sub, "python.exe")
                if os.path.isfile(p):
                    cands.append(p)
            p = os.path.join(d, "python.exe")
            if os.path.isfile(p):
                cands.append(p)
    for c in cands:
        if not c or not os.path.isfile(c):
            continue
        try:
            r = subprocess.run([c, "-c", "import playwright"],
                               capture_output=True, timeout=60)
            if r.returncode == 0:
                _py_cache["path"] = c
                return c
        except (OSError, subprocess.SubprocessError):
            continue
    _py_cache["path"] = sys.executable
    return sys.executable


# ---------------------------------------------------------------- 目录扫描

def _list_imgs(subdir, url_prefix, limit=None, offset=0):
    d = os.path.join(PUBLIC, subdir.replace("/", os.sep))
    items = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(IMG_EXT):
                items.append(url_prefix + f)
    total = len(items)
    if limit:
        items = items[offset:offset + limit]
    return items, total


# ---------------------------------------------------------------- GET

def handle_get(handler):
    path = handler.path.split("?", 1)[0]
    if path == "/shot":
        # 只认精确的 /shot；/shot/xxx.png（编辑器原有的「截图预览」成品）留给 editor_server 自己处理
        _send_file(handler, PAGE, "text/html; charset=utf-8")
        return True
    if path.startswith("/shots/"):
        rel = unquote(path[len("/shots/"):]).replace("/", os.sep)
        fp = os.path.normpath(os.path.join(SHOT_DIR, rel))
        if not _in_dir(fp, SHOT_DIR):
            _json(handler, 403, {"ok": False, "msg": "禁止访问"})
        else:
            _send_file(handler, fp)
        return True
    if path == "/api/shot/people":
        import shot_export as S
        pp = S.load_people()
        groups = {}
        for g, items in pp["groups"].items():
            groups[g] = [{"name": n, "avatar": a} for n, a in items.items()]
        presets = []
        for key, p in pp["presets"].items():
            if not isinstance(p, dict):
                continue
            presets.append({"key": key, "name": p.get("name") or key,
                            "avatar": p.get("avatar") or "",
                            "wxid": p.get("wxid") or "", "area": p.get("area") or "",
                            "gender": p.get("gender", 0),
                            "signature": p.get("signature") or ""})
        return _json(handler, 200, {"ok": True, "groups": groups, "presets": presets})
    if path == "/api/shot/avatars":
        items, total = _list_imgs("images/avatar", "/images/avatar/")
        return _json(handler, 200, {"ok": True, "items": items, "total": total})
    if path == "/api/shot/bgs":
        items, _ = _list_imgs("images/bg", "/images/bg/")
        return _json(handler, 200, {"ok": True, "items": items})
    if path == "/api/shot/assets":
        qs = {}
        for kv in (urlparse(handler.path).query or "").split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                qs[k] = unquote(v)
        kind = (qs.get("kind") or "photo").lower()
        off = max(0, int(qs.get("offset") or 0))
        lim = min(240, max(12, int(qs.get("limit") or 60)))
        dirs = CATEGORIES.get(kind) or CATEGORIES["photo"]
        items = []
        for sub in dirs:
            got, _t = _list_imgs(sub, "/" + sub + "/")
            items += got
        total = len(items)
        items = items[off:off + lim]
        ups, _ = _list_imgs("shots/assets", "/shots/assets/")
        if off == 0:
            items = ups + items
        return _json(handler, 200, {"ok": True, "items": items, "total": total + len(ups),
                                    "offset": off, "limit": lim})
    if path == "/api/shot/sample":
        return _json(handler, 200, {"ok": True, "config": sample_config()})
    if path == "/api/shot/format":
        try:
            with open(FORMAT_DOC, "r", encoding="utf-8") as f:
                return _json(handler, 200, {"ok": True, "text": f.read()})
        except OSError:
            return _json(handler, 404, {"ok": False, "msg": "格式说明文件不存在"})
    if path == "/api/shot/list":
        items = []
        if os.path.isdir(SHOT_DIR):
            for f in sorted(os.listdir(SHOT_DIR), reverse=True):
                if not f.lower().endswith(".png") or f.startswith("_probe_"):
                    continue
                fp = os.path.join(SHOT_DIR, f)
                it = {"name": f, "url": "/shots/" + f, "mtime": os.path.getmtime(fp),
                      "kbytes": int(os.path.getsize(fp) / 1024)}
                sp = os.path.join(SHOT_DIR, os.path.splitext(f)[0] + ".source.json")
                it["source"] = os.path.basename(sp) if os.path.isfile(sp) else ""
                items.append(it)
        return _json(handler, 200, {"ok": True, "items": items[:60]})
    return False


# ---------------------------------------------------------------- POST

def handle_post(handler, pre_body=None):
    path = handler.path.split("?", 1)[0]
    if path not in ("/api/shot/render", "/api/shot/upload", "/api/shot/delete"):
        return False

    if path == "/api/shot/upload":
        length = int(handler.headers.get("Content-Length", 0))
        raw = handler.rfile.read(length) if length else b""
        name = unquote(handler.headers.get("X-Shot-Name", "") or "") or "u.jpg"
        name = os.path.basename(name).replace("\\", "_").replace("/", "_")
        if length > 100 * 1024 * 1024:
            return _json(handler, 400, {"ok": False, "msg": "超过 100MB 上限"})
        if os.path.splitext(name)[1].lower() not in IMG_EXT:
            name = os.path.splitext(name)[0] + ".jpg"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        fp = os.path.join(UPLOAD_DIR, name)
        stem, n = os.path.splitext(name), 1
        while os.path.isfile(fp):
            fp = os.path.join(UPLOAD_DIR, stem[0] + "_%d" % n + stem[1])
            n += 1
        with open(fp, "wb") as f:
            f.write(raw)
        return _json(handler, 200, {"ok": True, "url": "/shots/assets/"
                                    + os.path.basename(fp), "bytes": length})

    data = _read_json_body(handler)
    if data is None:
        return _json(handler, 400, {"ok": False, "msg": "JSON 解析失败"})

    if path == "/api/shot/delete":
        name = os.path.basename(str(data.get("name") or ""))
        if not name:
            return _json(handler, 400, {"ok": False, "msg": "缺少 name"})
        killed = []
        for f in (name, os.path.splitext(name)[0] + ".source.json",
                  os.path.splitext(name)[0] + ".manifest.json"):
            fp = os.path.join(SHOT_DIR, f)
            if os.path.isfile(fp) and _in_dir(fp, SHOT_DIR):
                os.remove(fp)
                killed.append(f)
        return _json(handler, 200, {"ok": bool(killed), "deleted": killed})

    # ---- 出图：同步 ----
    cfg = data.get("config") if isinstance(data.get("config"), dict) else data
    if not _render_lock.acquire(blocking=False):
        return _json(handler, 429, {"ok": False,
                                    "msg": "正在出上一张图，稍等几秒再点"})
    try:
        opts = cfg.get("options") if isinstance(cfg.get("options"), dict) else {}
        tag = str(data.get("tag") or opts.get("filename")
                  or time.strftime("%m%d_%H%M%S")).strip() or time.strftime("%m%d_%H%M%S")
        py = pick_python()
        cfg_path = os.path.join(SHOT_DIR, "_cfg_%s.json" % uuid.uuid4().hex[:8])
        os.makedirs(SHOT_DIR, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        cmd = [py, os.path.join(MOD_DIR, "shot_export.py"),
               "--config", cfg_path, "--out-dir", SHOT_DIR, "--tag", tag]
        if data.get("manifest"):
            cmd.append("--manifest")
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=600)
        except subprocess.TimeoutExpired:
            return _json(handler, 504, {"ok": False, "msg": "出图超时（600s）"})
        finally:
            try:
                os.remove(cfg_path)
            except OSError:
                pass
        tail = ((r.stdout or b"").decode("utf-8", "replace")
                + (r.stderr or b"").decode("utf-8", "replace"))[-1200:]
        stem = None
        for line in reversed(tail.splitlines()):
            if line.startswith("[完成] 截图: "):
                stem = os.path.basename(line.split(": ")[1].split(" (")[0])
                break
        if not stem:
            return _json(handler, 400, {"ok": False, "msg": "出图失败：\n" + tail.strip()})
        fp = os.path.join(SHOT_DIR, stem)
        out = {"ok": True, "name": stem, "url": "/shots/" + stem + "?v=" + str(int(time.time())),
               "log": tail.strip()}
        try:
            from PIL import Image
            with Image.open(fp) as im:
                out["width"], out["height"] = im.size
        except Exception:                                    # noqa: BLE001
            pass
        return _json(handler, 200, out)
    except (OSError, RuntimeError) as e:
        return _json(handler, 500, {"ok": False, "msg": str(e)})
    finally:
        _render_lock.release()


# ---------------------------------------------------------------- 示例

def sample_config():
    return {
        "people": {"peer": "花店店主·林晚晚", "me": "学员-小康"},
        "messages": [
            {"from": "peer", "text": "在干嘛呢"},
            {"from": "me", "text": "刚下班 你呢"},
            {"from": "peer", "time": "昨天 21:30", "text": "在店里浇花 有点无聊"},
            {"from": "me", "text": "那我过去陪你？"},
            {"from": "peer", "emoji": "偷笑"},
            {"from": "peer", "text": "不用啦 我一个人挺好的"},
            {"from": "me", "text": "行吧 那我明天去你店里坐坐"},
            {"from": "peer", "voice": 4},
        ],
        "options": {"wallpaper": "default", "scale": 2,
                    "filename": "shot_sample"},
    }
