# -*- coding: utf-8 -*-
"""
截图模式 · JSON → 微信聊天截图 PNG
====================================
「微信聊天截图」生成器：一段 JSON 对话 → 一张正宗微信样式的聊天截图（PNG）。

与长图模式的关系：**共用同一个渲染引擎** `wx_export.run_once`（驱动 vue-WeChat 仿真页
排版、DOM 坐标真值、支持 text/image/emoji/voice/link），本模块只负责：

  1. schema 归一：截图版 JSON（people / messages / options）→ wx_export 的 cfg
  2. 人物解引用：`preset:花店店主·林晚晚` → peer_presets.json；裸名 → people.json
  3. 素材解析：短名（`偷笑` / `哭泣猫咪` / `s011_01.jpg`）→ 内置素材库真实 URL
  4. 出图选项：状态栏/顶栏开关、未读角标、聊天背景、出图倍率、裁剪、文件名
  5. 出 PNG（截图模式不出点评行/CTA/音乐，与视频线完全解耦）

用法（必须用装了 playwright 的系统 Python）：
    py 长图模式/shot_export.py --config 对话.json --out-dir 输出目录 --tag 我的批次
前提：vue-WeChat 前端在 8080 跑着（跑一次 启动.bat 即可）。
"""
import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DIR = os.path.join(ROOT, "长图模式")
PUBLIC = os.path.join(ROOT, "vue-WeChat", "public")
SHOT_DIR = os.path.join(PUBLIC, "shots")
if MOD_DIR not in sys.path:
    sys.path.insert(0, MOD_DIR)

import wx_export                                        # noqa: E402

# 短名素材的搜索目录（按优先级）：表情包 → 苹果 emoji → 微信小表情 → 随手拍图集 → 链接卡缩略图
ASSET_DIRS = ["images/sticker", "images/emoji", "images/wxemoji", "images/wxemoji3d",
              "images/sets2", "images/link", "images/avatar", "images/bg"]

_emoji_map_cache = None
_people_cache = None


# ---------------------------------------------------------------- 数据读取

def _load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default if default is not None else {}


def load_people():
    """合并两份人物资料：people.json（分组名→头像）+ peer_presets.json（完整人设）。"""
    global _people_cache
    if _people_cache is None:
        people = _load_json(os.path.join(ROOT, "people.json"), {})
        groups = {}
        if isinstance(people, dict):
            for g, items in people.items():
                if isinstance(items, dict):
                    groups[g] = dict(items)
        presets = _load_json(os.path.join(ROOT, "peer_presets.json"), {}).get("presets") or {}
        _people_cache = {"groups": groups, "presets": presets}
    return _people_cache


def load_emoji_map():
    """enhance/emoji_map.js 的「词 → 苹果 emoji 编码」表（词=开心/哈哈…）。"""
    global _emoji_map_cache
    if _emoji_map_cache is None:
        _emoji_map_cache = {}
        fp = os.path.join(ROOT, "enhance", "emoji_map.js")
        try:
            with open(fp, "r", encoding="utf-8") as f:
                txt = f.read()
            m = re.search(r"window\.__WX_EMOJI\s*=\s*(\{.*\})\s*;?\s*$", txt.strip(),
                          re.S)
            if m:
                data = json.loads(m.group(1))
                for k, v in data.items():
                    if isinstance(v, dict) and v.get("code"):
                        _emoji_map_cache[k] = v["code"]
        except (OSError, ValueError):
            pass
    return _emoji_map_cache


# ---------------------------------------------------------------- 解引用

def _uniq_name(name):
    """头像短名 → 唯一化：能唯一前缀匹配到内置头像就补全，不然原样返回。"""
    if not name:
        return ""
    s = str(name).strip()
    if s.startswith("/") or re.match(r"^https?://", s, re.I):
        return s
    if "/" in s or "\\" in s:
        return s.replace("\\", "/")
    hits = []
    for d in ASSET_DIRS:
        dd = os.path.join(PUBLIC, d.replace("/", os.sep))
        if not os.path.isdir(dd):
            continue
        for f in os.listdir(dd):
            if f.lower().startswith(s.lower()):
                hits.append("/%s/%s" % (d, f))
    return hits[0] if len(hits) == 1 else s


