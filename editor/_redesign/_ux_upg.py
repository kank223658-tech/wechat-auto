# -*- coding: utf-8 -*-
"""UX 可用性升级（2026-09-11）：
index.html —— 撤销/重做、插入到选中步骤之后、动作库拖拽插入、键盘快捷键
scene.html —— 文本输入不丢焦点不重建面板、卡片可折叠、保留滚动位置
铁律：只动视觉/交互层，不改任何 id、data-page-node-id、画布样式、数据契约。
"""
import io, sys

def apply(path, edits):
    s = io.open(path, encoding="utf-8").read()
    total = 0
    for old, new, expect in edits:
        n = s.count(old)
        if n != expect:
            print("ABORT %s: anchor hit %d times (expect %d):\n---\n%s\n---" % (path, n, expect, old[:160]))
            sys.exit(1)
        s = s.replace(old, new, 1)
        total += 1
    io.open(path, "w", encoding="utf-8", newline="").write(s)
    print("OK %s: %d edits applied" % (path, total))

# ============================ index.html ============================
IDX = r"G:\weixin-auto\editor\index.html"

UNDO_JS = '''    /* ================= 撤销 / 重做 ================= */
    const undoStack = [];
    const redoStack = [];
    function snapshot() {
      return JSON.stringify({ steps: workflow.steps, selected });
    }
    function pushUndo() {
      undoStack.push(snapshot());
      if (undoStack.length > 100) undoStack.shift();
      redoStack.length = 0;
    }
    let _lastSnapAt = 0;
    function pushUndoThrottled() {
      const now = Date.now();
      if (now - _lastSnapAt > 1200) { pushUndo(); _lastSnapAt = now; }
    }
    function restoreSnapshot(snap) {
      const data = JSON.parse(snap);
      workflow.steps = data.steps;
      selected = Math.max(-1, Math.min(data.selected, workflow.steps.length - 1));
      renderCanvas();
      renderProps();
      markDirty();
      saveLocalDebounced();
    }
    function undo() {
      if (!undoStack.length) return;
      redoStack.push(snapshot());
      restoreSnapshot(undoStack.pop());
    }
    function redo() {
      if (!redoStack.length) return;
      undoStack.push(snapshot());
      restoreSnapshot(redoStack.pop());
    }

    /* ================= 步骤操作 ================= */'''

