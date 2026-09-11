# -*- coding: utf-8 -*-
"""编辑器 UI v2：顶栏重组 + 白色简约主题（带深色上下文保护与命中校验）"""
import io, re, sys

BASE = r"G:\weixin-auto\editor"
PROTECT = []  # (placeholder, original) 恢复用

def protect(s, pattern):
    """把匹配到的深色上下文规则整体换成占位符，避免全局替换误伤"""
    global PROTECT
    m = re.search(pattern, s, flags=re.S)
    if not m:
        print("   (protect miss: %s)" % pattern[:50])
        return s
    PROTECT.append((m.group(0),))
    return s[:m.start()] + "\x00P%d\x00" % (len(PROTECT) - 1) + s[m.end():]

def restore(s):
    global PROTECT
    for i, (orig,) in enumerate(PROTECT):
        s = s.replace("\x00P%d\x00" % i, orig)
    PROTECT = []
    return s

def rep(s, old, new, must=1, label=""):
    n = s.count(old)
    if must and n != must:
        print("!! FAIL [%s] expected=%d got=%d : %r" % (label, must, n, old[:70]))
        sys.exit(1)
    if n:
        s = s.replace(old, new)
    print("   [%s] x%d" % (label, n))
    return s

MENU_CSS = """
  /* ---- UI v2: 顶栏菜单与统一尺寸 ---- */
  .topbar .btn { height: 32px; }
  .topbar .btn.small { height: 30px; }
  .topbar .btn.primary { height: 34px; }
  .menu-wrap { position: relative; display: inline-flex; }
  .menu-btn .caret { font-style: normal; font-size: 10px; opacity: .55; margin-left: 3px; }
  .menu {
    position: absolute; top: calc(100% + 6px); left: 0; z-index: 90;
    min-width: 176px; display: none; flex-direction: column; gap: 2px; padding: 6px;
    background: var(--panel); border: 1px solid var(--line-strong); border-radius: 12px;
    box-shadow: var(--shadow-pop, 0 12px 32px rgba(17, 24, 39, 0.14));
  }
  .menu-wrap.open .menu { display: flex; }
  .menu .btn, .menu button {
    display: flex; width: 100%; align-items: center; justify-content: flex-start; gap: 8px;
    height: 34px; padding: 0 10px; border: 0; border-radius: 8px; background: transparent;
    transform: none; box-shadow: none;
  }
  .menu .btn:hover, .menu button:hover { background: var(--panel-2); border: 0; transform: none; }
  .menu-sep { height: 1px; margin: 4px 6px; background: var(--line); }
"""

VIEW_CSS = """
  /* ---- UI v2: 分段式视图切换 ---- */
  .view-switch {
    display: inline-flex; align-items: center; gap: 2px; padding: 3px;
    border-radius: 11px; background: var(--panel-2); border: 1px solid var(--line);
  }
  .view-btn {
    height: 30px; padding: 0 13px; border: none; border-radius: 8px; background: transparent;
    color: var(--muted); font-size: 13px; font-weight: 500; cursor: pointer; white-space: nowrap;
    transition: background .14s ease, color .14s ease, box-shadow .14s ease;
  }
  .view-btn:hover { color: var(--text); }
  .view-btn.active { background: #ffffff; color: var(--ink-0); font-weight: 600; box-shadow: 0 1px 5px rgba(17, 24, 39, 0.14); }
"""

DARK_EDGE_CSS = """
  /* 深色部件与浅色界面的接缝 */
  .log { border-color: rgba(255, 255, 255, 0.08); }
  .log-head { border-color: rgba(255, 255, 255, 0.08); }
  .manual-syntax { border-color: rgba(255, 255, 255, 0.08); }
  .live-panel { border-color: #26282e; }
  .live-head { border-color: rgba(255, 255, 255, 0.08); }
  .live-tip { border-color: rgba(255, 255, 255, 0.08); }
  .live-typebar { border-color: rgba(255, 255, 255, 0.08); }
  .edit-pop { border-color: rgba(255, 255, 255, 0.14); }
  .phone-screen { border-color: #26282e; }
"""

