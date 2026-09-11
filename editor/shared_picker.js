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
.wxp-mask { position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 90; display: none; align-items: center; justify-content: center; }
.wxp-mask.show { display: flex; }
.wxp-modal { width: 720px; max-width: 94vw; background: #242528; color: #e7e8ea; border-radius: 14px; box-shadow: 0 20px 60px rgba(0,0,0,.5); max-height: 88vh; overflow: auto; padding: 16px; }
.wxp-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.wxp-head b { font-size: 15px; }
.wxp-head .wxp-target { font-size: 12px; color: #8a8b8f; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-head button { background: transparent; border: 0; font-size: 20px; color: #9a9b9f; cursor: pointer; padding: 0 4px; }
.wxp-toolbar { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.wxp-toolbar input { flex: 1; min-width: 140px; background: #17181a; color: #e7e8ea; border: 1px solid #3a3b3f; border-radius: 5px; padding: 6px 8px; font: inherit; }
.wxp-toolbar button { cursor: pointer; border: 1px solid #3a3b3f; background: #2a2b2f; color: #e7e8ea; border-radius: 6px; padding: 6px 12px; font: inherit; }
.wxp-toolbar button:hover { background: #34353a; }
.wxp-urlrow { display: flex; gap: 6px; margin-bottom: 8px; }
.wxp-urlrow input { flex: 1; background: #17181a; color: #e7e8ea; border: 1px solid #3a3b3f; border-radius: 5px; padding: 6px 8px; font: inherit; }
.wxp-urlrow button { cursor: pointer; border: 1px solid #07c160; background: #07c160; color: #06210f; border-radius: 6px; padding: 6px 14px; font-weight: 600; }
.wxp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: 8px; max-height: 320px; overflow: auto; padding: 4px; border: 1px solid #2a2b2e; border-radius: 8px; background: #17181a; }
.wxp-item { cursor: pointer; border: 1px solid transparent; border-radius: 8px; padding: 4px; text-align: center; }
.wxp-item:hover { background: #26272b; }
.wxp-item.sel { border-color: #07c160; background: #1f2a22; }
.wxp-thumb { height: 64px; display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 6px; background: #202124; }
.wxp-thumb img { max-width: 100%; max-height: 100%; object-fit: cover; }
.wxp-thumb.wxp-clear { font-size: 13px; color: #8a8b8f; }
.wxp-name { font-size: 11px; color: #9a9b9f; margin-top: 3px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-empty { grid-column: 1 / -1; color: #8a8b8f; text-align: center; padding: 24px 0; font-size: 13px; }
.wxp-footer { display: flex; gap: 12px; align-items: center; margin-top: 12px; }
.wxp-preview { display: flex; gap: 10px; align-items: center; flex: 1; min-width: 0; }
.wxp-preview img { width: 54px; height: 54px; border-radius: 8px; object-fit: cover; background: #17181a; border: 1px solid #3a3b3f; }
.wxp-preview .wxp-path { font-size: 12px; color: #9a9b9f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-footbtns { display: flex; gap: 8px; }
.wxp-footbtns button { cursor: pointer; border-radius: 6px; padding: 7px 16px; font: inherit; }
.wxp-footbtns .wxp-ok { background: #07c160; border-color: #07c160; color: #06210f; font-weight: 600; }
.wxp-footbtns .wxp-cancel { background: transparent; border: 1px solid #3a3b3f; color: #e7e8ea; }

/* ---- 配图面板 ---- */
.wxp-attach { border: 1px solid #2a2b2e; border-radius: 8px; background: #1d1e21; margin: 12px 0; overflow: hidden; }
.wxp-attach-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #26272b; cursor: pointer; }
.wxp-attach-head b { font-size: 13px; color: #e7e8ea; }
.wxp-attach-head .wxp-count { font-size: 12px; color: #9a9b9f; }
.wxp-attach-head .wxp-spacer { flex: 1; }
.wxp-attach-head .wxp-caret { color: #9a9b9f; font-size: 12px; transition: transform .15s ease; }
.wxp-attach-head.collapsed .wxp-caret { transform: rotate(-90deg); }
.wxp-slotlist { padding: 8px 12px; border-top: 1px solid #2a2b2e; }
.wxp-slot { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px dashed #2a2b2e; }
.wxp-slot:last-child { border-bottom: 0; }
.wxp-slot-no { flex: 0 0 34px; text-align: center; background: #2f3136; color: #cfd0d2; border-radius: 6px; font-size: 12px; padding: 3px 0; }
.wxp-slot-info { flex: 1; min-width: 0; font-size: 12px; color: #c6c7cb; }
.wxp-slot-info .wxp-desc { display: block; color: #e7e8ea; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-slot-thumb { flex: 0 0 42px; height: 42px; border-radius: 6px; background: #202124; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid #3a3b3f; }
.wxp-slot-thumb img { max-width: 100%; max-height: 100%; object-fit: cover; }
.wxp-slot-thumb .wxp-nopic { font-size: 11px; color: #8a8b8f; }
.wxp-slot-thumb.ok { border-color: #07c160; }
.wxp-slot-thumb.warn { border-color: #e9a23b; }
.wxp-slot-acts { display: flex; gap: 6px; flex: 0 0 auto; }
.wxp-slot-acts button { cursor: pointer; border: 1px solid #3a3b3f; background: #2a2b2f; color: #e7e8ea; border-radius: 6px; padding: 5px 10px; font-size: 12px; }
.wxp-slot-acts button:hover { background: #34353a; }
.wxp-slot-acts .wxp-pick { background: #07c160; border-color: #07c160; color: #06210f; font-weight: 600; }
.wxp-slot-acts .wxp-pick:hover { background: #09d268; }
.wxp-slot-acts .wxp-clear { color: #9a9b9f; }
.wxp-slot-acts .wxp-clear:hover { color: #e7e8ea; }
/* 配图槽位：自动打开动画 控件 */
.wxp-slot { flex-direction: column; align-items: stretch; gap: 4px; padding: 8px 0; }
.wxp-slot-main { display: flex; align-items: center; gap: 10px; }
.wxp-slot-opts { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; color: #9a9b9f; font-size: 12px; padding-left: 44px; }
.wxp-slot-opts label { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.wxp-slot-opts input[type=number] { width: 58px; background: #17181a; color: #e7e8ea; border: 1px solid #3a3b3f; border-radius: 5px; padding: 2px 4px; }
.wxp-slot-opts .wxp-focusbtn { cursor: pointer; border: 1px solid #3a3b3f; background: #2a2b2f; color: #e7e8ea; border-radius: 6px; padding: 3px 10px; font-size: 12px; }
.wxp-slot-opts .wxp-focusbtn:hover { background: #34353a; }
.wxp-dropbar { border: 1px dashed #3a3b3f; border-radius: 8px; color: #8a8b8f; text-align: center; padding: 10px; font-size: 12px; margin: 8px 0; }
.wxp-dropbar.drag { border-color: #07c160; color: #07c160; background: #1f2a22; }
.wxp-batchrow { display: flex; align-items: center; gap: 8px; margin: 4px 0 8px; flex-wrap: wrap; }
.wxp-batch { cursor: pointer; border: 1px solid #07c160; background: #07c160; color: #06210f; border-radius: 6px; padding: 8px 14px; font-weight: 600; font: inherit; }
.wxp-batch:hover { background: #09d268; }
.wxp-batch-hint { font-size: 11px; color: #8a8b8f; }
/* ---- 图库 分类筛选 + 命名 ---- */
.wxp-filter { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.wxp-filter select { background: #17181a; color: #e7e8ea; border: 1px solid #3a3b3f; border-radius: 5px; padding: 6px 8px; font: inherit; }
.wxp-typebtn { cursor: pointer; border: 1px solid #3a3b3f; background: #2a2b2f; color: #e7e8ea; border-radius: 6px; padding: 5px 12px; font: inherit; font-size: 12px; }
.wxp-typebtn:hover { background: #34353a; }
.wxp-typebtn.on { background: #07c160; border-color: #07c160; color: #06210f; font-weight: 600; }
.wxp-typebtn.on:hover { background: #09d268; }
.wxp-found { font-size: 11px; color: #8a8b8f; margin-left: auto; }
.wxp-item .wxp-tag { position: absolute; top: 3px; right: 4px; font-size: 10px; color: #e7e8ea; padding: 1px 5px; border-radius: 4px; border: 1px solid rgba(0,0,0,.4); }
.wxp-item .wxp-tag-ic { background: #3a4a6b; }
.wxp-item .wxp-tag-im { background: #2f5d3a; }
.wxp-sub { font-size: 10px; color: #6c6d72; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wxp-preview { align-items: flex-start; min-width: 220px; }
.wxp-footer { align-items: flex-start; flex-wrap: wrap; }
.wxp-pvmeta { display: flex; flex-direction: column; gap: 5px; min-width: 0; flex: 1; }
.wxp-labelbox { display: flex; gap: 6px; align-items: center; }
.wxp-labelbox input { flex: 1; min-width: 120px; background: #17181a; color: #e7e8ea; border: 1px solid #3a3b3f; border-radius: 5px; padding: 5px 8px; font: inherit; font-size: 12px; }
.wxp-labelbox .wxp-lb-btn { cursor: pointer; border: 1px solid #07c160; background: #07c160; color: #06210f; border-radius: 6px; padding: 5px 10px; font: inherit; font-size: 12px; font-weight: 600; }
.wxp-labelbox .wxp-lb-btn:hover { background: #09d268; }
.wxp-labelbox .wxp-lb-hint { font-size: 10px; color: #6c6d72; }
.wxp-footbtns .wxp-misc { cursor: pointer; border: 1px solid #3a3b3f; background: #2a2b2f; color: #e7e8ea; border-radius: 6px; padding: 6px 11px; font: inherit; font-size: 12px; }
.wxp-footbtns .wxp-misc:hover { background: #34353a; }
.wxp-footbtns .wxp-misc.danger:hover { border-color: #e5533d; color: #ff8a75; }
`;
        (document.head || document.documentElement).appendChild(st);
    }

    /* ---- 图片库缓存 ---- */
    let galleryCache = [];       // 旧字段：纯路径列表（兼容现有 listImages / picker）
    let galleryFiles = [];       // 元信息列表 [{path,name,folder,category,type,label,size,mtime}]
    let galleryVideos = [];      // 视频素材 [{path,name}]
    let galleryCategories = [];  // 分类清单 [{key,label,folders}]（后端下发）

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
    function catLabelOf(key) {
        const c = (galleryCategories || []).find(x => x.key === key);
        return c ? c.label : ({ avatar: '头像', sticker: '表情包', emoji: 'emoji',
                                bg: '背景', asset: '配图素材', icon: '系统图标' }[key] || key);
    }
    function uploadableCats() {
        const allow = ['avatar', 'sticker', 'emoji', 'bg', 'asset'];
        const list = (galleryCategories || []).filter(c => allow.includes(c.key));
        return list.length ? list
            : allow.map(k => ({ key: k, label: catLabelOf(k) }));
    }

    /* ---- 批量上传 ---- */
    function uploadFiles(files, cb, category) {
        const valid = (files || []).filter(f => f.size <= 10 * 1024 * 1024);
        if (!valid.length) { if (cb) cb([]); return; }
        let idx = 0; const paths = [];
        function next() {
            if (idx >= valid.length) {
                ensureGallery().then(() => { if (cb) cb(paths); });
                return;
            }
            const f = valid[idx];
            const reader = new FileReader();
            reader.onload = () => {
                fetch('/api/upload-image', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ data: reader.result, name: f.name, category: category || '' })
                }).then(r => r.json()).then(r => {
                    if (r && r.ok && r.path) paths.push(r.path);
                    idx++; next();
                }).catch(() => { idx++; next(); });
            };
            reader.readAsDataURL(f);
        }
        next();
    }

    /* ---- 打开图片选择弹窗 ---- */
    let pickerSel = '';
    let pickerQuery = '';
    let pickerOnPick = null;
    let pickerCurrent = '';
    let pickerCategory = ''; // ''=全部 | avatar/sticker/emoji/bg/asset/icon | 'video'
    let pickerFolder = '';  // ''=全部目录 | 目录名

    function pickerOpen(opts) {
        opts = opts || {};
        pickerOnPick = typeof opts.onPick === 'function' ? opts.onPick : null;
        pickerCurrent = opts.current || '';
        pickerSel = pickerCurrent;
        pickerQuery = '';
        pickerCategory = '';
        pickerFolder = '';
        const mask = document.getElementById('wxp-mask');
        if (!mask) return;
        mask.innerHTML = pickerMarkup();
        mask.classList.add('show');
        bindPickerEvents();
        renderPickerCats();
        renderUploadCatOptions();
        renderMoveOptions();
        renderPickerFolderOptions();
        renderPickerGrid();
        updatePickerPreview();
        // 每次打开都重新拉取图库，确保显示最新图片（含别处上传/命名的变更）
        ensureGallery().then(() => {
            renderPickerCats(); renderUploadCatOptions();
            renderPickerFolderOptions(); renderPickerGrid(); updatePickerPreview();
        });
    }

    function pickerMarkup() {
        return '<div class="wxp-modal">' +
            '<div class="wxp-head"><b>选择图片</b>' +
                '<span class="wxp-target" id="wxp-target">' + (pickerCurrent || '') + '</span>' +
                '<button id="wxp-close">×</button></div>' +
            '<div class="wxp-toolbar">' +
                '<input id="wxp-search" placeholder="搜索文件名/命名...">' +
                '<select id="wxp-upcat" title="上传的图片存入哪个分类"></select>' +
                '<button id="wxp-upload">⬆ 上传图片</button>' +
                '<button id="wxp-urlbtn">🔗 使用链接</button>' +
            '</div>' +
            '<div class="wxp-filter" id="wxp-cats"></div>' +
            '<div class="wxp-filter">' +
                '<select id="wxp-folder"><option value="">📁 全部目录</option></select>' +
                '<span class="wxp-found" id="wxp-found"></span>' +
            '</div>' +
            '<div class="wxp-urlrow" id="wxp-urlrow" style="display:none">' +
                '<input id="wxp-url" placeholder="输入 /images/... 或 http(s):// 图片链接">' +
                '<button id="wxp-urlapply">应用</button>' +
            '</div>' +
            '<div class="wxp-grid" id="wxp-grid"></div>' +
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

    /* 渲染分类筛选 chips（全部 / 各分类 / 🎬视频） */
    function renderPickerCats() {
        const box = document.getElementById('wxp-cats');
        if (!box) return;
        let h = '<span class="wxp-typebtn' + (pickerCategory === '' ? ' on' : '') + '" data-cat="">全部</span>';
        const cats = (galleryCategories && galleryCategories.length) ? galleryCategories
            : ['avatar', 'sticker', 'emoji', 'bg', 'asset', 'icon'].map(k => ({ key: k, label: catLabelOf(k) }));
        cats.forEach(c => {
            h += '<span class="wxp-typebtn' + (pickerCategory === c.key ? ' on' : '') + '" data-cat="' + escAttr(c.key) + '">' +
                 escAttr(c.label) + '</span>';
        });
        h += '<span class="wxp-typebtn' + (pickerCategory === 'video' ? ' on' : '') + '" data-cat="video">🎬 视频</span>';
        box.innerHTML = h;
        box.querySelectorAll('.wxp-typebtn').forEach(btn => {
            btn.onclick = () => {
                pickerCategory = btn.getAttribute('data-cat') || '';
                box.querySelectorAll('.wxp-typebtn').forEach(x => x.classList.toggle('on', x === btn));
                renderPickerGrid();
            };
        });
    }

    /* 渲染「上传存入分类」下拉（记忆上次选择） */
    function renderUploadCatOptions() {
        const sel = document.getElementById('wxp-upcat');
        if (!sel) return;
        let saved = '';
        try { saved = localStorage.getItem('wxp-upcat') || ''; } catch (e) { /* 忽略 */ }
        if (!uploadableCats().some(c => c.key === saved)) saved = 'avatar';
        sel.innerHTML = uploadableCats().map(c =>
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

    function renderPickerFolderOptions() {
        const sel = document.getElementById('wxp-folder');
        if (!sel) return;
        const keep = pickerFolder;
        sel.innerHTML = '<option value="">📁 全部目录</option>' +
            galleryFolders().map(f => '<option value="' + escAttr(f) + '">' + escAttr(f === '/' ? '根目录' : f) + '</option>').join('');
        sel.value = galleryFolders().includes(keep) ? keep : '';
        pickerFolder = sel.value;
    }

    function renderPickerGrid() {
        const grid = document.getElementById('wxp-grid');
        if (!grid) return;
        const isVideoTab = pickerCategory === 'video';
        const list = isVideoTab
            ? pickerVideos().map(v => ({ path: v.path, label: v.name || v.path, name: v.path, isVideo: true }))
            : pickerFiltered();
        const found = document.getElementById('wxp-found');
        if (found) found.textContent = '匹配 ' + list.length + (isVideoTab ? ' 个视频' : ' 张');
        let h = isVideoTab ? '' :
            '<div class="wxp-item" data-val=""><div class="wxp-thumb wxp-clear">无</div><span class="wxp-name">清除</span></div>';
        list.forEach(f => {
            const sel = f.path === pickerSel ? ' sel' : '';
            const tag = f.isVideo ? '视频' : catLabelOf(f.category);
            const tagCls = f.isVideo ? ' wxp-tag-ic' : (f.category === 'icon' ? ' wxp-tag-ic' : ' wxp-tag-im');
            const thumb = f.isVideo
                ? '<div class="wxp-thumb"><span style="font-size:26px">🎬</span></div>'
                : '<div class="wxp-thumb"><img src="' + escAttr(f.path) + '" onerror="this.style.opacity=.25">' +
                    '<span class="wxp-tag' + tagCls + '">' + tag + '</span></div>';
            h += '<div class="wxp-item' + sel + '" data-val="' + escAttr(f.path) + '" title="' + escAttr(f.path) + '">' +
                thumb +
                '<span class="wxp-name">' + escAttr(f.label || f.name) + '</span>' +
                '<span class="wxp-sub">' + escAttr(f.name) + '</span></div>';
        });
        if (!list.length) {
            h += isVideoTab
                ? '<div class="wxp-empty">还没有视频素材。用「上传视频」把 MP4 传进视频库，发朋友圈视频动态 / [播放视频] 就能选。</div>'
                : '<div class="wxp-empty">没有匹配的图片，换个关键词/分类试试，或上传一张。</div>';
        }
        grid.innerHTML = h;
        grid.querySelectorAll('.wxp-item').forEach(el => {
            el.onclick = () => {
                pickerSel = el.getAttribute('data-val');
                grid.querySelectorAll('.wxp-item').forEach(x => x.classList.toggle('sel', x === el));
                updatePickerPreview();
            };
            el.ondblclick = () => { pickerSel = el.getAttribute('data-val'); commitPicker(); };
        });
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
        // 增删改后重新拉取图库，保留当前选中路径并刷新网格/预览/目录
        return ensureGallery().then(() => {
            renderPickerFolderOptions();
            renderPickerGrid();
            updatePickerPreview();
        });
    }

    function bindPickerEvents() {
        const mask = document.getElementById('wxp-mask');
        if (!mask) return;
        const close = () => { const c = pickerOnPick; pickerOnPick = null; mask.classList.remove('show'); };
        const el = id => document.getElementById(id);
        if (el('wxp-close')) el('wxp-close').onclick = close;
        if (el('wxp-cancel')) el('wxp-cancel').onclick = close;
        if (el('wxp-ok')) el('wxp-ok').onclick = commitPicker;
        if (el('wxp-search')) el('wxp-search').oninput = e => { pickerQuery = e.target.value; renderPickerGrid(); };
        // 分类 chips 的点击在 renderPickerCats() 里自行绑定（含「全部/各分类/🎬视频」）
        if (el('wxp-folder')) el('wxp-folder').onchange = e => { pickerFolder = e.target.value; renderPickerGrid(); };
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
                const cat = (el('wxp-upcat') && el('wxp-upcat').value) || '';
                try { localStorage.setItem('wxp-upcat', cat); } catch (e) { /* 忽略 */ }
                uploadFiles(Array.from(inp.files), (paths) => {
                    if (paths.length) pickerSel = paths[paths.length - 1];
                    refreshPickerAfterApi();
                }, cat);
            };
            inp.click();
        };
        // 移动分类：真正搬移文件，并自动更新剧本/场景/人物库里的路径引用
        if (el('wxp-move')) el('wxp-move').onchange = e => {
            const cat = e.target.value || '';
            if (!cat || !pickerSel || pickerSel.startsWith('/videos/')) return;
            fetch('/api/gallery/move', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: pickerSel, category: cat })
            }).then(r => r.json()).then(r => {
                if (r && r.ok) {
                    pickerSel = r.path || '';
                    e.target.value = '';
                    refreshPickerAfterApi().then(updatePickerPreview);
                    if (r.changed && r.changed.length) {
                        alert('已移动到「' + catLabelOf(cat) + '」，并同步更新了引用：\n' + r.changed.join('、'));
                    }
                } else {
                    alert((r && r.msg) || '移动失败');
                    e.target.value = '';
                }
            }).catch(() => { alert('移动失败，请检查服务是否运行'); e.target.value = ''; });
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

    function renderAttachList() {
        const body = document.getElementById('wxp-attach-body');
        const count = document.getElementById('wxp-attach-count');
        if (!body) return;
        const filled = slots.filter(s => s.path).length;
        if (count) count.textContent = '已配 ' + filled + '/' + slots.length;
        body.innerHTML = slots.map((s, i) => {
            const optsHtml = (s && s.autoplayable)
                ? '<div class="wxp-slot-opts">' +
                    '<label>打开 <select class="wxp-open" data-id="' + escAttr(s.id) + '">' +
                      '<option value=""' + (slotOpenMode(s) === 'none' ? ' selected' : '') + '>不打开</option>' +
                      '<option value="只点开"' + (slotOpenMode(s) === 'view' ? ' selected' : '') + '>只点开(不放大)</option>' +
                      '<option value="是"' + (slotOpenMode(s) === 'zoom' ? ' selected' : '') + '>点开并放大</option>' +
                    '</select></label>' +
                    '<label>倍率 <input type="number" class="wxp-zoom" data-id="' + escAttr(s.id) + '" value="' + escAttr(slotZoomStr(s)) + '" min="1" max="4.5" step="0.1" placeholder="默认"></label>' +
                    '<label>停留 <input type="number" class="wxp-hold" data-id="' + escAttr(s.id) + '" value="' + escAttr(slotHold(s)) + '" min="0" step="0.1"></label>' +
                    '<button type="button" class="wxp-focusbtn" data-id="' + escAttr(s.id) + '">放大：' + escAttr(slotFocusLabel(s)) + '</button>' +
                    '<button type="button" class="wxp-previewbtn" data-id="' + escAttr(s.id) + '" title="预览点开效果">预览</button>' +
                  '</div>'
                : '';
            return '<div class="wxp-slot" data-id="' + escAttr(s.id) + '">' +
                '<div class="wxp-slot-main">' +
                    '<span class="wxp-slot-no">' + (s.no || ('图' + (i + 1))) + '</span>' +
                    '<span class="wxp-slot-info"><span class="wxp-desc">' + escAttr(s.speaker ? (s.speaker + ' · ') : '') + escAttr(s.desc || '') + '</span></span>' +
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
            const openSel = row.querySelector('.wxp-open');
            if (openSel) openSel.onchange = () => {
                const s = slots.find(x => x.id === id);
                if (s) { s.open = openSel.value; if (s.onOptsChange) s.onOptsChange(s); }
            };
            const zoomInp = row.querySelector('.wxp-zoom');
            if (zoomInp) zoomInp.onchange = () => {
                const s = slots.find(x => x.id === id);
                if (s) { s.openZoom = zoomInp.value; if (s.onOptsChange) s.onOptsChange(s); }
            };
            const holdInp = row.querySelector('.wxp-hold');
            if (holdInp) holdInp.onchange = () => {
                const s = slots.find(x => x.id === id);
                if (s) { s.openHold = holdInp.value; if (s.onOptsChange) s.onOptsChange(s); }
            };
            const focusBtn = row.querySelector('.wxp-focusbtn');
            if (focusBtn) focusBtn.onclick = () => {
                const s = slots.find(x => x.id === id);
                if (s) attachFocusPicker(s);
            };
            const prevBtn = row.querySelector('.wxp-previewbtn');
            if (prevBtn) prevBtn.onclick = () => {
                const s = slots.find(x => x.id === id);
                if (s) attachZoomPreview(s);
            };
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
            uploadFiles(files, (paths) => assignPathsInOrder(paths), 'asset');
        });
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
                uploadFiles(files, (paths) => assignPathsInOrder(paths));
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
        ensureGallery();
    }
    init();

    window.__wxPick = {
        onReady: ensureGallery,
        openPicker: pickerOpen,
        renderAttachPanel: renderAttachPanel,
        setSlotsState: setSlotsState,
        listImages: listImages,
        uploadFiles: uploadFiles,
    };
})();