IDX_EDITS = [
# 1) 工具栏加撤销/重做按钮
('''          <div class="board-actions">
            <button type="button" class="btn small" id="btnDuplicate" disabled>复制步骤</button>''',
'''          <div class="board-actions">
            <button type="button" class="btn small" id="btnUndo" title="撤销上一步操作 (Ctrl+Z)" disabled>↶ 撤销</button>
            <button type="button" class="btn small" id="btnRedo" title="重做 (Ctrl+Y 或 Ctrl+Shift+Z)" disabled>↷ 重做</button>
            <button type="button" class="btn small" id="btnDuplicate" disabled>复制步骤</button>''', 1),

# 2) renderCanvas 里同步撤销/重做按钮可用态
('''      $("btnRunFrom").disabled = selected < 0 || selected >= workflow.steps.length;''',
'''      $("btnRunFrom").disabled = selected < 0 || selected >= workflow.steps.length;
      if ($("btnUndo")) $("btnUndo").disabled = !undoStack.length;
      if ($("btnRedo")) $("btnRedo").disabled = !redoStack.length;''', 1),

# 3) 空画布引导文案补充快捷键说明
('''          '<p>从左侧动作库点击添加步骤；中间卡片就是流程本体，可上下移动、复制、删除，右侧编辑每个动作参数。</p>' +''',
'''          '<p>从左侧动作库点击添加步骤（新步骤会插到当前选中步骤之后）；也可直接把动作<b>拖拽</b>到流程的任意位置。支持 Ctrl+Z 撤销、Delete 删除选中、Ctrl+D 复制。</p>' +''', 1),

# 4) 参数输入时打点撤销快照（节流，不会每个键一张）
('''        const commit = () => {
          step.params[p.key] = ctrl.value;''',
'''        const commit = () => {
          pushUndoThrottled();
          step.params[p.key] = ctrl.value;''', 1),

# 5) 注入撤销/重做系统
('''    /* ================= 步骤操作 ================= */''', UNDO_JS, 1),

# 6) 动作库卡片可拖拽
('''          btn.onclick = () => addStep(a.action);
          el.appendChild(btn);''',
'''          btn.onclick = () => addStep(a.action);
          btn.draggable = true;
          btn.addEventListener("dragstart", (event) => {
            event.dataTransfer.effectAllowed = "copy";
            event.dataTransfer.setData("text/plain", "palette:" + a.action);
          });
          el.appendChild(btn);''', 1),

# 7) 节点 dragover 兼容两种拖拽来源
('''        card.addEventListener("dragover", (event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
        });''',
'''        card.addEventListener("dragover", (event) => {
          event.preventDefault();
        });''', 1),

# 8) 拖到节点上 = 从动作库插入到该位置 / 画布内排序
('''        card.addEventListener("drop", (event) => {
          event.preventDefault();
          const raw = event.dataTransfer.getData("text/plain");
          const from = Number(raw);
          if (!Number.isInteger(from)) return;
          moveStep(from, index);
        });''',
'''        card.addEventListener("drop", (event) => {
          event.preventDefault();
          const raw = event.dataTransfer.getData("text/plain");
          if (raw && raw.startsWith("palette:")) { addStep(raw.slice(8), index); return; }
          const from = Number(raw);
          if (!Number.isInteger(from)) return;
          moveStep(from, index);
        });''', 1),

# 9) 拖到画布空白处 = 从动作库追加到末尾
('''      el.ondrop = (event) => {
        event.preventDefault();
        const raw = event.dataTransfer.getData("text/plain");
        const from = Number(raw);
        if (!Number.isInteger(from)) return;
        moveStep(from, workflow.steps.length);
      };''',
'''      el.ondrop = (event) => {
        event.preventDefault();
        const raw = event.dataTransfer.getData("text/plain");
        if (raw && raw.startsWith("palette:")) { addStep(raw.slice(8)); return; }
        const from = Number(raw);
        if (!Number.isInteger(from)) return;
        moveStep(from, workflow.steps.length);
      };''', 1),

# 10) addStep：默认插入到选中步骤之后，并自动滚到新卡片
('''    function addStep(action) {
      const def = getDef(action);
      const params = {};
      (def.params || []).forEach((p) => {
        params[p.key] = p.default !== undefined ? p.default : "";
      });
      workflow.steps.push({ action, params });
      selected = workflow.steps.length - 1;
      renderCanvas();
      renderProps();
      markDirty();
      saveLocalDebounced();
    }''',
'''    function addStep(action, atIndex) {
      const def = getDef(action);
      const params = {};
      (def.params || []).forEach((p) => {
        params[p.key] = p.default !== undefined ? p.default : "";
      });
      const at = Number.isInteger(atIndex)
        ? Math.max(0, Math.min(workflow.steps.length, atIndex))
        : (selected >= 0 && selected < workflow.steps.length ? selected + 1 : workflow.steps.length);
      pushUndo();
      workflow.steps.splice(at, 0, { action, params });
      selected = at;
      renderCanvas();
      renderProps();
      const node = $("flowCanvas").querySelector('.step-node[data-index="' + at + '"]');
      if (node && node.scrollIntoView) node.scrollIntoView({ block: "nearest" });
      markDirty();
      saveLocalDebounced();
    }''', 1),

# 11) 删除/移动/复制前先存快照
('''    function removeStep(index) {
      if (index < 0 || index >= workflow.steps.length) return;
      workflow.steps.splice(index, 1);''',
'''    function removeStep(index) {
      if (index < 0 || index >= workflow.steps.length) return;
      pushUndo();
      workflow.steps.splice(index, 1);''', 1),
('''      } else {
        const [step] = workflow.steps.splice(from, 1);''',
'''      } else {
        pushUndo();
        const [step] = workflow.steps.splice(from, 1);''', 1),
('''      const copy = clone(workflow.steps[index]);
      workflow.steps.splice(index + 1, 0, copy);''',
'''      const copy = clone(workflow.steps[index]);
      pushUndo();
      workflow.steps.splice(index + 1, 0, copy);''', 1),

# 12) 按钮绑定 + 全局键盘快捷键
('''    $("btnDuplicate").onclick = () => duplicateStep(selected);
    $("btnDelete").onclick = () => removeStep(selected);''',
'''    $("btnUndo").onclick = () => undo();
    $("btnRedo").onclick = () => redo();
    $("btnDuplicate").onclick = () => duplicateStep(selected);
    $("btnDelete").onclick = () => removeStep(selected);
    /* 键盘快捷键：焦点在输入框里时不拦截 */
    document.addEventListener("keydown", (event) => {
      const t = event.target;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
      const mod = event.ctrlKey || event.metaKey;
      if (mod && !event.shiftKey && (event.key === "z" || event.key === "Z")) {
        if (!typing) { event.preventDefault(); undo(); }
        return;
      }
      if (mod && ((event.shiftKey && (event.key === "Z" || event.key === "z")) || event.key === "y" || event.key === "Y")) {
        if (!typing) { event.preventDefault(); redo(); }
        return;
      }
      if (typing) return;
      if (mod && (event.key === "d" || event.key === "D")) {
        event.preventDefault();
        if (selected >= 0 && selected < workflow.steps.length) duplicateStep(selected);
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        if (selected >= 0 && selected < workflow.steps.length) { event.preventDefault(); removeStep(selected); }
      }
    });''', 1),
]