def resolve_asset(name):
    """素材短名 → 内置素材真实 URL。

    支持：完整 web 路径 / 短文件名（s011_01.jpg）/ 中文片段（哭泣猫咪）/ 词（偷笑）。
    找不到时原样返回（页面会破图，但不会中断出图），由调用方收集成 warnings。
    """
    s = (name or "").strip()
    if not s:
        return "", False
    if s.startswith("/") or re.match(r"^https?://", s, re.I):
        return s, True
    base = s.replace("\\", "/")
    for d in ASSET_DIRS:
        dd = os.path.join(PUBLIC, d.replace("/", os.sep))
        if not os.path.isdir(dd):
            continue
        files = os.listdir(dd)
        low = base.lower()
        for f in files:                                   # ① 完整文件名（忽略大小写）
            if f.lower() == low:
                return "/%s/%s" % (d, f), True
        for f in files:                                   # ② 名字里含这个词（哭泣猫咪→哭泣猫咪_….jpg）
            if low in f.lower() and os.path.splitext(f)[1].lower() in (
                    ".jpg", ".jpeg", ".png", ".gif", ".webp"):
                return "/%s/%s" % (d, f), True
    code = load_emoji_map().get(base.strip("[]"))         # ③ 「[偷笑]」这类词 → 苹果 emoji
    if code:
        fp = os.path.join(PUBLIC, "images", "emoji", code + ".png")
        if os.path.isfile(fp):
            return "/images/emoji/%s.png" % code, True
    return s, False


def resolve_person(spec):
    """人物 spec → {"name","avatar","wxid","area","signature"}。

    支持三种写法（三级解引用）：
      "preset:花店店主·林晚晚"   显式走 peer_presets.json（完整人设）
      "林晚晚"                  先查 peer_presets 同名，再查 people.json，最后当自定义名字
      {"name":"小雅","avatar":"dygirl_47.jpg","wxid":"xx"}   直接给字段
    """
    pp = load_people()
    presets, groups = pp["presets"], pp["groups"]
    out = {"name": "", "avatar": "", "wxid": "", "area": "", "signature": ""}

    def from_preset(key):
        p = presets.get(key)
        if p is None:                                     # 模糊：key 出现在人设名里
            for k, v in presets.items():
                if key and (key in k or k in key):
                    p = v
                    break
        if isinstance(p, dict):
            out["name"] = str(p.get("name") or key).strip()
            out["avatar"] = str(p.get("avatar") or "").strip()
            out["wxid"] = str(p.get("wxid") or "").strip()
            out["area"] = str(p.get("area") or "").strip()
            out["signature"] = str(p.get("signature") or "").strip()
            return True
        return False

    def from_people(key):
        for gname, items in groups.items():
            for nm, av in items.items():
                if nm == key:
                    out["name"] = key
                    out["avatar"] = str(av or "").strip()
                    return True
        for gname, items in groups.items():               # 模糊：包含关系
            for nm, av in items.items():
                if key and (key in nm or nm in key):
                    out["name"] = nm
                    out["avatar"] = str(av or "").strip()
                    return True
        return False

    if spec is None or spec == "":
        return out
    if isinstance(spec, dict):
        out["name"] = str(spec.get("name") or "").strip()
        out["avatar"] = str(spec.get("avatar") or "").strip()
        for k in ("wxid", "area", "signature"):
            out[k] = str(spec.get(k) or "").strip()
    else:
        key = str(spec).strip()
        if re.match(r"^preset\s*[:：]", key, re.I):
            from_preset(re.sub(r"^preset\s*[:：]", "", key, flags=re.I).strip())
        elif not (from_people(key) or from_preset(key)):
            out["name"] = key                              # 自定义名字：头像留空走默认
    out["avatar"] = _uniq_name(out["avatar"])
    return out


# ---------------------------------------------------------------- schema 归一

def _iter_messages(cfg):
    """对话条目：优先 messages[]（截图版），兼容 blocks[]（长图模式写法）。"""
    src = cfg.get("messages")
    legacy = False
    if not isinstance(src, list) or not src:
        src = cfg.get("blocks") or []
        legacy = True
    for it in src:
        if not isinstance(it, dict):
            continue
        side = str(it.get("from") or it.get("side") or "peer").strip().lower()
        side = "me" if side in ("me", "self", "我", "我方", "right") else "peer"
        yield side, it, legacy


