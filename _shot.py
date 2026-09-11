# -*- coding: utf-8 -*-
"""临时工具：按 main.py 的注入顺序渲染朋友圈页并截图，用于与参考视频逐帧对比。

用法:
    py _shot.py                 # 截图到 _shot/now.png
    py _shot.py --scroll 420    # 先滚动 420px 再截图
    py _shot.py --cmp f_012     # 与 _ref_frames/f_012.png 并排拼图输出 _shot/cmp.png
"""
import os
import sys
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")
OUT = os.path.join(BASE, "_shot")
VW, VH = 600, 1300

CSS_ORDER = [
    "harmony_font.css", "keyboard.css", "iphone_frame.css", "weui_tokens.css",
    "wechat_modern.css", "human_actions.css", "transfer_ui.css",
    "send_image_ui.css", "peer_pages.css", "video_player.css",
    "homepage_exact.css", "wx_icons.css", "moments_exact.css",
]
JS_ORDER = [
    "config.js", "chat_extra.js", "moments_extra.js", "iphone_frame.js",
    "wxemoji_map.js", "emoji_map.js", "transfer_ui.js", "send_image_ui.js",
    "video_player.js", "peer_pages.js",
]


def read(name):
    p = os.path.join(ENH, name)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scroll", type=int, default=0)
    ap.add_argument("--cmp", default=None, help="参考帧名，如 f_012")
    ap.add_argument("--out", default="now")
    ap.add_argument("--dsf", type=int, default=1)
    ap.add_argument("--just-moments", action="store_true")
    ap.add_argument("--scene", default="scene.json")
    ap.add_argument("--align", type=int, default=0, help="把第 N 条动态滚到距画布顶部 300px")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        br = pw.chromium.launch(headless=True,
                                executable_path=chrome if os.path.isfile(chrome) else None)
        ctx = br.new_context(viewport={"width": VW, "height": VH},
                             device_scale_factor=args.dsf,
                             user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
                             is_mobile=True, has_touch=True, locale="zh-CN")
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
        page.add_style_tag(content=".welcome { display: none !important; }")
        for n in CSS_ORDER:
            c = read(n)
            if c:
                page.add_style_tag(content=c)
            else:
                print("  (skip css)", n)
        for n in JS_ORDER:
            c = read(n)
            if c:
                page.evaluate(c)
            else:
                print("  (skip js)", n)
        page.wait_for_timeout(800)
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(300)
        sc = os.path.join(BASE, args.scene)
        if os.path.isfile(sc):
            with open(sc, "r", encoding="utf-8") as fh:
                page.evaluate("(s) => window.__wxConfig && window.__wxConfig.applyScene(s)",
                              json.load(fh))
        page.wait_for_timeout(300)
        page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
        # 重新注入（SPA 路由不刷新页面时样式仍在；此处确保 config 生效）
        page.wait_for_timeout(1200)
        if args.align:
            page.evaluate('''(n) => {
                const el = document.getElementById('moments');
                const posts = document.querySelectorAll('#moments .moments__post');
                if (posts[n-1]) {
                    const top = posts[n-1].getBoundingClientRect().top;
                    el.scrollTop = (el.scrollTop || 0) + top - 300;
                }
            }''', args.align)
            page.wait_for_timeout(500)
        if args.scroll:
            page.evaluate("(y) => { const e=document.getElementById('moments'); "
                          "const s=e.querySelector('.moments-scroll')||e; s.scrollTop=y; }",
                          args.scroll)
            page.wait_for_timeout(500)
        path = os.path.join(OUT, args.out + ".png")
        # 转场/合成器可能还没稳定，先空拍一帧丢掉，再拍正式帧
        page.wait_for_timeout(900)
        page.screenshot(path=path + ".warm.png")
        page.wait_for_timeout(500)
        page.screenshot(path=path)
        print("shot:", path)
        box = page.evaluate("""() => {
            const r = {};
            const q = (s) => document.querySelector(s);
            const bb = (el) => { if(!el) return null; const b=el.getBoundingClientRect();
                return {x:+b.x.toFixed(1),y:+b.y.toFixed(1),w:+b.width.toFixed(1),h:+b.height.toFixed(1)}; };
            r.nav = bb(q('#moments #wx-header'));
            r.cover = bb(q('#moments .home-pic'));
            r.av = bb(q('#moments .top-pic'));
            r.name = bb(q('#moments .top-name'));
            const p = q('#moments .moments__post');
            r.post = bb(p);
            r.postAvatar = bb(p && p.querySelector('.weui-cell__hd img'));
            r.postTitle = bb(p && p.querySelector('.title'));
            r.para = bb(p && p.querySelector('.paragraph'));
            r.thumb = bb(p && p.querySelector('.thumbnail'));
            r.ts = bb(p && p.querySelector('.timestamp'));
            r.tog = bb(p && p.querySelector('.actionToggle'));
            r.scrollH = (q('#moments')||{}).scrollHeight;
            r.posts = Array.from(document.querySelectorAll('#moments .moments__post')).map(bb);
            r.fold = Array.from(document.querySelectorAll('#moments .paragraph-wrap')).map(w => w.className);
            r.ext = Array.from(document.querySelectorAll('#moments .paragraphExtender')).map(a => a.textContent);
            r.st = (q('#moments')||{}).scrollTop;
            r.navA = getComputedStyle(q('#moments')).getPropertyValue('--nav-a');
            return r;
        }""")
        print(json.dumps(box, ensure_ascii=False, indent=1))
        br.close()

    if args.cmp:
        from PIL import Image
        ref = Image.open(os.path.join(BASE, "_ref_frames", args.cmp + ".png")).convert("RGB")
        cur = Image.open(path).convert("RGB")
        h = 1000
        ref = ref.resize((int(ref.width * h / ref.height), h), Image.LANCZOS)
        cur = cur.resize((int(cur.width * h / cur.height), h), Image.LANCZOS)
        canvas = Image.new("RGB", (ref.width + cur.width + 12, h), (40, 40, 40))
        canvas.paste(ref, (0, 0))
        canvas.paste(cur, (ref.width + 12, 0))
        cp = os.path.join(OUT, "cmp.png")
        canvas.save(cp)
        print("cmp:", cp)


if __name__ == "__main__":
    main()
