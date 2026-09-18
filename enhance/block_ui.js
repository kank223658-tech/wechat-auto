/* ============================================================
   联系人设置页 + 拉黑动画（main.py 注入）
   ------------------------------------------------------------
   复刻参考视频「拉黑界面，实现拉黑的功能.mp4」的界面与全过程动画：

     对方资料页点右上角「…」  →  #wxBlockSettings（联系人设置页）
         └─ 拨「加入黑名单」开关（变绿）
              └─ 底部弹起确认弹窗（文案 + 确定/取消）
                   ├─ 确定 → 弹窗收起 → 中央「正在加载」Toast → 拉黑完成
                   └─ 取消 → 弹窗收起 → 开关弹回灰色

   对外 API（main.py / Playwright 调用，全部幂等）：
     window.__wxBlock.openSettings(contact?)   打开设置页（自动补资料页在底下）
     window.__wxBlock.closeSettings()          关闭设置页
     window.__wxBlock.backFromSettings()       设置页开着则关掉并返回 true
     window.__wxBlock.tapToggle()              拨「加入黑名单」开关（关→开变绿），返回是否成功
     window.__wxBlock.tapToggleOff()           拨回「加入黑名单」开关（开→关），用于移出黑名单
     window.__wxBlock.showSheet()              底部弹起确认弹窗
     window.__wxBlock.confirmSheet()           点「确定」：弹窗收起（拉黑生效）
     window.__wxBlock.cancelSheet()            点「取消」：弹窗收起（开关弹回）
     window.__wxBlock.showToast(sec)           显示「正在加载」Toast，sec 秒后自动消失
     window.__wxBlock.block(opts)              全自动演示一遍拉黑（开关→弹窗→确定→加载）
     window.__wxBlock.unblock(opts)            全自动演示一遍移出黑名单
     window.__wxBlock.isOpen()                 {settings, sheet, toast}
     window.__wxBlock.isBlocked()              是否已处于拉黑态
     window.__wxBlock.reset()                  复位（关弹窗/Toast、开关回灰、关设置页）

   —— 删除联系人链路（复刻参考视频「拉黑动作.mp4」：聊天详情抽屉 → 扫黑进设置页
      → 底部弹窗「即将删除联系人」→ 点删除 → 正在加载 → 扫黑回聊天列表 + 对勾 Toast）——
     window.__wxBlock.openChatDetail()         聊天页右上角 … 打开聊天详情抽屉
     window.__wxBlock.showDeleteSheet()        底部弹起「即将删除联系人"昵称"」弹窗
     window.__wxBlock.pressDelete()            点「删除」：按压高亮（0.15s 后转确认）
     window.__wxBlock.confirmDeleteSheet()     确认删除：弹窗收起
     window.__wxBlock.cancelDeleteSheet()      取消删除：弹窗收起，停在设置页
     window.__wxBlock.swapToSettingsInstant()  黑屏下瞬时：关抽屉/资料页 → 开设置页
     window.__wxBlock.sweepToListInstant()     黑屏下瞬时：关设置页 → 回聊天列表（会话+通讯录联系人消失）+ 对勾 Toast
     window.__wxBlock.showDeleteToast(sec)     「已删除联系人」对勾 Toast
     window.__wxBlock.deleteContact(opts)      全自动演示删除（设置页开着时调用，opts 同 block）

   opts：{ confirm: true/false, toast: 秒数, hold: 结束停留秒数 }
   ============================================================ */