# ============================ scene.html ============================
SCN = r"G:\weixin-auto\editor\scene.html"

FOLD_JS = '''/* ---------- 输入体验：文本边打边存，防抖刷新手机预览，不重建面板 ---------- */
let _phoneRefreshTimer = null;
function schedulePhoneRefresh() {
  if (_phoneRefreshTimer) clearTimeout(_phoneRefreshTimer);
  _phoneRefreshTimer = setTimeout(() => { _phoneRefreshTimer = null; renderPhone(); }, 250);
}

/* ---------- 卡片折叠：每个卡片可展开/收起，顶部可全部展开/收起 ---------- */
const cardFoldState = new Map();
function applyCardFolds() {
  const body = $('panelBody');
  body.querySelectorAll('.card').forEach((card, ci) => {
    const head = card.querySelector(':scope > .head');
    if (!head || head.querySelector('.fold-btn')) return;
    const fold = document.createElement('div');
    fold.className = 'card-fold';
    while (head.nextSibling) fold.appendChild(head.nextSibling);
    card.appendChild(fold);
    const key = panelTab + '#' + ci + '#' + (head.textContent || '').trim().slice(0, 10);
    fold.dataset.foldKey = key;
    const tog = document.createElement('button');
    tog.type = 'button';
    tog.className = 'fold-btn';
    tog.title = '展开 / 收起这个卡片';
    const open0 = cardFoldState.has(key) ? cardFoldState.get(key) : true;
    tog.textContent = open0 ? '▾' : '▸';
    if (!open0) fold.classList.add('closed');
    tog.onclick = (e) => {
      e.stopPropagation();
      const nowOpen = !fold.classList.contains('closed');
      cardFoldState.set(key, !nowOpen);
      fold.classList.toggle('closed', nowOpen);
      tog.textContent = nowOpen ? '▸' : '▾';
    };
    head.insertBefore(tog, head.firstChild);
  });
  if (!body.querySelector('.fold-toolbar')) {
    const bar = document.createElement('div');
    bar.className = 'fold-toolbar';
    bar.innerHTML = '<button type="button" data-fold="open">⊟ 全部展开</button><button type="button" data-fold="close">▤ 全部收起</button>';
    bar.querySelectorAll('button').forEach(b => {
      b.onclick = () => {
        const open = b.getAttribute('data-fold') === 'open';
        body.querySelectorAll('.card .card-fold').forEach(f => {
          f.classList.toggle('closed', !open);
          if (f.dataset.foldKey) cardFoldState.set(f.dataset.foldKey, open);
        });
        body.querySelectorAll('.card .fold-btn').forEach(t => { t.textContent = open ? '▾' : '▸'; });
      };
    });
    body.insertBefore(bar, body.firstChild);
  }
}

'''

