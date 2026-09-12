# -*- coding: utf-8 -*-
"""配图清单白色主题 + 状态配色；需配图步骤改琥珀色（2026-09-11）
- shared_picker.js：.wxp-* 全套由深色改为浅色（所有旧选择器保留），配图槽位改成状态卡片（待配图=琥珀 / 已配图=绿）
- index.html：脚本结果里「需要配图」的步骤改琥珀色 + 「待配图/已配图」标签
- concurrent.html：步骤行同样处理
铁律：不改 id、不改 JS 数据契约，只改样式与展示层标记。
"""
import io, re, sys

def load(p): return io.open(p, encoding="utf-8").read()
def save(p, s): io.open(p, "w", encoding="utf-8", newline="").write(s)
def must(c, m):
    if not c:
        print("ABORT:", m); sys.exit(1)

# ==================================================================
# 1) shared_picker.js —— 浅色主题
# ==================================================================
SP = r"G:\weixin-auto\editor\shared_picker.js"
s = load(SP)
start = s.find("        st.textContent = `")
must(start > 0, "shared_picker style start")
end = s.find("`;\n", start)
must(end > start, "shared_picker style end")
old_css = s[start + len("        st.textContent = `"): end]
old_sels = set(re.findall(r"^\s*([.\w\-\[\]=\"'\(\): >,+#]+?)\s*\{", old_css, re.M))
old_sels = {re.sub(r"\s+", " ", x).strip() for x in old_sels if x.strip()}

