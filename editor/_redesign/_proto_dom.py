"""探测真实前端的 DOM 结构 / 请求行为：为编辑器嵌入层提供接口锚点。"""
import asyncio
import io
import json

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8002/vue-wechat/#/"


async def main():
    scene = json.load(io.open(r"G:\weixin-auto\scene.json", encoding="utf-8"))
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        p = await b.new_page(viewport={"width": 600, "height": 1300})
        reqs = []
        p.on("request", lambda r: reqs.append(r.url.split("8002")[-1]))
        bad = []
        p.on("response", lambda r: bad.append((r.status, r.url.split("8002")[-1])) if r.status >= 400 else None)
        errs = []
        p.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        await p.goto(URL, wait_until="domcontentloaded")
        await p.wait_for_function("() => window.__wxEmbedReady === true", timeout=45000)
        await p.evaluate("(s) => window.__wxConfig.applyScene(s)", scene)
        await p.wait_for_timeout(2500)

        structure = await p.evaluate("""() => {
          const out = {};
          const probe = (sel) => {
            const els = document.querySelectorAll(sel);
            return els.length ? { n: els.length,
              cls: els[0].className,
              txt: (els[0].textContent || '').trim().slice(0, 24) } : null;
          };
          ['.outter', '.msg-list', '.msg-item', '.chat-item', '.sub-page',
           '.tabbar', '.tab-bar', '.wx-tab', '.dialogue-section', '.row',
           '.search', '.welcome', '.home-item', '.list-item', '.mint-cell'].forEach(s => {
            out[s] = probe(s);
          });
          // 首个会话行向上三层，看完整类名链
          const cands = [...document.querySelectorAll('div')].filter(
            e => /金善慧|女人|楠柒|Jennie/.test(e.textContent || '') && e.children.length < 6);
          out.firstRowChain = cands.slice(0, 3).map(e => {
            const chain = [];
            let n = e;
            for (let i = 0; i < 5 && n; i++) { chain.push(n.tagName + '.' + (n.className || '')); n = n.parentElement; }
            return chain;
          });
          return out;
        }""")
        print("=== DOM 结构 ===")
        print(json.dumps(structure, ensure_ascii=False, indent=1)[:2600])

        n0 = len(reqs)
        bad0 = len(bad)
        await p.wait_for_timeout(6000)
        print("=== 空闲 6s 新增请求 ===", len(reqs) - n0)
        print("  明细:", reqs[n0:][:12])
        print("=== 空闲 6s 新增 4xx/5xx ===", len(bad) - bad0, bad[bad0:][:6])
        print("=== console error ===", errs[:5] or "none")
        await b.close()


asyncio.run(main())
