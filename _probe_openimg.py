# -*- coding: utf-8 -*-
"""探针：开图瞬间 PhotoSwipe 的几何关系。
实测：缩略图 rect、.pswp 定位、占位图起始 rect/transform、滚动位置是否被 scrollIntoView 改动。
"""
import json
import os
import time
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"G:\weixin-auto")
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")

def read(name):
    p = os.path.join(ENH, name)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None

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

POSTS = [
    {"author": "小星", "avatar": "/images/avatar/枯木_20260903_141720_316.jpg",
     "text": "九宫格。", "time": "2分钟前",
     "images": ["/images/avatar/学习急救班素材_20260908_155548_722.png"] * 9},
    {"author": "铁木君", "avatar": "/images/avatar/枯木_20260903_141720_316.jpg",
     "text": "四张图。", "time": "20分钟前",
     "images": ["/images/avatar/学习急救班素材_20260908_155548_722.png"] * 4},
    {"author": "月亮", "avatar": "/images/avatar/学习急救班素材_20260908_155548_722.png",
     "text": "单图。", "time": "1小时前",
     "images": ["/images/avatar/学习急救班素材_20260908_155548_722.png"]},
]

GRAB_JS = """() => {
  const out = {};
  const n = document.querySelector('#moments.sub-page');
  out.containerScroll = n ? n.scrollTop : null;
  out.winScroll = window.pageYOffset;
  const pswp = document.querySelector('.pswp');
  if (pswp) {
    const cs = getComputedStyle(pswp);
    const r = pswp.getBoundingClientRect();
    out.pswp = { position: cs.position, rect: [r.left, r.top, r.width, r.height],
                 offsetParent: pswp.offsetParent ? (pswp.offsetParent.id || pswp.offsetParent.className) : null };
  }
  const ph = document.querySelector('.pswp__img--placeholder') ||
             document.querySelector('.pswp__item .pswp__img');
  if (ph) {
    const r = ph.getBoundingClientRect();
    const cs = getComputedStyle(ph.parentElement);
    out.placeholder = { rect: [r.left, r.top, r.width, r.height],
                        parentCls: ph.parentElement.className,
                        parentTransform: cs.transform,
                        parentTransition: cs.transition };
  }
  return out;
}"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 600, "height": 1300}, device_scale_factor=3,
                            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)",
                            is_mobile=True, has_touch=True, locale="zh-CN")
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

    page.evaluate("(p) => window.__wxConfig.setMomentsPosts(p)", POSTS)
    page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
    page.add_style_tag(content=".welcome { display: none !important; }")
    page.wait_for_timeout(1200)
    page.evaluate("() => window.__wxMoments && window.__wxMoments.renderPosts(window.__wxConfig.getMomentsPosts())")
    page.wait_for_timeout(600)
    page.evaluate("() => window.__wxMomentsInitGallery && window.__wxMomentsInitGallery()")
    page.wait_for_timeout(300)

    page.evaluate("""() => {
        const n = document.querySelector('#moments.sub-page');
        const target = Math.min(n.scrollHeight - n.clientHeight, n.scrollTop + 420);
        const start = n.scrollTop, dist = target - start, t0 = performance.now();
        const step = (now) => { const p = Math.min(1, (now - t0) / 450);
            n.scrollTop = start + dist * (p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2);
            if (p < 1) requestAnimationFrame(step); };
        requestAnimationFrame(step);
    }""")
    page.wait_for_timeout(600)

    before = page.evaluate("""() => {
        const n = document.querySelector('#moments.sub-page');
        const posts = document.querySelectorAll('#moments .moments__post');
        const gal = posts[0].querySelector('.my-gallery');
        const figures = Array.prototype.filter.call(gal.children,
            (x) => x.nodeType === 1 && !x.classList.contains('video-thumb'));
        const img = figures[2].getElementsByTagName('img')[0];
        const r = img.getBoundingClientRect();
        return { containerScroll: n.scrollTop, thumbRect: [r.left, r.top, r.width, r.height] };
    }""")
    print("打开前: 容器滚动 =", before["containerScroll"], " 缩略图3 rect =", before["thumbRect"])

    info = page.evaluate("""(GRAB) => new Promise((resolve) => {
        const log = [];
        const grab = eval('(' + GRAB + ')');
        const posts = document.querySelectorAll('#moments .moments__post');
        const gal = posts[0].querySelector('.my-gallery');
        const figures = Array.prototype.filter.call(gal.children,
            (x) => x.nodeType === 1 && !x.classList.contains('video-thumb'));
        const img = figures[2].getElementsByTagName('img')[0];
        const rr = img.getBoundingClientRect();
        log.push({ t: 'pre-click', containerScroll: document.querySelector('#moments.sub-page').scrollTop,
                   thumbRect: [rr.left, rr.top, rr.width, rr.height] });
        const a = figures[2].querySelector('a') || figures[2];
        a.click();
        requestAnimationFrame(() => {
            log.push({ t: 'frame1', ...grab() });
            requestAnimationFrame(() => {
                log.push({ t: 'frame2', ...grab() });
                setTimeout(() => resolve(log), 160);
            });
        });
    })""", GRAB_JS)
    print(json.dumps(info, ensure_ascii=False, indent=1))

    time.sleep(0.3)
    st = page.evaluate("""() => {
        const n = document.querySelector('#moments.sub-page');
        const img = document.querySelector('.pswp__item .pswp__img');
        const r = img ? img.getBoundingClientRect() : null;
        return { containerScroll: n.scrollTop, fullscreenImgRect: r ? [r.left, r.top, r.width, r.height] : null,
                 pswpOpen: !!document.querySelector('.pswp--open') };
    }""")
    print("打开后:", json.dumps(st, ensure_ascii=False))

    page.evaluate("() => window.__wxMoments.closeImage()")
    page.wait_for_timeout(400)
    st2 = page.evaluate("() => document.querySelector('#moments.sub-page').scrollTop")
    print("关闭后容器滚动 =", st2, " (打开前 =", before["containerScroll"], ")")

    # ---- 关图后检查格子 DOM 是否被 PhotoSwipe 改动 ----
    before_html = page.evaluate("""() => {
        const posts = document.querySelectorAll('#moments .moments__post');
        const gal = posts[0].querySelector('.my-gallery');
        const figures = Array.prototype.filter.call(gal.children,
            (x) => x.nodeType === 1 && !x.classList.contains('video-thumb'));
        const img = figures[2].getElementsByTagName('img')[0];
        const cs = getComputedStyle(img);
        return { html: figures[2].outerHTML.slice(0, 400),
                 style: { width: cs.width, height: cs.height, objectFit: cs.objectFit },
                 rect: img.getBoundingClientRect().toJSON() };
    }""")
    print('打开前 tile3:', json.dumps(before_html, ensure_ascii=False)[:500])

    page.evaluate("() => window.__wxMoments.openImage(1, 3)")
    page.wait_for_timeout(500)
    page.evaluate("() => window.__wxMoments.closeImage()")
    page.wait_for_timeout(600)
    after_html = page.evaluate("""() => {
        const posts = document.querySelectorAll('#moments .moments__post');
        const gal = posts[0].querySelector('.my-gallery');
        const figures = Array.prototype.filter.call(gal.children,
            (x) => x.nodeType === 1 && !x.classList.contains('video-thumb'));
        const img = figures[2].getElementsByTagName('img')[0];
        const cs = getComputedStyle(img);
        return { html: figures[2].outerHTML.slice(0, 400),
                 style: { width: cs.width, height: cs.height, objectFit: cs.objectFit },
                 rect: img.getBoundingClientRect().toJSON() };
    }""")
    print('关闭后 tile3:', json.dumps(after_html, ensure_ascii=False)[:500])
    browser.close()