(() => {
    if (window.__wxBlock) return;

    const SETTINGS_ID = 'wxBlockSettings';
    const SHEET_MASK_ID = 'wxBlockSheetMask';
    const TOAST_ID = 'wxBlockToast';
    const CHAT_DETAIL_ID = 'wxChatDetail';      // 聊天详情抽屉（聊天页右上角 … 进入）
    const DELETE_SHEET_ID = 'wxDeleteSheet';    // 「即将删除联系人」底部弹窗
    const DELETE_TOAST_ID = 'wxDeleteToast';    // 「已删除联系人」对勾 Toast

    const MSG_BLOCK = '加入黑名单，你将不再收到对方的消息，并且你们互相看不到对方朋友圈的更新';
    const MSG_UNBLOCK = '移出黑名单，你将重新收到对方的消息，并且你们互相可以看到对方的朋友圈更新';

    let blocked = false;      // 当前是否处于「已拉黑」态
    let sheetMode = null;     // 'block' | 'unblock' | null —— 本次弹窗对应的方向

    /* ---------- DOM 工具 ---------- */
    const el = (tag, cls, text) => {
        const n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    };

    /* ---------- 设置页 ---------- */
    function cellRow(title, opts) {
        opts = opts || {};
        const cell = el('div', 'wxb-cell' + (opts.danger ? ' danger' : ''));
        cell.appendChild(el('div', 'wxb-cell-title', title));
        if (opts.arrow) cell.appendChild(el('span', 'wxb-cell-arrow'));
        if (opts.switchId) {
            const sw = el('span', 'wxb-switch');
            sw.id = opts.switchId;
            cell.appendChild(sw);
        }
        return cell;
    }

    function ensureSettings() {
        let root = document.getElementById(SETTINGS_ID);
        if (root) return root;
        root = el('div', 'wx-block-page');
        root.id = SETTINGS_ID;
        root.setAttribute('aria-hidden', 'true');
        root.innerHTML =
            '<div class="wxb-nav">' +
            '  <span class="wxb-back" data-block-back></span>' +
            '  <span class="wxb-title">设置</span>' +
            '</div>' +
            '<div class="wxb-scroll">' +
            '  <div class="wxb-group">' +
            '    <!-- 编辑备注 / 设置权限 -->' +
            cellRow('编辑备注', { arrow: true }).outerHTML +
            cellRow('设置权限', { arrow: true }).outerHTML +
            '  </div>' +
            '  <div class="wxb-group">' +
            '    <!-- 推荐给朋友（参考视频里单独一组） -->' +
            cellRow('把他 (她) 推荐给朋友', { arrow: true }).outerHTML +
            '  </div>' +
            '  <div class="wxb-group">' +
            '    <!-- 星标（单独一组） -->' +
            cellRow('设为星标朋友', { switchId: 'wxbStarSwitch' }).outerHTML +
            '  </div>' +
            '  <div class="wxb-group">' +
            '    <!-- 黑名单 / 投诉（同组） -->' +
            cellRow('加入黑名单', { switchId: 'wxbBlackSwitch' }).outerHTML +
            cellRow('投诉', { arrow: true }).outerHTML +
            '  </div>' +
            '  <div class="wxb-group">' +
            '    <!-- 删除联系人 -->' + cellRow('删除联系人', { danger: true }).outerHTML +
            '  </div>' +
            '</div>';
        document.body.appendChild(root);
        void root.offsetWidth;   // 先按关闭态算样式，保证加 .open 能触发滑入

        const back = root.querySelector('[data-block-back]');
        if (back) back.addEventListener('click', () => closeSettings());
        const black = root.querySelector('#wxbBlackSwitch');
        if (black) black.addEventListener('click', () => tapToggle());
        return root;
    }

    function setSettingsOpen(open) {
        const root = ensureSettings();
        root.classList.toggle('open', !!open);
        root.setAttribute('aria-hidden', open ? 'false' : 'true');
        // 底层（聊天页 / 主页）左移压暗的视差效果复用 peer 层的类
        syncPushDim();
    }

    function isOpenPeer() {
        const prof = document.getElementById('wxPeerProfile');
        const mom = document.getElementById('wxPeerMoments');
        return !!((prof && prof.classList.contains('open')) ||
                  (mom && mom.classList.contains('open')));
    }

    /* 当前设置页是否开着 */
    function isSettingsPageOpen() {
        const root = document.getElementById(SETTINGS_ID);
        return !!(root && root.classList.contains('open'));
    }

    /* 推入态统一同步：聊天详情抽屉 / 资料页 / 朋友圈 / 设置页 任一开着，
       底层页面都要左移压暗（复用 peer 层的 wx-peer-open / #wxPeerDim） */
    function syncPushDim() {
        const anyOpen = isChatDetailOpen() || isOpenPeer() || isSettingsPageOpen();
        document.body.classList.toggle('wx-peer-open', anyOpen);
        const app = document.getElementById('app');
        const dim = document.getElementById('wxPeerDim');
        if (app) app.classList.toggle('wx-peer-pushing', anyOpen);
        if (dim) dim.classList.toggle('on', anyOpen);
    }

    /* ---------- 当前对方人设（抽屉头像 / 弹窗文案用） ---------- */
    function peerInfo() {
        const FALLBACK = '/images/avatar/2_20260831_184618_874.jpg';
        try {
            const p = (window.__wxConfig && window.__wxConfig.getPeer()) || {};
            return {
                name: p.name || p.nickname || p.remark || '微信好友',
                avatar: p.avatar || FALLBACK,
            };
        } catch (e) { return { name: '微信好友', avatar: FALLBACK }; }
    }

    function openSettings(contact) {
        // 真机路径是「资料页 → 右上角 … → 设置」：资料页没开时先补在底下，返回栈才对
        if (contact && window.__wxConfig && window.__wxConfig.setPeer) {
            const presets = window.__wxConfig.getPeerPresets
                ? window.__wxConfig.getPeerPresets() : null;
            if (presets && presets[contact]) window.__wxConfig.setPeer(contact);
        }
        if (!isOpenPeer() && window.__wxPeer && window.__wxPeer.openProfile) {
            window.__wxPeer.openProfile();
        }
        setSettingsOpen(true);
        return true;
    }

    function closeSettings() {
        setSettingsOpen(false);
        return true;
    }

    /* 供 __wxPeer.back() 复用：设置页开着时先退设置页 */
    function backFromSettings() {
        const root = document.getElementById(SETTINGS_ID);
        if (root && root.classList.contains('open')) {
            closeSettings();
            return true;
        }
        return false;
    }

    /* ---------- 聊天详情抽屉（聊天页右上角 … 右滑推入，复刻参考视频第 1 段） ----------
       视频路径：聊天页 → 聊天详情抽屉 → 扫黑 → 联系人设置页。
       纯展示层：行内容与参考视频一致，无实际业务。 */
    function chatDetailRow(title) {
        return '<div class="wxb-group"><div class="wxb-cell">' +
               '<span class="wxb-cell-title">' + title + '</span></div></div>';
    }

    function ensureChatDetail() {
        let root = document.getElementById(CHAT_DETAIL_ID);
        if (root) return root;
        const info = peerInfo();
        root = el('div', 'wx-chat-detail');
        root.id = CHAT_DETAIL_ID;
        root.setAttribute('aria-hidden', 'true');
        root.innerHTML =
            '<div class="wxb-nav">' +
            '  <span class="wxb-back" data-cd-back></span>' +
            '  <span class="wxb-title">聊天详情</span>' +
            '</div>' +
            '<div class="wxb-scroll">' +
            '  <div class="wxcd-head">' +
            '    <div class="wxcd-avatar-box">' +
            '      <img class="wxcd-avatar" src="' + info.avatar + '" alt="">' +
            '      <div class="wxcd-name">' + info.name + '</div>' +
            '    </div>' +
            '    <div class="wxcd-add"><i></i></div>' +
            '  </div>' +
            chatDetailRow('查找聊天内容') +
            chatDetailRow('消息免打扰') +
            chatDetailRow('置顶聊天') +
            chatDetailRow('提醒') +
            chatDetailRow('设置当前聊天背景') +
            chatDetailRow('清空聊天记录') +
            chatDetailRow('投诉') +
            '</div>';
        document.body.appendChild(root);
        void root.offsetWidth;   // 先按关闭态算样式，保证加 .open 能触发滑入
        const back = root.querySelector('[data-cd-back]');
        if (back) back.addEventListener('click', () => closeChatDetail());
        return root;
    }

    function isChatDetailOpen() {
        const root = document.getElementById(CHAT_DETAIL_ID);
        return !!(root && root.classList.contains('open'));
    }

    function setChatDetailOpen(open) {
        const root = ensureChatDetail();
        root.classList.toggle('open', !!open);
        root.setAttribute('aria-hidden', open ? 'false' : 'true');
        syncPushDim();
    }

    function openChatDetail() {
        const root = ensureChatDetail();
        const info = peerInfo();          // 每次打开都刷新头像/昵称（人设可能已切换）
        const img = root.querySelector('.wxcd-avatar');
        const name = root.querySelector('.wxcd-name');
        if (img) img.src = info.avatar;
        if (name) name.textContent = info.name;
        setChatDetailOpen(true);
        return true;
    }

    function closeChatDetail() {
        if (!isChatDetailOpen()) return false;
        setChatDetailOpen(false);
        return true;
    }

    /* 拦截聊天页右上角「…」（router-link 到旧版 dialogue-detail），
       改为打开本抽屉。capture 阶段截停，vue-router 不会导航。 */
    document.addEventListener('click', (e) => {
        if (e.target && e.target.closest &&
            e.target.closest('#wx-header .other .icon-chat-friends')) {
            e.preventDefault();
            e.stopImmediatePropagation();
            e.stopPropagation();
            openChatDetail();
        }
    }, true);

    /* ---------- 「即将删除联系人」底部弹窗（复刻参考视频，双按钮横排） ---------- */
    function ensureDeleteSheet() {
        let mask = document.getElementById(DELETE_SHEET_ID);
        if (mask) return mask;
        mask = el('div', 'wxd-sheet-mask');
        mask.id = DELETE_SHEET_ID;
        const sheet = el('div', 'wxd-sheet');
        const title = el('div', 'wxd-title');
        title.id = 'wxDelTitle';
        const sub = el('div', 'wxd-sub', '删除后对方不会收到通知');
        const check = el('div', 'wxd-checkrow');
        check.id = 'wxDelCheckRow';
        check.innerHTML =
            '<span class="wxd-check on"><svg viewBox="0 0 24 24" fill="none" ' +
            'stroke="#fff" stroke-width="3" stroke-linecap="round" ' +
            'stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>' +
            '<span class="wxd-check-text">删除联系人同时清空聊天记录</span>';
        const btns = el('div', 'wxd-btns');
        const cancel = el('div', 'wxd-btn cancel', '取消');
        const del = el('div', 'wxd-btn delete', '删除');
        cancel.addEventListener('click', () => cancelDeleteSheet());
        del.addEventListener('click', () => pressDelete());
        btns.appendChild(cancel);
        btns.appendChild(del);
        const safe = el('div', 'wxd-safe');
        sheet.appendChild(title);
        sheet.appendChild(sub);
        sheet.appendChild(check);
        sheet.appendChild(btns);
        sheet.appendChild(safe);
        mask.appendChild(sheet);
        document.body.appendChild(mask);
        void mask.offsetWidth;
        check.addEventListener('click', () => {
            const c = check.querySelector('.wxd-check');
            if (c) c.classList.toggle('on');
        });
        return mask;
    }

    /* 底部弹起删除确认弹窗（文案带当前对方昵称） */
    function showDeleteSheet() {
        const mask = ensureDeleteSheet();
        const title = mask.querySelector('#wxDelTitle');
        if (title) title.textContent = '即将删除联系人"' + peerInfo().name + '"';
        mask.classList.add('on');
        return true;
    }

    /* 点「删除」：先按出按压高亮（0.15s 内由 main.py 转 confirmDeleteSheet） */
    function pressDelete() {
        const mask = document.getElementById(DELETE_SHEET_ID);
        if (!mask || !mask.classList.contains('on')) return false;
        const del = mask.querySelector('.wxd-btn.delete');
        if (del) del.classList.add('pressing');
        return true;
    }

    /* 确认删除：弹窗收起 */
    function confirmDeleteSheet() {
        const mask = document.getElementById(DELETE_SHEET_ID);
        if (!mask || !mask.classList.contains('on')) return false;
        mask.classList.remove('on');
        const del = mask.querySelector('.wxd-btn.delete');
        if (del) del.classList.remove('pressing');
        return true;
    }

    /* 取消删除：弹窗收起（停留在设置页） */
    function cancelDeleteSheet() {
        const mask = document.getElementById(DELETE_SHEET_ID);
        if (!mask || !mask.classList.contains('on')) return false;
        mask.classList.remove('on');
        const del = mask.querySelector('.wxd-btn.delete');
        if (del) del.classList.remove('pressing');
        return true;
    }

    /* ---------- 「已删除联系人」对勾 Toast（扫黑回聊天列表后亮出） ---------- */
    function ensureDeleteToast() {
        let t = document.getElementById(DELETE_TOAST_ID);
        if (t) return t;
        t = el('div', 'wxd-toast');
        t.id = DELETE_TOAST_ID;
        t.innerHTML =
            '<svg class="wxd-tick" viewBox="0 0 48 48" fill="none" stroke="#fff" ' +
            'stroke-width="4" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M9 25.5l10.5 10.5L39 14"/></svg>' +
            '<div class="wxd-toast-text">已删除联系人</div>';
        document.body.appendChild(t);
        return t;
    }

    let delToastTimer = null;
    /* 显示对勾 Toast；sec 非空时 sec 秒后自动淡出（缺省由 main.py 手动收） */
    function showDeleteToast(sec) {
        const t = ensureDeleteToast();
        t.classList.add('on');
        if (delToastTimer) { clearTimeout(delToastTimer); delToastTimer = null; }
        if (sec != null && Number(sec) > 0) {
            delToastTimer = setTimeout(() => t.classList.remove('on'),
                                       Number(sec) * 1000);
        }
        return true;
    }

    function hideDeleteToast() {
        const t = document.getElementById(DELETE_TOAST_ID);
        if (t) t.classList.remove('on');
        if (delToastTimer) { clearTimeout(delToastTimer); delToastTimer = null; }
        return true;
    }

    /* ---------- 扫黑换页（黑幕 #wxCutBlack 由 main.py 的 _black_in/_black_out 挂） ----------
       约定：调用时 body 已带 wx-peer-nocut（transition: none），换页在黑屏下瞬时完成。 */

    /* 抽屉 / 资料页 → 设置页：关抽屉关资料页，瞬时开设置页 */
    function swapToSettingsInstant() {
        document.body.classList.add('wx-peer-nocut');
        closeChatDetail();
        if (window.__wxPeer && window.__wxPeer.close) window.__wxPeer.close();
        setSettingsOpen(true);
        void document.body.offsetWidth;
        return true;
    }

    /* 已删除联系人名单：删除后从消息列表和通讯录里一起消失。
       Vue 重渲染会恢复行，所以用定时器周期性重新摘除。 */
    const deletedNames = new Set();
    let hiddenTimer = null;
    let hiddenObserver = null;

    function applyDeletedHidden() {
        if (!deletedNames.size) return;
        document.querySelectorAll('.wechat-list li').forEach((li) => {
            const a = li.querySelector('.desc-author');
            if (a && deletedNames.has(a.textContent.trim())) swapOrHideChatRow(li);
        });
        document.querySelectorAll('#contact .weui-cell').forEach((cell) => {
            const bd = cell.querySelector('.weui-cell__bd');
            if (bd && deletedNames.has(bd.textContent.trim())) cell.classList.add('wxb-deleted');
        });
    }

    /* 删除补位：主页会话行是绝对定位（1~8 行全可见，第 9 行半行，第 10 行在屏幕外），
       直接 display:none 会在原地留一个洞。脚本侧已把会话自动补齐到 10 个——
       删除时把屏幕外补位行（第 10 行）的内容搬进被删者的行，列表始终满屏不漏空；
       没有可用补位行（脚本未补齐 / 补位行已用掉 / 删的就是补位行）时退回旧行为（隐藏该行）。 */
    function swapOrHideChatRow(li) {
        const rows = document.querySelectorAll('.wechat-list li');
        const filler = rows.length >= 10 ? rows[rows.length - 1] : null;
        const sInfo = filler && filler !== li && !filler.classList.contains('wxb-deleted')
            ? filler.querySelector('.list-info') : null;
        const dInfo = li.querySelector('.list-info');
        if (sInfo && dInfo) {
            try {
                dInfo.innerHTML = sInfo.innerHTML;
                filler.classList.add('wxb-deleted');
                li.classList.remove('wxb-deleted');
                return;
            } catch (e) { /* 搬运失败退化到隐藏 */ }
        }
        li.classList.add('wxb-deleted');
    }

    function ensureHiddenTimer() {
        if (hiddenTimer) return;
        hiddenTimer = setInterval(applyDeletedHidden, 400);
        /* Vue 切 Tab 重建 #contact 时，靠 observer 在同一绘制帧内摘行，
           否则被删的人会闪现一帧（400ms 定时器来不及） */
        hiddenObserver = new MutationObserver(() => {
            if (!deletedNames.size || hiddenObserver._pending) return;
            hiddenObserver._pending = requestAnimationFrame(() => {
                hiddenObserver._pending = null;
                applyDeletedHidden();
            });
        });
        hiddenObserver.observe(document.body, { childList: true, subtree: true });
    }

    function hideConversationOfCurrentPeer() {
        const info = peerInfo();
        if (info.name) {
            deletedNames.add(info.name);
            ensureHiddenTimer();
        }
        applyDeletedHidden();
    }

    /* 设置页 → 聊天列表：关设置页 + 关抽屉 + 关资料页（主页滑入路径会开着）
       + 列表/通讯录里摘掉该联系人 + 切回微信 Tab + 亮对勾 Toast */
    function sweepToListInstant() {
        document.body.classList.add('wx-peer-nocut');
        document.body.classList.add('wx-nocut');
        closeSettings();
        closeChatDetail();
        if (window.__wxPeer && window.__wxPeer.close) window.__wxPeer.close();
        hideConversationOfCurrentPeer();
        try { if (location.hash !== '#/') location.hash = '#/'; } catch (e) { /* noop */ }
        showDeleteToast();
        void document.body.offsetWidth;
        return true;
    }

    /* ---------- 开关 ---------- */
    function blackSwitch() { return document.getElementById('wxbBlackSwitch'); }

    /* 拨「加入黑名单」开关：关→开（变绿）。已开时返回 false（无动作） */
    function tapToggle() {
        const sw = blackSwitch();
        if (!sw || blocked) return false;
        sw.classList.add('on', 'animating');
        setTimeout(() => sw.classList.remove('animating'), 300);
        return true;
    }

    function tapToggleOff() {
        const sw = blackSwitch();
        if (!sw || !blocked) return false;
        sw.classList.remove('on');
        return true;
    }

    /* ---------- 确认弹窗 ---------- */
    function ensureSheet() {
        let mask = document.getElementById(SHEET_MASK_ID);
        if (mask) return mask;
        mask = el('div', 'wxb-sheet-mask');
        mask.id = SHEET_MASK_ID;
        const sheet = el('div', 'wxb-sheet');
        const msg = el('div', 'wxb-sheet-msg');
        msg.id = 'wxbSheetMsg';
        const ok = el('div', 'wxb-sheet-btn confirm', '确定');
        const gap = el('div', 'wxb-sheet-gap');
        const no = el('div', 'wxb-sheet-btn cancel', '取消');
        const safe = el('div', 'wxb-sheet-safe');
        ok.addEventListener('click', () => confirmSheet());
        no.addEventListener('click', () => cancelSheet());
        sheet.appendChild(msg);
        sheet.appendChild(ok);
        sheet.appendChild(gap);
        sheet.appendChild(no);
        sheet.appendChild(safe);
        mask.appendChild(sheet);
        document.body.appendChild(mask);
        void mask.offsetWidth;
        return mask;
    }

    /* 底部弹起确认弹窗。direction：'block'（拉黑，默认）| 'unblock'（移出黑名单） */
    function showSheet(direction) {
        const mask = ensureSheet();
        sheetMode = direction === 'unblock' ? 'unblock' : 'block';
        const msg = mask.querySelector('#wxbSheetMsg');
        if (msg) msg.textContent = sheetMode === 'unblock' ? MSG_UNBLOCK : MSG_BLOCK;
        mask.classList.add('on');
        return true;
    }

    /* 点「确定」：弹窗收起，拉黑/移出生效 */
    function confirmSheet() {
        const mask = document.getElementById(SHEET_MASK_ID);
        if (!mask || !mask.classList.contains('on')) return false;
        mask.classList.remove('on');
        blocked = sheetMode === 'block';
        sheetMode = null;
        return true;
    }

    /* 点「取消」：弹窗收起，开关弹回（拉黑方向的取消才回弹） */
    function cancelSheet() {
        const mask = document.getElementById(SHEET_MASK_ID);
        if (!mask || !mask.classList.contains('on')) return false;
        mask.classList.remove('on');
        if (sheetMode === 'block') {
            const sw = blackSwitch();
            if (sw) sw.classList.remove('on');
        }
        sheetMode = null;
        return true;
    }

    /* ---------- 正在加载 Toast ---------- */
    let toastTimer = null;
    function ensureToast() {
        let t = document.getElementById(TOAST_ID);
        if (t) return t;
        t = el('div', 'wxb-toast');
        t.id = TOAST_ID;
        t.appendChild(el('span', 'wxb-spinner'));
        t.appendChild(el('span', 'wxb-toast-text', '正在加载'));
        document.body.appendChild(t);
        return t;
    }

    /* 显示「正在加载」，sec 秒后自动淡出（sec 缺省 1.4） */
    function showToast(sec) {
        const t = ensureToast();
        t.classList.add('on');
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => t.classList.remove('on'),
                                Math.max(0.2, Number(sec) || 1.4) * 1000);
        return true;
    }

    /* ---------- 全自动演示（手动测试 / 一行动作出整段动画用） ---------- */
    /* step(fn, ms)：执行 fn 后等待 ms 毫秒，返回一个 promise 链 */
    function step(fn, ms) {
        return new Promise((res) => {
            fn && fn();
            setTimeout(res, ms);
        });
    }

    function block(opts) {
        opts = opts || {};
        const toast = Number(opts.toast) > 0 ? Number(opts.toast) : 1.4;
        const hold = Number(opts.hold) > 0 ? Number(opts.hold) : 0.8;
        const cancelled = opts.confirm === false;
        openSettings();
        return step(null, 400)
            .then(() => step(() => tapToggle(), 500))
            .then(() => step(() => showSheet('block'), 850))
            .then(() => step(() => (cancelled ? cancelSheet() : confirmSheet()), 400))
            .then(() => step(() => (!cancelled && showToast(toast)), (toast + 0.5) * 1000))
            .then(() => step(null, hold * 1000))
            .then(() => ({ blocked: blocked, cancelled: cancelled }));
    }

    function unblock(opts) {
        opts = opts || {};
        const toast = Number(opts.toast) > 0 ? Number(opts.toast) : 1.4;
        const hold = Number(opts.hold) > 0 ? Number(opts.hold) : 0.8;
        const cancelled = opts.confirm === false;
        openSettings();
        return step(null, 400)
            .then(() => step(() => tapToggleOff(), 500))
            .then(() => step(() => showSheet('unblock'), 850))
            .then(() => step(() => (cancelled ? cancelSheet() : confirmSheet()), 400))
            .then(() => step(() => (!cancelled && showToast(toast)), (toast + 0.5) * 1000))
            .then(() => step(null, hold * 1000))
            .then(() => ({ blocked: blocked, cancelled: cancelled }));
    }

    /* ---------- 删除联系人全自动演示（手动测试 / 一行动作出整段动画用） ----------
       前提：设置页已开着（openSettings / 打开对方设置 之后调用）。
       流程复刻参考视频：底部弹窗（0.65s）→ 点删除（按压 0.15s + 收起 0.3s）
       → 「正在加载」（toast 秒）→ 扫黑切到聊天列表 + 对勾 Toast → 黑幕淡出 → 停留。
       JS 侧用 #wxCutBlack 自带黑幕（与 main.py 的闪黑同一元素同一 CSS）。 */
    function blackIn(dur) {
        let f = document.getElementById('wxCutBlack');
        if (!f) {
            f = document.createElement('div');
            f.id = 'wxCutBlack';
            document.body.appendChild(f);
        }
        f.style.transition = 'opacity ' + (dur || 0.16) + 's ease-in';
        void f.offsetWidth;
        f.classList.add('on');
        return step(null, (dur || 0.16) * 1000 + 20);
    }

    function blackOut(dur) {
        const f = document.getElementById('wxCutBlack');
        if (f) {
            f.style.transition = 'opacity ' + (dur || 0.26) + 's ease-out';
            void f.offsetWidth;
            f.classList.remove('on');
        }
        return step(null, (dur || 0.26) * 1000 + 40);
    }

    function deleteContact(opts) {
        opts = opts || {};
        const toast = Number(opts.toast) > 0 ? Number(opts.toast) : 1.2;
        const hold = Number(opts.hold) > 0 ? Number(opts.hold) : 0.8;
        const cancelled = opts.confirm === false;
        if (!isSettingsPageOpen()) openSettings();
        return step(null, 400)
            .then(() => step(() => showDeleteSheet(), 650))
            .then(() => (cancelled
                ? step(() => cancelDeleteSheet(), 300)
                : step(() => pressDelete(), 150)
                    .then(() => step(() => confirmDeleteSheet(), 300))
                    .then(() => step(() => showToast(toast), (toast + 0.3) * 1000))))
            .then(() => (cancelled ? step(null, hold * 1000)
                : blackIn(0.16)
                    .then(() => sweepToListInstant())
                    .then(() => step(null, 120))
                    .then(() => blackOut(0.26))
                    .then(() => step(null, 700))
                    .then(() => step(() => hideDeleteToast(), hold * 1000))))
            .then(() => ({ cancelled: cancelled }));
    }

    /* ---------- 状态 ---------- */
    function isOpen() {
        const root = document.getElementById(SETTINGS_ID);
        const mask = document.getElementById(SHEET_MASK_ID);
        const toast = document.getElementById(TOAST_ID);
        return {
            settings: !!(root && root.classList.contains('open')),
            sheet: !!(mask && mask.classList.contains('on')),
            toast: !!(toast && toast.classList.contains('on')),
        };
    }

    function reset() {
        const mask = document.getElementById(SHEET_MASK_ID);
        if (mask) mask.classList.remove('on');
        const toast = document.getElementById(TOAST_ID);
        if (toast) toast.classList.remove('on');
        const delMask = document.getElementById(DELETE_SHEET_ID);
        if (delMask) delMask.classList.remove('on');
        hideDeleteToast();
        const sw = blackSwitch();
        if (sw) sw.classList.remove('on');
        blocked = false;
        sheetMode = null;
        deletedNames.clear();
        document.querySelectorAll('.wxb-deleted')
            .forEach((n) => { n.classList.remove('wxb-deleted'); });
        closeChatDetail();
        closeSettings();
        return true;
    }

    /* ---------- 入口绑定：资料页右上角「…」→ 打开设置页 ----------
       资料页 DOM 是懒创建的，这里用事件委托保证任何时候点「…」都能进设置页。 */
    document.addEventListener('click', (e) => {
        if (e.target && e.target.closest && e.target.closest('#wxPeerProfile .wpp-more')) {
            openSettings();
        }
    });

    window.__wxBlock = {
        openSettings,
        closeSettings,
        backFromSettings,
        tapToggle,
        tapToggleOff,
        showSheet,
        confirmSheet,
        cancelSheet,
        showToast,
        block,
        unblock,
        /* 聊天详情抽屉（聊天页右上角 …） */
        openChatDetail,
        closeChatDetail,
        isChatDetailOpen,
        /* 删除联系人链路（复刻参考视频「拉黑动作.mp4」） */
        showDeleteSheet,
        pressDelete,
        confirmDeleteSheet,
        cancelDeleteSheet,
        showDeleteToast,
        hideDeleteToast,
        swapToSettingsInstant,
        sweepToListInstant,
        deleteContact,
        isOpen,
        isBlocked: () => blocked,
        reset,
    };
})();
