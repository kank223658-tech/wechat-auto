# -*- coding: utf-8 -*-
"""图片库改造冒烟：后端分类/批量接口 + 选图弹窗的「记忆分类/计数/多选/拖拽/分类管理」。

跑法：先起编辑器服务（py editor_server.py --port 8765），再 `py _smoke_gallery.py`。
结束会把自己造的测试图/测试分类清理干净，并还原改过的分类显示名。
"""
import base64
import io
import json
import sys
import urllib.request

BASE = "http://localhost:8765"
OK = 0
BAD = 0


def req(path, payload=None, method=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if data else "GET"),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check(name, cond, extra=""):
    global OK, BAD
    if cond:
        OK += 1
        print("[ok]   %s %s" % (name, extra))
    else:
        BAD += 1
        print("[FAIL] %s %s" % (name, extra))


# 1×1 透明 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")
DATA_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()

print("=" * 68)
print("一、后端：分类可改名 / 可新增")
print("=" * 68)
g = req("/api/gallery")
cats = g.get("categories") or []
check("分类清单带 canUpload 标记", all("canUpload" in c for c in cats),
      "-> " + ", ".join("%s(%s)" % (c["key"], "可上传" if c["canUpload"] else "只读") for c in cats))
check("计数下发", isinstance(g.get("counts"), dict) and g["counts"].get("__all") == len(g["files"]),
      "-> 全部 %s 张" % g["counts"].get("__all"))

old_label = next(c["label"] for c in cats if c["key"] == "asset")
r = req("/api/gallery/category", {"op": "rename", "key": "asset", "label": "配图素材2"})
check("改分类显示名", r.get("ok") and any(c["label"] == "配图素材2" for c in r["gallery"]["categories"]))
r = req("/api/gallery/category", {"op": "rename", "key": "asset", "label": old_label})
check("显示名改回", r.get("ok") and any(c["label"] == old_label and c["key"] == "asset"
                                      for c in r["gallery"]["categories"]))

r = req("/api/gallery/category", {"op": "add", "label": "冒烟测试分类"})
new_key = (r.get("category") or {}).get("key") if isinstance(r.get("category"), dict) else None
check("新增自定义分类", bool(r.get("ok") and new_key), "-> key=%s" % new_key)
check("新分类出现在清单里且可上传",
      any(c["key"] == new_key and c.get("canUpload") for c in r["gallery"]["categories"]))

print("=" * 68)
print("二、后端：上传到新分类 -> 批量搬运 -> 批量删除")
print("=" * 68)
r = req("/api/upload-image", {"data": DATA_URL, "name": "smoke_gallery_test", "category": new_key})
p1 = r.get("path") or ""
check("上传进自定义分类", r.get("ok") and ("/" + str(new_key) + "/") in p1, "-> " + p1)

r = req("/api/gallery/batch", {"op": "move", "paths": [p1], "category": "sticker"})
moved = (r.get("results") or [{}])[0]
p2 = moved.get("newPath") or ""
check("批量接口搬单张（自定义分类 -> 表情包）", r.get("ok") and moved.get("ok") and "/sticker/" in p2, "-> " + p2)

r = req("/api/gallery/batch", {"op": "move", "paths": [p2], "category": "asset"})
moved2 = (r.get("results") or [{}])[0]
p3 = moved2.get("newPath") or ""
check("再搬一次（表情包 -> 配图素材）", r.get("ok") and moved2.get("ok") and "/asset/" in p3, "-> " + p3)

r = req("/api/gallery/batch", {"op": "delete", "paths": [p3]})
check("批量删除", r.get("ok") and r.get("done") == 1 and r.get("failed") == 0)
check("删除后图库里已经没有它", p3 not in (req("/api/gallery").get("images") or []))

r = req("/api/gallery/category", {"op": "remove", "key": new_key})
check("删掉测试分类", r.get("ok") and not any(c["key"] == new_key for c in r["gallery"]["categories"]))
try:
    req("/api/gallery/category", {"op": "remove", "key": "avatar"})
    check("内置分类不允许删除", False)
except Exception as e:                                   # noqa: BLE001
    check("内置分类不允许删除", "内置分类不能删除" in str(e) or "400" in str(e))

print("=" * 68)
print("三、前端：选图弹窗（记忆分类 / 张数 / 多选 / 分类管理）")
print("=" * 68)
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[skip] 本机 Python 没有 playwright，跳过界面部分")
    print("\n后端小结：通过 %d，失败 %d" % (OK, BAD))
    sys.exit(1 if BAD else 0)

errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    pg = br.new_page(viewport={"width": 1680, "height": 1050})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console.%s: %s" % (m.type, m.text)) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.dismiss())
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.wait_for_function("() => !!window.__wxPick")
    pg.evaluate("() => { try { localStorage.removeItem('wxp-picker-cat'); } catch(e){} }")

    # 第一次打开（没有记忆）→ 应默认停在「配图素材」
    pg.evaluate("() => window.__wxPick.openPicker({})")
    pg.wait_for_selector(".wxp-mask.show .wxp-typebtn", timeout=8000)
    pg.wait_for_timeout(900)
    active = pg.evaluate("() => (document.querySelector('.wxp-typebtn.on')||{}).getAttribute('data-cat')")
    check("首次打开默认停在「配图素材」(asset)", active == "asset", "-> 实际 %r" % active)
    cnt = pg.evaluate("""() => {
        const b = document.querySelector('.wxp-typebtn.on .wxp-cnt');
        return b ? b.textContent : '';
    }""")
    check("分类按钮上显示张数", bool(cnt) and cnt.isdigit(), "-> 配图素材 %s 张" % cnt)
    check("有「多选」按钮", pg.evaluate("() => !!document.getElementById('wxp-multibtn')"))
    check("有「⚙ 分类」按钮", pg.evaluate("() => !!document.getElementById('wxp-catbtn')"))
    check("有排序下拉且已填选项",
          pg.evaluate("() => (document.querySelector('#wxp-sort')||{}).options && document.querySelector('#wxp-sort').options.length >= 3"))
    check("有拖入提示", pg.evaluate("() => !!document.querySelector('.wxp-drophint')"))
    pg.screenshot(path="_shot/gallery_picker_default.png")

    # 记忆：切到 emoji，关掉，再打开应还在 emoji
    pg.evaluate("() => document.querySelector('.wxp-typebtn[data-cat=\\\"emoji\\\"]').click()")
    pg.wait_for_timeout(300)
    pg.evaluate("() => document.getElementById('wxp-cancel').click()")
    pg.wait_for_timeout(200)
    pg.evaluate("() => window.__wxPick.openPicker({})")
    pg.wait_for_selector(".wxp-mask.show .wxp-typebtn", timeout=8000)
    pg.wait_for_timeout(900)
    active2 = pg.evaluate("() => (document.querySelector('.wxp-typebtn.on')||{}).getAttribute('data-cat')")
    check("再次打开停在上次的分类 (emoji)", active2 == "emoji", "-> 实际 %r" % active2)
    upcat = pg.evaluate("() => (document.getElementById('wxp-upcat')||{}).value")
    check("上传目标分类跟着切到 emoji", upcat == "emoji", "-> %r" % upcat)

    # 多选 + 全选
    pg.evaluate("() => document.getElementById('wxp-multibtn').click()")
    pg.wait_for_timeout(200)
    pg.evaluate("() => [...document.querySelectorAll('#wxp-bulk button')].find(b => b.textContent.indexOf('全选当前') >= 0).click()")
    pg.wait_for_timeout(400)
    marked = pg.evaluate("() => document.querySelectorAll('.wxp-item.marked').length")
    check("多选：全选当前生效", marked > 5, "-> %d 张被勾选" % marked)
    has_move = pg.evaluate("() => !!document.getElementById('wxp-bulkmove') && !!document.getElementById('wxp-bulkdel')")
    check("批量条里有「整批移到分类」「删掉选中的」", has_move)
    pg.screenshot(path="_shot/gallery_picker_bulk.png")
    pg.evaluate("() => [...document.querySelectorAll('#wxp-bulk button')].find(b => b.textContent.indexOf('退出多选') >= 0).click()")
    pg.wait_for_timeout(200)

    # 分类管理
    pg.evaluate("() => document.getElementById('wxp-catbtn').click()")
    pg.wait_for_selector(".wxp-cm.show .wxp-cm-row", timeout=5000)
    rows = pg.evaluate("() => document.querySelectorAll('.wxp-cm-row').length")
    check("分类管理列出全部分类", rows >= 6, "-> %d 行" % rows)
    pg.screenshot(path="_shot/gallery_cat_manager.png")
    pg.evaluate("() => document.getElementById('wxp-cm-close').click()")

    # 拖拽：把一张缩略图拖到「背景」分类按钮上（用 HTML5 DnD 事件模拟）
    before = req("/api/gallery")
    first = next((f for f in before["files"] if f["category"] == "asset"), None)
    if first:
        pg.evaluate("() => document.getElementById('wxp-cancel').click()")
        pg.wait_for_timeout(200)
        pg.evaluate("() => window.__wxPick.openPicker({ category: 'asset' })")
        pg.wait_for_selector(".wxp-mask.show .wxp-item", timeout=8000)
        pg.wait_for_timeout(900)
        res = pg.evaluate("""(path) => {
            const item = [...document.querySelectorAll('.wxp-item')].find(x => x.getAttribute('data-val') === path);
            const chip = document.querySelector('.wxp-typebtn[data-cat="bg"]');
            if (!item || !chip) return 'missing';
            const dt = new DataTransfer();
            item.dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:dt}));
            chip.dispatchEvent(new DragEvent('dragover', {bubbles:true, cancelable:true, dataTransfer:dt}));
            chip.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt}));
            return 'sent';
        }""", first["path"])
        check("拖拽事件已发出", res == "sent", "-> " + str(res))
        pg.wait_for_timeout(2200)
        after = req("/api/gallery")
        moved_to_bg = any(f["path"].startswith("/images/bg/") and f["label"] == first["label"] for f in after["files"])
        check("拖到「背景」按钮上，图真的搬过去了", moved_to_bg)
        if moved_to_bg:
            # 搬回去，别动用户的库
            target = next(f["path"] for f in after["files"]
                          if f["path"].startswith("/images/bg/") and f["label"] == first["label"])
            back = req("/api/gallery/batch", {"op": "move", "paths": [target], "category": "asset"})
            check("测试图已搬回配图素材", bool((back.get("results") or [{}])[0].get("ok")),
                  "-> " + str((back.get("results") or [{}])[0].get("newPath")))

    pg.evaluate("() => document.getElementById('wxp-cancel').click()")
    br.close()

check("界面无 JS 报错", not errs, "-> " + ("; ".join(errs[:4]) if errs else "干净"))

print("\n" + "=" * 68)
print("小结：通过 %d，失败 %d" % (OK, BAD))
print("=" * 68)
sys.exit(1 if BAD else 0)
