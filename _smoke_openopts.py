# -*- coding: utf-8 -*-
"""冒烟：配图清单「打开动画」新编辑器（renderOpenOptsInto）
在 / 页面挂载一个假槽位，验证：分段开关切换 / 滑杆写回 / 焦点小图存在。
只操作自建 DOM 容器，不碰页面真实状态。
"""
import json
from playwright.sync_api import sync_playwright

RESULT = {"steps": []}

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:8000/", wait_until="domcontentloaded")
        pg.wait_for_function("() => !!window.__wxPick && !!window.__wxPick.renderOpenOptsInto", timeout=8000)
        RESULT["steps"].append("component ready")

        # 挂一个测试容器 + 模拟槽位（openZoom/openHold 直接可写，模拟并发页 step 槽）
        pg.evaluate("""() => {
            window.__t = { host: document.createElement('div'), writes: [] };
            document.body.appendChild(window.__t.host);
            window.__t.slot = {
                id: 'test', path: '/images/avatar/2_20260831_184618_874.jpg',
                open: '', openZoom: '', openHold: '',
                onOptsChange: (s) => { window.__t.writes.push(s.open + '|' + s.openZoom + '|' + s.openHold); }
            };
            window.__wxPick.renderOpenOptsInto(window.__t.host, window.__t.slot);
        }""")
        RESULT["steps"].append("mounted")

        # 1) 初始态：默认不打开，无 detail 区
        r = pg.evaluate("""() => ({
            segs: [...window.__t.host.querySelectorAll('.wxp-segmode')].map(b => b.classList.contains('on')),
            detail: !!window.__t.host.querySelector('.wxp-openrow-detail'),
            badge: (window.__t.host.querySelector('.wxp-prevbtn2')||{}).textContent
        })""")
        assert r["segs"] == [True, False, False], r
        assert r["detail"] is False, r
        RESULT["steps"].append("initial mode=none OK")

        # 2) 点「点开放大」→ 出现 detail：焦点小图 + 两个滑杆；倍率徽章=默认
        pg.click(f"#__nada", timeout=1) if False else None
        pg.evaluate("""() => {
            [...window.__t.host.querySelectorAll('.wxp-segmode')]
              .find(b => b.dataset.mode === 'zoom').click();
        }""")
        r = pg.evaluate("""() => ({
            detail: !!window.__t.host.querySelector('.wxp-openrow-detail'),
            focusThumb: !!window.__t.host.querySelector('.wxp-focusthumb img'),
            sliders: [...window.__t.host.querySelectorAll('input[type=range]')].map(i => i.className),
            zoomBadge: (window.__t.host.querySelector('.wxp-zoom-slider')||{parentElement:{}}).parentElement?.querySelector('.wxp-sval')?.textContent,
            holdBadge: document.querySelectorAll('#__none').length,
            writes: window.__t.writes
        })""")
        assert r["detail"] and r["focusThumb"], r
        assert len(r["sliders"]) == 2, r
        assert "默认" in (r["zoomBadge"] or ""), r
        assert r["writes"] and r["writes"][-1].startswith("是|"), r
        RESULT["steps"].append("zoom mode UI OK; write-back: %s" % r["writes"][-1])

        # 3) 拖倍率滑杆到 2.0 → 徽章更新且写回 openZoom
        pg.evaluate("""() => {
            const inp = window.__t.host.querySelector('.wxp-zoom-slider');
            inp.value = 2; inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.dispatchEvent(new Event('change', {bubbles:true}));
        }""")
        r = pg.evaluate("""() => ({
            badge: window.__t.host.querySelector('.wxp-zoom-slider').parentElement.querySelector('.wxp-sval').textContent,
            zoom: window.__t.slot.openZoom, writes: window.__t.writes
        })""")
        assert r["zoom"] == "2.00", r
        assert "2.00×" in r["badge"], r
        RESULT["steps"].append("zoom slider write-back OK: %s" % r["zoom"])

        # 4) 停留滑杆默认态 + 写回
        pg.evaluate("""() => {
            const inp = window.__t.host.querySelectorAll('.wxp-sliderwrap')[1].querySelector('input');
            inp.value = 3.5; inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.dispatchEvent(new Event('change', {bubbles:true}));
        }""")
        r = pg.evaluate("() => ({ hold: window.__t.slot.openHold, writes: window.__t.writes })")
        assert r["hold"] == "3.5", r
        RESULT["steps"].append("hold slider write-back OK: %s" % r["hold"])

        # 5) 切回「不打开」→ detail 消失
        pg.evaluate("""() => {
            [...window.__t.host.querySelectorAll('.wxp-segmode')]
              .find(b => b.dataset.mode === 'none').click();
        }""")
        r = pg.evaluate("() => ({ detail: !!window.__t.host.querySelector('.wxp-openrow-detail'), open: window.__t.slot.open })")
        assert r["detail"] is False and r["open"] == "", r
        RESULT["steps"].append("back to none OK")

        # 6) 真实配图清单面板渲染：注入一个 openable 槽位走 setSlotsState → renderAttachList
        pg.evaluate("""() => {
            window.__t.host2 = document.createElement('div');
            document.body.appendChild(window.__t.host2);
            window.__wxPick.renderAttachPanel(window.__t.host2, [
                { id: 'a1', no: '图1', desc: '测试槽', path: '/images/avatar/2_20260831_184618_874.jpg', openable: true, open: '是', onOptsChange: () => {} },
                { id: 'a2', no: '图2', desc: '无控件槽', path: '' }
            ], () => {});
        }""")
        r = pg.evaluate("""() => ({
            hosts: window.__t.host2.querySelectorAll('.wxp-openhost').length,
            rendered: window.__t.host2.querySelector('.wxp-openhost .wxp-openrow') ? 1 : 0,
            segOn: [...(window.__t.host2.querySelector('.wxp-openhost')||{querySelectorAll:()=>[]}).querySelectorAll('.wxp-segmode')].filter(b=>b.classList.contains('on')).map(b=>b.textContent)
        })""")
        assert r["hosts"] == 1 and r["rendered"] == 1, r
        assert r["segOn"] == ["点开放大"], r
        RESULT["steps"].append("attach panel integration OK")

        assert not errors, errors
        RESULT["ok"] = True
        b.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        RESULT["error"] = repr(e)
    print(json.dumps(RESULT, ensure_ascii=False, indent=1))
