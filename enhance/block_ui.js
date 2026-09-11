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

   opts：{ confirm: true/false, toast: 秒数, hold: 结束停留秒数 }
   ============================================================ */
(() => {
    if (window.__wxBlock) return;

    const SETTINGS_ID = 'wxBlockSettings';
    const SHEET_MASK_ID = 'wxBlockSheetMask';
    const TOAST_ID = 'wxBlockToast';

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
        document.body.classList.toggle('wx-peer-open', open || isOpenPeer());
        const app = document.getElementById('app');
        const dim = document.getElementById('wxPeerDim');
        const pushing = open || isOpenPeer();
        if (app) app.classList.toggle('wx-peer-pushing', pushing);
        if (dim) dim.classList.toggle('on', pushing);
    }

    function isOpenPeer() {
        const prof = document.getElementById('wxPeerProfile');
        const mom = document.getElementById('wxPeerMoments');
        return !!((prof && prof.classList.contains('open')) ||
                  (mom && mom.classList.contains('open')));
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
        const sw = blackSwitch();
        if (sw) sw.classList.remove('on');
        blocked = false;
        sheetMode = null;
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
        isOpen,
        isBlocked: () => blocked,
        reset,
    };
})();