NEW_CSS = r'''
:root {
  --wxp-text: #1f2328;
  --wxp-text-2: #4b5563;
  --wxp-muted: #6b7280;
  --wxp-muted-2: #9aa0a6;
  --wxp-bg: #ffffff;
  --wxp-panel: #f7f8fa;
  --wxp-panel-2: #f1f3f5;
  --wxp-field: #ffffff;
  --wxp-line: rgba(17, 24, 39, .10);
  --wxp-line-strong: rgba(17, 24, 39, .20);
  --wxp-accent: #0aac5f;
  --wxp-accent-soft: #e8f7ef;
  --wxp-accent-line: rgba(10, 172, 95, .40);
  --wxp-amber: #b26a06;
  --wxp-amber-soft: #fff8ea;
  --wxp-amber-line: rgba(214, 148, 32, .55);
  --wxp-red: #d5493f;
}
.wxp-mask { position: fixed; inset: 0; background: rgba(17, 24, 39, .35); z-index: 90; display: none; align-items: center; justify-content: center; }
.wxp-mask.show { display: flex; }
.wxp-modal { width: 720px; max-width: 94vw; background: var(--wxp-bg); color: var(--wxp-text); border: 1px solid var(--wxp-line); border-radius: 14px; box-shadow: 0 24px 60px rgba(17, 24, 39, .22); max-height: 88vh; overflow: auto; padding: 16px; }
.wxp-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.wxp-head b { font-size: 15px; color: var(--wxp-text); }
.wxp-head .wxp-target { font-size: 12px; color: var(--wxp-muted); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-head button { background: transparent; border: 0; font-size: 20px; color: var(--wxp-muted-2); cursor: pointer; padding: 0 4px; }
.wxp-head button:hover { color: var(--wxp-text); }
.wxp-toolbar { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.wxp-toolbar input { flex: 1; min-width: 140px; background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 7px; padding: 6px 9px; font: inherit; }
.wxp-toolbar input:focus { outline: none; border-color: var(--wxp-accent-line); box-shadow: 0 0 0 3px rgba(10, 172, 95, .12); }
.wxp-toolbar button { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 6px 12px; font: inherit; }
.wxp-toolbar button:hover { background: var(--wxp-panel); border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-urlrow { display: flex; gap: 6px; margin-bottom: 8px; }
.wxp-urlrow input { flex: 1; background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 7px; padding: 6px 9px; font: inherit; }
.wxp-urlrow button { cursor: pointer; border: 1px solid var(--wxp-accent); background: var(--wxp-accent); color: #ffffff; border-radius: 7px; padding: 6px 14px; font-weight: 600; }
.wxp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: 8px; max-height: 320px; overflow: auto; padding: 6px; border: 1px solid var(--wxp-line); border-radius: 10px; background: var(--wxp-panel); }
.wxp-item { position: relative; cursor: pointer; border: 1px solid transparent; border-radius: 9px; padding: 4px; text-align: center; background: var(--wxp-bg); }
.wxp-item:hover { background: var(--wxp-panel-2); border-color: var(--wxp-line); }
.wxp-item.sel { border-color: var(--wxp-accent); background: var(--wxp-accent-soft); }
.wxp-thumb { height: 64px; display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 6px; background: var(--wxp-panel-2); }
.wxp-thumb img { max-width: 100%; max-height: 100%; object-fit: cover; }
.wxp-thumb.wxp-clear { font-size: 13px; color: var(--wxp-muted); }
.wxp-name { font-size: 11px; color: var(--wxp-text-2); margin-top: 3px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-empty { grid-column: 1 / -1; color: var(--wxp-muted); text-align: center; padding: 24px 0; font-size: 13px; }
.wxp-footer { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
.wxp-preview { display: flex; gap: 10px; align-items: center; flex: 1; min-width: 0; }
.wxp-preview img { width: 54px; height: 54px; border-radius: 8px; object-fit: cover; background: var(--wxp-panel-2); border: 1px solid var(--wxp-line); }
.wxp-preview .wxp-path { font-size: 12px; color: var(--wxp-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-footbtns { display: flex; gap: 8px; }
.wxp-footbtns button { cursor: pointer; border-radius: 7px; padding: 7px 16px; font: inherit; }
.wxp-footbtns .wxp-ok { background: var(--wxp-accent); border: 1px solid var(--wxp-accent); color: #ffffff; font-weight: 600; }
.wxp-footbtns .wxp-cancel { background: var(--wxp-bg); border: 1px solid var(--wxp-line-strong); color: var(--wxp-text); }
.wxp-footbtns .wxp-cancel:hover { background: var(--wxp-panel); }

/* ---- 配图面板（浅色卡片式） ---- */
.wxp-attach { border: 1px solid var(--wxp-line); border-radius: 12px; background: var(--wxp-bg); margin: 12px 0; overflow: hidden; }
.wxp-attach-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: var(--wxp-panel); cursor: pointer; border-bottom: 1px solid var(--wxp-line); }
.wxp-attach-head b { font-size: 13px; color: var(--wxp-text); }
.wxp-attach-head .wxp-count { font-size: 11px; font-weight: 600; color: var(--wxp-muted); background: var(--wxp-panel-2); border: 1px solid var(--wxp-line); border-radius: 999px; padding: 2px 9px; }
.wxp-attach-head .wxp-count.pending { color: var(--wxp-amber); background: var(--wxp-amber-soft); border-color: var(--wxp-amber-line); }
.wxp-attach-head .wxp-count.done { color: var(--wxp-accent); background: var(--wxp-accent-soft); border-color: var(--wxp-accent-line); }
.wxp-attach-head .wxp-spacer { flex: 1; }
.wxp-attach-head .wxp-caret { color: var(--wxp-muted-2); font-size: 12px; transition: transform .15s ease; }
.wxp-attach-head.collapsed .wxp-caret { transform: rotate(-90deg); }
.wxp-attach-head.collapsed { border-bottom: 0; }
.wxp-slotlist { padding: 10px 12px; }
.wxp-slot { position: relative; display: flex; flex-direction: column; align-items: stretch; gap: 6px; padding: 9px 11px 9px 14px; margin-bottom: 7px; border: 1px solid var(--wxp-line); border-radius: 10px; background: var(--wxp-bg); }
.wxp-slot:last-child { margin-bottom: 0; }
.wxp-slot::before { content: ""; position: absolute; left: 0; top: 9px; bottom: 9px; width: 3px; border-radius: 0 3px 3px 0; background: var(--wxp-line-strong); }
.wxp-slot.empty { border-color: var(--wxp-amber-line); background: var(--wxp-amber-soft); }
.wxp-slot.empty::before { background: #e9a23b; }
.wxp-slot.filled { border-color: var(--wxp-accent-line); }
.wxp-slot.filled::before { background: var(--wxp-accent); }
.wxp-slot-no { flex: 0 0 38px; text-align: center; background: var(--wxp-panel-2); color: var(--wxp-text-2); border: 1px solid var(--wxp-line); border-radius: 7px; font-size: 12px; font-weight: 600; padding: 4px 0; }
.wxp-slot-info { flex: 1; min-width: 0; font-size: 12px; color: var(--wxp-text-2); }
.wxp-slot-info .wxp-desc { display: block; color: var(--wxp-text); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-slot-tag { flex: none; font-size: 11px; font-weight: 600; border-radius: 999px; padding: 2px 9px; background: var(--wxp-amber-soft); color: var(--wxp-amber); border: 1px solid var(--wxp-amber-line); }
.wxp-slot-tag.ok { background: var(--wxp-accent-soft); color: var(--wxp-accent); border-color: var(--wxp-accent-line); }
.wxp-slot-thumb { flex: 0 0 44px; height: 44px; border-radius: 8px; background: var(--wxp-panel-2); display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid var(--wxp-line-strong); }
.wxp-slot-thumb img { max-width: 100%; max-height: 100%; object-fit: cover; }
.wxp-slot-thumb .wxp-nopic { font-size: 11px; color: var(--wxp-muted); }
.wxp-slot-thumb.ok { border-color: var(--wxp-accent); }
.wxp-slot-thumb.warn { border-color: var(--wxp-amber-line); border-style: dashed; }
.wxp-slot-acts { display: flex; gap: 6px; flex: 0 0 auto; }
.wxp-slot-acts button { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 5px 10px; font-size: 12px; }
.wxp-slot-acts button:hover { background: var(--wxp-panel); border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-slot-acts .wxp-pick { background: var(--wxp-accent); border-color: var(--wxp-accent); color: #ffffff; font-weight: 600; }
.wxp-slot-acts .wxp-pick:hover { background: #099a55; color: #ffffff; }
.wxp-slot-acts .wxp-clear { color: var(--wxp-muted); }
.wxp-slot-acts .wxp-clear:hover { color: var(--wxp-red); border-color: rgba(213, 73, 65, .4); background: #fdf3f2; }
/* 配图槽位：自动打开动画 控件 */
.wxp-slot-main { display: flex; align-items: center; gap: 10px; }
.wxp-slot-opts { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; color: var(--wxp-muted); font-size: 12px; padding-left: 48px; }
.wxp-slot-opts label { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.wxp-slot-opts input[type=number] { width: 58px; background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 6px; padding: 3px 5px; }
.wxp-slot-opts .wxp-focusbtn { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 3px 10px; font-size: 12px; }
.wxp-slot-opts .wxp-focusbtn:hover { background: var(--wxp-panel); border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-dropbar { border: 1px dashed var(--wxp-line-strong); border-radius: 9px; color: var(--wxp-muted); text-align: center; padding: 10px; font-size: 12px; margin: 8px 12px 12px; background: var(--wxp-panel); }
.wxp-dropbar.drag { border-color: var(--wxp-accent); color: var(--wxp-accent); background: var(--wxp-accent-soft); }
.wxp-header-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 0 12px 10px; }
.wxp-batchrow { display: flex; align-items: center; gap: 8px; margin: 4px 0 8px; flex-wrap: wrap; }
.wxp-batch { cursor: pointer; border: 1px solid var(--wxp-accent); background: var(--wxp-accent); color: #ffffff; border-radius: 7px; padding: 8px 14px; font-weight: 600; font: inherit; }
.wxp-batch:hover { background: #099a55; }
.wxp-batch-hint { font-size: 11px; color: var(--wxp-muted); line-height: 1.6; }
/* ---- 图库 分类筛选 + 命名 ---- */
.wxp-filter { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.wxp-filter select { background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 7px; padding: 6px 8px; font: inherit; }
.wxp-typebtn { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 999px; padding: 5px 12px; font: inherit; font-size: 12px; }
.wxp-typebtn:hover { background: var(--wxp-panel); border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-typebtn.on { background: var(--wxp-accent); border-color: var(--wxp-accent); color: #ffffff; font-weight: 600; }
.wxp-typebtn.on:hover { background: #099a55; color: #ffffff; }
.wxp-found { font-size: 11px; color: var(--wxp-muted); margin-left: auto; }
.wxp-item .wxp-tag { position: absolute; top: 3px; right: 4px; font-size: 10px; color: #ffffff; padding: 1px 5px; border-radius: 4px; border: 1px solid rgba(255, 255, 255, .5); }
.wxp-item .wxp-tag-ic { background: #3a5ba8; }
.wxp-item .wxp-tag-im { background: #0a8a4f; }
.wxp-sub { font-size: 10px; color: var(--wxp-muted-2); display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-preview { align-items: flex-start; min-width: 220px; }
.wxp-footer { align-items: flex-start; flex-wrap: wrap; }
.wxp-pvmeta { display: flex; flex-direction: column; gap: 5px; min-width: 0; flex: 1; }
.wxp-labelbox { display: flex; gap: 6px; align-items: center; }
.wxp-labelbox input { flex: 1; min-width: 120px; background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 7px; padding: 5px 8px; font: inherit; font-size: 12px; }
.wxp-labelbox .wxp-lb-btn { cursor: pointer; border: 1px solid var(--wxp-accent); background: var(--wxp-accent); color: #ffffff; border-radius: 7px; padding: 5px 10px; font: inherit; font-size: 12px; font-weight: 600; }
.wxp-labelbox .wxp-lb-btn:hover { background: #099a55; }
.wxp-labelbox .wxp-lb-hint { font-size: 10px; color: var(--wxp-muted-2); }
.wxp-footbtns .wxp-misc { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 6px 11px; font: inherit; font-size: 12px; }
.wxp-footbtns .wxp-misc:hover { background: var(--wxp-panel); }
.wxp-footbtns .wxp-misc.danger:hover { border-color: rgba(213, 73, 65, .45); color: var(--wxp-red); background: #fdf3f2; }
'''