MENU_JS = """
<script>
/* UI v2: 顶栏下拉菜单（纯展示层，不改动任何既有功能绑定） */
(function () {
  "use strict";
  var wraps = document.querySelectorAll(".menu-wrap");
  wraps.forEach(function (w) {
    var btn = w.querySelector(".menu-btn");
    if (!btn) return;
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var wasOpen = w.classList.contains("open");
      wraps.forEach(function (o) { o.classList.remove("open"); });
      if (!wasOpen) w.classList.add("open");
    });
    w.querySelectorAll(".menu-item").forEach(function (it) {
      it.addEventListener("click", function () { w.classList.remove("open"); });
    });
  });
  document.addEventListener("click", function () {
    wraps.forEach(function (o) { o.classList.remove("open"); });
  });
})();
</script>
"""

CAM_JS = """
<script>
/* UI v2: 场景编辑器镜头切换激活态（纯视觉反馈） */
(function () {
  "use strict";
  var ids = ["btnCamList", "btnCamMoments", "btnCamPeer", "btnCamPeerMoments"];
  ids.forEach(function (id) {
    var b = document.getElementById(id);
    if (!b) return;
    b.addEventListener("click", function () {
      ids.forEach(function (o) {
        var x = document.getElementById(o);
        if (x) x.classList.remove("active");
      });
      b.classList.add("active");
    });
  });
  var first = document.getElementById("btnCamList");
  if (first) first.classList.add("active");
})();
</script>
"""

LIGHT_ROOT_INDEX = """:root {
  color-scheme: light;
  --bg: #f4f5f7;
  --panel: #ffffff;
  --panel-2: #f2f3f6;
  --panel-3: #e9ebef;
  --field: #f7f8fa;
  --line: rgba(17, 24, 39, 0.08);
  --line-strong: rgba(17, 24, 39, 0.16);
  --text: #1c1e22;
  --muted: #5c616b;
  --muted-2: #9095a0;
  --accent: #0aac5f;
  --accent-strong: #0a9d57;
  --accent-soft: rgba(10, 172, 95, 0.10);
  --accent-border: rgba(10, 172, 95, 0.38);
  --green: #0aac5f;
  --green-soft: rgba(10, 172, 95, 0.10);
  --green-line: rgba(10, 172, 95, 0.32);
  --amber: #b9791e;
  --amber-soft: rgba(202, 138, 20, 0.10);
  --amber-line: rgba(202, 138, 20, 0.32);
  --red: #d54941;
  --red-soft: rgba(213, 73, 65, 0.10);
  --red-line: rgba(213, 73, 65, 0.32);
  --ink-0: #0f1115;
  --shadow: 0 24px 64px rgba(17, 24, 39, 0.16);
  --shadow-soft: 0 6px 20px rgba(17, 24, 39, 0.06);
  --shadow-pop: 0 12px 32px rgba(17, 24, 39, 0.14);
  --radius: 14px;
  --radius-sm: 10px;
  --topbar-h: 58px;
  --log-h: 176px;
}"""

LIGHT_ROOT_SCENE = """  :root {
    color-scheme: light;
    --bg: #f4f5f7;
    --panel: #ffffff;
    --panel-2: #f2f3f6;
    --panel-3: #e9ebef;
    --field: #f7f8fa;
    --line: rgba(17, 24, 39, 0.08);
    --line-strong: rgba(17, 24, 39, 0.16);
    --text: #1c1e22;
    --muted: #5c616b;
    --muted-2: #9095a0;
    --accent: #0aac5f;
    --accent-strong: #0a9d57;
    --accent-soft: rgba(10, 172, 95, 0.10);
    --accent-border: rgba(10, 172, 95, 0.38);
    --amber: #b9791e;
    --red: #d54941;
    --ink-0: #0f1115;
    --shadow: 0 24px 64px rgba(17, 24, 39, 0.16);
    --shadow-soft: 0 6px 20px rgba(17, 24, 39, 0.06);
  }"""