def message_to_block(side, it, warnings):
    """一条对话 → wx_export 的 block（含 kind）。返回 None = 这条无效，跳过。"""
    kind = (it.get("kind") or "").strip().lower()
    text = str(it.get("text") or "").strip()
    if not kind:
        if it.get("image") or it.get("img"):
            kind = "image"
        elif it.get("emoji"):
            kind = "emoji"
        elif it.get("voice") or it.get("seconds"):
            kind = "voice"
        elif it.get("link"):
            kind = "link"
        else:
            kind = "text"
    b = {"side": side, "kind": kind}
    if it.get("time"):
        b["time"] = it["time"]
    if kind == "text":
        if not text:
            return None
        b["text"] = text
    elif kind == "image":
        url, ok = resolve_asset(it.get("image") or it.get("img"))
        if not url:
            return None
        if not ok:
            warnings.append("图片素材没找到，原样上屏: %s" % url)
        b["img"] = url
    elif kind == "emoji":
        url, ok = resolve_asset(it.get("emoji"))
        if not ok:
            warnings.append("表情素材没找到，原样上屏: %s" % url)
        b["emoji"] = url or "/images/sticker/cat_01.jpg"
    elif kind == "voice":
        try:
            b["voice"] = max(1, int(float(it.get("voice") or it.get("seconds") or 1)))
        except (TypeError, ValueError):
            b["voice"] = 1
    elif kind == "link":
        lk = it.get("link") if isinstance(it.get("link"), dict) else {}
        img, ok = resolve_asset(lk.get("image") or it.get("image") or "")
        if lk.get("image") and not ok:
            warnings.append("链接卡缩略图没找到，原样上屏: %s" % img)
        b["link"] = {"title": str(lk.get("title") or text or "").strip(),
                     "image": img, "source": str(lk.get("source") or "").strip()}
    return b


def shot_to_export(cfg):
    """截图版 JSON → wx_export 的 cfg。返回 (cfg, warnings)。"""
    warnings = []
    cfg = cfg or {}
    people = cfg.get("people") or {}
    meta = cfg.get("meta") or {}                       # 兼容长图模式的 meta 写法

    peer = resolve_person(people.get("peer") if people else None)
    me = resolve_person(people.get("me") if people else None)
    peer_name = (peer["name"] or str(meta.get("peer_name") or "").strip() or "朋友")
    peer_avatar = peer["avatar"] or str(meta.get("peer_avatar") or "").strip()
    my_avatar = me["avatar"] or str(meta.get("my_avatar") or "").strip()
    my_name = me["name"] or str(meta.get("my_name") or "").strip()

    blocks = []
    for side, it, legacy in _iter_messages(cfg):
        if legacy:
            blk = {"side": side, "text": str(it.get("text") or "").strip(),
                   "img": str(it.get("img") or it.get("image") or "").strip()}
            if not blk["text"] and not blk["img"]:
                continue
            if it.get("time"):
                blk["time"] = it["time"]
        else:
            blk = message_to_block(side, it, warnings)
            if blk is None:
                continue
        blocks.append(blk)

    if not blocks:
        raise ValueError("对话为空：至少写一条消息（messages 里的一条 text）")

    src = {"peer_name": peer_name, "peer_avatar": peer_avatar}
    if my_name:
        src["my_name"] = my_name
    if my_avatar:
        src["my_avatar"] = my_avatar
    return {"meta": src, "blocks": blocks}, warnings


def shot_options(cfg):
    """截图版 options → wx_export.run_once 的 opts + 出图参数。

    模式（options.mode，二选一）：
      short （默认）短截图：只出聊天消息区——不画状态栏/顶栏，自动裁掉底部空白
      full          全屏截图：完整手机屏（iOS 状态栏 + 微信顶栏齐全，满屏高度）
    旧写法兼容：chrome.statusbar / chrome.header / trim 显式给出时，覆盖模式默认值。
    """
    cfg = cfg or {}
    o = cfg.get("options") if isinstance(cfg.get("options"), dict) else {}
    chrome = o.get("chrome") if isinstance(o.get("chrome"), dict) else {}
    mode = str(o.get("mode") or "").strip().lower()
    if mode in ("full", "fullscreen", "full_screen", "全屏"):
        mode = "full"
    elif not mode:                       # 无 mode 时按旧 chrome 写法推断（都开着=全屏）
        mode = "full" if (chrome.get("statusbar") is True
                          and chrome.get("header") is True) else "short"
    else:
        mode = "short"

    def _shown(key):
        if key in chrome and chrome[key] is not None:    # 显式指定优先
            return bool(chrome[key])
        return mode == "full"

    opts = {
        "hide_statusbar": not _shown("statusbar"),
        "hide_header": not _shown("header"),
    }
    badge = o.get("badge", None)
    if badge is not None:                        # None = 不动默认的 99 胶囊
        opts["badge"] = "" if str(badge).strip() in ("", "none", "0") else str(badge).strip()
    bg = (o.get("wallpaper") or "").strip()
    if bg and bg.lower() not in ("default", "none"):
        url, ok = resolve_asset(bg)
        opts["bg"] = url
    trim = bool(o["trim"]) if "trim" in o else (mode == "short")
    info = {
        "scale": o.get("scale"),
        "filename": str(o.get("filename") or "").strip(),
        "trim": trim,
        "note_style": bool(o.get("note_style")),
        "mode": mode,
    }
    return opts, info


