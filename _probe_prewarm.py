# -*- coding: utf-8 -*-
"""验证表情面板「图片预热」是否生效：打开面板的同一刻，面板里的 <img> 应已全部加载完成。
对照修复前实测：面板到位后仍有 ~260ms 空窗（图片未就绪）。
用法：py _probe_prewarm.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

IMG_JS = """() => {
    const imgs = Array.from(document.querySelectorAll('.wx-emoji-panel img'));
    return { total: imgs.length, done: imgs.filter(i => i.complete && i.naturalWidth > 0).length };
}"""

with sync_playwright() as pw:
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    br = pw.chromium.launch(headless=True,
                            executable_path=chrome if os.path.isfile(chrome) else None,
                            args=["--disable-background-timer-throttling",
                                  "--disable-backgrounding-occluded-windows",
                                  "--disable-renderer-backgrounding",
                                  "--disable-features=CalculateNativeWinOcclusion"])
    ctx = br.new_context(viewport={"width": main.VIEWPORT_W, "height": main.VIEWPORT_H},
                         device_scale_factor=main.DEVICE_SCALE_FACTOR,
                         user_agent=main.MOBILE_UA, is_mobile=True, has_touch=True, locale="zh-CN")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto("http://127.0.0.1:8080/#/", wait_until="domcontentloaded")
    main.inject_overlays(page)
    page.wait_for_timeout(900)
    page.evaluate("window.__wxConfig && window.__wxConfig.apply()")
    page.wait_for_timeout(300)

    print("预热 API:", page.evaluate("typeof window.__wxPreWarmPanels"))
    # 进聊天页
    page.evaluate("""() => { const li=document.querySelector('.wechat-list li .list-info'); if(li) li.click(); }""")
    page.wait_for_timeout(1500)
    if page.locator(".dialogue-section").count() == 0:
        print("!! 没进聊天页"); print("\n".join(errs[:10])); br.close(); sys.exit(1)

    # 预热是否把图都拉下来了
    page.wait_for_timeout(800)
    res = page.evaluate("""() => {
        const rs = performance.getEntriesByType('resource').filter(r => /wxemoji3d|emoji_panel|wxpanel/.test(r.name));
        const pending = window.__wxPreWarmPanels ? window.__wxPreWarmPanels() : -1;
        return { n: rs.length, pendingNew: pending,
                 byDir: rs.reduce((m, r) => {
                     const k = r.name.includes('wxemoji3d') ? 'emoji3d'
                             : (r.name.includes('emoji_panel') ? 'tabs' : 'wxpanel');
                     m[k] = (m[k] || 0) + 1; return m; }, {}) };
    }""")
    print("预热已取资源:", res)

    for rnd in (1, 2):
        print(f"\n=== 第 {rnd} 次打开表情面板 ===")
        # 同一次 evaluate 里：调 open 后立刻数图片就绪数
        immediate = page.evaluate("""() => {
            window.__wxPanels.set('表情');
            const imgs = Array.from(document.querySelectorAll('.wx-emoji-panel img'));
            return { t: performance.now(),
                     total: imgs.length,
                     done: imgs.filter(i => i.complete && i.naturalWidth > 0).length };
        }""")
        print(f"  打开同一刻: {immediate['done']}/{immediate['total']} 张已就绪")
        # 逐帧跟踪到全部就绪
        frames = page.evaluate("""async () => {
            const out = [];
            for (let k = 0; k < 20; k++) {
                await new Promise(r => requestAnimationFrame(r));
                const imgs = Array.from(document.querySelectorAll('.wx-emoji-panel img'));
                out.push(imgs.filter(i => i.complete && i.naturalWidth > 0).length);
            }
            return out;
        }""")
        print(f"  随后 20 帧就绪数: {frames}")
        page.wait_for_timeout(500)
        page.evaluate("window.__wxPanels.set('收起')")
        page.wait_for_timeout(600)

    print("\n=== 页面报错 ===")
    print("\n".join("  " + e for e in errs[:15]) if errs else "  （无）")
    br.close()
