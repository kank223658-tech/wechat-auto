# -*- coding: utf-8 -*-
"""验证「场景编辑器 · 对方主页」多人物 × 多方案改造。

覆盖：
  1. 老场景（单 peer）自动迁移成 peers[]
  2. 面板三段式渲染（人物列表 / 编辑方案 / 动态列表）
  3. 新建人物 / 复制方案 / 切换方案
  4. 模板一键生成（文案+配图+日期）
  5. 点赞评论编辑（面板 + 预览点选）
  6. 预览内添加动态（data-pact）
  7. 保存场景写回 peers[]；生成工作流按人物×当前方案产出 [编辑对方资料]（含 peerNav 多人物导航）
  8. /api/peer/ai-copy 无 Key 时返回可读错误

用法（先起编辑器服务）:
    py editor_server.py --port 8799
    py _verify_peer_plans.py --port 8799
结束后会恢复 scene.json / workflow.json 原状。
"""
import os
import sys
import json
import shutil
import argparse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(BASE, "scene.json")
SCENE_BAK = SCENE + ".peerverify.bak"
WF = os.path.join(BASE, "workflow.json")
WF_BAK = WF + ".peerverify.bak"


def api(port, path, payload=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except ValueError:
            return {"ok": False, "msg": "HTTP %d" % e.code}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    args = ap.parse_args()
    url = "http://127.0.0.1:%d/scene.html" % args.port

    if os.path.isfile(SCENE):
        shutil.copyfile(SCENE, SCENE_BAK)
    if os.path.isfile(WF):
        shutil.copyfile(WF, WF_BAK)

    from playwright.sync_api import sync_playwright
    report = {"checks": [], "errors": []}

    def check(name, ok, detail=""):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:200]})
        print(("  PASS " if ok else "  FAIL ") + name + (("  -> " + str(detail)[:200]) if detail else ""))

    def set_field(page, sel, value):
        page.eval_on_selector(sel, """(el, v) => {
            el.value = v; el.dispatchEvent(new Event('change', {bubbles: true}));
        }""", value)

    try:
        with sync_playwright() as pw:
            chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            br = pw.chromium.launch(headless=True,
                                    executable_path=chrome if os.path.isfile(chrome) else None)
            ctx = br.new_context(viewport={"width": 1680, "height": 1000}, locale="zh-CN")
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("dialog", lambda d: d.accept())   # window.confirm 一律接受
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            print("[1] 迁移与数据结构")
            st = page.evaluate("() => ({ peers: scene.peers.length, pb: PB(), sel: peerSel })")
            check("老场景自动迁移出 peers[]（>=1 人物）", st["peers"] >= 1, st)
            check("寻址根 PB() 指向 plans", ".plans." in st["pb"], st["pb"])

            print("[2] 面板三段式")
            page.click('[data-tab="peer"]')
            page.wait_for_timeout(400)
            html = page.evaluate("() => document.getElementById('panelBody').innerHTML")
            for kw in ["① 人物列表", "② 编辑方案", "一键生成整套动态", "③ 朋友圈动态", "预设库"]:
                check("面板包含「%s」" % kw, kw in html)

            print("[3] 人物 / 方案管理")
            n0 = page.evaluate("() => scene.peers.length")
            page.click('button[data-act="peer-add"]')
            page.wait_for_timeout(300)
            n1 = page.evaluate("() => scene.peers.length")
            check("新建空白人物", n1 == n0 + 1, "%d -> %d" % (n0, n1))
            check("新人物自动选中", page.evaluate("() => peerSel") == n1 - 1)

            set_field(page, 'input[data-set="peers[%d].plans.A.name"]' % (n1 - 1), "测试人物")
            page.wait_for_timeout(300)
            page.click('button[data-act="plan-copy"]')
            page.wait_for_timeout(300)
            keys = page.evaluate("() => Object.keys(scene.peers[scene.peers.length-1].plans)")
            check("复制当前方案 -> 出现新方案字母", len(keys) == 2, keys)
            check("复制后自动切到新方案", page.evaluate(
                "() => scene.peers[scene.peers.length-1].activePlan") == keys[1], keys)
            page.click('button[data-act="plan-use"][data-k="A"]')
            page.wait_for_timeout(200)
            check("点字母切回方案 A", page.evaluate(
                "() => scene.peers[scene.peers.length-1].activePlan") == "A")

            print("[4] 模板一键生成")
            page.eval_on_selector('#peerTplSel', "el => { el.value = 'travel';"
                                  " el.dispatchEvent(new Event('change',{bubbles:true})); }")
            page.click('button[data-act="peer-tpl-gen"]')
            page.wait_for_timeout(300)
            posts = page.evaluate("""() => {
                const pp = scene.peers[scene.peers.length-1];
                return (pp.plans[pp.activePlan].posts || []).map(p => ({
                    date: p.date, nimg: (p.images || []).length, t: (p.text || '').length }));
            }""")
            check("模板生成 6 条动态", len(posts) == 6, posts)
            check("每条都有日期与文案", all(p["date"] and p["t"] > 0 for p in posts), posts)
            check("配图从图片库挑到了", sum(p["nimg"] for p in posts) > 0, posts)

            print("[5] 点赞 / 评论")
            page.click('button[data-act="peer-add-comment"][data-i="0"]')
            page.wait_for_timeout(200)
            set_field(page, 'input[data-set="peers[%d].plans.A.posts[0].comments[0].name"]' % (n1 - 1), "小雨")
            set_field(page, 'input[data-set="peers[%d].plans.A.posts[0].comments[0].text"]' % (n1 - 1), "太好看了吧")
            set_field(page, 'input[data-set="peers[%d].plans.A.posts[0].likesText"]' % (n1 - 1), "阿月、小雨")
            page.wait_for_timeout(300)
            p0 = page.evaluate("""() => {
                const pp = scene.peers[scene.peers.length-1];
                return pp.plans[pp.activePlan].posts[0];
            }""")
            check("点赞（顿号）转数组", p0.get("likes") == ["阿月", "小雨"], p0.get("likes"))
            check("评论写入", (p0.get("comments") or [{}])[0].get("name") == "小雨"
                  and p0["comments"][0].get("text") == "太好看了吧", p0.get("comments"))

            print("[6] 预览（对方朋友圈）点选结构编辑")
            page.click("#btnCamPeerMoments")
            page.wait_for_timeout(400)
            prev = page.evaluate("() => document.getElementById('phoneInner').innerHTML")
            check("预览渲染点赞卡片 wpm-social", "wpm-social" in prev)
            check("预览渲染评论（评论人可见）", "小雨" in prev)
            check("预览顶部有「＋ 添加动态」", 'data-pact="add-post"' in prev)
            n_posts = page.evaluate("""() => {
                const pp = scene.peers[scene.peers.length-1];
                return pp.plans[pp.activePlan].posts.length; }""")
            page.click('#phoneInner [data-pact="add-post"]')
            page.wait_for_timeout(300)
            n_posts2 = page.evaluate("""() => {
                const pp = scene.peers[scene.peers.length-1];
                return pp.plans[pp.activePlan].posts.length; }""")
            check("预览点「＋ 添加动态」+1 条", n_posts2 == n_posts + 1, "%d -> %d" % (n_posts, n_posts2))
            page.hover('#phoneInner .wpm-post:last-child')   # 悬停后才出现 ↑↓✕ 工具条；删刚加的最后一条
            page.wait_for_timeout(200)
            page.click('#phoneInner .wpm-post:last-child .wpm-ops i[data-pact="del-post"]')
            page.wait_for_timeout(500)
            n_posts3 = page.evaluate("""() => {
                const pp = scene.peers[scene.peers.length-1];
                return pp.plans[pp.activePlan].posts.length; }""")
            check("预览点 ✕ 删除动态 -1 条", n_posts3 == n_posts2 - 1, "%d -> %d" % (n_posts2, n_posts3))

            print("[7] 保存场景 + 生成工作流")
            page.click("#btnSave")
            page.wait_for_timeout(800)
            saved = json.load(open(SCENE, encoding="utf-8"))
            check("scene.json 写入 peers[]", isinstance(saved.get("peers"), list)
                  and len(saved["peers"]) == n1, len(saved.get("peers") or []))
            check("scene.json 仍镜像 peer 字段（兼容）", isinstance(saved.get("peer"), dict))
            check("镜像 peer 有测试人物数据", saved["peer"].get("name") == "测试人物", saved["peer"].get("name"))
            mirror_posts = saved["peer"].get("posts") or []
            check("镜像动态带点赞数组", mirror_posts and mirror_posts[0].get("likes") == ["阿月", "小雨"],
                  mirror_posts[0].get("likes") if mirror_posts else None)

            page.check('input[data-set="peerNav"]')
            page.wait_for_timeout(200)
            page.click("#btnToWorkflow")
            page.wait_for_timeout(800)
            wf = json.load(open(WF, encoding="utf-8"))
            acts = [s["action"] for s in wf.get("steps", [])]
            n_edit = acts.count("编辑对方资料")
            check("工作流包含 [编辑对方资料]（只有 1 个人物有数据）", n_edit == 1, n_edit)
            check("peerNav 开 -> 打开对方主页 + 进入对方朋友圈",
                  "打开对方主页" in acts and "进入对方朋友圈" in acts)

            print("[8] /api/peer/ai-copy 参数校验（不真调大模型）")
            r = api(args.port, "/api/peer/ai-copy", {"name": "", "keywords": ""})
            check("空关键词返回 400 可读提示", r.get("ok") is False
                  and "关键词" in (r.get("msg") or ""), r.get("msg"))

            check("页面无 JS 报错", not errs, "; ".join(errs[:3]))
            br.close()
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(str(exc))
        print("  FAIL 异常: %r" % exc)
    finally:
        if os.path.isfile(SCENE_BAK):
            shutil.move(SCENE_BAK, SCENE)
        if os.path.isfile(WF_BAK):
            shutil.move(WF_BAK, WF)
        print("（已恢复 scene.json / workflow.json 原状）")

    bad = [c for c in report["checks"] if not c["ok"]]
    print("\n== 结果: %d 项通过, %d 项失败 ==" % (len(report["checks"]) - len(bad), len(bad)))
    sys.exit(1 if (bad or report["errors"]) else 0)


if __name__ == "__main__":
    main()
