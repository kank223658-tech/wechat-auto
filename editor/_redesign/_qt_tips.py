# -*- coding: utf-8 -*-
"""给 editor 三个页面的功能控件加悬停问号提示（? 角标 + 悬停说明浮层）。
- 有 title 的按钮：title 升级为 data-tip（悬停浮层），不再走原生 title
- 无说明的控件：补 data-tip 文案
- 注入统一的 CSS + 运行时 JS（扫描 [data-tip] 加角标，事件委托显示浮层）
每处替换打印命中数，0 命中即中止。"""
import re, shutil, sys, io

BASE = r"G:\weixin-auto\editor"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CSS_JS = """<style id="qtTipsStyle">
/* 悬停问号提示 */
.qt-host { position: relative; }
.qt-badge {
  position: absolute; top: 1px; right: 2px; width: 11px; height: 11px;
  border-radius: 50%; background: #0aac5f; color: #fff;
  font-size: 8px; line-height: 11px; text-align: center; font-style: normal;
  font-weight: 700; pointer-events: none; opacity: .85;
}
.qt-pop {
  position: fixed; z-index: 99999; max-width: 300px;
  background: #23272e; color: #e8eaee; font-size: 12px; line-height: 1.75;
  padding: 7px 11px; border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,.3);
  pointer-events: none; opacity: 0; transition: opacity .12s ease;
}
.qt-pop.show { opacity: 1; }
</style>
<script id="qtTipsJs">
(function () {
  var VOID_TAGS = { INPUT: 1, SELECT: 1, TEXTAREA: 1, IMG: 1, BR: 1 };
  var DYN_IDS = __DYN_IDS__; /* 动态重渲染区域里需要把 title 转成 data-tip 的 id */
  function decorate(el) {
    if (!el || el.classList.contains('qt-host')) return;
    el.classList.add('qt-host');
    if (!VOID_TAGS[el.tagName] && !el.querySelector(':scope > .qt-badge')) {
      var b = document.createElement('i');
      b.className = 'qt-badge'; b.textContent = '?';
      el.appendChild(b);
    }
  }
  function adoptTitles() {
    DYN_IDS.forEach(function (id) {
      var el = document.getElementById(id);
      if (el && el.hasAttribute('title') && !el.hasAttribute('data-tip')) {
        el.setAttribute('data-tip', el.getAttribute('title'));
        el.removeAttribute('title');
      }
    });
  }
  function scan() {
    adoptTitles();
    document.querySelectorAll('[data-tip]').forEach(decorate);
  }
  scan();
  var moT = null;
  new MutationObserver(function () {
    clearTimeout(moT); moT = setTimeout(scan, 200);
  }).observe(document.body, { childList: true, subtree: true });
  var pop = null, cur = null;
  function ensure() {
    if (!pop) { pop = document.createElement('div'); pop.className = 'qt-pop'; document.body.appendChild(pop); }
    return pop;
  }
  function show(host) {
    var tip = host.getAttribute('data-tip'); if (!tip) return;
    var p = ensure(); p.textContent = tip; p.classList.add('show');
    var r = host.getBoundingClientRect();
    var pw = p.offsetWidth, ph = p.offsetHeight;
    var x = Math.min(Math.max(8, r.left + r.width / 2 - pw / 2), window.innerWidth - pw - 8);
    var y = r.bottom + 7;
    if (y + ph > window.innerHeight - 8) y = r.top - ph - 7;
    p.style.left = x + 'px'; p.style.top = Math.max(8, y) + 'px';
    cur = host;
  }
  function hide() { if (pop) pop.classList.remove('show'); cur = null; }
  document.addEventListener('mouseover', function (e) {
    var h = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (h !== cur) { h ? show(h) : hide(); }
  });
  document.addEventListener('click', hide);
  window.addEventListener('scroll', hide, true);
  window.addEventListener('resize', hide);
})();
</script>
"""

