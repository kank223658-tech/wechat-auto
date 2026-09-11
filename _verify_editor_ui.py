# -*- coding: utf-8 -*-
"""临时验证工具：验证「场景模拟器（编辑器）」的「朋友圈」tab 真的能编辑视频动态，
   并能一键生成「进入朋友圈 + 打开视频/图片」的工作流。

用法（先启动编辑器服务）:
    py editor_server.py --port 8799
    py _verify_editor_ui.py --port 8799
"""
import os
import sys
import json
import shutil
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "_shot")
WF = os.path.join(BASE, "workflow.json")
WF_BAK = WF + ".uiverify.bak"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    args = ap.parse_args()
    url = "http://127.0.0.1:%d/scene.html" % args.port
    os.makedirs(OUT, exist_ok=True)

    if os.path.isfile(WF):
        shutil.copyfile(WF, WF_BAK)

    from playwright.sync_api import sync_playwright
    report = {"checks": [], "panel": {}, "workflow": None, "errors": []}

    def check(name, ok, detail=""):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("  ✅ " if ok else "  ❌ ") + name + (("  → " + str(detail)) if detail else ""))

    try:
        with sync_playwright() as pw:
            chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            br = pw.chromium.launch(headless=True,
                                    executable_path=chrome if os.path.isfile(chrome) else None)
            ctx = br.new_context(viewport={"width": 1680, "height": 1000}, locale="zh-CN")
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            print("[1] 打开「朋友圈」tab")
            page.click('[data-tab="moments"]')
            page.wait_for_timeout(500)

            src_videos = page.evaluate("() => sourceVideos")
            check("编辑器已加载源视频库 /api/source-videos",
                  isinstance(src_videos, list) and len(src_videos) > 0, src_videos)

            h = page.evaluate("() => document.getElementById('panelBody').innerHTML")
            report["panel"]["momentsTabHtmlLen"] = len(h)
            check("朋友圈 tab 有「生成工作流时进入朋友圈」区块", "生成工作流时进入朋友圈" in h)
            check("有 momentsNav 开关", 'data-set="momentsNav"' in h)
            check("有 momentsOpen 打开方式下拉", 'data-set="momentsOpen"' in h)
            check("有 momentsOpenIndex 条数输入", 'data-set="momentsOpenIndex"' in h)
            check("每条动态有「加视频」按钮", 'data-act="moment-video"' in h)
            check("每条动态有「作者头像」字段", 'moments[0].avatar' in h and '作者头像' in h)
            check("有「公司名」字段", 'moments[0].company' in h)
            check("配图改为多图列表（最多 9 张）", "配图（最多 9 张）" in h)

            print("[2] 新增一条动态 → 点「加视频」")
            page.click('[data-act="add-moment"]')
            page.wait_for_timeout(400)
            btns = page.query_selector_all('[data-act="moment-video"]')
            check("新增动态后出现「加视频」按钮", len(btns) > 0, "共 %d 条动态" % len(btns))
            # 给最后一条动态加视频
            btns[-1].click()
            page.wait_for_timeout(500)

            h2 = page.evaluate("() => document.getElementById('panelBody').innerHTML")
            check("加视频后出现视频地址输入", 'video.src' in h2)
            check("加视频后出现「⬆ 上传视频」按钮", 'data-video="upload"' in h2)
            check("加视频后出现视频封面字段", 'video.cover' in h2)
            check("出现「从已上传的视频里选」下拉", 'data-video="pick"' in h2)

            print("[3] 填写视频地址 → 手机预览应出现视频缩略图")
            page.click("#btnCamMoments")          # 手机预览切到「朋友圈」视图
            page.wait_for_timeout(600)
            # 3a) 顺便验证「⬆ 上传视频」整条链路：文件选择 → /api/upload-video → 回填地址
            try:
                with page.expect_file_chooser(timeout=8000) as fc:
                    page.click('[data-video="upload"]')
                fc.value.set_files(os.path.join(BASE, "vue-WeChat", "public", "videos", "_test.mp4"))
                page.wait_for_timeout(2500)
                up_val = page.evaluate("""() => {
                    const i = document.querySelector('#panelBody input[data-set$=".video.src"]');
                    return i ? i.value : '';
                }""")
                vids = page.evaluate("() => sourceVideos")
                check("「⬆ 上传视频」把文件传上去并回填地址",
                      up_val.startswith("/videos/") and up_val in vids, up_val)
            except Exception as e:                           # noqa: BLE001
                check("「⬆ 上传视频」把文件传上去并回填地址", False, str(e))

            page.evaluate("""() => {
                const inp = document.querySelector('#panelBody input[data-set$=".video.src"]');
                inp.value = '/videos/_test.mp4';
                inp.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            page.wait_for_timeout(700)
            prev = page.evaluate("""() => ({
                vThumb: document.querySelectorAll('#phoneInner .m-video').length,
                play: document.querySelectorAll('#phoneInner .m-video .mv-play').length,
                src: (() => { const s = document.querySelector('#phoneInner .mv-src');
                              return s ? s.textContent : ''; })(),
                poster: (() => { const i = document.querySelector('#phoneInner .m-video img');
                                 return i ? (i.getAttribute('src') || '') : ''; })(),
                videoEls: document.querySelectorAll('#panelBody video.mv-preview').length,
            })""")
            report["panel"]["preview"] = prev
            check("手机预览出现视频缩略图（封面+播放角标）", prev["vThumb"] >= 1 and prev["play"] >= 1, prev)
            check("面板里出现可播放的视频预览元素", prev["videoEls"] >= 1, prev)

            print("[4] 勾选「自动进入朋友圈并打开视频」→ 生成工作流")
            page.evaluate("""() => {
                const cb = document.querySelector('#panelBody input[data-set="momentsNav"]');
                cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            page.wait_for_timeout(300)
            page.evaluate("""() => {
                const sel = document.querySelector('#panelBody select[data-set="momentsOpen"]');
                sel.value = 'video'; sel.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            page.wait_for_timeout(300)
            page.evaluate("""() => {
                const inp = document.querySelector('#panelBody input[data-set="momentsOpenIndex"]');
                inp.value = '3'; inp.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            page.wait_for_timeout(300)

            with page.expect_response(lambda r: "/api/scene/to-workflow" in r.url, timeout=15000):
                page.click("#btnToWorkflow")
            page.wait_for_timeout(600)
            check("生成工作流无 JS 报错", not errs, errs[:3])

            page.screenshot(path=os.path.join(OUT, "verify_editor_moments_tab.png"), full_page=False)
            print("      截图: _shot/verify_editor_moments_tab.png")

            br.close()
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append(str(e))
        print("  ❌ 异常:", e)
    finally:
        # 还原 workflow.json
        if os.path.isfile(WF_BAK):
            shutil.copyfile(WF_BAK, WF)
            os.remove(WF_BAK)

    # 检查生成出来的工作流
    wf_path = os.path.join(BASE, "_runtime", "_wf_from_editor.json")
    if os.path.isfile(wf_path):
        pass
    print("\n[5] 检查生成的工作流步骤")
    try:
        import editor_server as es
        sc = json.load(open(es.SCENE_PATH, encoding="utf-8"))
        # 用 3 条动态的场景模拟「打开第 3 条」，验证序号能如实传下去
        sc["moments"] = [
            {"author": "A", "text": "a", "images": ["/images/avatar/2_20260831_184618_874.jpg"]},
            {"author": "B", "text": "b", "images": ["/images/avatar/2_20260831_184618_874.jpg"]},
            {"author": "C", "text": "c",
             "video": {"src": "/videos/_test.mp4", "cover": "/images/avatar/2_20260831_184618_874.jpg"}},
        ]
        sc["momentsNav"] = True
        sc["momentsOpen"] = "video"
        sc["momentsOpenIndex"] = 3
        wf = es._build_scene_workflow(sc)
        report["workflow"] = [s["action"] for s in wf["steps"]]
        acts = [s["action"] for s in wf["steps"]]
        print("      步骤:", " → ".join(acts))
        check("工作流含 [进入朋友圈]", "进入朋友圈" in acts)
        check("工作流含 [向下滚动]", "向下滚动" in acts)
        check("工作流含 [播放视频]，序号 = 3（打开第 3 条）",
              any(s["action"] == "播放视频" and str(s["params"].get("序号")) == "3"
                  for s in wf["steps"]))
        # 图片模式
        sc["momentsOpen"] = "image"
        sc["momentsOpenIndex"] = 2
        wf2 = es._build_scene_workflow(sc)
        check("工作流含 [点开图片]，序号 = 2（打开第 2 条的第 1 张）",
              any(s["action"] == "点开图片" and str(s["params"].get("序号")) == "2"
                  for s in wf2["steps"]))
    except Exception as e:                                   # noqa: BLE001
        report["errors"].append("workflow check: %s" % e)
        print("  ❌ 工作流检查异常:", e)

    ok = all(c["ok"] for c in report["checks"]) and not report["errors"]
    print("\n=== 总判 ===", "✅ 全部通过" if ok else "❌ 有失败项")
    if report["errors"]:
        print("错误:", report["errors"])
    print(json.dumps(report, ensure_ascii=False, indent=1)[:4000])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
