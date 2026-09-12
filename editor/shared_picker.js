/* ============================================================
   共享「图片选择 + 配图面板」组件（editor_server.py 托管 /shared_picker.js）
   ------------------------------------------------------------
   供两个页面复用：编辑器「脚本模式」(index.html) 与场景编辑器「剧本一键导入」(scene.html)。
   独立命名空间 window.__wxPick，用 wxp- 前缀的类名/ID，避免与两页已有
   gallery / pickerSel / picker-* 全局变量和样式冲突。

   API：
   window.__wxPick
     .onReady(cb)                        —— 组件就绪后回调（拉取一次图片库）
     .openPicker({ current, onPick })    —— 打开图片选择弹窗：搜索+缩略图网格+批量上传+链接+预览；onPick(path) 选中后回调
     .renderAttachPanel(el, slots, onChange)
                                         —— 渲染「配图面板」：逐槽显示 序号+说话人+描述+缩略图+选图；
                                            onChange(id, path) 在某槽配图后回调；返回后可随时用 restoreAssigns() 回填
     .setSlotsState(slots)               —— 更新现有槽的 path（例如回填已配的图）；自动刷新缩略图
     .listImages()                       —— 返回当前缓存的图片库路径数组
     .uploadFiles(files, cb, category)   —— 批量上传（供拖拽配图复用），category 指定存入分类；cb(pathList)
   ============================================================ */