missing = [x for x in old_sels if x not in NEW_CSS]
must(not missing, "shared_picker lost selectors: %s" % missing)
s = s[:start] + "        st.textContent = `" + NEW_CSS + s[end:]
print("shared_picker: style replaced (%d selectors preserved)" % len(old_sels))

# 配图槽位标记：状态类 + 状态标签
old = """            return '<div class="wxp-slot" data-id="' + escAttr(s.id) + '">' +
                '<div class="wxp-slot-main">' +
                    '<span class="wxp-slot-no">' + (s.no || ('图' + (i + 1))) + '</span>' +
                    '<span class="wxp-slot-info"><span class="wxp-desc">' + escAttr(s.speaker ? (s.speaker + ' · ') : '') + escAttr(s.desc || '') + '</span></span>' +
                    '<span class="wxp-slot-thumb' + (s.path ? ' ok' : ' warn') + '">' +"""
must(s.count(old) == 1, "slot markup anchor")
new = """            const slotFilled = !!s.path;
            return '<div class="wxp-slot ' + (slotFilled ? 'filled' : 'empty') + '" data-id="' + escAttr(s.id) + '">' +
                '<div class="wxp-slot-main">' +
                    '<span class="wxp-slot-no">' + (s.no || ('图' + (i + 1))) + '</span>' +
                    '<span class="wxp-slot-info"><span class="wxp-desc">' + escAttr(s.speaker ? (s.speaker + ' · ') : '') + escAttr(s.desc || '') + '</span></span>' +
                    '<span class="wxp-slot-tag' + (slotFilled ? ' ok' : '') + '">' + (slotFilled ? '已配图' : '待配图') + '</span>' +
                    '<span class="wxp-slot-thumb' + (s.path ? ' ok' : ' warn') + '">' +"""