INDEX_TOPBAR = """  <header class="topbar">
      <div class="brand" title="微信录屏工作流可视化编辑器">
        <div class="brand-mark">微</div>
        <div>
          工作流编辑器
          <span class="brand-sub">可视化编排 · 本地运行 · 自动生成视频</span>
        </div>
      </div>

      <div class="view-switch" role="tablist">
        <button type="button" class="view-btn active" id="btnViewFlow" role="tab">工作流编辑</button>
        <button type="button" class="view-btn" id="btnViewScript" role="tab">脚本模式</button>
        <button type="button" class="view-btn" id="btnViewGenerate" role="tab">✨ 创作</button>
      </div>

      <div class="menu-wrap" id="fileMenuWrap">
        <button type="button" class="btn small menu-btn" id="btnFileMenu">文件<i class="caret">▾</i></button>
        <div class="menu">
          <button type="button" class="btn small menu-item" id="btnNew">新建流程</button>
          <button type="button" class="btn small menu-item" id="btnLoad">载入流程</button>
          <button type="button" class="btn small menu-item" id="btnSave">保存流程</button>
          <div class="menu-sep"></div>
          <button type="button" class="btn small menu-item" id="btnImport">导入 JSON…</button>
          <button type="button" class="btn small menu-item" id="btnExport">导出 JSON…</button>
        </div>
      </div>
      <input type="file" id="fileInput" class="sr-only" accept=".json,application/json">

      <input class="flow-name" id="flowName" value="未命名流程" placeholder="流程名称" aria-label="流程名称">

      <div class="spacer"></div>

      <div class="toolbar-group">
        <button type="button" class="btn small" id="btnScene" title="打开独立的场景编辑器：可放大、点选即改联系人/消息/朋友圈，一键生成工作流">🎬 场景</button>
        <button type="button" class="btn small" id="btnConcurrent" title="并发生产：一次导入多条剧本，各自解析/配图后同时跑批出片">⚡ 并发</button>
        <button type="button" class="btn small" id="btnManual" title="打开离线使用手册：所有功能的书写格式与用法，支持搜索">📖 手册</button>
      </div>

      <div class="menu-wrap" id="toolMenuWrap">
        <button type="button" class="btn small menu-btn" id="btnToolMenu">工具<i class="caret">▾</i></button>
        <div class="menu">
          <button type="button" class="btn small menu-item" id="btnEditMode" title="进入编辑模式：实时画面可点击操作（进聊天/切页），并可直接点选元素修改文字、头像、背景">✏️ 编辑模式</button>
          <button type="button" class="btn small menu-item" id="btnLive">📱 实时画面</button>
          <button type="button" class="btn small menu-item" id="btnShot">📷 截图预览</button>
          <button type="button" class="btn small menu-item" id="btnVideos">📂 视频目录</button>
        </div>
      </div>

      <span class="status-pill" id="statusPill">就绪</span>
      <button type="button" class="btn small danger" id="btnStop" disabled>停止</button>
      <button type="button" class="btn primary" id="btnRun">▶ 运行并生成视频</button>
      <span class="save-state" id="saveState">本地已保存</span>
    </header>"""

