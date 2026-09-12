# -*- coding: utf-8 -*-
"""冒烟：图片查看器「共享元素飞入/飞回」动画（human_actions.js）
在 8080 手机模拟器页面上注入查看器，造一张假缩略图，采样 .iv-img 的视口矩形：
  打开第一帧应≈缩略图矩形 → 末帧≈全屏 contain 尺寸（飞入）
  关闭过程应从当前态飞回缩略图矩形，结束时查看器 display:none
不碰页面其他状态，全部自建 DOM。
"""
import io
import json

RESULT = {"steps": [], "samples_open": [], "samples_close": []}

def _tiny_png_data_url():
    """生成 400x300 纯色 PNG 的 data URL（自包含，不依赖任何服务器素材）。"""
    import struct
    import zlib
    w, h = 400, 300
    raw = b"".join(b"\x00" + b"\xc8\x64\x32" * w for _ in range(h))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    return "data:image/png;base64," + __import__("base64").b64encode(png).decode()

def main():
    css = io.open("enhance/human_actions.css", encoding="utf-8").read()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 600, "height": 1300})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:8000/", wait_until="domcontentloaded")
        pg.add_style_tag(content=css)
        pg.add_script_tag(path="enhance/human_actions.js")
        pg.wait_for_function("() => !!window.__wxHuman && !!window.__wxHuman.openImage", timeout=8000)
        RESULT["steps"].append("viewer injected")

        src = _tiny_png_data_url()
        pg.evaluate("""(src) => {
            const im = document.createElement('img');
            im.id = 'smoke-thumb';
            im.src = src;
            im.style.cssText = 'position:fixed;left:40px;top:200px;width:120px;height:160px;object-fit:cover;z-index:50;';
            document.body.appendChild(im);
        }""", src)
        pg.wait_for_function("() => { const im = document.getElementById('smoke-thumb'); return im && im.complete && im.naturalWidth > 0; }", timeout=8000)
        thumb = pg.evaluate("() => { const r = document.getElementById('smoke-thumb').getBoundingClientRect(); return {l: r.left, t: r.top, w: r.width, h: r.height}; }")
        RESULT["thumb"] = thumb

        # 打开：飞入采样（MutationObserver 捕捉 transform 首次生效帧，避免 rAF 采样竞态）
        samples = pg.evaluate("""(src) => new Promise((res) => {
            const iv = document.querySelector('#imageViewer .iv-img');
            const out = [];
            const grab = () => {
                const r = iv.getBoundingClientRect();
                out.push({ w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left), y: Math.round(r.top) });
            };
            const mo = new MutationObserver(() => { if (out.length < 3) grab(); });
            mo.observe(iv, { attributes: true, attributeFilter: ['style'] });
            window.__wxHuman.openImage(src, null, {});
            const t0 = performance.now();
            const tick = () => {
                grab();
                if (performance.now() - t0 < 700) requestAnimationFrame(tick);
                else { mo.disconnect(); res(out); }
            };
            requestAnimationFrame(tick);
        })""", src)
        RESULT["samples_open"] = samples
        first, last = samples[0], samples[-1]
        def center(r):
            return (r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)
        def dist(a, b):
            return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        tc = (thumb["l"] + thumb["w"] / 2, thumb["t"] + thumb["h"] / 2)
        sc = (600 / 2, 1300 / 2)   # 屏幕中心 = 终态中心
        # 飞入起点 = 前几帧里最小的一帧（observer 必然晚于第一帧写入，允许少量进度）
        first = min(samples[:4], key=lambda r: r["w"])
        fc = center(first)
        assert first["w"] < thumb["w"] * 1.35, (first, thumb)          # 起点接近缩略图宽度
        assert dist(fc, tc) < dist(fc, sc) / 2, (first, thumb)          # 起点更贴近缩略图而非屏幕中心
        # 末帧显著变大（飞入完成）
        assert last["w"] > thumb["w"] * 2.2, (first, last)
        RESULT["steps"].append("fly-in OK: start %s -> end %s" % (first, last))

        # 等捏合跑一段（停 400ms），再关闭：飞回采样（轮询直到动画结束隐藏）
        pg.wait_for_timeout(400)
        samples2 = pg.evaluate("""() => new Promise((res) => {
            const iv = document.querySelector('#imageViewer .iv-img');
            const viewer = document.getElementById('imageViewer');
            const out = [];
            window.__wxHuman.closeImage();
            const tick = () => {
                if (viewer.style.display !== 'none') {
                    const r = iv.getBoundingClientRect();
                    out.push({ w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left), y: Math.round(r.top) });
                    if (out.length < 60) requestAnimationFrame(tick);
                }
                if (viewer.style.display === 'none' || out.length >= 60) res(out);
            };
            requestAnimationFrame(tick);
        })""")
        RESULT["samples_close"] = samples2
        f2, l2 = samples2[0], samples2[-1]
        assert l2["w"] < f2["w"], (f2, l2)            # 关闭过程中在变小
        lc = center(l2)
        assert dist(lc, tc) < 60, (l2, thumb)          # 收回到缩略图中心附近
        assert l2["w"] < thumb["w"] * 1.5, (l2, thumb)  # 末帧已缩回缩略图量级
        hidden = pg.evaluate("() => document.getElementById('imageViewer').style.display")
        assert hidden == "none", hidden
        RESULT["steps"].append("fly-back OK: %s -> %s, display=%s" % (f2, l2, hidden))

        # 兜底路径：无锚点打开（乱给一个不存在的 src）也应能打开/关闭
        pg.evaluate("() => window.__wxHuman.openImage('/images/bg/nonexist_missing.jpg', null, {})")
        pg.wait_for_timeout(120)
        opened = pg.evaluate("() => window.__wxHuman.isImageOpen()")
        assert opened, "fallback open failed"
        pg.evaluate("() => window.__wxHuman.closeImage()")
        pg.wait_for_timeout(400)
        assert not pg.evaluate("() => window.__wxHuman.isImageOpen()")
        RESULT["steps"].append("fallback open/close OK")

        # 只点开不放大：noZoom 路径 + anchorEl 直传
        pg.evaluate("""(src) => {
            const im = document.getElementById('smoke-thumb');
            window.__wxHuman.openImage(src, null, { noZoom: true, anchorEl: im });
        }""", src)
        pg.wait_for_timeout(120)
        assert pg.evaluate("() => window.__wxHuman.isImageOpen()")
        pg.evaluate("() => window.__wxHuman.closeImage()")
        pg.wait_for_timeout(400)
        RESULT["steps"].append("noZoom + anchorEl path OK")

        assert not errors, errors
        RESULT["ok"] = True
        b.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        RESULT["error"] = repr(e)
    print(json.dumps(RESULT, ensure_ascii=False, indent=1))
