# -*- coding: utf-8 -*-
"""临时探针：量「我的朋友圈」的配图排版几何 + 图片查看器开关耗时。

用法:
    py _probe_moments.py                      # 只量几何
    py _probe_moments.py --timing             # 几何 + 开关耗时
    py _probe_moments.py --timing --dsf 2     # 用 DPR2 量（更接近成片）
    py _probe_moments.py --shot               # 顺便截一张到 _shot/probe.png
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

GEOM_JS = r"""
() => {
  const posts = Array.from(document.querySelectorAll('#moments .moments__post'));
  const bb = (el) => { const b = el.getBoundingClientRect();
    return [ +b.x.toFixed(1), +b.y.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1) ]; };
  return posts.map((p, i) => {
    const bd = p.querySelector('.weui-cell__bd');
    const gal = p.querySelector('.thumbnails');
    const kids = gal ? Array.from(gal.children) : [];
    const tiles = [];
    const rows = [];
    kids.forEach(el => {
      const t = bb(el);
      tiles.push(t);
      let r = rows.find(x => Math.abs(x.y - t[1]) < 4);
      if (!r) { r = { y: t[1], tiles: [] }; rows.push(r); }
      r.tiles.push(t);
    });
    let style = null;
    if (gal) {
      const cs = getComputedStyle(gal);
      const c0 = kids.length ? getComputedStyle(kids[0]) : null;
      style = { display: cs.display, gap: cs.rowGap + '/' + cs.columnGap,
                flexWrap: cs.flexWrap, w: cs.width,
                tileW: c0 && c0.width, tileH: c0 && c0.height,
                tileMargin: c0 && (c0.marginTop + ' ' + c0.marginRight + ' ' + c0.marginBottom + ' ' + c0.marginLeft) };
    }
    return {
      i: i + 1,
      author: (p.querySelector('.wx-name') || {}).textContent || '',
      cls: gal ? gal.className : null,
      bd: bd ? bb(bd) : null,
      gal: gal ? bb(gal) : null,
      style: style,
      tiles: tiles,
      rows: rows.map(r => ({ n: r.tiles.length, x: r.tiles.map(t => t[0]), w: r.tiles.map(t => t[2]), h: r.tiles[0][3] })),
    };
  });
}
"""

# 打开计时：rAF 采样，记录「查看器出现 / 真实图片加载完 / 图片淡入完成 / UI 就绪」
OPEN_JS = r"""
([postIdx, imgIdx]) => new Promise(resolve => {
  const pswp = document.querySelector('.pswp');
  const t0 = performance.now();
  const rec = { marks: {} };
  const hit = (k, now) => { if (rec.marks[k] === undefined) rec.marks[k] = +(now).toFixed(1); };
  const sample = () => {
    const now = performance.now() - t0;
    if (pswp.classList.contains('pswp--open')) hit('open', now);
    const img = pswp.querySelector('.pswp__img:not(.pswp__img--placeholder)');
    if (img && img.complete && img.naturalWidth > 0) {
      hit('imgLoaded', now);
      if (getComputedStyle(img).opacity === '1') hit('imgShown', now);
    }
    const ph = pswp.querySelector('.pswp__img--placeholder');
    if (!ph) hit('placeholderGone', now);
    const ui = pswp.querySelector('.pswp__ui');
    if (ui && !ui.classList.contains('pswp__ui--hidden')) hit('uiShown', now);
    // 淡入曲线走完（333ms）就算稳定
    if (rec.marks.imgShown !== undefined && now - rec.marks.imgShown > 400) {
      rec.total = +now.toFixed(1); resolve(rec); return;
    }
    if (now > 8000) { rec.total = +now.toFixed(1); rec.timeout = true; resolve(rec); return; }
    requestAnimationFrame(sample);
  };
  window.__wxMoments.openImage(postIdx, imgIdx);
  requestAnimationFrame(sample);
})
"""

CLOSE_JS = r"""
() => new Promise(resolve => {
  const pswp = document.querySelector('.pswp');
  const t0 = performance.now();
  const rec = { marks: {} };
  const hit = (k, now) => { if (rec.marks[k] === undefined) rec.marks[k] = +(now).toFixed(1); };
  const btn = pswp.querySelector('.pswp__button--close');
  if (!btn) { resolve({ err: 'no close button' }); return; }
  btn.click();
  const sample = () => {
    const now = performance.now() - t0;
    if (!pswp.classList.contains('pswp--open')) hit('classOff', now);
    const st = getComputedStyle(pswp);
    if (st.display === 'none' || st.opacity === '0') hit('hidden', now);
    if (rec.marks.classOff !== undefined && now - rec.marks.classOff > 500) {
      rec.total = +now.toFixed(1); resolve(rec); return;
    }
    if (now > 5000) { rec.total = +now.toFixed(1); rec.timeout = true; resolve(rec); return; }
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
})
"""


def read(name):
    p = os.path.join(ENH, name)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="_probe_scene.json")
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--dsf", type=int, default=1)
    ap.add_argument("--shot", action="store_true")
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
        for n in JS_ORDER:
            c = read(n)
            if c:
                page.evaluate(c)
        page.wait_for_timeout(800)
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(300)
        sc = os.path.join(BASE, args.scene)
        if os.path.isfile(sc):
            with open(sc, "r", encoding="utf-8") as fh:
                page.evaluate("(s) => window.__wxConfig && window.__wxConfig.applyScene(s)",
                              json.load(fh))
        page.wait_for_timeout(400)
        page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        print("=" * 96)
        print("【一】配图排版几何（画布 600×1300, DPR=%d）" % args.dsf)
        print("=" * 96)
        geom = page.evaluate(GEOM_JS)
        for g in geom:
            bd = g["bd"]
            print("\n第%d条「%s」  className=%s" % (g["i"], g["author"], g["cls"]))
            if bd:
                print("   正文列 bd: x=%.1f w=%.1f  (右边界 x=%.1f)" % (bd[0], bd[2], bd[0] + bd[2]))
            if g["gal"]:
                gl = g["gal"]
                print("   配图容器 : x=%.1f y=%.1f w=%.1f h=%.1f" % tuple(gl))
            if g["style"]:
                s = g["style"]
                print("   style: display=%s gap=%s wrap=%s tile=%sx%s margin=%s"
                      % (s["display"], s["gap"], s["flexWrap"], s["tileW"], s["tileH"], s["tileMargin"]))
            for k, r in enumerate(g["rows"]):
                print("   第%d行: %d 张  x=%s w=%s h=%s" % (k + 1, r["n"], r["x"], r["w"], r["h"]))
            if bd and g["gal"]:
                over = (g["gal"][0] + g["gal"][2]) - (bd[0] + bd[2])
                print("   容器右溢出: %.1fpx %s" % (over, "← 溢出！" if over > 0.5 else ""))

        if args.shot:
            page.screenshot(path=os.path.join(OUT, "probe.png"), full_page=False)
            print("\nshot: _shot/probe.png")

        if args.timing:
            print("\n" + "=" * 96)
            print("【二】点开 / 退出图片的耗时（毫秒，从点击算起）")
            print("=" * 96)
            cases = [(1, 1, "2图-第1张"), (3, 1, "4图-第1张"),
                     (9, 1, "单图-9MB大图")]
            for pidx, iidx, label in cases:
                r = page.evaluate(OPEN_JS, [pidx, iidx])
                print("\n打开 %-14s %s" % (label, json.dumps(r, ensure_ascii=False)))
                page.wait_for_timeout(600)
                c = page.evaluate(CLOSE_JS)
                print("  关闭 %-12s %s" % ("", json.dumps(c, ensure_ascii=False)))
                page.wait_for_timeout(400)

        br.close()


if __name__ == "__main__":
    main()