s = s.replace(old, new, 1)

old_count = """        if (count) count.textContent = '已配 ' + filled + '/' + slots.length;"""
must(s.count(old_count) == 1, "count anchor")
new_count = """        if (count) {
            count.textContent = '已配 ' + filled + '/' + slots.length;
            count.className = 'wxp-count' + (filled >= slots.length ? ' done' : ' pending');
        }"""
s = s.replace(old_count, new_count, 1)
save(SP, s)
print("shared_picker.js saved")

# ==================================================================
# 2) index.html —— 需配图步骤改琥珀色 + 状态标签
# ==================================================================
IDX = r"G:\weixin-auto\editor\index.html"
s = load(IDX)

HELPER = '''    /* 图片参数是否已配真实图（占位描述/关键词不算已配） */
    function imgPathFilled(v) {
      const t = String(v == null ? "" : v).trim();
      return !!t && (t.startsWith("/") || /^https?:/i.test(t));
    }
    function isImageStep(step) {'''
must(s.count("    function isImageStep(step) {") == 1, "isImageStep anchor")
s = s.replace("    function isImageStep(step) {", HELPER, 1)

old = '''        card.className = "script-step" + (index === scriptSelected ? " selected" : "") + (isImageStep(step) ? " img" : "");'''
must(s.count(old) == 1, "script-step class anchor")
new = '''        const imgStep = isImageStep(step);
        const imgReady = imgStep && (imgPathFilled((step.params || {})["图片"]) || imgPathFilled((step.params || {})["表情"]));
        card.className = "script-step" + (index === scriptSelected ? " selected" : "") +
          (imgStep ? (" img" + (imgReady ? " filled" : "")) : "");'''