# ---------------------------------------------------------------- 出图

def _safe_stem(s):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(s or "").strip())
    return s[:60] or time.strftime("shot_%m%d_%H%M%S")


def render_shot(cfg, out_dir=None, tag=None, want_manifest=False, log=print):
    """截图版 JSON → PNG。返回 (png路径, info)；失败抛异常。"""
    exp_cfg, warnings = shot_to_export(cfg)
    opts, oinfo = shot_options(cfg)
    out_dir = out_dir or SHOT_DIR
    os.makedirs(out_dir, exist_ok=True)
    stem = _safe_stem(oinfo["filename"] or tag or time.strftime("shot_%m%d_%H%M%S"))
    png = os.path.join(out_dir, stem + ".png")

    if not wx_export._port_open(wx_export.PORT):
        raise RuntimeError("前端 8080 未运行：先跑一次软件（main.py / 启动.bat）把仿真页面拉起来")

    # 第一遍 dsf=1 量高度 → 定倍率 → 第二遍正式出图（与长图模式同策略）
    probe = os.path.join(out_dir, "_probe_" + stem + ".png")
    data, h_css = wx_export.run_once(exp_cfg, 1, probe, opts)
    try:
        os.remove(probe)
    except OSError:
        pass
    if oinfo["scale"]:
        try:
            dsf = max(1, min(4, int(oinfo["scale"])))
        except (TypeError, ValueError):
            dsf = 1
    else:
        dsf = max(1, min(3, int(wx_export.MAX_SHOT_PX // max(1, h_css))))
    if dsf < 3:
        log("[提示] 截图较高（%dpx），倍率降为 %dx" % (h_css, dsf))

    run_opts = dict(opts)
    data, h_css = wx_export.run_once(exp_cfg, dsf, png, run_opts)

    info = {"name": os.path.basename(png), "path": png, "scale": dsf,
            "count": len(exp_cfg["blocks"]), "warnings": warnings,
            "width": wx_export.VIEW_W * dsf}
    try:
        from PIL import Image
        with Image.open(png) as im:
            w, h = im.size
            if oinfo["trim"] and data.get("section"):
                # 裁到消息区底部 + 留白（短对话截图不要拖一大截空白）
                cut = int((data["items"][-1].get("note") or data["items"][-1].get("row")
                           or {}).get("y1", 0) * dsf) + 60 * dsf
                cut = max(400, min(h, cut))
                if cut < h:
                    im.crop((0, 0, w, cut)).save(png)
                    h = cut
            info["width"], info["height"] = w, h
        info["kbytes"] = int(os.path.getsize(png) / 1024)
    except Exception as e:                                     # noqa: BLE001
        log("[警告] 读取成品尺寸失败: %s" % e)

    # 源 JSON 就地存一份：截图库靠它做「复跑 / 改一版」
    try:
        with open(os.path.join(out_dir, stem + ".source.json"), "w",
                  encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
    except OSError:
        pass

    if want_manifest:
        mf = {"image": os.path.relpath(png, ROOT).replace("\\", "/"),
              "css_width": wx_export.VIEW_W, "dsf": dsf,
              "width_px": info.get("width", 0), "section": data.get("section"),
              "items": data.get("items") or [], "ending": data.get("ending")}
        with open(os.path.join(out_dir, stem + ".manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump(mf, f, ensure_ascii=False, indent=1)
        info["manifest"] = stem + ".manifest.json"
    log("[完成] 截图: %s (%sx%s, %dx)" % (png, info.get("width"), info.get("height"), dsf))
    return png, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="截图 JSON 文件")
    ap.add_argument("--out-dir", default=SHOT_DIR)
    ap.add_argument("--tag", default="")
    ap.add_argument("--manifest", action="store_true", help="额外输出消息矩形清单")
    args = ap.parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    render_shot(cfg, args.out_dir, args.tag, want_manifest=args.manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
