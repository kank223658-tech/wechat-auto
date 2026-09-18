# -*- coding: utf-8 -*-
"""
长图模式 · 编辑器 API 与静态路由
==================================
被 editor_server.py 以两行接入：

    import longimg_api
    # do_GET  开头:  if longimg_api.handle_get(self): return
    # do_POST 开头:  if longimg_api.handle_post(self, body): return

路由：
  GET  /longimg                     长图模式工作台页面（editor/longimg.html）
  GET  /longimg-assets/*            上传素材（长图/BGM/头像）→ vue-WeChat/public/longimg/*
  GET  /api/longimg/assets          素材列表
  GET  /api/longimg/avatars         内置头像库列表（vue-WeChat/public/images/avatar）
  GET  /api/longimg/jobs            任务列表
  GET  /api/longimg/sample          示例配置
  GET  /api/longimg/exported        最近导出的微信长图（预览/复用）
  GET  /api/longimg/format          JSON 格式说明（长图模式/JSON格式说明.md）
  POST /api/longimg/upload          上传（原始二进制 + X-Longimg-Kind: image|bgm）
  POST /api/longimg/wxshot          同步导出「微信仿真长图」PNG（JSON 对话 → 真微信样式长图）
  POST /api/longimg/preview         生成关键帧预览（同步，约 5~15s）
  POST /api/longimg/render          提交渲染任务（异步，子进程）

两种出片模式（payload 的 mode 字段）：
  wx      JSON 对话 → wx_export.py 出正宗微信长图 → 动态镜头渲染（默认，推荐）
  longimg 自己上传的长图 → 动态镜头渲染
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DIR = os.path.join(ROOT, "长图模式")
ASSET_DIR = os.path.join(ROOT, "vue-WeChat", "public", "longimg")
OUT_DIR = os.path.join(ROOT, "vue-WeChat", "public", "videos", "longimg")
JOBS_DIR = os.path.join(ROOT, "_runtime", "longimg_jobs")
PAGE = os.path.join(ROOT, "editor", "longimg.html")
JOBS_JSON = os.path.join(JOBS_DIR, "jobs.json")

_lock = threading.Lock()


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
    size = os.path.getsize(fp)
    rng = handler.headers.get("Range")
    if rng and mime.startswith(("video/", "audio/")):
        try:
            start = int(rng.split("bytes=")[1].split("-")[0])
        except (ValueError, IndexError):
            start = 0
        end = min(size - 1, start + 4 * 1024 * 1024 - 1)
        with open(fp, "rb") as f:
            f.seek(start)
            data = f.read(end - start + 1)
        handler.send_response(206)
        handler.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    else:
        with open(fp, "rb") as f:
            data = f.read()
        handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    try:
        handler.wfile.write(data)
    except OSError:
        pass


# ---------------------------------------------------------------- 路径口径
#
# ★ 本项目装在 U 盘里，盘符随电脑变（这台是 F:，以前是 G:），所以：
#   - 任何「要落盘」的路径一律存成相对项目根的相对路径（_rel）；
#   - 读盘时统一经 _abs 还原成本机绝对路径；老记录里那种已失效的绝对路径
#     （旧盘符如「X:\...\weixin-auto\...」）会按当前 ROOT 自动修复，不必手工清 jobs.json。

def _rel(p):
    """绝对路径 → 项目相对路径（正斜杠；项目外的路径原样返回）。"""
    if not p:
        return p
    s = str(p).replace("\\", "/")
    root = ROOT.replace("\\", "/").rstrip("/")
    if s.lower().startswith(root.lower() + "/"):
        return s[len(root) + 1:]
    return s


def _abs(p):
    """落盘路径 → 本机绝对路径（盘符漂移自愈）。"""
    if not p:
        return p
    s = str(p).replace("\\", "/")
    if s.startswith("/") and not s.startswith("//"):
        return s                          # web 路径不碰
    if os.path.isabs(s):
        if os.path.exists(s):
            return s
        # 盘符失效：把 ".../weixin-auto/<项目内相对路径>" 剥出来挂到当前 ROOT 下
        m = re.match(r"^[A-Za-z]:/(?:.*?/)?weixin-auto/(.+)$", s, re.I)
        if m:
            return os.path.join(ROOT, m.group(1).replace("/", os.sep))
        return s
    return os.path.join(ROOT, s.replace("/", os.sep))


# ---------------------------------------------------------------- 任务表

def _load_jobs():
    try:
        with open(JOBS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_jobs(jobs):
    os.makedirs(JOBS_DIR, exist_ok=True)
    tmp = JOBS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=1)
    os.replace(tmp, JOBS_JSON)


def _tail_log(job_id, n=30):
    lp = os.path.join(JOBS_DIR, job_id + ".log")
    try:
        with open(lp, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def _refresh_job(j):
    """按产物文件刷新任务状态（out_path 存的是项目相对路径，读时经 _abs 还原）。"""
    out = _abs(j.get("out_path"))
    if j.get("status") == "running" and out and os.path.isfile(out) \
            and time.time() - j.get("started", 0) > 5:
        j["status"] = "success"
        j["finished"] = time.time()
        j["log"] = _tail_log(j["id"])
        j["url"] = "/videos/longimg/" + os.path.basename(out)
    return j


# ---------------------------------------------------------------- 渲染提交

def _submit(steps, out_path, tag, cfg_path=None):
    """提交渲染任务（steps = argv 列表的列表，顺序执行，全部写入同一个日志）。

    状态判定看最终产物 out_path 是否落盘；wx 模式是「先导长图、再渲染」两步，
    长图那步没出图时渲染必然失败，日志里能看到原因。
    """
    os.makedirs(JOBS_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    jid = "li" + time.strftime("%m%d%H%M%S") + uuid.uuid4().hex[:4]
    # 落盘存相对路径：U 盘换电脑（盘符变）后任务列表依然能定位产物
    job = {"id": jid, "tag": tag, "status": "running", "cfg": _rel(cfg_path or ""),
           "out_path": _rel(out_path), "started": time.time(), "log": "", "url": ""}
    with _lock:
        jobs = _load_jobs()
        jobs[jid] = job
        _save_jobs(jobs)
    logf = open(os.path.join(JOBS_DIR, jid + ".log"), "w", encoding="utf-8")

    def run():
        try:
            for cmd in steps:
                logf.write("$ " + " ".join(str(c) for c in cmd) + "\n")
                logf.flush()
                subprocess.run(cmd, cwd=ROOT, stdout=logf,
                               stderr=subprocess.STDOUT,
                               timeout=3600, check=False)
        except Exception as e:                                # noqa: BLE001
            try:
                logf.write("\n[异常] %s\n" % e)
            except OSError:
                pass
        finally:
            logf.close()
            with _lock:
                jobs = _load_jobs()
                j = jobs.get(jid)
                if j:
                    j["status"] = ("success" if os.path.isfile(out_path)
                                   and os.path.getsize(out_path) > 10000 else "failed")
                    j["finished"] = time.time()
                    logf2 = open(os.path.join(JOBS_DIR, jid + ".log"),
                                 "a", encoding="utf-8")
                    logf2.close()
                    j["log"] = _tail_log(jid, 40)
                    if j["status"] == "success":
                        j["url"] = "/videos/longimg/" + os.path.basename(out_path)
                    _save_jobs(jobs)

    threading.Thread(target=run, daemon=True).start()
    return job


# ---------------------------------------------------------------- 微信长图线

def _wx_page_url(u):
    """工作台素材 URL → 仿真聊天页(8080)里可直接用的 URL。

    上传的素材落在 vue-WeChat/public/longimg/，页面侧叫 /longimg/*；
    内置头像/图片走 /images/*，两条都直接给 8080 用。
    """
    p = (u or "").strip()
    if not p:
        return ""
    if p.startswith("/longimg-assets/"):
        return "/longimg/" + p[len("/longimg-assets/"):]
    return p


def _wx_blocks(blocks):
    """工作台 blocks → wx_export 的 blocks（只留有效字段，图路径转成页面 URL）。"""
    out = []
    for b in blocks or []:
        side = "me" if str(b.get("side")) == "me" else "peer"
        text = (b.get("text") or "").strip()
        img = (b.get("img") or "").strip()
        if not text and not img:
            continue
        item = {"side": side}
        if img:
            item["img"] = _wx_page_url(img)
        if text:
            item["text"] = text
        if (b.get("note") or "").strip():
            item["note"] = b["note"].strip()
        if (b.get("note_color") or "").strip():
            item["note_color"] = b["note_color"].strip()
        if (b.get("time") or "").strip():
            item["time"] = b["time"].strip()
        out.append(item)
    return out


def _wx_export_cfg(cfg):
    """工作台 payload → wx_export.py 的配置。"""
    meta = cfg.get("meta") or {}
    ending = cfg.get("ending") or {}
    return {
        "meta": {
            "peer_name": (meta.get("peer_name") or "朋友").strip(),
            "peer_avatar": _wx_page_url(meta.get("peer_avatar")),
            "my_avatar": _wx_page_url(meta.get("my_avatar")),
        },
        "blocks": _wx_blocks(cfg.get("blocks")),
        "ending": {"note": (ending.get("note") or "").strip(),
                   "color": (ending.get("color") or "red")},
    }


def _run_wxshot(cfg, tag, logf=None):
    """同步导出微信仿真长图 → (png, manifest)；失败返回 (None, 错误信息)。"""
    if not _port_open(8080):
        return None, "前端 8080 未运行：先跑一次 软件（main.py）把仿真页面拉起来"
    exp = _wx_export_cfg(cfg)
    if not exp["blocks"]:
        return None, "对话为空：至少写一条台词"
    cf = os.path.join(JOBS_DIR, "wxcfg_%s.json" % tag)
    os.makedirs(JOBS_DIR, exist_ok=True)
    with open(cf, "w", encoding="utf-8") as f:
        json.dump(exp, f, ensure_ascii=False, indent=1)
    cmd = [sys.executable, os.path.join(MOD_DIR, "wx_export.py"),
           "--config", cf, "--out-dir", OUT_DIR, "--tag", tag]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None, "导出长图超时（600s）"
    tail = (r.stdout or b"").decode("utf-8", "replace")[-1500:]
    if logf is not None:
        logf.write("$ " + " ".join(cmd) + "\n" + tail + "\n")
    png = os.path.join(OUT_DIR, "wxshot_%s.png" % tag)
    mf = os.path.join(OUT_DIR, "wxshot_%s.manifest.json" % tag)
    if not os.path.isfile(png):
        return None, "导出失败：\n" + tail
    return png, cf


def _wx_render_cfg(cfg, bgm_path, png):
    """工作台 payload → render_longimg 的配置（wx 路）。"""
    return {"meta": cfg.get("meta") or {},
            "pace": cfg.get("pace") or {},
            "intro": cfg.get("intro") or {},
            "quality": cfg.get("quality") or {},
            "longimg_opts": {"zoom": max(1.0, float(
                (cfg.get("longimg_opts") or {}).get("zoom", 1.0) or 1.0)),
                "pan": "side"},
            "wxshot": png,
            "bgm": {"path": bgm_path,
                    "fade_out": float(cfg.get("fade_out", 1.2) or 1.2)}}


def _port_open(port):
    """端口是否有人监听。

    ⚠️ 不要用 connect_ex + settimeout 的组合：Windows 上带超时的 socket 是非阻塞的，
    connect_ex 会立刻返回 WSAEWOULDBLOCK(10035)，把「能连上」误判成「没在跑」。
    用阻塞式 connect()（内部会按 timeout 等），失败重试 3 次。
    """
    import socket as _s
    for _ in range(3):
        sk = _s.socket()
        sk.settimeout(2.0)
        try:
            sk.connect(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.3)
        finally:
            try:
                sk.close()
            except OSError:
                pass
    return False



# ---------------------------------------------------------------- GET

def handle_get(handler):
    path = handler.path.split("?", 1)[0]
    if path in ("/longimg", "/longimg/"):
        _send_file(handler, PAGE, "text/html; charset=utf-8")
        return True
    if path.startswith("/longimg-assets/"):
        rel = os.path.normpath(path[len("/longimg-assets/"):])
        if rel.startswith("..") or os.path.isabs(rel):
            _json(handler, 403, {"ok": False, "msg": "禁止访问"})
        else:
            _send_file(handler, os.path.join(ASSET_DIR, rel))
        return True
    if path == "/api/longimg/assets":
        imgs, bgms = [], []
        if os.path.isdir(ASSET_DIR):
            for f in sorted(os.listdir(ASSET_DIR)):
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    imgs.append("/longimg-assets/" + f)
                elif f.lower().endswith((".mp3", ".wav", ".m4a", ".aac")):
                    bgms.append("/longimg-assets/" + f)
        return _json(handler, 200, {"ok": True, "images": imgs, "bgm": bgms})
    if path == "/api/longimg/jobs":
        with _lock:
            jobs = _load_jobs()
            changed = False
            for j in jobs.values():
                old = j.get("status")
                _refresh_job(j)
                changed |= old != j.get("status")
                # 顺手把老记录里的绝对路径迁成相对路径（换过盘的 G:\... 会被就地修正）
                for k in ("out_path", "cfg"):
                    if j.get(k):
                        nv = _rel(_abs(j[k]))
                        if nv != j[k]:
                            j[k] = nv
                            changed = True
            if changed:
                _save_jobs(jobs)
        items = sorted(jobs.values(), key=lambda j: -j.get("started", 0))[:30]
        for j in items:
            j.pop("cfg", None)
            if j.get("status") == "running":
                j["log"] = _tail_log(j["id"], 8)
        return _json(handler, 200, {"ok": True, "items": items})
    if path == "/api/longimg/photos":
        # 聊天气泡里能用的随手拍照片：上传素材库 + 内置图集（分页）
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(handler.path).query)
        off = max(0, int((qs.get("offset") or ["0"])[0] or 0))
        lim = min(120, max(12, int((qs.get("limit") or ["60"])[0] or 60)))
        items = []
        if os.path.isdir(ASSET_DIR):
            for f in sorted(os.listdir(ASSET_DIR), reverse=True):
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    items.append("/longimg-assets/" + f)
        sdir = os.path.join(ROOT, "vue-WeChat", "public", "images", "sets2")
        names = []
        if os.path.isdir(sdir):
            names = sorted([f for f in os.listdir(sdir)
                            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))],
                           reverse=True)
        total = len(items) + len(names)
        page = (items + ["/images/sets2/" + n for n in names])[off:off + lim]
        return _json(handler, 200, {"ok": True, "items": page, "total": total,
                                    "offset": off, "limit": lim})
    if path == "/api/longimg/avatars":
        adir = os.path.join(ROOT, "vue-WeChat", "public", "images", "avatar")
        items = []
        if os.path.isdir(adir):
            for f in sorted(os.listdir(adir)):
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    items.append("/images/avatar/" + f)
        return _json(handler, 200, {"ok": True, "items": items})
    if path == "/api/longimg/exported":
        items = []
        if os.path.isdir(OUT_DIR):
            for f in sorted(os.listdir(OUT_DIR), reverse=True):
                if f.startswith("wxshot_") and f.lower().endswith(".png"):
                    fp = os.path.join(OUT_DIR, f)
                    items.append({"url": "/videos/longimg/" + f, "name": f,
                                  "mtime": os.path.getmtime(fp),
                                  "kbytes": int(os.path.getsize(fp) / 1024)})
        return _json(handler, 200, {"ok": True, "items": items[:40]})
    if path == "/api/longimg/format":
        fp = os.path.join(MOD_DIR, "JSON格式说明.md")
        try:
            with open(fp, "r", encoding="utf-8") as f:
                return _json(handler, 200, {"ok": True, "text": f.read()})
        except OSError:
            return _json(handler, 404, {"ok": False, "msg": "说明文件不存在"})
    if path == "/api/longimg/sample":
        sample = os.path.join(MOD_DIR, "sample_config.json")
        try:
            with open(sample, "r", encoding="utf-8") as f:
                return _json(handler, 200, {"ok": True, "config": json.load(f)})
        except (OSError, ValueError) as e:
            return _json(handler, 500, {"ok": False, "msg": str(e)})
    return False


# ---------------------------------------------------------------- POST

def handle_post(handler, pre_body=None):
    path = handler.path.split("?", 1)[0]
    if path not in ("/api/longimg/upload", "/api/longimg/render",
                    "/api/longimg/preview", "/api/longimg/wxshot"):
        return False

    if path == "/api/longimg/upload":
        length = int(handler.headers.get("Content-Length", 0))
        raw = handler.rfile.read(length) if length else b""
        kind = handler.headers.get("X-Longimg-Kind", "image")
        # 文件名的中文/空格在 HTTP 头里会被百分号编码或变 latin-1 乱码，统一先 unquote
        name = unquote(handler.headers.get("X-Longimg-Name", "") or "") or ("u." + kind)
        name = os.path.basename(name).replace("\\", "_").replace("/", "_")
        if length > 200 * 1024 * 1024:
            return _json(handler, 400, {"ok": False, "msg": "超过 200MB 上限"})
        os.makedirs(ASSET_DIR, exist_ok=True)
        ext = os.path.splitext(name)[1].lower()
        allow = (".png", ".jpg", ".jpeg", ".webp") if kind == "image" \
            else (".mp3", ".wav", ".m4a", ".aac")
        if ext not in allow:
            ext = ".png" if kind == "image" else ".mp3"
            name = os.path.splitext(name)[0] + ext
        fp = os.path.join(ASSET_DIR, name)
        stem, n = os.path.splitext(name), 1
        while os.path.isfile(fp):
            fp = os.path.join(ASSET_DIR, stem[0] + "_%d" % n + stem[1])
            n += 1
        with open(fp, "wb") as f:
            f.write(raw)
        url = "/longimg-assets/" + os.path.basename(fp)
        return _json(handler, 200, {"ok": True, "url": url, "bytes": length})

    data = _read_json_body(handler)
    if data is None:
        return _json(handler, 400, {"ok": False, "msg": "JSON 解析失败"})

    # 兼容两种形状：{config:{...}} 包裹 或 前端直接发的扁平 {mode,bgm_path,blocks,...}
    cfg = data.get("config") if isinstance(data.get("config"), dict) else data
    cfg = cfg or {}
    mode = str(data.get("mode") or cfg.get("mode") or "").lower()
    if not mode:
        mode = "longimg" if cfg.get("longimg") else "wx"
    if mode in ("json", "wx"):
        mode = "wx"                              # 老页面的 "json" 一律走微信仿真线
    if mode not in ("wx", "longimg"):
        return _json(handler, 400, {"ok": False, "msg": "未知 mode: " + mode})

    # ---- ① 只导长图（同步）：JSON 对话 → 正宗微信长图 PNG ----
    if path == "/api/longimg/wxshot":
        if mode != "wx":
            return _json(handler, 400, {"ok": False, "msg": "该接口仅 wx 模式可用"})
        tag = time.strftime("%m%d_%H%M%S")
        os.makedirs(OUT_DIR, exist_ok=True)
        os.makedirs(JOBS_DIR, exist_ok=True)
        png, info = _run_wxshot(cfg, tag)
        if not png:
            return _json(handler, 400, {"ok": False, "msg": info})
        mf = os.path.splitext(png)[0] + ".manifest.json"
        n_msg, dsf, wpx, hpx = 0, 1, 0, 0
        try:
            with open(mf, "r", encoding="utf-8") as f:
                mm = json.load(f)
            n_msg = len(mm.get("items") or [])
            dsf = mm.get("dsf", 1)
            wpx = mm.get("width_px", 0)
        except (OSError, ValueError):
            pass
        try:
            from PIL import Image
            with Image.open(png) as im:
                wpx = wpx or im.width
                hpx = im.height
        except Exception:                                     # noqa: BLE001
            pass
        return _json(handler, 200, {"ok": True, "url": "/videos/longimg/"
                                    + os.path.basename(png) + "?v=" + str(int(time.time())),
                                    "name": os.path.basename(png),
                                    "count": n_msg, "dsf": dsf,
                                    "width_px": wpx, "height_px": hpx})

    # ---- 以下都要 BGM ----
    bgm = str(cfg.get("bgm_path") or "").strip()
    if not bgm:
        return _json(handler, 400, {"ok": False, "msg": "缺少背景音乐"})

    def resolve(p):
        posix = p.replace("\\", "/")
        if posix.startswith("/longimg-assets/"):
            return os.path.join(ASSET_DIR, posix[len("/longimg-assets/"):])
        if posix.startswith("/"):
            cand = os.path.join(ROOT, "vue-WeChat", "public", posix.lstrip("/"))
            return cand if os.path.isfile(cand) else os.path.join(ROOT, posix.lstrip("/"))
        return p

    bgm = resolve(bgm)
    if not os.path.isfile(bgm):
        return _json(handler, 400, {"ok": False, "msg": "BGM 不存在: " + bgm})

    exports = []                                 # 需要先跑的命令（wx 模式含导长图）
    if mode == "wx":
        blocks = _wx_blocks(cfg.get("blocks"))
        if not blocks:
            return _json(handler, 400, {"ok": False, "msg": "对话为空：至少写一条台词"})
        wx_cfg = {"meta": cfg.get("meta") or {}, "blocks": cfg.get("blocks") or [],
                  "ending": cfg.get("ending") or {}}
        if path == "/api/longimg/preview":
            # 预览：先同步出长图（顺带返回预览图 URL），再出关键帧拼图
            tag = time.strftime("%m%d_%H%M%S")
            os.makedirs(OUT_DIR, exist_ok=True)
            os.makedirs(JOBS_DIR, exist_ok=True)
            png, info = _run_wxshot(wx_cfg, tag)
            if not png:
                return _json(handler, 400, {"ok": False, "msg": info})
            rcfg = _wx_render_cfg(cfg, bgm, png)
            name = "长图_%s_wx.mp4" % time.strftime("%m%d_%H%M")
            jid = "pv" + uuid.uuid4().hex[:8]
            cfg_path = os.path.join(JOBS_DIR, jid + ".json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(rcfg, f, ensure_ascii=False, indent=1)
            prev_out = os.path.join(OUT_DIR, name[:-4])
            try:
                subprocess.run(
                    [sys.executable, os.path.join(MOD_DIR, "render_longimg.py"),
                     "--config", cfg_path, "--wxshot", png,
                     "--out", prev_out, "--preview-only"],
                    cwd=ROOT, capture_output=True, timeout=240)
            except subprocess.TimeoutExpired:
                return _json(handler, 504, {"ok": False, "msg": "预览超时"})
            prev_jpg = prev_out + ".preview.jpg"
            if not os.path.isfile(prev_jpg):
                return _json(handler, 500, {"ok": False,
                                            "msg": "关键帧预览失败（看服务端日志）"})
            try:
                os.remove(cfg_path)
            except OSError:
                pass
            return _json(handler, 200, {
                "ok": True,
                "url": "/videos/longimg/" + os.path.basename(prev_jpg)
                       + "?v=" + str(int(time.time())),
                "shot": "/videos/longimg/" + os.path.basename(png)
                        + "?v=" + str(int(time.time()))})
        tag = "wx" + time.strftime("%m%d_%H%M%S")
        wxcfg_path = os.path.join(JOBS_DIR, "wxcfg_%s.json" % tag)
        os.makedirs(JOBS_DIR, exist_ok=True)
        os.makedirs(OUT_DIR, exist_ok=True)
        png = os.path.join(OUT_DIR, "wxshot_%s.png" % tag)
        with open(wxcfg_path, "w", encoding="utf-8") as f:
            json.dump(_wx_export_cfg(cfg), f, ensure_ascii=False, indent=1)
        exports = [
            [sys.executable, os.path.join(MOD_DIR, "wx_export.py"),
             "--config", wxcfg_path, "--out-dir", OUT_DIR, "--tag", tag],
        ]
        rcfg = _wx_render_cfg(cfg, bgm, png)
        tag_name = "微信"
    else:
        img = resolve(str(cfg.get("longimg") or ""))
        if not os.path.isfile(img):
            return _json(handler, 400, {"ok": False, "msg": "长图不存在"})
        rcfg = {"meta": cfg.get("meta") or {}, "pace": cfg.get("pace") or {},
                "intro": cfg.get("intro") or {}, "ending": cfg.get("ending") or {},
                "quality": cfg.get("quality") or {},
                "bgm": {"path": bgm, "fade_out": float(cfg.get("fade_out", 1.2))}}
        rcfg["longimg"] = img
        opts = cfg.get("longimg_opts") or {}
        pan = str(opts.get("pan", "side")).lower()
        if pan not in ("side", "center"):       # auto/zigzag 等旧值兼容
            pan = "side"
        rcfg["longimg_opts"] = {"zoom": max(1.0, float(opts.get("zoom", 1.0))),
                                "pan": pan}
        tag_name = "整图"

    name = "长图_%s_%s.mp4" % (time.strftime("%m%d_%H%M"), tag_name)

    if path == "/api/longimg/preview":
        os.makedirs(JOBS_DIR, exist_ok=True)
        jid = "pv" + uuid.uuid4().hex[:8]
        cfg_path = os.path.join(JOBS_DIR, jid + ".json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(rcfg, f, ensure_ascii=False, indent=1)
        prev_out = os.path.join(OUT_DIR, name[:-4])          # 实际产物 = prev_out + ".preview.jpg"
        try:
            subprocess.run(
                [sys.executable, os.path.join(MOD_DIR, "render_longimg.py"),
                 "--config", cfg_path, "--out", prev_out, "--preview-only"],
                cwd=ROOT, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            return _json(handler, 504, {"ok": False, "msg": "预览超时"})
        except OSError as e:
            return _json(handler, 500, {"ok": False, "msg": str(e)})
        prev_jpg = prev_out + ".preview.jpg"
        if not os.path.isfile(prev_jpg):
            return _json(handler, 500, {"ok": False, "msg": "预览生成失败（看服务端日志）"})
        os.remove(cfg_path)
        return _json(handler, 200, {"ok": True, "url": "/videos/longimg/"
                                    + os.path.basename(prev_jpg) + "?v=" + str(int(time.time()))})

    out = os.path.join(OUT_DIR, name)
    # wx 模式：先出微信长图（exports），再渲染；整图模式 exports 为空
    rcfg_path = os.path.join(JOBS_DIR, "rcfg_%s.json" % time.strftime("%m%d%H%M%S"))
    with open(rcfg_path, "w", encoding="utf-8") as f:
        json.dump(rcfg, f, ensure_ascii=False, indent=1)
    render = [sys.executable, os.path.join(MOD_DIR, "render_longimg.py"),
              "--config", rcfg_path]
    if mode == "wx":
        render += ["--wxshot", png]
    steps = list(exports) + [render + ["--out", out]]
    job = _submit(steps, out, tag_name, cfg_path=rcfg_path)
    job.pop("cfg", None)
    return _json(handler, 200, {"ok": True, "job": job})