s = s.replace(old, new, 1)

old = '''          '<div class="ss-main"><div class="ss-title">' + esc(step.action) + '</div>' +
          '<div class="ss-summary">' + esc(scriptStepSummary(step)) + '</div></div>' +
          '<div class="ss-ops">' +'''
must(s.count(old) == 1, "ss-main anchor")
new = '''          '<div class="ss-main"><div class="ss-title">' + esc(step.action) + '</div>' +
          '<div class="ss-summary">' + esc(scriptStepSummary(step)) + '</div></div>' +
          (imgStep ? '<span class="ss-need' + (imgReady ? ' ok' : '') + '">' + (imgReady ? '已配图' : '待配图') + '</span>' : '') +
          '<div class="ss-ops">' +'''
s = s.replace(old, new, 1)

IMG_CSS_OLD = '''/* 图片消息步骤：绿色高亮便于区分（发图片/图片消息） */
.script-step.img {
  border-color: var(--green-line);
  background: rgba(10, 172, 95, 0.07);
  box-shadow: 0 4px 14px rgba(10, 172, 95, 0.08);
}
.script-step.img .ss-index { background: var(--green-soft); color: #0a8a4f; }
.script-step.img .ss-title { color: #0a7a4a; }'''
must(s.count(IMG_CSS_OLD) == 1, "img css anchor")
IMG_CSS_NEW = '''/* 需要配图的步骤：琥珀色 = 待配图，绿色 = 已配图 */
.script-step.img {
  border-color: var(--amber-line);
  background: var(--amber-soft);
  box-shadow: 0 4px 14px rgba(214, 148, 32, 0.10);
}
.script-step.img .ss-index { background: rgba(233, 162, 59, 0.20); color: #a5650a; }
.script-step.img .ss-title { color: #8a5306; }
.script-step.img.filled {
  border-color: var(--green-line);
  background: rgba(10, 172, 95, 0.06);
  box-shadow: 0 4px 14px rgba(10, 172, 95, 0.08);
}
.script-step.img.filled .ss-index { background: var(--green-soft); color: #0a8a4f; }
.script-step.img.filled .ss-title { color: #0a7a4a; }
.script-step .ss-need {
  flex: none; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600;
  background: rgba(233, 162, 59, 0.18); color: #a5650a; border: 1px solid var(--amber-line);
}
.script-step .ss-need.ok { background: var(--green-soft); color: #0a8a4f; border-color: var(--green-line); }'''
s = s.replace(IMG_CSS_OLD, IMG_CSS_NEW, 1)
save(IDX, s)
print("index.html saved")