SCENE_TOPBAR = """<div class="topbar" data-page-node-id="n2xdjBKpmnpWhpFzXrwFL4">
    <div class="brand" data-page-node-id="IEI3KB8HJVzZeRortHTMGF">🎬 场景编辑器 <small data-page-node-id="9cyTmEj0BAHrg3oswbXHtT">· 600×1300 / 点选即改</small></div>
    <div class="view-switch" role="tablist">
      <button id="btnCamList" class="view-btn active" data-page-node-id="OA9bkwqZn4GGMnUm4fZbXz">会话列表</button>
      <button id="btnCamMoments" class="view-btn" data-page-node-id="w9t7yX5NBeVDnRQ26Xm7nW">朋友圈</button>
      <button id="btnCamPeer" class="view-btn" data-page-node-id="CIZFGUlcZCy3W49sHB4nGV">对方主页</button>
      <button id="btnCamPeerMoments" class="view-btn" data-page-node-id="obfJqISeDtofBZjN03CBON">对方朋友圈</button>
    </div>
    <button id="btnLib" title="打开图片库：浏览/搜索/上传/重命名/删除/复制路径" data-page-node-id="Zhab7kK8NM1Rd87ajuFNl2">📚 图片库</button>
    <button id="btnScriptImport" title="从两人对白剧本一键生成完整聊天消息历史（格式有误可用 AI 修正）" data-page-node-id="28pAaLLKnip3Z7fIeO6DhL">📜 剧本导入</button>
    <button id="btnPeopleLib" title="打开人物库：浏览/搜索/新增人物/改头像/改名/删除；也可把某个联系人直接用人物库头像填充" data-page-node-id="uGwqNxbHNgcPBZynM9oGaZ">👥 人物库</button>
    <div class="menu-wrap" id="sceneToolMenuWrap">
      <button type="button" class="menu-btn" id="btnSceneToolMenu">工具<i class="caret">▾</i></button>
      <div class="menu">
        <button id="btnCheckImgs" class="menu-item" title="检查场景中所有引用图片能否正常加载，失败项在画面中用红框标出" data-page-node-id="5vlt84fI3AiaU05K97CNhf">🖼 检查图片</button>
        <button id="btnPeopleSync" class="menu-item" title="把当前会话列表里所有已填头像的人保存到人物库；之后在脚本里写这几个 [会话] 名字会自动带上对应头像" data-page-node-id="AXo0xlylqq1JNY9endKyrN">💾 保存到人物库</button>
        <button id="btnManual" class="menu-item" title="打开历史会话使用手册：会话列表/消息历史的每个字段与按钮、点选即改、来源图、保存生成运行、剧本导入、常见问题" data-page-node-id="0PhMCCaVjDC3NL1rhp7O7D">📖 使用手册</button>
      </div>
    </div>
    <span class="spacer" data-page-node-id="1W6kBZ0KFP6FAHJoo3iGiA"></span>
    <div class="menu-wrap" id="sceneFileMenuWrap">
      <button type="button" class="menu-btn" id="btnSceneFileMenu">文件<i class="caret">▾</i></button>
      <div class="menu">
        <button id="btnLoad" class="menu-item" data-page-node-id="BA1S8ewzCyREOHhnAEqEhU">载入场景</button>
        <button id="btnSave" class="menu-item" data-page-node-id="GoGBsmHFJPMKTMo2J1aSDv">保存场景</button>
        <button id="btnToWorkflow" class="menu-item" data-page-node-id="qniAjqWw3nfWBMEVevaU4O">生成工作流</button>
        <button id="btnVideos" class="menu-item" data-page-node-id="O2iIowqx9FVqFsyBCWospU">📂 打开视频目录</button>
      </div>
    </div>
    <div class="zoom" data-page-node-id="32KdXu33FLMnOtRPdwjhEU">
      <button id="btnZoomOut" data-page-node-id="7gN1sbcxQGRseIQlRHBxMG">−</button>
      <b id="zoomLabel" data-page-node-id="sR5DnCRTCV6ZXWdGAqGOck">100%</b>
      <button id="btnZoomIn" data-page-node-id="jJacHmEaYuM64AiYVFxnBG">＋</button>
      <button id="btnZoomFit" data-page-node-id="0W9ub5tsYeYkGtWzky8chH">适应</button>
    </div>
    <button id="btnEditMode" title="进入编辑模式：实时画面可点选元素修改文字/头像/背景" data-page-node-id="BXJgVc9752XC2qycx2DaIG">✏️ 编辑模式</button>
    <button id="btnLive" title="打开/关闭实时手机画面" data-page-node-id="9rjcxCVUwTYBP4GLnqnTEk">🖥 实时画面</button>
    <button id="btnStop" title="停止当前运行" data-page-node-id="8LJzdGKlk1eNbZwG8xBGdM">⏹ 停止</button>
    <button id="btnRun" class="primary" title="保存场景 → 生成工作流 → 立即运行并打开实时画面" data-page-node-id="CzCsyRgZXayBPD03VWzkIZ">▶ 生成并运行</button>
  </div>"""