(() => {
    if (window.__wxPick) return;

    /* ---- 注入样式（深色主题，对齐场景编辑器） ---- */
    function initStyles() {
        if (document.getElementById('wxp-style')) return;
        const st = document.createElement('style');
        st.id = 'wxp-style';
        st.textContent = `
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
/* 打开动画编辑器：分段开关 + 滑杆 + 焦点小图（配图清单 / 运行确认弹窗共用） */
.wxp-openrow { display: flex; flex-direction: column; gap: 7px; }
.wxp-slot .wxp-openrow { padding-left: 48px; }.wxp-openrow-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.wxp-openrow-head .wxp-olabel { font-size: 12px; font-weight: 600; color: var(--wxp-text-2); flex: 0 0 auto; }
.wxp-openrow-head .wxp-olinetip { font-size: 11px; color: var(--wxp-muted); }
.wxp-seg { display: inline-flex; border: 1px solid var(--wxp-line-strong); border-radius: 8px; overflow: hidden; background: var(--wxp-panel); flex: 0 0 auto; }
.wxp-seg button { cursor: pointer; border: 0; background: transparent; color: var(--wxp-text-2); font-size: 12px; padding: 5px 12px; border-right: 1px solid var(--wxp-line); font: inherit; font-size: 12px; }
.wxp-seg button:last-child { border-right: 0; }
.wxp-seg button:hover { background: var(--wxp-panel-2); }
.wxp-seg button.on { background: var(--wxp-accent); color: #ffffff; font-weight: 600; }
.wxp-prevbtn2 { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 4px 11px; font-size: 12px; font: inherit; font-size: 12px; }
.wxp-prevbtn2:hover { background: var(--wxp-panel); border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-openrow-detail { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; background: var(--wxp-panel); border: 1px solid var(--wxp-line); border-radius: 9px; padding: 8px 12px; }
.wxp-focuswrap { display: flex; flex-direction: column; align-items: center; gap: 3px; flex: 0 0 auto; }
.wxp-focusthumb { position: relative; width: 46px; height: 46px; border-radius: 8px; overflow: hidden; border: 1px solid var(--wxp-line-strong); cursor: crosshair; background: var(--wxp-panel-2); display: block; padding: 0; }
.wxp-focusthumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.wxp-focusthumb .wxp-fdot { position: absolute; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%; background: var(--wxp-accent); border: 2px solid #ffffff; box-shadow: 0 0 0 1px rgba(0, 0, 0, .25); }
.wxp-focusthumb .wxp-fempty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 10px; color: var(--wxp-muted); }
.wxp-focuswrap .wxp-focuscap { font-size: 10px; color: var(--wxp-muted); max-width: 60px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-sliderwrap { display: flex; align-items: center; gap: 8px; min-width: 210px; flex: 1; }
.wxp-sliderwrap .wxp-slabel { font-size: 12px; color: var(--wxp-text-2); flex: 0 0 auto; }
.wxp-sliderwrap input[type=range] { flex: 1; min-width: 100px; accent-color: var(--wxp-accent); cursor: pointer; }
.wxp-sliderwrap .wxp-sval { font-size: 11px; font-weight: 600; color: var(--wxp-accent); background: var(--wxp-accent-soft); border: 1px solid var(--wxp-accent-line); border-radius: 999px; padding: 2px 8px; flex: 0 0 auto; min-width: 56px; text-align: center; }
.wxp-sliderwrap .wxp-sval.dim { color: var(--wxp-muted); background: var(--wxp-panel-2); border-color: var(--wxp-line); font-weight: 500; }
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

/* ---- 图库：分类计数 / 记忆 / 批量 / 拖拽 ---- */
.wxp-typebtn .wxp-cnt { display: inline-block; margin-left: 5px; font-size: 10px; font-weight: 600; opacity: .75; background: rgba(17, 24, 39, .07); border-radius: 999px; padding: 0 5px; }
.wxp-typebtn.on .wxp-cnt { background: rgba(255, 255, 255, .28); opacity: .95; }
.wxp-typebtn.drop { border-color: var(--wxp-accent); background: var(--wxp-accent-soft); color: var(--wxp-accent); transform: scale(1.06); }
.wxp-minibtn { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 6px 10px; font: inherit; font-size: 12px; }
.wxp-minibtn:hover { border-color: var(--wxp-accent-line); color: var(--wxp-accent); background: var(--wxp-panel); }
.wxp-minibtn.on { background: var(--wxp-accent); border-color: var(--wxp-accent); color: #ffffff; font-weight: 600; }
.wxp-bulk { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 0 0 8px; padding: 7px 10px; border: 1px solid var(--wxp-accent-line); background: var(--wxp-accent-soft); border-radius: 9px; font-size: 12px; color: var(--wxp-text); }
.wxp-bulk b { color: var(--wxp-accent); }
.wxp-bulk select { background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 6px; padding: 4px 6px; font: inherit; font-size: 12px; }
.wxp-bulk button { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 6px; padding: 4px 10px; font: inherit; font-size: 12px; }
.wxp-bulk button:hover { border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-bulk button.danger { color: var(--wxp-red); border-color: rgba(213, 73, 65, .4); }
.wxp-bulk button.danger:hover { background: #fdf3f2; color: var(--wxp-red); }
.wxp-item.marked { border-color: var(--wxp-accent); box-shadow: inset 0 0 0 2px var(--wxp-accent); }
.wxp-item[draggable="true"] { cursor: grab; }
.wxp-item[draggable="true"]:active { cursor: grabbing; }
.wxp-item .wxp-check { position: absolute; left: 4px; top: 3px; width: 16px; height: 16px; border-radius: 4px; border: 1px solid var(--wxp-line-strong); background: #ffffff; display: none; align-items: center; justify-content: center; font-size: 11px; line-height: 1; color: #ffffff; z-index: 2; }
body.wxp-bulkmode .wxp-item .wxp-check { display: flex; }
.wxp-item.marked .wxp-check { background: var(--wxp-accent); border-color: var(--wxp-accent); }
.wxp-item.marked .wxp-check::after { content: "✓"; }
.wxp-drophint { margin: 8px 0 0; border: 1px dashed var(--wxp-line-strong); border-radius: 9px; background: var(--wxp-panel); color: var(--wxp-muted); font-size: 11px; text-align: center; padding: 6px 8px; }
.wxp-dropcover { position: fixed; inset: 0; z-index: 96; display: none; align-items: center; justify-content: center; background: rgba(10, 172, 95, .10); border: 3px dashed var(--wxp-accent); }
.wxp-dropcover.show { display: flex; }
.wxp-dropcover span { background: var(--wxp-bg); border: 1px solid var(--wxp-accent-line); color: var(--wxp-accent); font-weight: 600; font-size: 15px; border-radius: 12px; padding: 14px 22px; box-shadow: 0 12px 30px rgba(17, 24, 39, .18); }
/* ---- 分类管理弹窗 ---- */
.wxp-cm { position: fixed; inset: 0; z-index: 97; display: none; align-items: center; justify-content: center; background: rgba(17, 24, 39, .40); }
.wxp-cm.show { display: flex; }
.wxp-cm-box { width: 470px; max-width: 92vw; max-height: 80vh; overflow: auto; background: var(--wxp-bg); color: var(--wxp-text); border-radius: 12px; border: 1px solid var(--wxp-line); padding: 14px; box-shadow: 0 24px 60px rgba(17, 24, 39, .25); }
.wxp-cm-box > b { font-size: 14px; }
.wxp-cm-tip { font-size: 11px; color: var(--wxp-muted); margin: 6px 0 10px; line-height: 1.7; }
.wxp-cm-row { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px dashed var(--wxp-line); }
.wxp-cm-row input { flex: 1; min-width: 0; background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 7px; padding: 5px 8px; font: inherit; font-size: 12px; }
.wxp-cm-row .wxp-cm-tag { font-size: 10px; color: var(--wxp-muted); border: 1px solid var(--wxp-line); border-radius: 999px; padding: 1px 7px; white-space: nowrap; }
.wxp-cm-row button { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 6px; padding: 4px 10px; font: inherit; font-size: 12px; }
.wxp-cm-row button:hover { border-color: var(--wxp-accent-line); color: var(--wxp-accent); }
.wxp-cm-row button.danger:hover { border-color: rgba(213, 73, 65, .45); color: var(--wxp-red); }
.wxp-cm-add { display: flex; gap: 8px; margin-top: 10px; }
.wxp-cm-add input { flex: 1; min-width: 0; background: var(--wxp-field); color: var(--wxp-text); border: 1px solid var(--wxp-line-strong); border-radius: 7px; padding: 6px 9px; font: inherit; }
.wxp-cm-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.wxp-cm-foot button { cursor: pointer; border: 1px solid var(--wxp-line-strong); background: var(--wxp-bg); color: var(--wxp-text); border-radius: 7px; padding: 6px 14px; font: inherit; }
.wxp-cm-foot .wxp-ok { background: var(--wxp-accent); border-color: var(--wxp-accent); color: #ffffff; font-weight: 600; }
`;
        (document.head || document.documentElement).appendChild(st);
    }

    /* ---- 图片库缓存 ---- */
    let galleryCache = [];       // 旧字段：纯路径列表（兼容现有 listImages / picker）
    let galleryFiles = [];       // 元信息列表 [{path,name,folder,category,type,label,size,mtime}]
    let galleryVideos = [];      // 视频素材 [{path,name}]
    let galleryCategories = [];  // 分类清单 [{key,label,folders,canUpload}]（后端下发，可自定义）

    function ensureGallery() {
        return fetch('/api/gallery').then(r => r.json()).then(d => {
            galleryFiles = (d && (d.files || [])) || [];
            galleryCache = (d && (d.images || [])) || galleryFiles.map(f => f.path);
            galleryVideos = (d && d.videos) || [];
            galleryCategories = (d && d.categories) || [];
            return galleryCache;
        }).catch(() => { galleryCache = galleryCache || []; return galleryCache; });
    }

    function listImages() { return galleryCache.slice(); }

    function galleryFolders() {
        const set = [];
        (galleryFiles || []).forEach(f => { if (f && !set.includes(f.folder)) set.push(f.folder); });
        set.sort();
        return set;
    }

    /* ---- 分类工具 ---- */
    function catList() {
        return (galleryCategories && galleryCategories.length) ? galleryCategories
            : ['avatar', 'sticker', 'emoji', 'bg', 'asset', 'icon'].map(k =>
                ({ key: k, label: catLabelOf(k), canUpload: k !== 'icon' }));
    }
    function catLabelOf(key) {
        const c = (galleryCategories || []).find(x => x.key === key);
        return c ? c.label : ({ avatar: '头像', sticker: '表情包', emoji: 'emoji',
                                bg: '背景', asset: '配图素材', icon: '系统图标' }[key] || key);
    }
    /* 每个分类现在有多少张（'' = 全部，'video' = 视频）。前端现算，永远与网格一致。 */
    function catCount(key) {
        if (key === '' ) return (galleryFiles || []).length;
        if (key === 'video') return (galleryVideos || []).length;
        return (galleryFiles || []).filter(f => f.category === key).length;
    }
    function uploadableCats() {
        return catList().filter(c => c.canUpload !== false &&
            (c.canUpload === true || ['avatar', 'sticker', 'emoji', 'bg', 'asset'].includes(c.key)));
    }

    /* ---- 批量上传 ----
       files: File[]；cb(pathList)；category 指定存入分类（字符串，或 (file, idx)=>cat 函数，逐个决定）；onProgress(done, total, name)。
       单个文件失败不会中断整批，失败原因收集在 errs 里（第 4 个回调参数）。 */
    function uploadFiles(files, cb, category, onProgress) {
        const valid = (files || []).filter(f => f && f.size <= 10 * 1024 * 1024);
        const errs = [];
        (files || []).forEach(f => { if (f && f.size > 10 * 1024 * 1024) errs.push((f.name || '?') + '：超过 10MB'); });
        if (!valid.length) { if (cb) cb([], errs); return; }
        let idx = 0; const paths = [];
        function catOf(file, i) {
            return (typeof category === 'function') ? (category(file, i) || '') : (category || '');
        }
        function next() {
            if (idx >= valid.length) {
                ensureGallery().then(() => { if (cb) cb(paths, errs); });
                return;
            }
            const f = valid[idx];
            const cat = catOf(f, idx);
            const reader = new FileReader();
            reader.onload = () => {
                fetch('/api/upload-image', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ data: reader.result, name: f.name, category: cat })
                }).then(r => r.json()).then(r => {
                    if (r && r.ok && r.path) paths.push(r.path);
                    else errs.push((f.name || '?') + '：' + ((r && r.msg) || '上传失败'));
                    idx++; if (onProgress) onProgress(idx, valid.length, f.name); next();
                }).catch(() => {
                    errs.push((f.name || '?') + '：网络错误');
                    idx++; if (onProgress) onProgress(idx, valid.length, f.name); next();
                });
            };
            reader.onerror = () => {
                errs.push((f.name || '?') + '：读取失败');
                idx++; if (onProgress) onProgress(idx, valid.length, f.name); next();
            };
            reader.readAsDataURL(f);
        }
        next();
    }

    /* 判断一组拖入的文件里有没有图片（拖文件夹时 files 为空但有 items）。 */
    function pickImageFiles(list) {
        return (list || []).filter(f => f && (/^image\//.test(f.type) ||
            /\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name || '')));
    }

    /* ---- 打开图片选择弹窗 ---- */
    const LS_CAT = 'wxp-picker-cat';        // 记忆：上次所在的分类
    const LS_FOLDER = 'wxp-picker-folder';  // 记忆：上次所在的目录
    const LS_SORT = 'wxp-picker-sort';      // 记忆：排序方式
    const SORTS = [
        { key: 'new', label: '最新在前' },
        { key: 'old', label: '最早在前' },
        { key: 'name', label: '按名称' },
        { key: 'size', label: '按体积' },
    ];
    let pickerSel = '';
    let pickerQuery = '';
    let pickerOnPick = null;
    let pickerCurrent = '';
    let pickerCategory = ''; // ''=全部 | avatar/sticker/emoji/bg/asset/icon/自定义 | 'video'
    let pickerFolder = '';   // ''=全部目录 | 目录名
    let pickerSort = 'new';
    let pickerBulkMode = false;
    let pickerMarked = [];   // 批量选中的路径（数组，保持顺序）
    let pickerLastIdx = -1;  // Shift 范围选择用
    let pickerCatAuto = false;  // 分类是"首次自动选的"→ 图库加载完再校正一次
    let dragPaths = [];      // 正在从网格里拖动的图片路径（区别于拖入文件）

    function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
    function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 忽略 */ } }

    /* 从没选过分类时默认停在「配图素材」；那一类没有图就退回「全部」。 */
    function defaultCategory() { return catCount('asset') > 0 ? 'asset' : ''; }

    /* 恢复上次所在的分类（记忆失败/分类已不存在时回落到默认）。 */
    function restoreCat() {
        const v = lsGet(LS_CAT);
        if (v === null) { pickerCatAuto = true; return defaultCategory(); }
        if (v === '' || v === 'video') return v;
        if (catList().some(c => c.key === v)) return v;
        pickerCatAuto = true;
        return defaultCategory();
    }

    function pickerOpen(opts) {
        opts = opts || {};
        pickerOnPick = typeof opts.onPick === 'function' ? opts.onPick : null;
        pickerCurrent = opts.current || '';
        pickerSel = pickerCurrent;
        pickerQuery = '';
        pickerCatAuto = false;
        pickerCategory = (typeof opts.category === 'string') ? opts.category : restoreCat();
        pickerFolder = lsGet(LS_FOLDER) || '';
        const s = lsGet(LS_SORT);
        pickerSort = SORTS.some(x => x.key === s) ? s : 'new';
        pickerBulkMode = false;
        pickerMarked = [];
        pickerLastIdx = -1;
        dragPaths = [];
        const mask = document.getElementById('wxp-mask');
        if (!mask) return;
        mask.innerHTML = pickerMarkup();
        mask.classList.add('show');
        document.body.classList.remove('wxp-bulkmode');
        bindPickerEvents();
        renderSortOptions();
        renderUploadCatOptions();
        syncUpcatWithCategory();
        renderMoveOptions();
        renderPickerCats();
        renderPickerFolderOptions();
        renderPickerGrid();
        renderBulkBar();
        updatePickerPreview();
        buildDropCover();
        // 每次打开都重新拉取图库，确保显示最新图片（含别处上传/命名的变更）
        ensureGallery().then(() => {
            if (pickerCatAuto) { pickerCategory = defaultCategory(); pickerCatAuto = false; }
            renderPickerCats(); renderUploadCatOptions(); syncUpcatWithCategory();
            renderMoveOptions(); renderPickerFolderOptions(); renderPickerGrid(); updatePickerPreview();
        });
    }

    /* 「存到」下拉跟随当前分类：省得每次上传还要再选一遍目标分类 */
    function syncUpcatWithCategory() {
        const sel = document.getElementById('wxp-upcat');
        if (!sel) return;
        if (uploadableCats().some(c => c.key === pickerCategory)) {
            sel.value = pickerCategory;
            try { localStorage.setItem('wxp-upcat', pickerCategory); } catch (e) { /* 忽略 */ }
        }
    }

    function pickerMarkup() {
        return '<div class="wxp-modal">' +
            '<div class="wxp-head"><b>选择图片</b>' +
                '<span class="wxp-target" id="wxp-target">' + (pickerCurrent || '') + '</span>' +
                '<button id="wxp-close">×</button></div>' +
            '<div class="wxp-toolbar">' +
                '<input id="wxp-search" placeholder="搜索文件名/命名...">' +
                '<select id="wxp-upcat" title="上传的图片存入哪个分类（拖入/Ctrl+V 粘贴也存这里）"></select>' +
                '<button id="wxp-upload">⬆ 上传图片</button>' +
                '<button id="wxp-urlbtn">🔗 使用链接</button>' +
                '<button id="wxp-catbtn" title="给分类改名，或新建自己的分类">⚙ 分类</button>' +
            '</div>' +
            '<div class="wxp-filter" id="wxp-cats"></div>' +
            '<div class="wxp-filter">' +
                '<select id="wxp-folder"><option value="">📁 全部目录</option></select>' +
                '<select id="wxp-sort" title="列表排序方式"></select>' +
                '<button id="wxp-multibtn" class="wxp-minibtn" title="进入多选：可一次把多张图搬到别的分类，或一次删多张">☑ 多选</button>' +
                '<span class="wxp-found" id="wxp-found"></span>' +
            '</div>' +
            '<div class="wxp-bulk" id="wxp-bulk" style="display:none"></div>' +
            '<div class="wxp-urlrow" id="wxp-urlrow" style="display:none">' +
                '<input id="wxp-url" placeholder="输入 /images/... 或 http(s):// 图片链接">' +
                '<button id="wxp-urlapply">应用</button>' +
            '</div>' +
            '<div class="wxp-grid" id="wxp-grid"></div>' +
            '<div class="wxp-drophint">💡 把图片拖到窗口任意位置即可上传；也可直接 Ctrl+V 粘贴截图。把缩略图拖到上方分类按钮上＝把这张图搬过去。</div>' +
            '<div class="wxp-footer">' +
                '<div class="wxp-preview">' +
                    '<img id="wxp-previmg" alt="">' +
                    '<div class="wxp-pvmeta">' +
                        '<div class="wxp-path" id="wxp-prevpath"></div>' +
                        '<div class="wxp-labelbox">' +
                            '<input id="wxp-label" placeholder="命名，便于搜索/识别（不改文件路径）">' +
                            '<button id="wxp-labelok" class="wxp-lb-btn">✏️ 命名</button>' +
                        '</div>' +
                        '<div class="wxp-labelbox">' +
                            '<select id="wxp-move" title="把这张图移动到指定分类（自动更新剧本/场景里的引用）">' +
                                '<option value="">📂 移动到分类…</option>' +
                            '</select>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="wxp-footbtns">' +
                    '<button id="wxp-copypath" class="wxp-misc">📋 复制</button>' +
                    '<button id="wxp-del" class="wxp-misc danger">🗑 删除</button>' +
                    '<button id="wxp-cancel" class="wxp-cancel">取消</button>' +
                    '<button id="wxp-ok" class="wxp-ok">确定</button>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    /* 排序下拉（记住上次选择） */
    function renderSortOptions() {
        const sel = document.getElementById('wxp-sort');
        if (!sel) return;
        sel.innerHTML = SORTS.map(s =>
            '<option value="' + s.key + '"' + (s.key === pickerSort ? ' selected' : '') + '>' +
            '⇅ ' + s.label + '</option>').join('');
    }

    function pickerSorted(list) {
        const arr = (list || []).slice();
        const nm = x => String((x && (x.label || x.name)) || '');
        arr.sort((a, b) => {
            if (pickerSort === 'old') return (a.ctime || 0) - (b.ctime || 0) || nm(a).localeCompare(nm(b), 'zh');
            if (pickerSort === 'name') return nm(a).localeCompare(nm(b), 'zh');
            if (pickerSort === 'size') return (b.size || 0) - (a.size || 0);
            return (b.ctime || 0) - (a.ctime || 0) || nm(a).localeCompare(nm(b), 'zh');
        });
        return arr;
    }

    function pickerFiltered() {
        const q = (pickerQuery || '').toLowerCase();
        return (galleryFiles || []).filter(f => {
            if (pickerCategory && f.category !== pickerCategory) return false;
            if (pickerFolder && f.folder !== pickerFolder) return false;
            if (q) {
                const hay = ((f.label || '') + ' ' + (f.name || '') + ' ' + (f.path || '')).toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
    }

    function pickerVideos() {
        const q = (pickerQuery || '').toLowerCase();
        return (galleryVideos || []).filter(v =>
            !q || (((v.name || '') + ' ' + (v.path || '')).toLowerCase().includes(q)));
    }

    /* 渲染分类筛选 chips（全部 / 各分类 / 🎬视频），按钮上带张数，还可当拖拽搬运的目标 */
    function renderPickerCats() {
        const box = document.getElementById('wxp-cats');
        if (!box) return;
        const mk = (key, label) =>
            '<span class="wxp-typebtn' + (pickerCategory === key ? ' on' : '') + '" data-cat="' + escAttr(key) + '">' +
            escAttr(label) + '<span class="wxp-cnt">' + catCount(key) + '</span></span>';
        let h = mk('', '全部');
        catList().forEach(c => { h += mk(c.key, c.label); });
        h += mk('video', '🎬 视频');
        box.innerHTML = h;
        box.querySelectorAll('.wxp-typebtn').forEach(btn => {
            const key = btn.getAttribute('data-cat') || '';
            btn.onclick = () => setPickerCategory(key);
            // 把缩略图拖到分类按钮上 = 直接把这张（或已多选的这些）搬过去
            btn.addEventListener('dragover', e => {
                if (!dragPaths.length) return;
                e.preventDefault(); e.stopPropagation();
                btn.classList.add('drop');
            });
            btn.addEventListener('dragleave', () => btn.classList.remove('drop'));
            btn.addEventListener('drop', e => {
                if (!dragPaths.length) return;
                e.preventDefault(); e.stopPropagation();
                btn.classList.remove('drop');
                const paths = dragPaths.slice();
                dragPaths = [];
                movePathsToCategory(paths, key);
            });
        });
    }

    /* 切换分类：记住选择，并让「上传存入分类」跟着走 */
    function setPickerCategory(key) {
        pickerCategory = key;
        pickerBulkMode = false;
        pickerMarked = [];
        pickerLastIdx = -1;
        document.body.classList.remove('wxp-bulkmode');
        lsSet(LS_CAT, key);
        syncUpcatWithCategory();
        renderPickerCats();
        renderPickerGrid();
        renderBulkBar();
    }

    /* 渲染「上传存入分类」下拉（记忆上次选择） */
    function renderUploadCatOptions() {
        const sel = document.getElementById('wxp-upcat');
        if (!sel) return;
        let saved = '';
        try { saved = localStorage.getItem('wxp-upcat') || ''; } catch (e) { /* 忽略 */ }
        const cats = uploadableCats();
        if (!cats.some(c => c.key === saved)) saved = cats.some(c => c.key === 'avatar') ? 'avatar' : (cats[0] || {}).key || '';
        sel.innerHTML = cats.map(c =>
            '<option value="' + escAttr(c.key) + '"' + (c.key === saved ? ' selected' : '') + '>' +
            '存到 · ' + escAttr(c.label) + '</option>').join('');
    }

    /* 渲染「移动到分类」下拉（图片专用） */
    function renderMoveOptions() {
        const sel = document.getElementById('wxp-move');
        if (!sel) return;
        sel.innerHTML = '<option value="">📂 移动到分类…</option>' +
            uploadableCats().map(c => '<option value="' + escAttr(c.key) + '">' + escAttr(c.label) + '</option>').join('');
    }

    /* 当前上传目标分类（拖入 / Ctrl+V 粘贴都存这里） */
    function targetUploadCat() {
        const sel = document.getElementById('wxp-upcat');
        return (sel && sel.value) || 'avatar';
    }

    function renderPickerFolderOptions() {
        const sel = document.getElementById('wxp-folder');
        if (!sel) return;
        const keep = pickerFolder;
        sel.innerHTML = '<option value="">📁 全部目录</option>' +
            galleryFolders().map(f => '<option value="' + escAttr(f) + '">' + escAttr(f === '/' ? '根目录' : f) + '</option>').join('');
        sel.value = galleryFolders().includes(keep) ? keep : '';
        pickerFolder = sel.value;
    }

    /* 网格：排序 + 多选标记 + 可拖动（拖到分类按钮即搬家） */
    function renderPickerGrid() {
        const grid = document.getElementById('wxp-grid');
        if (!grid) return;
        const isVideoTab = pickerCategory === 'video';
        const list = isVideoTab
            ? pickerSorted(pickerVideos().map(v => ({ path: v.path, label: v.name || v.path, name: v.path, isVideo: true })))
            : pickerSorted(pickerFiltered());
        const found = document.getElementById('wxp-found');
        if (found) found.textContent = '匹配 ' + list.length + (isVideoTab ? ' 个视频' : ' 张' +
            (pickerMarked.length ? ' · 已选 ' + pickerMarked.length : ''));
        let h = isVideoTab ? '' :
            '<div class="wxp-item" data-val=""><div class="wxp-thumb wxp-clear">无</div><span class="wxp-name">清除</span></div>';
        list.forEach(f => {
            const sel = f.path === pickerSel ? ' sel' : '';
            const marked = pickerMarked.indexOf(f.path) >= 0 ? ' marked' : '';
            const tag = f.isVideo ? '视频' : catLabelOf(f.category);
            const tagCls = f.isVideo ? ' wxp-tag-ic' : (f.category === 'icon' ? ' wxp-tag-ic' : ' wxp-tag-im');
            const thumb = f.isVideo
                ? '<div class="wxp-thumb"><span style="font-size:26px">🎬</span><span class="wxp-tag' + tagCls + '">' + tag + '</span></div>'
                : '<div class="wxp-thumb"><img src="' + escAttr(f.path) + '" alt="" draggable="false" onerror="this.style.opacity=.25">' +
                    '<span class="wxp-tag' + tagCls + '">' + tag + '</span></div>';
            h += '<div class="wxp-item' + sel + marked + '" data-val="' + escAttr(f.path) + '" title="' +
                escAttr(f.path + (f.size ? '\n' + fmtSize(f.size) : '')) + '" draggable="true">' +
                '<span class="wxp-check"></span>' +
                thumb +
                '<span class="wxp-name">' + escAttr(f.label || f.name) + '</span>' +
                '<span class="wxp-sub">' + escAttr(f.name) + '</span></div>';
        });
        if (!list.length) {
            h += isVideoTab
                ? '<div class="wxp-empty">还没有视频素材。用「上传视频」把 MP4 传进视频库，发朋友圈视频动态 / [播放视频] 就能选。</div>'
                : '<div class="wxp-empty">这里还没有图片。把图片拖到窗口任意位置、按 Ctrl+V 粘贴，或点「⬆ 上传图片」——都会存进右上角选的那个分类。</div>';
        }
        grid.innerHTML = h;
        const items = Array.prototype.slice.call(grid.querySelectorAll('.wxp-item'));
        items.forEach((el, idx) => {
            const val = el.getAttribute('data-val') || '';
            const sync = () => items.forEach(x => x.classList.toggle('sel', x.getAttribute('data-val') === pickerSel));
            el.onclick = (e) => {
                if (!val) {                       // 「清除」格子：只做选中
                    pickerSel = ''; sync(); updatePickerPreview(); return;
                }
                if (pickerBulkMode) { toggleMark(val, idx, e && e.shiftKey); return; }
                if (e && (e.ctrlKey || e.metaKey)) { setBulkMode(true); toggleMark(val, idx, false); return; }
                if (e && e.shiftKey && pickerLastIdx >= 0) {
                    const a = Math.min(pickerLastIdx, idx), b = Math.max(pickerLastIdx, idx);
                    setBulkMode(true);
                    for (let k = a; k <= b; k++) {
                        const v = items[k].getAttribute('data-val') || '';
                        if (v && pickerMarked.indexOf(v) < 0) pickerMarked.push(v);
                    }
                    pickerLastIdx = idx;
                    renderPickerGrid(); renderBulkBar(); return;
                }
                pickerSel = val; pickerLastIdx = idx;
                sync(); updatePickerPreview();
            };
            el.ondblclick = () => {
                if (pickerBulkMode || !val) return;
                pickerSel = val; commitPicker();
            };
            if (!val || el.getAttribute('draggable') !== 'true') return;
            el.addEventListener('dragstart', (e) => {
                dragPaths = (pickerMarked.indexOf(val) >= 0 && pickerMarked.length) ? pickerMarked.slice() : [val];
                el.style.opacity = '.45';
                try {
                    e.dataTransfer.setData('text/plain', dragPaths.join('\n'));
                    e.dataTransfer.effectAllowed = 'move';
                } catch (err) { /* 忽略 */ }
            });
            el.addEventListener('dragend', () => { dragPaths = []; el.style.opacity = ''; });
        });
    }

    function fmtSize(n) {
        const b = Number(n) || 0;
        if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + 'MB';
        if (b >= 1024) return Math.round(b / 1024) + 'KB';
        return b + 'B';
    }

    /* ---- 多选 / 批量 ---- */
    function setBulkMode(on) {
        pickerBulkMode = !!on;
        if (!on) { pickerMarked = []; pickerLastIdx = -1; }
        document.body.classList.toggle('wxp-bulkmode', pickerBulkMode);
        const b = document.getElementById('wxp-multibtn');
        if (b) b.classList.toggle('on', pickerBulkMode);
    }
    function toggleMark(val, idx, range) {
        if (!val) return;
        const i = pickerMarked.indexOf(val);
        if (i >= 0) pickerMarked.splice(i, 1); else pickerMarked.push(val);
        pickerLastIdx = idx;
        renderPickerGrid(); renderBulkBar();
    }
    function renderBulkBar() {
        const bar = document.getElementById('wxp-bulk');
        const mb = document.getElementById('wxp-multibtn');
        if (mb) mb.classList.toggle('on', pickerBulkMode);
        if (!bar) return;
        if (!pickerBulkMode) { bar.style.display = 'none'; return; }
        bar.style.display = 'flex';
        const n = pickerMarked.length;
        bar.innerHTML = '<span>已选 <b>' + n + '</b> 张</span>' +
            '<select id="wxp-bulkmove"><option value="">📂 整批移到分类…</option>' +
              uploadableCats().map(c => '<option value="' + escAttr(c.key) + '">' + escAttr(c.label) + '</option>').join('') +
            '</select>' +
            '<button id="wxp-bulkdel" class="danger">🗑 删掉选中的</button>' +
            '<button id="wxp-bulkall">全选当前 ' + (pickerCategory === 'video' ? '视频' : '图片') + '</button>' +
            '<button id="wxp-bulknone">清空选择</button>' +
            '<button id="wxp-bulkexit">退出多选</button>';
        const mv = document.getElementById('wxp-bulkmove');
        if (mv) mv.onchange = () => {
            const cat = mv.value; mv.value = '';
            if (!cat) return;
            if (!pickerMarked.length) { alert('还没有选中图片：点缩略图左上角会出现勾选框，或按「全选当前」。'); return; }
            movePathsToCategory(pickerMarked.slice(), cat);
        };
        const del = document.getElementById('wxp-bulkdel');
        if (del) del.onclick = () => {
            if (!pickerMarked.length) { alert('还没有选中图片。'); return; }
            if (!confirm('确定删除选中的 ' + pickerMarked.length + ' 张图片吗？\n\n删掉后无法恢复。')) return;
            fetch('/api/gallery/batch', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ op: 'delete', paths: pickerMarked.slice() })
            }).then(r => r.json()).then(r => {
                if (!r || !r.ok) { alert((r && r.msg) || '批量删除失败'); return; }
                pickerMarked = []; pickerSel = '';
                return refreshPickerAfterApi().then(() => {
                    renderPickerCats(); renderBulkBar(); updatePickerPreview();
                    if (r.failed) alert('有 ' + r.failed + ' 张没删成功。');
                });
            }).catch(() => alert('批量删除失败，请检查编辑器服务是否运行'));
        };
        const all = document.getElementById('wxp-bulkall');
        if (all) all.onclick = () => {
            const list = (pickerCategory === 'video')
                ? pickerVideos().map(v => v.path)
                : pickerSorted(pickerFiltered()).map(f => f.path);
            pickerMarked = list.slice();
            renderPickerGrid(); renderBulkBar();
        };
        const none = document.getElementById('wxp-bulknone');
        if (none) none.onclick = () => { pickerMarked = []; renderPickerGrid(); renderBulkBar(); };
        const exit = document.getElementById('wxp-bulkexit');
        if (exit) exit.onclick = () => { setBulkMode(false); renderPickerGrid(); renderBulkBar(); };
    }

    /* 把若干张图搬到指定分类（批量接口；会自动同步剧本/场景里的路径引用） */
    function movePathsToCategory(paths, catKey) {
        const P = (paths || []).filter(p => p && !String(p).startsWith('/videos/'));
        if (!P.length) return;
        const up = uploadableCats().find(c => c.key === catKey);
        if (!up) {
            alert('「' + catLabelOf(catKey) + '」不能作为搬运目标。\n请拖到可上传的分类上（头像/表情包/emoji/背景/配图素材或你新建的分类）。');
            return;
        }
        fetch('/api/gallery/batch', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ op: 'move', paths: P, category: catKey })
        }).then(r => r.json()).then(r => {
            if (!r || !r.ok) { alert((r && r.msg) || '移动失败'); return; }
            const moved = (r.results || []).filter(x => x.ok);
            const failed = (r.results || []).filter(x => !x.ok);
            if (moved.length === 1 && moved[0].newPath) pickerSel = moved[0].newPath;
            else if (moved.length > 1 && moved.some(m => m.path === pickerSel)) pickerSel = '';
            pickerMarked = [];
            setBulkMode(false);
            return refreshPickerAfterApi().then(() => {
                renderPickerCats(); renderBulkBar(); updatePickerPreview();
                const found = document.getElementById('wxp-found');
                if (found && !failed.length) found.textContent = '已把 ' + moved.length + ' 张搬到「' + up.label + '」';
                if (failed.length) alert('有 ' + failed.length + ' 张没搬成功：\n' + failed.slice(0, 5).map(f => f.msg).join('\n'));
            });
        }).catch(() => alert('移动失败，请检查编辑器服务是否运行'));
    }

    function updatePickerPreview() {
        const img = document.getElementById('wxp-previmg');
        const p = document.getElementById('wxp-prevpath');
        const lab = document.getElementById('wxp-label');
        const target = document.getElementById('wxp-target');
        const isVideo = (pickerSel || '').startsWith('/videos/');
        const selFile = (galleryFiles || []).find(f => f.path === pickerSel);
        if (!img || !p) return;
        if (pickerSel) {
            if (isVideo) { img.removeAttribute('src'); img.style.visibility = 'hidden'; }
            else { img.src = pickerSel; img.style.visibility = 'visible'; }
            p.textContent = pickerSel;
            if (lab) { lab.value = (!isVideo && selFile && selFile.label) ? selFile.label : ''; lab.disabled = isVideo; }
            if (target) target.textContent = (selFile && selFile.label ? selFile.label + ' · ' : '') + pickerSel;
        } else {
            img.removeAttribute('src'); img.style.visibility = 'hidden';
            p.textContent = '（未选择）';
            if (lab) { lab.value = ''; lab.disabled = false; }
            if (target) target.textContent = pickerCurrent || '';
        }
        setPickerActionEnabled(!!pickerSel && !isVideo);
        const mv = document.getElementById('wxp-move');
        if (mv) { mv.disabled = isVideo || !pickerSel; mv.style.opacity = (isVideo || !pickerSel) ? '.45' : ''; }
    }

    function setPickerActionEnabled(on) {
        ['wxp-labelok', 'wxp-copypath', 'wxp-del'].forEach(id => {
            const b = document.getElementById(id);
            if (b) { b.disabled = !on; b.style.opacity = on ? '' : '.45'; b.style.cursor = on ? '' : 'not-allowed'; }
        });
    }

    function commitPicker() {
        const cb = pickerOnPick;
        pickerOnPick = null;
        const mask = document.getElementById('wxp-mask');
        if (mask) mask.classList.remove('show');
        if (cb) cb(pickerSel || '');
    }

    function refreshPickerAfterApi() {
        // 增删改后重新拉取图库，保留当前选中路径并刷新网格/预览/目录/分类计数
        return ensureGallery().then(() => {
            renderPickerFolderOptions();
            renderPickerCats();
            renderUploadCatOptions();
            renderMoveOptions();
            renderPickerGrid();
            updatePickerPreview();
        });
    }

    /* ---- 整个弹窗可拖入上传 + Ctrl+V 粘贴上传 ---- */
    let dropCover = null;
    function buildDropCover() {
        if (!dropCover || !document.body.contains(dropCover)) {
            dropCover = document.createElement('div');
            dropCover.id = 'wxp-dropcover';
            dropCover.className = 'wxp-dropcover';
            dropCover.innerHTML = '<span id="wxp-dropcover-tip"></span>';
            document.body.appendChild(dropCover);
        }
    }
    function showDropCover(show) {
        buildDropCover();
        if (!dropCover) return;
        if (show) {
            const t = document.getElementById('wxp-dropcover-tip');
            if (t) t.textContent = '松手就上传到「' + catLabelOf(targetUploadCat()) + '」 · 也可以 Ctrl+V 直接粘贴图片';
            dropCover.classList.add('show');
        } else {
            dropCover.classList.remove('show');
        }
    }
    let dropDepth = 0;
    /* 拖进来的是"外部文件"吗？（区别于从网格里拖缩略图去分类） */
    function isFileDrag(e) {
        if (dragPaths.length) return false;
        const dt = e.dataTransfer;
        if (!dt || !dt.types) return false;
        return Array.prototype.indexOf.call(dt.types, 'Files') >= 0;
    }

    function doUpload(files, cat) {
        const imgs = pickImageFiles(files);
        if (!imgs.length) {
            alert('没识别到图片文件。\n支持 PNG / JPG / GIF / WebP / BMP，单张不超过 10MB。');
            return;
        }
        const target = cat || targetUploadCat();
        const found = document.getElementById('wxp-found');
        if (found) found.textContent = '上传中 0/' + imgs.length + '…';
        uploadFiles(imgs, (paths, errs) => {
            if (paths.length) {
                pickerSel = paths[paths.length - 1];
                pickerCategory = target;                 // 传完自动切到目标分类，立刻看到刚传的
                lsSet(LS_CAT, target);
                try { localStorage.setItem('wxp-upcat', target); } catch (e) { /* 忽略 */ }
            }
            refreshPickerAfterApi().then(() => updatePickerPreview());
            if (errs && errs.length) alert('有 ' + errs.length + ' 张没传成功：\n' + errs.slice(0, 6).join('\n'));
        }, target, (done, total, name) => {
            const f = document.getElementById('wxp-found');
            if (f) f.textContent = '上传中 ' + done + '/' + total + '：' + (name || '');
        });
    }

    function bindGlobalPaste() {
        if (window.__wxpPasteBound) return;
        window.__wxpPasteBound = true;
        document.addEventListener('paste', (e) => {
            const mask = document.getElementById('wxp-mask');
            if (!mask || !mask.classList.contains('show')) return;
            const items = (e.clipboardData && e.clipboardData.items) || [];
            const files = [];
            for (let i = 0; i < items.length; i++) {
                if (items[i] && items[i].kind === 'file') {
                    const f = items[i].getAsFile();
                    if (f && /^image\//.test(f.type || '')) files.push(f);
                }
            }
            if (!files.length) return;
            e.preventDefault();
            doUpload(files);
        });
    }

    /* ---- 分类管理（改名 / 新建 / 删除自定义分类） ---- */
    function openCatManager() {
        let box = document.getElementById('wxp-cm');
        if (!box) {
            box = document.createElement('div');
            box.id = 'wxp-cm';
            box.className = 'wxp-cm';
            document.body.appendChild(box);
            box.addEventListener('click', e => { if (e.target === box) closeCatManager(); });
        }
        renderCatManager();
        box.classList.add('show');
    }
    function closeCatManager() {
        const box = document.getElementById('wxp-cm');
        if (box) box.classList.remove('show');
    }
    function renderCatManager() {
        const box = document.getElementById('wxp-cm');
        if (!box) return;
        let h = '<div class="wxp-cm-box"><b>⚙ 分类管理</b>' +
            '<div class="wxp-cm-tip">改名只影响界面上看到的叫法，不动已有图片；要让某张图换分类，' +
            '在图片库里把缩略图拖到分类按钮上即可。「系统图标」是微信界面素材，不能上传。</div>';
        catList().forEach(c => {
            h += '<div class="wxp-cm-row" data-key="' + escAttr(c.key) + '">' +
                '<input class="wxp-cm-in" value="' + escAttr(c.label) + '" maxlength="20">' +
                '<span class="wxp-cm-tag">' + catCount(c.key) + ' 张</span>' +
                '<span class="wxp-cm-tag">' + (c.canUpload === false ? '只读' : '可上传') + '</span>' +
                '<button class="wxp-cm-save">改名</button>' +
                (c.builtin ? '' : '<button class="wxp-cm-del danger">删掉</button>') +
            '</div>';
        });
        h += '<div class="wxp-cm-add"><input id="wxp-cm-new" placeholder="新分类的名字，如：探店素材" maxlength="20">' +
             '<button id="wxp-cm-addbtn">＋ 新建分类</button></div>' +
             '<div class="wxp-cm-foot"><button id="wxp-cm-close" class="wxp-ok">完成</button></div></div>';
        box.innerHTML = h;
        const api = (payload, okMsg) => {
            fetch('/api/gallery/category', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(r => r.json()).then(r => {
                if (!r || !r.ok) { alert((r && r.msg) || '操作失败'); return; }
                return refreshPickerAfterApi().then(() => {
                    renderCatManager();
                    // 其它页面（场景编辑器/并发生产）挂了 onCategoriesChanged 就同步刷新它们的图库
                    if (typeof window.__wxPick.onCategoriesChanged === 'function') {
                        try { window.__wxPick.onCategoriesChanged(); } catch (e) { /* 忽略 */ }
                    }
                    const found = document.getElementById('wxp-found');
                    if (found && okMsg) found.textContent = okMsg;
                });
            }).catch(() => alert('操作失败，请检查编辑器服务是否运行'));
        };
        box.querySelectorAll('.wxp-cm-row').forEach(row => {
            const key = row.getAttribute('data-key');
            const inp = row.querySelector('.wxp-cm-in');
            const save = row.querySelector('.wxp-cm-save');
            const del = row.querySelector('.wxp-cm-del');
            if (save) save.onclick = () => {
                const v = (inp && inp.value || '').trim();
                if (!v) { alert('分类名不能为空。'); return; }
                if (v === catLabelOf(key)) { alert('名字没改哦。'); return; }
                api({ op: 'rename', key: key, label: v }, '「' + catLabelOf(key) + '」已改名为「' + v + '」');
            };
            if (inp) inp.onkeydown = e => { if (e.key === 'Enter' && save) save.click(); };
            if (del) del.onclick = () => {
                if (!confirm('删掉分类「' + catLabelOf(key) + '」？\n\n只会从分类列表里去掉它，已经上传的图片不会被删除（它们会回到「配图素材」里）。')) return;
                api({ op: 'remove', key: key }, '已删除分类「' + catLabelOf(key) + '」');
            };
        });
        const addBtn = document.getElementById('wxp-cm-addbtn');
        const newInp = document.getElementById('wxp-cm-new');
        if (addBtn) addBtn.onclick = () => {
            const v = (newInp && newInp.value || '').trim();
            if (!v) { alert('请先填新分类的名字。'); return; }
            api({ op: 'add', label: v }, '已新建分类「' + v + '」');
            if (newInp) newInp.value = '';
        };
        if (newInp) newInp.onkeydown = e => { if (e.key === 'Enter' && addBtn) addBtn.click(); };
        const cl = document.getElementById('wxp-cm-close');
        if (cl) cl.onclick = closeCatManager;
    }

    function bindPickerEvents() {
        const mask = document.getElementById('wxp-mask');
        if (!mask) return;
        const close = () => { const c = pickerOnPick; pickerOnPick = null; mask.classList.remove('show'); showDropCover(false); };
        const el = id => document.getElementById(id);
        if (el('wxp-close')) el('wxp-close').onclick = close;
        if (el('wxp-cancel')) el('wxp-cancel').onclick = close;
        if (el('wxp-ok')) el('wxp-ok').onclick = commitPicker;
        if (el('wxp-search')) el('wxp-search').oninput = e => { pickerQuery = e.target.value; renderPickerGrid(); };
        if (el('wxp-search')) el('wxp-search').onkeydown = e => {
            if (e.key === 'Enter' && pickerSel && pickerMarked.length === 0) commitPicker();
        };
        // 分类 chips 的点击/拖放目标在 renderPickerCats() 里绑定
        if (el('wxp-folder')) el('wxp-folder').onchange = e => {
            pickerFolder = e.target.value; lsSet(LS_FOLDER, pickerFolder); renderPickerGrid();
        };
        if (el('wxp-sort')) el('wxp-sort').onchange = e => {
            pickerSort = e.target.value; lsSet(LS_SORT, pickerSort); renderPickerGrid();
        };
        if (el('wxp-multibtn')) el('wxp-multibtn').onclick = () => {
            setBulkMode(!pickerBulkMode);
            renderPickerGrid(); renderBulkBar();
        };
        if (el('wxp-catbtn')) el('wxp-catbtn').onclick = openCatManager;
        // 命名：写入展示名（不改文件路径）
        const saveLabel = () => {
            if (!pickerSel) return;
            const inp = el('wxp-label');
            const label = (inp && inp.value || '').trim();
            fetch('/api/gallery/label', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: pickerSel, label: label })
            }).then(r => r.json()).then(r => {
                refreshPickerAfterApi().then(() => updatePickerPreview());
                if (!(r && r.ok)) alert((r && r.msg) || '命名失败');
            }).catch(() => alert('命名失败，请检查服务是否运行'));
        };
        if (el('wxp-labelok')) el('wxp-labelok').onclick = saveLabel;
        if (el('wxp-label')) el('wxp-label').onkeydown = e => { if (e.key === 'Enter') saveLabel(); };
        // 复制路径
        if (el('wxp-copypath')) el('wxp-copypath').onclick = () => {
            if (!pickerSel) return;
            try { navigator.clipboard.writeText(pickerSel); } catch (e) { /* 忽略 */ }
            if (el('wxp-prevpath')) el('wxp-prevpath').textContent = pickerSel + '（已复制）';
        };
        // 删除（仅图片；视频素材请在系统文件夹里手动清理）
        if (el('wxp-del')) el('wxp-del').onclick = () => {
            if (!pickerSel || pickerSel.startsWith('/videos/')) return;
            if (!confirm('确定删除这张图片吗？\n' + pickerSel + '\n\n删除后无法恢复。')) return;
            fetch('/api/gallery/delete', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: pickerSel })
            }).then(r => r.json()).then(r => {
                if (r && r.ok) {
                    pickerSel = '';
                    refreshPickerAfterApi();
                } else alert((r && r.msg) || '删除失败');
            }).catch(() => alert('删除失败，请检查服务是否运行'));
        };
        if (el('wxp-upload')) el('wxp-upload').onclick = () => {
            const inp = document.createElement('input');
            inp.type = 'file'; inp.multiple = true;
            inp.accept = 'image/png,image/jpeg,image/gif,image/webp,image/bmp';
            inp.onchange = () => {
                if (!inp.files.length) return;
                const cat = targetUploadCat();
                try { localStorage.setItem('wxp-upcat', cat); } catch (e) { /* 忽略 */ }
                doUpload(Array.from(inp.files), cat);
            };
            inp.click();
        };
        // 上传目标分类：记住选择
        if (el('wxp-upcat')) el('wxp-upcat').onchange = e => {
            try { localStorage.setItem('wxp-upcat', e.target.value); } catch (err) { /* 忽略 */ }
        };
        // 移动分类：真正搬移文件，并自动更新剧本/场景/人物库里的路径引用
        if (el('wxp-move')) el('wxp-move').onchange = e => {
            const cat = e.target.value || '';
            e.target.value = '';
            if (!cat || !pickerSel || pickerSel.startsWith('/videos/')) return;
            fetch('/api/gallery/move', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: pickerSel, category: cat })
            }).then(r => r.json()).then(r => {
                if (r && r.ok) {
                    pickerSel = r.path || '';
                    refreshPickerAfterApi().then(updatePickerPreview);
                    if (r.changed && r.changed.length) {
                        alert('已移动到「' + catLabelOf(cat) + '」，并同步更新了引用：\n' + r.changed.join('、'));
                    }
                } else {
                    alert((r && r.msg) || '移动失败');
                }
            }).catch(() => alert('移动失败，请检查服务是否运行'));
        };
        if (el('wxp-urlbtn')) el('wxp-urlbtn').onclick = () => {
            const row = el('wxp-urlrow');
            row.style.display = row.style.display === 'none' ? 'flex' : 'none';
            if (row.style.display === 'flex') el('wxp-url').focus();
        };
        if (el('wxp-urlapply')) el('wxp-urlapply').onclick = () => {
            const v = (el('wxp-url').value || '').trim();
            if (!v) return; pickerSel = v; updatePickerPreview(); renderPickerGrid();
        };
        if (el('wxp-url')) el('wxp-url').onkeydown = e => { if (e.key === 'Enter' && el('wxp-urlapply')) el('wxp-urlapply').click(); };

        // —— 整个弹窗都是「拖图上传」的落点 ——
        dropDepth = 0;
        mask.addEventListener('dragenter', e => {
            if (!isFileDrag(e)) return;
            e.preventDefault();
            dropDepth++;
            showDropCover(true);
        });
        mask.addEventListener('dragover', e => {
            if (!isFileDrag(e)) return;
            e.preventDefault();
            try { e.dataTransfer.dropEffect = 'copy'; } catch (err) { /* 忽略 */ }
            showDropCover(true);
        });
        mask.addEventListener('dragleave', e => {
            if (!isFileDrag(e)) return;
            dropDepth = Math.max(0, dropDepth - 1);
            if (!dropDepth) showDropCover(false);
        });
        mask.addEventListener('drop', e => {
            if (!isFileDrag(e)) return;
            e.preventDefault();
            dropDepth = 0;
            showDropCover(false);
            doUpload(Array.from(e.dataTransfer.files || []));
        });
        // 点遮罩空白处 = 关闭（但别把拖放的落点算进去）
        mask.onclick = e => { if (e.target === mask) close(); };
    }

    /* ---- 配图面板 ---- */
    let slots = [];            // [{id, no, speaker, desc, path}]
    let slotsOnChange = null;

    function setSlotsState(newSlots) {
        slots = (newSlots || []).slice();
        renderAttachList();
    }

    function renderAttachPanel(el, slotList, onChange) {
        slots = (slotList || []).slice();
        slotsOnChange = typeof onChange === 'function' ? onChange : null;
        if (!el) return;
        el.innerHTML = attachMarkup();
        const head = el.querySelector('.wxp-attach-head');
        if (head) head.onclick = () => {
            const body = el.querySelector('.wxp-slotlist');
            const collapsed = head.classList.toggle('collapsed');
            if (body) body.style.display = collapsed ? 'none' : '';
        };
        bindDropZone(el);
        bindBatchUpload(el);
        renderAttachList();
    }

    function attachMarkup() {
        return '<div class="wxp-attach">' +
            '<div class="wxp-attach-head"><b>🖼 配图清单</b><span class="wxp-count" id="wxp-attach-count"></span>' +
                '<span class="wxp-spacer"></span><span class="wxp-caret">▼</span></div>' +
            '<div class="wxp-slotlist" id="wxp-attach-body"></div>' +
            '<div class="wxp-header-row"><button type="button" id="wxp-batch" class="wxp-batch">📤 上传图片（按顺序）</button>' +
                '<span class="wxp-batch-hint">将你选的图片按先后顺序依次填入「图1、图2、…」对应槽位：选 N 张就填 N 个槽（可覆盖已配的图）。Ctrl/Shift 可多选</span></div>' +
            '<div class="wxp-dropbar" id="wxp-dropbar">也可以把图片直接拖到这里，按顺序给多个槽配图</div>' +
        '</div>';
    }

    /* ---- 打开动画编辑器（配图清单 / 运行确认弹窗共用）----
       槽位协议：open / openHold / openFocus / openZoom 读写访问器 + onOptsChange + path。
       「打开」三档（不打开 / 只点开 / 点开放大）用分段开关；倍率/停留用滑杆；
       放大中心点直接点小缩略图设置（与放大位置弹层联动）。 */
    function _openFocusDotHtml(slot) {
        const f = slotFocusObj(slot);
        return f ? '<span class="wxp-fdot" style="left:' + (f.x * 100) + '%;top:' + (f.y * 100) + '%;"></span>' : '';
    }
    function _openSliderHtml(kind, label) {
        const cfg = kind === 'zoom'
            ? 'min="1" max="3" step="0.05"'
            : 'min="0" max="10" step="0.5"';
        return '<div class="wxp-sliderwrap">' +
            '<span class="wxp-slabel">' + label + '</span>' +
            '<input type="range" class="wxp-' + kind + '-slider" ' + cfg + '>' +
            '<span class="wxp-sval"></span>' +
        '</div>';
    }
    function _bindOpenSlider(host, kind, slot) {
        const inp = host.querySelector('.wxp-' + kind + '-slider');
        if (!inp) return;
        const badge = inp.parentElement.querySelector('.wxp-sval');
        const setBadge = (txt, dim) => { badge.textContent = txt; badge.classList.toggle('dim', !!dim); };
        if (kind === 'zoom') {
            const raw = slotZoomStr(slot);
            const eff = slotZoomNum(slot);
            inp.value = eff;
            setBadge(eff.toFixed(2) + '×' + (raw ? '' : ' 默认'), !raw);
            inp.oninput = () => setBadge(Number(inp.value).toFixed(2) + '×', false);
            inp.onchange = () => {
                slot.openZoom = Number(inp.value).toFixed(2);
                if (slot.onOptsChange) slot.onOptsChange(slot);
            };
        } else {
            const raw = String(slot.openHold === undefined || slot.openHold === null ? '' : slot.openHold).trim();
            const eff = (raw && isFinite(Number(raw))) ? Number(raw) : 2;
            inp.value = eff;
            setBadge(raw ? eff.toFixed(1) + ' 秒' : '默认', !raw);
            inp.oninput = () => setBadge(Number(inp.value).toFixed(1) + ' 秒', false);
            inp.onchange = () => {
                slot.openHold = Number(inp.value).toFixed(1);
                if (slot.onOptsChange) slot.onOptsChange(slot);
            };
        }
    }
    function renderOpenOptsInto(host, slot) {
        if (!host || !slot) return;
        const mode = slotOpenMode(slot);
        const hasImg = !!slot.path;
        const segBtn = (key, label) =>
            '<button type="button" class="wxp-segmode' + (mode === key ? ' on' : '') + '" data-mode="' + key + '">' + label + '</button>';
        host.innerHTML =
            '<div class="wxp-openrow">' +
                '<div class="wxp-openrow-head">' +
                    '<span class="wxp-olabel">打开动画</span>' +
                    '<span class="wxp-seg">' +
                        segBtn('none', '不打开') + segBtn('view', '只点开') + segBtn('zoom', '点开放大') +
                    '</span>' +
                    (hasImg ? '' : '<span class="wxp-olinetip">先选图，才能设焦点 / 预览</span>') +
                    '<span style="flex:1"></span>' +
                    '<button type="button" class="wxp-prevbtn2" title="按当前设置模拟点开效果">▶ 预览</button>' +
                '</div>' +
                (mode === 'none' ? '' :
                    '<div class="wxp-openrow-detail">' +
                        (mode === 'zoom' ?
                            '<button type="button" class="wxp-focuswrap" title="点击小图设置放大中心点（绿色圆点处）">' +
                                '<span class="wxp-focusthumb">' +
                                    (hasImg ? '<img src="' + escAttr(slot.path) + '" onerror="this.style.opacity=.25">' : '<span class="wxp-fempty">未配图</span>') +
                                    _openFocusDotHtml(slot) +
                                '</span>' +
                                '<span class="wxp-focuscap">' + escAttr(slotFocusLabel(slot)) + '</span>' +
                            '</button>' : '') +
                        (mode === 'zoom' ? _openSliderHtml('zoom', '倍率') : '') +
                        _openSliderHtml('hold', '停留') +
                    '</div>') +
            '</div>';
        host.querySelectorAll('.wxp-segmode').forEach(btn => {
            btn.onclick = () => {
                const v = btn.getAttribute('data-mode');
                slot.open = v === 'none' ? '' : (v === 'view' ? '只点开' : '是');
                if (slot.onOptsChange) slot.onOptsChange(slot);
                renderOpenOptsInto(host, slot);
            };
        });
        const prev = host.querySelector('.wxp-prevbtn2');
        if (prev) prev.onclick = () => attachZoomPreview(slot);
        const fth = host.querySelector('.wxp-focuswrap');
        if (fth) fth.onclick = () => attachFocusPicker(slot);
        _bindOpenSlider(host, 'zoom', slot);
        _bindOpenSlider(host, 'hold', slot);
    }

    function renderAttachList() {
        const body = document.getElementById('wxp-attach-body');
        const count = document.getElementById('wxp-attach-count');
        if (!body) return;
        const filled = slots.filter(s => s.path).length;
        if (count) {
            count.textContent = '已配 ' + filled + '/' + slots.length;
            count.className = 'wxp-count' + (filled >= slots.length ? ' done' : ' pending');
        }
        body.innerHTML = slots.map((s, i) => {
            // 「打开」控件显示条件：autoplayable（历史会话块图片）或 openable（发送图片/对方发图片
            // 等运行时支持「打开/停留/焦点/放大倍率」参数的图片槽）。两种槽都通过 open/openHold/
            // openFocus/openZoom 访问器读写，控件本体由 renderOpenOptsInto 统一渲染。
            const optsHtml = (s && (s.autoplayable || s.openable))
                ? '<div class="wxp-openhost" data-id="' + escAttr(s.id) + '"></div>'
                : '';
            const slotFilled = !!s.path;
            return '<div class="wxp-slot ' + (slotFilled ? 'filled' : 'empty') + '" data-id="' + escAttr(s.id) + '">' +
                '<div class="wxp-slot-main">' +
                    '<span class="wxp-slot-no">' + (s.no || ('图' + (i + 1))) + '</span>' +
                    '<span class="wxp-slot-info"><span class="wxp-desc">' + escAttr(s.speaker ? (s.speaker + ' · ') : '') + escAttr(s.desc || '') + '</span></span>' +
                    '<span class="wxp-slot-tag' + (slotFilled ? ' ok' : '') + '">' + (slotFilled ? '已配图' : '待配图') + '</span>' +
                    '<span class="wxp-slot-thumb' + (s.path ? ' ok' : ' warn') + '">' +
                        (s.path ? '<img src="' + escAttr(s.path) + '" onerror="this.style.opacity=.25">' : '<span class="wxp-nopic">未配图</span>') +
                    '</span>' +
                    '<span class="wxp-slot-acts">' +
                        '<button class="wxp-pick" data-act="pick">选图</button>' +
                        (s.path ? '<button class="wxp-clear" data-act="clear">清除</button>' : '') +
                    '</span>' +
                '</div>' +
                optsHtml +
            '</div>';
        }).join('');
        body.querySelectorAll('.wxp-slot').forEach(row => {
            const id = row.getAttribute('data-id');
            const pickBtn = row.querySelector('[data-act="pick"]');
            const clearBtn = row.querySelector('[data-act="clear"]');
            if (pickBtn) pickBtn.onclick = () => {
                const s = slots.find(x => x.id === id);
                pickerOpen({ current: s ? s.path : '', onPick: path => { assignSlot(id, path); } });
            };
            if (clearBtn) clearBtn.onclick = () => assignSlot(id, '');
        });
        // 「打开动画」编辑器（局部挂载：槽位协议 open/openHold/openFocus/openZoom + onOptsChange）
        body.querySelectorAll('.wxp-openhost').forEach(h => {
            const s = slots.find(x => x.id === h.getAttribute('data-id'));
            if (s) renderOpenOptsInto(h, s);
        });
    }

    /* 读取/展示 打开动画 控件状态 */
    function slotIsOn(s) { return !!(s && s.open); }
    function slotOpenMode(s) {
        const v = (s && typeof s.open !== 'undefined' && s.open !== null) ? String(s.open).trim().toLowerCase() : '';
        if (v === '' || ['0', 'no', 'off', 'false', '否', '不', '关闭', '不打开'].includes(v)) return 'none';
        if (['只点开', '不放大', '查看', '只显示', '不缩放', 'open', 'view'].includes(v)) return 'view';
        return 'zoom';
    }
    function slotZoomStr(s) {
        const v = s && s.openZoom;
        return (v === undefined || v === null || v === '') ? '' : String(v);
    }
    function slotZoomNum(s) {
        const n = parseFloat(slotZoomStr(s));
        return (isFinite(n) && n > 0.5) ? n : 1.6;
    }
    function slotHold(s) {
        const v = s && s.openHold;
        return (v === undefined || v === null || v === '') ? '' : v;
    }
    function slotFocusLabel(s) {
        const f = s && s.openFocus ? String(s.openFocus).trim() : '';
        const p = f.split(',');
        if (p.length === 2 && isFinite(Number(p[0])) && isFinite(Number(p[1]))) {
            return Number(p[0]).toFixed(2) + ', ' + Number(p[1]).toFixed(2);
        }
        return '居中';
    }
    function slotFocusObj(s) {
        const f = s && s.openFocus ? String(s.openFocus).trim() : '';
        const p = f.split(',');
        if (p.length === 2 && isFinite(Number(p[0])) && isFinite(Number(p[1]))) {
            return { x: Math.min(0.97, Math.max(0.03, Number(p[0]))), y: Math.min(0.97, Math.max(0.03, Number(p[1]))) };
        }
        return null;
    }

    /* 预览点开效果：按当前 打开模式/倍率/焦点 近似渲染图片放大后的样子 */
    let zoomPreviewModal = null;
    function attachZoomPreview(slot) {
        if (!slot) return;
        const src = slot.path;
        if (!src) { alert('请先为这张图「选图」，之后才能预览点开效果。'); return; }
        if (!zoomPreviewModal) {
            zoomPreviewModal = document.createElement('div');
            zoomPreviewModal.id = 'wxp-preview-modal';
            zoomPreviewModal.style.cssText =
                'position:fixed;inset:0;z-index:100002;background:#000;display:none;align-items:center;justify-content:center;overflow:hidden;';
            zoomPreviewModal.innerHTML =
                '<div style="position:absolute;top:16px;left:0;right:0;text-align:center;color:rgba(255,255,255,.85);font-size:13px;">' +
                    '<span id="wxp-preview-info"></span> ' +
                    '<button id="wxp-preview-close" type="button" style="margin-left:10px;background:#2b3140;border:1px solid #3a3f47;border-radius:6px;padding:4px 10px;color:#e6e6e6;cursor:pointer;">关闭</button>' +
                '</div>' +
                '<div style="position:relative;width:92%;height:92%;display:flex;align-items:center;justify-content:center;overflow:hidden;">' +
                    '<img id="wxp-preview-img" alt="预览" draggable="false" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:6px;will-change:transform;transition:transform .18s ease;">' +
                '</div>';
            document.body.appendChild(zoomPreviewModal);
            zoomPreviewModal.querySelector('#wxp-preview-close').onclick = () => { zoomPreviewModal.style.display = 'none'; };
            zoomPreviewModal.addEventListener('click', (e) => {
                if (e.target === zoomPreviewModal) zoomPreviewModal.style.display = 'none';
            });
        }
        const img = zoomPreviewModal.querySelector('#wxp-preview-img');
        img.src = src;
        const mode = slotOpenMode(slot);
        const zoom = slotZoomNum(slot);
        const focus = slotFocusObj(slot);
        const ox = focus ? focus.x : 0.5;
        const oy = focus ? focus.y : 0.5;
        const modeLabel = mode === 'view' ? '只点开(不放大)' : (mode === 'zoom' ? '点开并放大' : '不打开');
        if (mode === 'view') {
            img.style.transformOrigin = '50% 50%';
            img.style.transform = 'none';
        } else {
            img.style.transformOrigin = (ox * 100) + '% ' + (oy * 100) + '%';
            img.style.transform = 'none';
            void img.offsetWidth;
            img.style.transform = 'scale(' + zoom.toFixed(2) + ')';
        }
        zoomPreviewModal.querySelector('#wxp-preview-info').textContent = modeLabel + ' · 倍率 ' + zoom.toFixed(2) + '×' +
            (focus ? (' · 焦点 ' + ox.toFixed(2) + ',' + oy.toFixed(2)) : ' · 居中');
        zoomPreviewModal.style.display = 'flex';
    }

    /* 选放大位置：点图片任意处即设为中心（配图面板专用） */
    let focusModal = null;
    let focusSlot = null;
    function attachFocusPicker(slot) {
        if (!slot) return;
        const src = slot.path;
        if (!src) { alert('请先为这张图「选图」，之后才能设置放大位置。'); return; }
        focusSlot = slot;
        if (!focusModal) {
            focusModal = document.createElement('div');
            focusModal.id = 'wxp-focus-modal';
            focusModal.style.cssText =
                'position:fixed;inset:0;z-index:100001;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;';
            focusModal.innerHTML =
                '<div style="background:#20242a;border-radius:12px;padding:14px;max-width:92vw;max-height:92vh;overflow:auto;color:#e6e6e6;font-size:13px;">' +
                    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">' +
                        '<b>点击图片选择放大位置</b><span id="wxp-rf-coord" style="opacity:.85;"></span>' +
                        '<button id="wxp-rf-reset" type="button" style="margin-left:auto;background:#2b3140;border:1px solid #3a3f47;border-radius:6px;padding:4px 10px;color:#e6e6e6;cursor:pointer;">重置居中</button>' +
                        '<button id="wxp-rf-close" type="button" style="background:#2b3140;border:1px solid #3a3f47;border-radius:6px;padding:4px 10px;color:#e6e6e6;cursor:pointer;">取消</button>' +
                    '</div>' +
                    '<div id="wxp-rf-box" style="position:relative;display:inline-block;cursor:crosshair;">' +
                        '<img id="wxp-rf-img" style="max-width:86vw;max-height:70vh;line-height:0;user-select:none;" alt="">' +
                        '<div id="wxp-rf-marker" style="display:none;position:absolute;width:14px;height:14px;margin:-7px 0 0 -7px;border:2px solid #07c160;border-radius:50%;pointer-events:none;box-shadow:0 0 0 2px rgba(0,0,0,.5);"></div>' +
                    '</div>' +
                '</div>';
            document.body.appendChild(focusModal);
            const box = focusModal.querySelector('#wxp-rf-box');
            const img = focusModal.querySelector('#wxp-rf-img');
            const marker = focusModal.querySelector('#wxp-rf-marker');
            box.addEventListener('mousemove', (e) => {
                const r = img.getBoundingClientRect();
                const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
                const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
                marker.style.display = 'block';
                marker.style.left = (x * 100) + '%';
                marker.style.top = (y * 100) + '%';
                focusModal.querySelector('#wxp-rf-coord').textContent = '(' + x.toFixed(2) + ',' + y.toFixed(2) + ')';
            });
            box.addEventListener('mouseleave', () => { marker.style.display = 'none'; });
            box.addEventListener('click', (e) => {
                const r = img.getBoundingClientRect();
                const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
                const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
                const sl = focusSlot;
                closeFocus();
                if (sl) { sl.openFocus = x.toFixed(2) + ',' + y.toFixed(2); if (sl.onOptsChange) sl.onOptsChange(sl); renderAttachList(); }
            });
            focusModal.querySelector('#wxp-rf-close').onclick = closeFocus;
            focusModal.querySelector('#wxp-rf-reset').onclick = () => {
                const sl = focusSlot;
                closeFocus();
                if (sl) { sl.openFocus = '0.50,0.50'; if (sl.onOptsChange) sl.onOptsChange(sl); renderAttachList(); }
            };
        } else {
            focusModal.querySelector('#wxp-rf-img').src = src;
        }
        focusModal.querySelector('#wxp-rf-img').src = src;
        const cur = slot.openFocus ? String(slot.openFocus).trim() : '';
        focusModal.querySelector('#wxp-rf-coord').textContent = cur ? ('当前：' + slotFocusLabel(slot)) : '点击图片任意处设置（默认居中）';
        focusModal.style.display = 'flex';
    }
    function closeFocus() { if (focusModal) focusModal.style.display = 'none'; }

    function assignSlot(id, path) {
        const s = slots.find(x => x.id === id);
        if (!s) return;
        s.path = path || '';
        if (slotsOnChange) slotsOnChange(id, s.path);
        renderAttachList();
    }

    function assignPathsInOrder(paths) {
        if (!paths || !paths.length) return;
        // 按顺序把上传结果填入「图1、图2、…」对应的槽：第 i 张图填进第 i 个槽，
        // 覆盖原有的图也照填，保证「上传的图」与「剧本里的顺序」一一对应。
        paths.forEach((p, i) => { if (slots[i]) assignSlot(slots[i].id, p); });
    }

    function bindDropZone(el) {
        const bar = el.querySelector('.wxp-dropbar');
        if (!bar) return;
        ['dragover', 'dragenter'].forEach(ev => bar.addEventListener(ev, e => { e.preventDefault(); bar.classList.add('drag'); }));
        ['dragleave', 'drop'].forEach(ev => bar.addEventListener(ev, e => { e.preventDefault(); bar.classList.remove('drag'); }));
        bar.addEventListener('drop', e => {
            const files = Array.from(e.dataTransfer.files || []);
            if (!files.length) return;
            // 第 i 张图进第 i 个槽：槽上标了 uploadCat（或表情槽 emoji:true→表情包）就按槽的分类存
            uploadFiles(files, (paths) => assignPathsInOrder(paths), slotUploadCat);
        });
    }

    function slotUploadCat(f, i) {
        const s = slots[i] || {};
        return s.uploadCat || (s.emoji ? 'sticker' : 'asset');
    }

    function bindBatchUpload(el) {
        const btn = el.querySelector('#wxp-batch');
        if (!btn) return;
        btn.onclick = () => {
            const inp = document.createElement('input');
            inp.type = 'file';
            inp.multiple = true;
            inp.accept = 'image/png,image/jpeg,image/gif,image/webp,image/bmp';
            inp.onchange = () => {
                if (!inp.files.length) return;
                const files = Array.from(inp.files).slice(0, Math.max(1, slots.length));
                uploadFiles(files, (paths) => assignPathsInOrder(paths), slotUploadCat);
            };
            inp.click();
        };
    }

    /* ---- 工具 ---- */
    function escAttr(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    /* ---- 初始化 ---- */
    function init() {
        initStyles();
        if (!document.getElementById('wxp-mask')) {
            const mask = document.createElement('div');
            mask.id = 'wxp-mask';
            mask.className = 'wxp-mask';
            document.body.appendChild(mask);
        }
        bindGlobalPaste();
        ensureGallery();
    }
    init();

    window.__wxPick = {
        onReady: ensureGallery,
        openPicker: pickerOpen,
        openCategoryManager: openCatManager,
        listCategories: function () { return catList().slice(); },
        renderAttachPanel: renderAttachPanel,
        setSlotsState: setSlotsState,
        renderOpenOptsInto: renderOpenOptsInto,
        listImages: listImages,
        uploadFiles: uploadFiles,
    };
})();