# ==================================================================
# 3) concurrent.html —— 步骤行同样处理
# ==================================================================
CC = r"G:\weixin-auto\editor\concurrent.html"
s = load(CC)

old = """    return '<div class="step-row' + (imgKey ? ' img' : '') + '" data-step="' + i + '">' +
      '<span class="no">' + (i + 1) + '</span>' +
      '<span class="act">' + esc(s.action || '?') + '</span>' +"""
must(s.count(old) == 1, "step-row anchor")
new = """    const rowFilled = imgKey ? imgPathFilled((s.params || {})[imgKey]) : false;
    return '<div class="step-row' + (imgKey ? (' img' + (rowFilled ? ' filled' : '')) : '') + '" data-step="' + i + '">' +
      '<span class="no">' + (i + 1) + '</span>' +
      '<span class="act">' + esc(s.action || '?') + '</span>' +
      (imgKey ? '<span class="need' + (rowFilled ? ' ok' : '') + '">' + (rowFilled ? '已配图' : '待配图') + '</span>' : '') +"""
s = s.replace(old, new, 1)

old_img = """      imgHtml = '<button type="button" class="imgslot" data-step="' + i + '" data-act="pickimg" title="' +"""
must(s.count(old_img) == 1, "imgslot anchor")
new_img = """      imgHtml = '<button type="button" class="imgslot' + (imgPathFilled(cur) ? ' ok' : ' need') + '" data-step="' + i + '" data-act="pickimg" title="' +"""
s = s.replace(old_img, new_img, 1)

HELPER2 = '''function imgPathFilled(v) {
  const t = String(v == null ? '' : v).trim();
  return !!t && (t.startsWith('/') || /^https?:/i.test(t));
}
function stepSummary(p) {'''
must(s.count("function stepSummary(p) {") == 1, "stepSummary anchor")
s = s.replace("function stepSummary(p) {", HELPER2, 1)

CSS_OLD = """  .step-row.img { border-color: var(--accent-border); background: rgba(10, 172, 95, 0.06); }
  .step-row.img .act { color: #0a7a4a; }
  .step-row.img .no { background: var(--accent-soft); color: #0a8a4f; }
  .step-row.img .empty-sum { color: #0a7a4a; }"""
must(s.count(CSS_OLD) == 1, "step-row img css anchor")
CSS_NEW = """  .step-row.img { border-color: var(--wxp-amber-line); background: #fff8ea; }
  .step-row.img .act { color: #8a5306; }
  .step-row.img .no { background: rgba(233, 162, 59, 0.20); color: #a5650a; }
  .step-row.img .empty-sum { color: #8a5306; }
  .step-row.img.filled { border-color: var(--wxp-accent-line); background: #f2fbf7; }
  .step-row.img.filled .act { color: #0a7a4a; }
  .step-row.img.filled .no { background: #e8f7ef; color: #0a8a4f; }
  .step-row.img.filled .empty-sum { color: #0a7a4a; }
  .step-row .need { flex: 0 0 auto; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: rgba(233, 162, 59, 0.18); color: #a5650a; border: 1px solid var(--wxp-amber-line); }
  .step-row .need.ok { background: #e8f7ef; color: #0a8a4f; border-color: var(--wxp-accent-line); }
  .step-row .imgslot.need { border-color: var(--wxp-amber-line); background: #fff8ea; }
  .step-row .imgslot.ok { border-color: var(--wxp-accent); }"""
s = s.replace(CSS_OLD, CSS_NEW, 1)

TOKEN_CSS = """
/* ---------- 浅色状态配色令牌（配图相关） ---------- */
:root {
  --wxp-amber-soft: #fff8ea;
  --wxp-amber-line: rgba(214, 148, 32, .55);
  --wxp-accent-line: rgba(10, 172, 95, .40);
}
</style>"""
must(s.count('</style>') == 1, "concurrent style block")
s = s.replace('</style>', TOKEN_CSS, 1)
save(CC, s)
print("concurrent.html saved")
print("ALL DONE")