CONCURRENT_TOPBAR = """<div class="topbar">
  <div class="brand">⚡ 并发生产 <small>· 一次跑多条剧本，各自出片</small></div>
  <div class="menu-wrap" id="ccImportMenuWrap">
    <button type="button" class="menu-btn" id="btnCcImportMenu">导入<i class="caret">▾</i></button>
    <div class="menu">
      <button id="btnImport" class="menu-item" title="粘贴/加载一段剧本，新建一条任务">📜 导入剧本</button>
      <button id="btnImportFolder" class="menu-item" title="从一个文件夹读取所有 .txt 剧本，每个文件新建一条任务">📁 从文件夹导入</button>
    </div>
  </div>
  <button id="btnParseAll" title="对所有还没解析的任务调用 AI 转译">🤖 全部解析(AI)</button>
  <button id="btnParseAllOffline" title="对所有还没解析的任务做离线规则解析（不需要 API Key）">⚙ 全部解析(离线)</button>
  <span class="spacer"></span>
  <div class="conf" title="同时最多跑几条（1~8）">同时跑
    <input type="number" id="maxConcurrent" min="1" max="8" value="3"></div>
  <button id="btnStopAll" class="danger" title="停止所有正在跑/排队的任务">⏹ 全部停止</button>
  <button id="btnRunAll" class="primary" title="把已解析的任务全部排队，按上限同时开跑">▶ 全部开始</button>
  <span class="spacer"></span>
  <div class="menu-wrap" id="ccToolMenuWrap">
    <button type="button" class="menu-btn" id="btnCcToolMenu">工具<i class="caret">▾</i></button>
    <div class="menu">
      <button id="btnLib" class="menu-item">🖼 图片库</button>
      <button id="btnVideos" class="menu-item">📂 打开视频目录</button>
      <div class="menu-sep"></div>
      <button id="btnCleanDone" class="menu-item">🗑 清空已完成</button>
    </div>
  </div>
  <button id="btnBack" title="回到可视化工作流编辑器">↩ 工作流编辑器</button>
</div>"""


def common_light(s, kind):
    """kind: 'index' | 'scene' | 'concurrent' —— 主题色替换（深色上下文已保护）"""
    s = rep(s, "rgba(16, 199, 108", "rgba(10, 172, 95", 0, "accent rgba")
    s = rep(s, "rgba(122, 134, 255", "rgba(71, 86, 216", 0, "indigo rgba")
    s = rep(s, "rgba(230, 176, 84", "rgba(202, 138, 20", 0, "amber rgba")
    s = rep(s, "rgba(229, 105, 95", "rgba(213, 73, 65", 0, "red rgba")
    s = rep(s, "#5fe3a1", "#0a8a4f", 0, "green text")
    s = rep(s, "#f0c67e", "#b9791e", 0, "amber text")
    s = rep(s, "#ff9187", "#c73e35", 0, "red text a")
    s = rep(s, "#ff9b9b", "#c73e35", 0, "red text b")
    s = rep(s, "#aeb6ff", "#4756d8", 0, "indigo text")
    s = rep(s, "#f6d592", "#8f5e0e", 0, "warn b")
    s = rep(s, "#ffe2a8", "#7a5200", 0, "hit text")
    s = rep(s, "#f0d8b0", "#8a5a0b", 0, "warn panel text")
    s = rep(s, "#7fe0a5", "#0a7a4a", 0, "img act")
    s = rep(s, "#86e0ab", "#0a7a4a", 0, "img sum")
    s = rep(s, "#8fa8ff", "#4756d8", 0, "link")
    s = rep(s, "#b3c4ff", "#6474e8", 0, "link hov")
    s = rep(s, "color: #04150c", "color: #ffffff", 0, "on-green")
    s = rep(s, "color: #dfe2e8", "color: var(--text)", 0, "textarea text")
    return s