# ---- 每页目标清单 ----
# CONV: 已有 title 的按钮 -> title 转 data-tip
# ADD:  无说明控件 -> 补 data-tip（dict: id -> 文案）
# LABEL_TIP: 不是按 id 的定点替换（(old, new) 精确串）
# DYN: 动态渲染区需要运行时 title->data-tip 的 id 列表
PAGES = {
    "index.html": {
        "CONV": ["btnScene", "btnConcurrent", "btnManual", "btnEditMode", "btnUndo",
                 "btnRedo", "btnRunFrom", "btnLlmConfig", "btnTranslate", "btnOffline",
                 "btnInsertImg", "btnInsertHistory", "btnMoments", "btnRunScript",
                 "btnGenerate", "btnGenRefreshRefs", "btnGenClearRefs", "btnGenAddRef",
                 "btnGenCopy", "btnGenRegen", "btnGenUse",
                 "btnGenSkillAdd", "btnGenSkillRefresh", "btnGenHistoryRefresh",
                 "btnGenHistoryClear", "btnRunUpload", "modeTap", "modePick"],
        "ADD": {
            "btnViewFlow": "可视化搭建工作流：从左侧动作库添加步骤、编辑参数，运行后生成视频",
            "btnViewScript": "剧本模式：粘贴或书写剧本，用 AI / 离线转译成工作流步骤再运行",
            "btnViewGenerate": "创作模式：只给一个主题，AI 自动生成完整剧本并可校验纠错",
            "btnFileMenu": "文件菜单：新建 / 载入 / 保存 / 导入 / 导出工作流",
            "btnNew": "清空画布，从零开始搭新工作流（未保存的内容会丢失）",
            "btnLoad": "载入之前保存的工作流文件",
            "btnSave": "把当前工作流保存为 JSON 文件",
            "btnImport": "导入工作流 JSON 或剧本文件",
            "btnExport": "把当前工作流导出为 JSON 文件备份",
            "btnToolMenu": "工具菜单：编辑模式、实时画面、截图、打开视频目录",
            "btnLive": "在页面角落打开实时手机画面，观看当前运行效果",
            "btnShot": "截取当前真实渲染器画面并保存为图片",
            "btnVideos": "打开生成视频所在的文件夹",
            "btnStop": "停止当前正在运行的任务",
            "btnRun": "按当前工作流从第一步运行，生成视频",
            "btnDuplicate": "复制当前选中的步骤（含全部参数）",
            "btnDelete": "删除当前选中的步骤",
            "btnLoadExample": "载入一份示例剧本，快速了解书写格式",
            "btnClearScript": "清空剧本输入框（不可恢复）",
            "btnGenFeedback": "对这次生成结果不满意？提交反馈，帮助改进生成规则库",
        },
        "LABEL_TIP": [],
        "DYN": [],
    },
    "scene.html": {
        "CONV": ["btnLib", "btnScriptImport", "btnPeopleLib", "btnCheckImgs",
                 "btnPeopleSync", "btnManual", "btnEditMode", "btnLive", "btnStop",
                 "btnRun", "btnStagePick", "btnStageBack", "btnViewPv", "btnViewLive",
                 "btnViewDraft"],
        "ADD": {
            "btnCamList": "切换到会话列表画面：编辑微信首页的会话与联系人",
            "btnCamMoments": "切换到朋友圈画面：编辑自己的朋友圈帖子",
            "btnCamPeer": "切换到对方主页画面：编辑对方的头像、昵称、背景等资料",
            "btnCamPeerMoments": "切换到对方朋友圈画面：编辑对方发过的帖子",
            "btnSceneToolMenu": "工具菜单：检查图片、同步人物库、使用手册",
            "btnSceneFileMenu": "文件菜单：载入 / 保存场景、生成工作流、打开视频目录",
            "btnLoad": "重新载入 scene.json，未保存的修改会丢失",
            "btnSave": "把当前场景保存为 scene.json",
            "btnToWorkflow": "按当前场景自动生成工作流步骤（只生成不运行）",
            "btnVideos": "打开生成视频所在的文件夹",
            "btnZoomOut": "缩小手机画面",
            "btnZoomIn": "放大手机画面",
            "btnZoomFit": "恢复手机画面默认大小",
            "QxJ5SiKtwp4kYn4Go1bXVf": "会话列表面板：管理微信首页的会话与联系人",
            "BlCbWK5hyDnBDqOlDBJvoB": "消息历史面板：管理进聊天前就已存在的消息",
            "sk5zwVvNJQcUPWmwgqKMCH": "朋友圈面板：编辑朋友圈的帖子内容",
            "C7Uf2SbZMj4WIDk4ULhuGB": "对方主页面板：编辑对方的资料与主页",
            "DdNbGCyzPW1xwgMaWZa1RH": "我的资料面板：编辑「我」的头像、昵称等信息",
        },
        "LABEL_TIP": [],
        "DYN": [],
    },
    "concurrent.html": {
        "CONV": ["btnImport", "btnImportFolder", "btnParseAll", "btnParseAllOffline",
                 "btnStopAll", "btnRunAll", "btnBack", "btnDeselect", "btnRunSelected"],
        "ADD": {
            "btnCcImportMenu": "导入菜单：粘贴单个剧本，或从文件夹批量导入",
            "btnCcToolMenu": "工具菜单：图片库、视频目录、清空已完成任务",
            "btnLib": "打开图片库：管理配图素材",
            "btnVideos": "打开生成视频所在的文件夹",
            "btnCleanDone": "删除所有已完成 / 已失败的任务记录",
            "btnSelectAll": "勾选全部任务",
            "maxConcurrent": "同时最多运行的任务数（1~8），其余自动排队",
        },
        "LABEL_TIP": [
            ('<label><input type="checkbox" id="importAutoParse" checked> 导入后自动离线解析</label>',
             '<label data-tip="导入后立即自动做离线解析，省一步手动点解析（可再点「全部解析(AI)」升级为 AI 转译）"><input type="checkbox" id="importAutoParse" checked> 导入后自动离线解析</label>'),
        ],
        # 图片库弹窗是动态渲染的，运行时把 title 转成 data-tip
        "DYN": ["libSort", "libUpcat", "libMove", "libCatMgr"],
    },
}

