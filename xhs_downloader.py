# -*- coding: utf-8 -*-
"""
小红书无水印下载器（独立模块 + CLI + 可被 editor_server 调用）
=============================================================
技术路线（与 _下载工作文件 里的验证版一致，做了无水印增强）：
  1. 访问笔记页 HTML，提取 window.__INITIAL_STATE__ 里的完整元数据
  2. 图片 → 用 imageId 拼出 CDN 原图地址（sns-img-hw.xhscdn.com，无水印无压缩）
     失败时回退到 urlDefault（页面展示图，可能有缩放参数）
  3. 视频 → videoH264List 里的 masterUrl（H.264 主码流，本身无水印）

用法：
    py xhs_downloader.py <笔记链接> [输出目录]
    py xhs_downloader.py "https://www.xiaohongshu.com/explore/xxx?xsec_token=..." D:\\out

作为模块：
    import xhs_downloader
    meta = xhs_downloader.parse_note(url)          # 只解析元数据
    files = xhs_downloader.download_note(url, outdir)  # 解析 + 下载

Cookie（遇到登录墙时）：
    在本文件同目录放一个 xhs_cookie.txt，内容为浏览器里复制的
    "web_session=...; a1=..." 原始 Cookie 字符串即可。
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(ROOT, "xhs_profile")   # Playwright 持久化登录态（首次使用需扫码登录）
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
COOKIE_FILE = os.path.join(ROOT, "xhs_cookie.txt")

# ---------------------------------------------------------------- 基础请求

def _load_cookie():
    """读取可选 Cookie 文件（登录墙兜底用）"""
    try:
        if os.path.isfile(COOKIE_FILE):
            txt = open(COOKIE_FILE, "r", encoding="utf-8").read().strip()
            # 兼容整行 "Cookie: xxx" 的粘贴格式
            if txt.lower().startswith("cookie:"):
                txt = txt[7:].strip()
            return txt
    except Exception:
        pass
    return ""


def _headers(extra=None, referer=None):
    h = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        h["Referer"] = referer
    ck = _load_cookie()
    if ck:
        h["Cookie"] = ck
    if extra:
        h.update(extra)
    return h


def fetch(url, path, referer="https://www.xiaohongshu.com/"):
    """下载一个媒体文件到 path，返回字节数"""
    req = urllib.request.Request(url, headers=_headers(referer=referer))
    with urllib.request.urlopen(req, timeout=90) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(path)


def fetch_text(url):
    """抓取页面/接口文本"""
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------- 链接处理

def normalize_url(raw):
    """把各种形态的输入归一成带 xsec_token 的 PC 笔记页链接"""
    raw = (raw or "").strip()
    # 分享口令里常带整段链接，截取出来
    m = re.search(r'https?://[^\s"\'，。）)]+', raw)
    if m:
        raw = m.group(0)
    p = urllib.parse.urlparse(raw)
    if "xiaohongshu.com" not in p.netloc:
        raise ValueError("不是小红书链接：%s" % raw)
    # /explore/<id> 或 /user/profile/<uid>/<id> 或 /discovery/item/<id>
    m = re.search(r'/(?:explore|discovery/item)/([0-9a-f]{24})', p.path)
    if not m:
        m = re.search(r'/user/profile/[0-9a-f]+/([0-9a-f]{24})', p.path)
    if not m:
        raise ValueError("无法从链接中识别笔记 ID：%s" % p.path)
    note_id = m.group(1)
    qs = urllib.parse.parse_qs(p.query)
    token = (qs.get("xsec_token") or [""])[0]
    source = (qs.get("xsec_source") or ["pc_user"])[0]
    if not token:
        # 没有 token 的链接（如直接复制的 explore 短链）也先试试
        return "https://www.xiaohongshu.com/explore/%s?xsec_source=%s" % (note_id, source), note_id, token
    return ("https://www.xiaohongshu.com/explore/%s?xsec_token=%s&xsec_source=%s"
            % (note_id, urllib.parse.quote(token, safe="="), source)), note_id, token


# ---------------------------------------------------------------- 元数据解析

_STATE_RE = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>', re.S)


def _state_note_ok(html, note_id):
    """判断 HTML 里的 state 是否已经包含该笔记的真实数据（而非登录墙）"""
    try:
        state = _extract_state(html)
    except Exception:
        return False
    detail = ((state.get("noteData") or {}).get("data")
              or (state.get("noteDetailMap") or {}).get(note_id, {}).get("note") or {})
    return bool(detail)


def _fetch_html_browser(page_url, note_id, wait_timeout=180, on_log=None):
    """Playwright 兜底：真实浏览器打开笔记页，绕过登录墙/风控。

    首次使用会弹出浏览器窗口，若遇到登录页按提示扫码登录一次即可，
    登录态保存在 xhs_profile/ 目录，之后全自动。
    """
    def log(msg):
        if on_log:
            on_log(msg)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport={"width": 1280, "height": 860},
            args=["--disable-blink-features=AutomationControlled"])
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + wait_timeout
            html = ""
            logged_hint = False
            while time.time() < deadline:
                html = page.content()
                if _state_note_ok(html, note_id):
                    log("[browser] 已取到笔记数据")
                    return html
                # 提示登录（只提示一次）
                if not logged_hint and ("login" in page.url or "登录" in (page.title() or "")):
                    log("[browser] 检测到登录墙，请在弹出的浏览器窗口里扫码登录（一次即可）...")
                    logged_hint = True
                time.sleep(2)
            return html   # 超时也返回最后内容，交给上层报错
        finally:
            ctx.close()


def _extract_state(html):
    m = _STATE_RE.search(html)
    if not m:
        raise RuntimeError("页面里没有 __INITIAL_STATE__（可能被登录墙拦截）")
    txt = m.group(1)
    # JS 里的 undefined 不是合法 JSON，替换成 null
    txt = re.sub(r'\bundefined\b', 'null', txt)
    return json.loads(txt)


def parse_note(raw_url, on_log=None):
    """解析笔记，返回 {id,url,title,desc,type,author,images,video}

    先用纯 HTTP 抓取（快）；被登录墙拦截时自动回退 Playwright 真实浏览器。
    """
    page_url, note_id, _token = normalize_url(raw_url)

    def _log(msg):
        if on_log:
            on_log(msg)

    html = ""
    try:
        html = fetch_text(page_url)
    except Exception as e:
        _log("[http] 直连失败：%r，改用浏览器" % e)
    if html and not _state_note_ok(html, note_id):
        _log("[http] 被登录墙拦截，启动浏览器兜底 ...")
        html = _fetch_html_browser(page_url, note_id, on_log=on_log)
    if not html:
        raise RuntimeError("页面内容为空，无法解析")

    state = _extract_state(html)
    detail = ((state.get("noteData") or {}).get("data")
              or (state.get("noteDetailMap") or {}).get(note_id, {}).get("note") or {})
    if not detail:
        raise RuntimeError("未取到笔记数据（笔记可能已删除/私密，或被登录墙拦截）")

    user = detail.get("user") or {}
    images = []
    for img in (detail.get("imageList") or []):
        urls = _clean_image_urls(img)
        if urls:
            images.append(urls)
    video_url = _clean_video_url(detail.get("video") or {})

    return {
        "id": detail.get("noteId") or note_id,
        "url": page_url,
        "type": detail.get("type") or ("video" if video_url else "normal"),
        "title": (detail.get("title") or "").strip(),
        "desc": (detail.get("desc") or "").strip(),
        "author": user.get("nickname") or user.get("nickName") or "",
        "time": detail.get("time") or "",
        "images": images,       # 每张图一个候选 URL 列表（按优先级排序）
        "video": video_url,     # 无水印视频直链（可能为 None）
    }


def _clean_image_urls(img):
    """返回一张图的候选 URL：优先无水印原图（sns-img-hw），再回退页面展示图"""
    cands = []
    # 1) imageId 拼原图直链（最干净：无水印、无缩放参数）
    for key in ("imageId", "id"):
        iid = (img.get(key) or "").strip()
        if iid:
            cands.append("https://sns-img-hw.xhscdn.com/%s" % iid)
            cands.append("https://sns-img-qc.xhscdn.com/%s" % iid)
            break
    # 2) urlDefault / infoList 兜底
    u = img.get("urlDefault") or img.get("url") or ""
    if u:
        cands.append(u)
        # urlDefault 若带 ！场景后缀，去掉后缀也常是原图
        base = u.split("!")[0]
        if base != u and "/sns-webpic" in base or "/ci.xiaohongshu" in base:
            cands.append(base)
    for info in (img.get("infoList") or []):
        iu = (info.get("url") or "").strip()
        if iu and iu not in cands:
            cands.append(iu)
    # 去重保序
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _clean_video_url(video):
    """提取无水印视频直链：h264 优先（兼容性最好）"""
    media = video.get("media") or video
    for key in ("videoH264List", "videoH265List"):
        for s in (media.get(key) or []):
            if isinstance(s, str) and s:
                return s
            if isinstance(s, dict):
                u = (s.get("masterUrl") or s.get("url") or "").strip()
                if u:
                    return u
    # 旧结构兜底：stream.h264[0].masterUrl
    stream = media.get("stream") or {}
    for key in ("h264", "h265", "av1"):
        for s in (stream.get(key) or []):
            u = (s.get("masterUrl") or "").strip()
            if u:
                return u
    return None


# ---------------------------------------------------------------- 下载

def _safe_name(name, maxlen=30):
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', " ", name)
    name = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return (name[:maxlen].strip() or "untitled")


def download_note(raw_url, outdir=None, on_log=print):
    """解析并下载一篇笔记的无水印媒体，返回 {meta, files}"""
    meta = parse_note(raw_url, on_log=on_log)
    title = _safe_name(meta["title"] or meta["desc"] or "untitled")
    if outdir is None:
        outdir = os.path.join(ROOT, "xhs_downloads", "%s_%s" % (meta["id"], title))
    os.makedirs(outdir, exist_ok=True)

    files = []
    if meta["type"] == "video" and meta["video"]:
        dest = os.path.join(outdir, "video.mp4")
        size = _try_download(meta["video"], dest, referer=meta["url"])
        if size:
            files.append(dest)
            if on_log:
                on_log("[OK] video.mp4  %dKB" % (size // 1024))
    for i, cands in enumerate(meta["images"]):
        dest = os.path.join(outdir, "img_%02d.jpg" % (i + 1))
        size = 0
        for u in cands:
            size = _try_download(u, dest, referer=meta["url"])
            if size:
                break
        if size:
            files.append(dest)
            if on_log:
                on_log("[OK] img_%02d.jpg  %dKB" % (i + 1, size // 1024))
        else:
            if on_log:
                on_log("[FAIL] img_%02d.jpg 全部候选地址失败" % (i + 1))
    return {"meta": meta, "files": files, "outdir": outdir}


def _try_download(url, dest, referer=None):
    try:
        return fetch(url, dest, referer=referer)
    except Exception:
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except Exception:
            pass
        return 0


# ---------------------------------------------------------------- CLI

def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    url = argv[1]
    outdir = argv[2] if len(argv) > 2 else None
    result = download_note(url, outdir)
    meta = result["meta"]
    print("\n标题: %s" % (meta["title"] or "(无标题)"))
    print("作者: %s" % meta["author"])
    print("类型: %s  图片 %d 张  视频 %s" % (
        meta["type"], len(meta["images"]), "有" if meta["video"] else "无"))
    print("保存目录: %s" % result["outdir"])
    print("成功文件: %d 个" % len(result["files"]))
    return 0 if result["files"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