SCN_EDITS = [
# 1) renderPanel：保留滚动位置 + 应用折叠
('''function renderPanel() {
  const body = $('panelBody');
  if (panelTab === 'conversations') body.innerHTML = panelConversations();
  else if (panelTab === 'messages') body.innerHTML = panelMessages();
  else if (panelTab === 'moments') body.innerHTML = panelMoments();
  else if (panelTab === 'peer') body.innerHTML = panelPeer();
  else body.innerHTML = panelMe();
  bindPanelEvents();
}''',
FOLD_JS + '''function renderPanel() {
  const body = $('panelBody');
  const keepScroll = body.scrollTop;
  if (panelTab === 'conversations') body.innerHTML = panelConversations();
  else if (panelTab === 'messages') body.innerHTML = panelMessages();
  else if (panelTab === 'moments') body.innerHTML = panelMoments();
  else if (panelTab === 'peer') body.innerHTML = panelPeer();
  else body.innerHTML = panelMe();
  applyCardFolds();
  bindPanelEvents();
  body.scrollTop = keepScroll;
}''', 1),

# 2) data-set 提交逻辑：文本不再触发面板重建
('''  document.querySelectorAll('#panelBody [data-set]').forEach(el => {
    el.onchange = () => {
      const path = el.getAttribute('data-set');
      const val = el.type === 'checkbox' ? el.checked : el.type === 'number' ? (parseInt(el.value, 10) || 0) : el.value;
      setPath(path, val);
      normalizeLists();
      renderPhone(); renderPanel();
    };
  });''',
'''  document.querySelectorAll('#panelBody [data-set]').forEach(el => {
    const isText = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type !== 'checkbox' && el.type !== 'number' && el.type !== 'range');
    const commit = (redrawPanel) => {
      const path = el.getAttribute('data-set');
      const val = el.type === 'checkbox' ? el.checked : el.type === 'number' ? (parseInt(el.value, 10) || 0) : el.value;
      setPath(path, val);
      normalizeLists();
      schedulePhoneRefresh();
      if (redrawPanel) renderPanel();
    };
    if (isText) {
      /* 文本输入：边打字边提交 + 防抖刷新手机预览；不重建面板，焦点和滚动位置都不丢 */
      el.oninput = () => commit(false);
      el.onchange = () => commit(false);
    } else {
      el.onchange = () => commit(true);
    }
  });''', 1),

# 3) 折叠样式（追加到 style 块末尾）
('</style>',
'''/* ---------- 卡片折叠控件 ---------- */
.fold-toolbar { display: flex; gap: 6px; margin: 0 0 10px; }
.fold-toolbar button {
  padding: 3px 10px; font-size: 11px; cursor: pointer;
  border: 1px solid var(--line); border-radius: 8px;
  background: var(--panel-2); color: var(--muted);
}
.fold-toolbar button:hover { color: var(--accent); border-color: var(--accent-border); }
.fold-btn {
  flex: none; width: 22px; height: 22px; padding: 0;
  display: grid; place-items: center; cursor: pointer;
  border: 1px solid transparent; border-radius: 7px;
  background: transparent; color: var(--muted); font-size: 12px; line-height: 1;
}
.fold-btn:hover { border-color: var(--line); background: var(--panel-3); color: var(--accent); }
.card-fold.closed { display: none; }
</style>''', 1),
]

apply(IDX, IDX_EDITS)
apply(SCN, SCN_EDITS)
print("ALL DONE")