for fname, cfg in PAGES.items():
    path = f"{BASE}\\{fname}"
    s = open(path, encoding="utf-8").read()
    if 'id="qtTipsJs"' in s:
        print(f"== {fname} 已注入过，跳过")
        continue
    shutil.copy2(path, path + ".bak_qt")
    print(f"== {fname} (备份 -> .bak_qt)")
    fail = False

    for bid in cfg["CONV"]:
        pat = re.compile(r'(<button[^>]*\bid="' + bid + r'"[^>]*?)\s+title="([^"]*)"')
        m = pat.findall(s)
        n = len(m)
        print(f"  CONV {bid}: {n}")
        if n != 1:
            fail = True; continue
        s = pat.sub(lambda mm: mm.group(1) + ' data-tip="' + mm.group(2) + '"', s, count=1)

    for bid, tip in cfg["ADD"].items():
        old = f'id="{bid}"'
        n = s.count(old)
        print(f"  ADD  {bid}: {n}")
        if n != 1:
            fail = True; continue
        s = s.replace(old, old + f' data-tip="{tip}"', 1)

    for old, new in cfg["LABEL_TIP"]:
        n = s.count(old)
        print(f"  LABEL {old[:40]}...: {n}")
        if n != 1:
            fail = True; continue
        s = s.replace(old, new, 1)

    if "</body>" not in s:
        print("  !! 找不到 </body>"); fail = True
    if 'id="qtTipsJs"' in s:
        print("  !! 已注入过，跳过注入"); fail = True
    if fail:
        print(f"  ** {fname} 存在未命中项，不写盘"); continue

    inject = CSS_JS.replace("__DYN_IDS__", repr(cfg["DYN"]))
    s = s.replace("</body>", inject + "</body>", 1)
    open(path, "w", encoding="utf-8", newline="").write(s)
    print(f"  OK 写入 {path}")
print("done")