def do_index():
    p = BASE + r"\index.html"
    s = io.open(p, encoding="utf-8").read()
    print("== index.html")
    a = s.index('<header class="topbar">')
    b = s.index("</header>") + len("</header>")
    s = s[:a] + INDEX_TOPBAR + s[b:]
    print("   topbar ok")
    s = rep(s, '  <script src="/manual.js"></script>', MENU_JS + '  <script src="/manual.js"></script>', 1, "menu js")

    # 保护深色上下文
    for pat in [r"\.log-body \.ok\s*\{[^}]*\}", r"\.log-body \.err\s*\{[^}]*\}", r"\.log-body \.warn\s*\{[^}]*\}",
                r"\.manual-syntax\s*\{[^}]*\}", r"\.edit-pop \.ep-kind\s*\{[^}]*\}",
                r"\.edit-pop \{[^}]*?color: #dfe2e8;[^}]*\}", r"\.live-head \{[^}]*?color: #dfe2e8;[^}]*\}"]:
        s = protect(s, pat)

    s = re.sub(r":root \{.*?\n\}", LIGHT_ROOT_INDEX, s, count=1, flags=re.S)
    print("   :root -> light")
    s = rep(s, "    radial-gradient(1100px 480px at 18% -12%, rgba(16, 199, 108, 0.055), transparent 60%),\n    radial-gradient(900px 420px at 88% -18%, rgba(120, 130, 255, 0.045), transparent 60%),",
            "    radial-gradient(1100px 480px at 18% -12%, rgba(10, 172, 95, 0.04), transparent 60%),\n    radial-gradient(900px 420px at 88% -18%, rgba(71, 86, 216, 0.03), transparent 60%),", 1, "body bg")
    s = rep(s, "background: rgba(18, 20, 24, 0.82);", "background: rgba(255, 255, 255, 0.82);", 1, "topbar bg")
    s = rep(s, "background: rgba(255, 255, 255, 0.12);", "background: rgba(17, 24, 39, 0.14);", 1, "scrollbar")
    s = rep(s, "background-color: rgba(255, 255, 255, 0.22);", "background-color: rgba(17, 24, 39, 0.24);", 1, "scrollbar hov")
    s = rep(s, "background-image: radial-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px);",
            "background-image: radial-gradient(rgba(17, 24, 39, 0.07) 1px, transparent 1px);", 1, "dot grid")
    s = rep(s, "background: rgba(255, 255, 255, 0.04);", "background: rgba(17, 24, 39, 0.05);", 1, "view-switch bg")
    s = rep(s, "border-radius: 999px;\n  background: rgba(255, 255, 255, 0.08);\n}", "border-radius: 999px;\n  background: rgba(17, 24, 39, 0.08);\n}", 1, "progress track")
    s = rep(s, "rgba(255, 255, 255, 0.015)", "rgba(17, 24, 39, 0.02)", 2, "empty bg")
    s = rep(s, "box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.06);",
            "box-shadow: 0 1px 5px rgba(17, 24, 39, 0.14);", 1, "view-btn active")
    s = rep(s, "color: #3a3d44;", "color: #c8ccd4;", 1, "star empty")
    s = rep(s, ".gsc-title { font-size: 13px; font-weight: 600; color: #7ee2ac;", ".gsc-title { font-size: 13px; font-weight: 600; color: #0a8a4f;", 1, "gsc-title")
    s = rep(s, "  color: #7ee2ac;\n  font-size: 12px;\n  font-weight: 500;\n  line-height: 1.5;", "  color: #0a8a4f;\n  font-size: 12px;\n  font-weight: 500;\n  line-height: 1.5;", 1, "gen-progress")
    s = rep(s, 'color: #7ee2ac;\n  font-family: Consolas, "Courier New", monospace;\n  font-size: 11.5px;', 'color: #0a7a4a;\n  font-family: Consolas, "Courier New", monospace;\n  font-size: 11.5px;', 1, "tips code")
    s = rep(s, "#8ce8b8", "#0a7a4a", 1, "ss-title img")

    s = common_light(s, "index")
    s = restore(s)

    s = rep(s, "</style>", MENU_CSS + VIEW_CSS + DARK_EDGE_CSS + "</style>", 1, "append css")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("   saved")


