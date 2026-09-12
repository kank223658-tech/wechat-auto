# -*- coding: utf-8 -*-
"""三轮冒烟：配图清单白色主题 + 待配图/已配图配色"""
import asyncio, json
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
errors = []

JS_SETUP = """() => {
  const host = document.createElement('div');
  host.id = 'smokeAttach';
  document.body.appendChild(host);
  window.__wxPick.renderAttachPanel(host, [
    { id: 'a', no: '图1', desc: '对方发来一张自拍', path: '' },
    { id: 'b', no: '图2', desc: '我的照片', path: '/images/album/x.jpg' }
  ], () => {});
  const lum = (c) => {
    const m = c.match(/\\d+/g).map(Number);
    return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
  };
  const pick = (sel) => {
    const el = document.querySelector(sel);
    return el ? getComputedStyle(el) : null;
  };
  const attachBg = getComputedStyle(host.querySelector('.wxp-attach')).backgroundColor;
  const emptyBg = getComputedStyle(host.querySelector('.wxp-slot.empty')).backgroundColor;
  const modalBg = (() => {
    const st = document.getElementById('wxp-style');
    return st ? /--wxp-bg:\\s*#ffffff/.test(st.textContent) : false;
  })();
  // 合成元素验证步骤行/脚本步骤配色
  const mk = (cls) => { const d = document.createElement('div'); d.className = cls; document.body.appendChild(d); return getComputedStyle(d).backgroundColor; };
  return {
    attachBg, attachLum: lum(attachBg),
    emptyBg, emptyLum: lum(emptyBg),
    lightTokens: modalBg,
    slotTags: [...host.querySelectorAll('.wxp-slot-tag')].map(e => e.textContent),
    slotCls: [...host.querySelectorAll('.wxp-slot')].map(e => e.className),
    count: host.querySelector('#wxp-attach-count').textContent,
    countCls: host.querySelector('#wxp-attach-count').className,
    stepImg: mk('step-row img'),
    scriptImg: null,
  };
}"""

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])

        # ---------- concurrent：配图清单浅色 + 状态色 ----------
        pc = await b.new_page()
        pc.on("pageerror", lambda e: errors.append("concurrent: " + str(e)))
        pc.on("console", lambda m: errors.append("concurrent: " + m.text) if m.type == "error" else None)
        await pc.goto(BASE + "/concurrent.html", wait_until="networkidle")
        r = await pc.evaluate(JS_SETUP)
        assert r["lightTokens"], "shared_picker 仍非浅色令牌"
        assert r["attachLum"] > 230, "配图清单底色不是白色: %s" % r["attachBg"]
        assert 200 < r["emptyLum"] < 253, "待配图槽不是浅琥珀底: %s" % r["emptyBg"]
        assert r["slotTags"] == ["待配图", "已配图"], "状态标签错误: %s" % r["slotTags"]
        assert "empty" in r["slotCls"][0] and "filled" in r["slotCls"][1], "槽位状态类错误: %s" % r["slotCls"]
        assert r["count"] == "已配 1/2" and "pending" in r["countCls"], "计数错误: %s %s" % (r["count"], r["countCls"])
        # 步骤行琥珀/绿
        lum = lambda c: sum(w * int(x) for w, x in zip((0.2126, 0.7152, 0.0722), c[c.find("(")+1:c.find(")")].split(",")[:3]))
        img_row = await pc.evaluate("() => { const d = document.createElement('div'); d.className='step-row img'; document.body.appendChild(d); return getComputedStyle(d).backgroundColor; }")
        assert lum(img_row) > 240, "需配图步骤行不是浅色琥珀底: %s" % img_row
        print("CONCURRENT OK", r["attachBg"], r["emptyBg"], img_row)

        # ---------- index：脚本步骤琥珀/绿 ----------
        pi = await b.new_page()
        pi.on("pageerror", lambda e: errors.append("index: " + str(e)))
        pi.on("console", lambda m: errors.append("index: " + m.text) if m.type == "error" else None)
        await pi.goto(BASE + "/index.html", wait_until="networkidle")
        res = await pi.evaluate("""() => {
          const host = document.createElement('div');
          host.style.background = '#ffffff';
          host.style.position = 'fixed'; host.style.left = '-9999px';
          document.body.appendChild(host);
          const mk = (cls) => { const d = document.createElement('div'); d.className = cls; host.appendChild(d);
            return getComputedStyle(d).backgroundColor; };
          const need = mk('script-step img');
          const filled = mk('script-step img filled');
          const plain = mk('script-step');
          // rgba 叠加到白底：计算实际呈现色
          const over = (c, bg) => {
            const m = c.match(/[\\d.]+/g).map(Number);
            if (m.length === 3) return m;
            const a = m[3];
            return [0, 1, 2].map(i => Math.round(m[i] * a + bg[i] * (1 - a)));
          };
          const white = [255, 255, 255];
          return { need, filled, plain, needRGB: over(need, white), filledRGB: over(filled, white) };
        }""")
        need_rgb, filled_rgb = res["needRGB"], res["filledRGB"]
        # 待配图：合成后是浅琥珀（R 明显大于 B）；已配图：浅绿（G 最大）
        assert need_rgb[0] > 235 and need_rgb[0] - need_rgb[2] > 8, "待配图不是浅琥珀: %s" % need_rgb
        assert filled_rgb[1] > 240 and filled_rgb[1] - filled_rgb[0] > 4, "已配图不是浅绿: %s" % filled_rgb
        print("INDEX OK  need=%s filled=%s" % (need_rgb, filled_rgb))

        await b.close()
    real = [e for e in errors if "favicon" not in e and "404" not in e]
    if real:
        print("ERRORS:", json.dumps(real[:6], ensure_ascii=False)); raise SystemExit(1)
    print("SMOKE PASS")

asyncio.run(main())
