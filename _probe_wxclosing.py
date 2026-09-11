# -*- coding: utf-8 -*-
"""探针：验证 pswp--wx-closing 淡出机制在活页面里是否生效。

检查：
1) 文档里有几个 .pswp 根？openImage 打开的是不是 querySelector('.pswp') 那个？
2) closeImage() 后：根上有没有挂上 pswp--wx-closing？
3) zoom-wrap 的 computed opacity 是否按预期走到 0（30~120ms 内）？
4) 根节点何时隐藏。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ENH = os.path.join(BASE, "enhance")
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

POSTS = [
    {"author": "小星", "text": "九宫格。",
     "images": ["/images/avatar/枯木_20260903_141720_316.jpg"] * 9,
     "time": "2分钟前", "likes": [], "comments": []},
]

SAMPLE_JS = r"""
() => {
  const root = document.querySelector('.pswp');
  const open = document.querySelector('.pswp--open');
  const zw = root && root.querySelector('.pswp__zoom-wrap');
  const cs = zw ? getComputedStyle(zw) : null;
  const cr = root ? getComputedStyle(root) : null;
  return {
    nRoots: document.querySelectorAll('.pswp').length,
    rootIsOpenOne: root === open,
    rootClass: root ? root.className : null,
    zwOpacity: cs ? cs.opacity : null,
    zwTransform: cs ? cs.transform.slice(0, 60) : null,
    rootDisplay: cr ? cr.display : null,
  };
}
"""


def read(name):
    p = os.path.join(ENH, name)
    return open(p, "r", encoding="utf-8").read() if os.path.isfile(p) else None


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        br = pw.chromium.launch(headless=True,
                                executable_path=chrome if os.path.isfile(chrome) else None)
        ctx = br.new_context(viewport={"width": VW, "height": VH},
                             device_scale_factor=3,
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
        page.wait_for_timeout(600)
        page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
        page.wait_for_timeout(300)
        page.goto("http://127.0.0.1:8080/#/explore/moments", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        page.evaluate("(s) => window.__wxMoments.renderPosts(s)", POSTS)
        page.wait_for_timeout(500)

        print("== 初始 ==")
        print(json.dumps(page.evaluate(SAMPLE_JS), ensure_ascii=False, indent=1))

        print("\n== openImage(1,3) ==")
        ok = page.evaluate("() => window.__wxMoments.openImage(1, 3)")
        page.wait_for_timeout(600)
        st = page.evaluate(SAMPLE_JS)
        print("opened:", ok, json.dumps(st, ensure_ascii=False, indent=1))

        # CSS 规则存在性检查
        has_rule = page.evaluate(r"""
() => {
  let found = [];
  for (const ss of document.styleSheets) {
    let rules; try { rules = ss.cssRules; } catch (e) { continue; }
    for (const r of rules) {
      if (r.selectorText && r.selectorText.includes('wx-closing')) {
        found.push(r.cssText.slice(0, 160));
      }
    }
  }
  return found;
}
""")
        print("\nwx-closing CSS 规则:", json.dumps(has_rule, ensure_ascii=False, indent=1))

        print("\n== closeImage() 时间线 ==")
        timeline = page.evaluate(r"""
() => new Promise(resolve => {
  const out = [];
  const t0 = performance.now();
  window.__wxMoments.closeImage();
  const tick = () => {
    const t = +(performance.now() - t0).toFixed(0);
    const root = document.querySelector('.pswp');
    const zw = root && root.querySelector('.pswp__zoom-wrap');
    const cs = zw ? getComputedStyle(zw) : null;
    out.push({ t,
      cls: root ? root.className : null,
      op: cs ? cs.opacity : null,
      disp: root ? getComputedStyle(root).display : null });
    if (t < 650) { setTimeout(tick, 40); } else { resolve(out); }
  };
  setTimeout(tick, 10);
})
""")
        for s in timeline:
            print("  t=%4dms  op=%s  disp=%s  cls=%s" % (
                s["t"], s["op"], s["disp"], (s["cls"] or "")[:70]))
        br.close()


if __name__ == "__main__":
    main()