def do_scene():
    p = BASE + r"\scene.html"
    s = io.open(p, encoding="utf-8").read()
    print("== scene.html")
    a = s.index('<div class="topbar"')
    b = s.index('<div class="hint"')
    s = s[:a] + SCENE_TOPBAR + "\n  " + s[b:]
    print("   topbar ok")
    s = rep(s, '<script src="/shared_picker.js">', MENU_JS + CAM_JS + '<script src="/shared_picker.js">', 1, "menu js")

    for pat in [r"\.edit-pop \.ep-kind\s*\{[^}]*\}", r"\.edit-pop \{[^}]*?color: #dfe2e8;[^}]*\}",
                r"\.live-head \{[^}]*?color: #dfe2e8;[^}]*\}", r"\.manual-body code\s*\{[^}]*\}"]:
        s = protect(s, pat)

    s = re.sub(r":root \{.*?\n  \}", LIGHT_ROOT_SCENE, s, count=1, flags=re.S)
    print("   :root -> light")
    s = rep(s, "      radial-gradient(1100px 480px at 18% -12%, rgba(16, 199, 108, 0.05), transparent 60%),",
            "      radial-gradient(1100px 480px at 18% -12%, rgba(10, 172, 95, 0.04), transparent 60%),", 1, "body bg")
    s = rep(s, "background: rgba(18, 20, 24, 0.82);", "background: rgba(255, 255, 255, 0.82);", 1, "topbar bg")
    s = rep(s, "background: rgba(255, 255, 255, 0.12);", "background: rgba(17, 24, 39, 0.14);", 1, "scrollbar")
    s = rep(s, "background-color: rgba(255, 255, 255, 0.22);", "background-color: rgba(17, 24, 39, 0.24);", 1, "scrollbar hov")
    s = rep(s, "background-image: radial-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px);",
            "background-image: radial-gradient(rgba(17, 24, 39, 0.06) 1px, transparent 1px);", 1, "stage dots")
    s = rep(s, "#8ce8b8", "#0a7a4a", 1, "m-tip")
    s = rep(s, ".phone { width: 600px; height: 1300px; background: #181818; border: 1px solid #2a2b2e; overflow: hidden; position: relative; box-shadow: 0 30px 80px rgba(0, 0, 0, 0.55); }",
            ".phone { width: 600px; height: 1300px; background: #181818; border: 1px solid #1a1b1e; overflow: hidden; position: relative; box-shadow: 0 30px 80px rgba(17, 24, 39, 0.28); }", 1, "phone shadow")

    s = common_light(s, "scene")
    s = restore(s)

    s = rep(s, "</style>", MENU_CSS + VIEW_CSS + DARK_EDGE_CSS + "</style>", 1, "append css")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("   saved")


def do_concurrent():
    p = BASE + r"\concurrent.html"
    s = io.open(p, encoding="utf-8").read()
    print("== concurrent.html")
    a = s.index('<div class="topbar">')
    b = s.index('<div class="hint"')
    s = s[:a] + CONCURRENT_TOPBAR + "\n  " + s[b:]
    print("   topbar ok")
    s = rep(s, '<script src="/shared_picker.js">', MENU_JS + '<script src="/shared_picker.js">', 1, "menu js")

    s = re.sub(r":root \{.*?\n  \}", LIGHT_ROOT_SCENE, s, count=1, flags=re.S)
    print("   :root -> light")
    s = rep(s, "      radial-gradient(1100px 480px at 18% -12%, rgba(16, 199, 108, 0.05), transparent 60%),",
            "      radial-gradient(1100px 480px at 18% -12%, rgba(10, 172, 95, 0.04), transparent 60%),", 1, "body bg")
    s = rep(s, "background: rgba(18, 20, 24, 0.82);", "background: rgba(255, 255, 255, 0.82);", 1, "topbar bg")
    s = rep(s, "background: rgba(255, 255, 255, 0.12);", "background: rgba(17, 24, 39, 0.14);", 1, "scrollbar")
    s = rep(s, "background-color: rgba(255, 255, 255, 0.22);", "background-color: rgba(17, 24, 39, 0.24);", 1, "scrollbar hov")

    s = common_light(s, "concurrent")

    s = rep(s, "</style>", MENU_CSS + DARK_EDGE_CSS.replace(".log ", ".run-log ").replace(".manual-syntax { border-color: rgba(255, 255, 255, 0.08); }", "").replace(".edit-pop { border-color: rgba(255, 255, 255, 0.14); }", "").replace(".phone-screen { border-color: #26282e; }", "") + "</style>", 1, "append css")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("   saved")


if __name__ == "__main__":
    do_index()
    do_scene()
    do_concurrent()
    print("ALL DONE")
