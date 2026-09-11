/* ============================================================
   转账详情页（收款）—— 参考视频《接受转账的画面.mp4》像素级复刻
   ------------------------------------------------------------
   流程对齐参考视频：
   1. 点击聊天页对方发来的橙色转账卡片 → 详情页从右侧推入（400ms，
      聊天页内容同时左移 30%），推入同时出现「正在加载」toast，
      约 0.9s 后消失；
   2. 待收款态：蓝色时钟 +「待你收款」+「¥ 金额」+「转账时间」行 +
      绿色「收款」按钮 +「1天内未确认，将退还给对方。退还」；
   3. 点「收款」→「正在加载」toast 约 0.9s → 单帧瞬时切换已收款态：
      绿色对勾 +「你已收款，资金已存入零钱」+「零钱余额」链接 +
      转账/收款时间两行 + 零钱通推广行 +「账单详情」；
      同时聊天页卡片变为「已被接收」（对勾图标）；
   4. 点返回箭头：详情页右滑退出（400ms）。

   对外 API：window.__wxTransferDetail
     .open(cardEl)   .accept()   .close()   .isOpen()
   ============================================================ */
(() => {
    if (window.__wxTransferDetail) return;

    /* ---------- 工具 ---------- */
    function pad(n) { return n < 10 ? '0' + n : '' + n; }
    function cnTime(d) {
        d = d || new Date();
        return d.getFullYear() + '年' + pad(d.getMonth() + 1) + '月' + pad(d.getDate()) + '日 ' +
            pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    }
    function fmtAmount(v) {
        const n = parseFloat(v);
        return isNaN(n) ? String(v || '1.00') : n.toFixed(2);
    }
    /* 已接收状态的对勾圆圈图标（替换卡片 ⇄ 贴图，参考视频 f0240） */
    const CHECK_ICON = 'data:image/svg+xml;utf8,' + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none">' +
        '<circle cx="50" cy="50" r="43" stroke="#e6e6e6" stroke-width="7"/>' +
        '<path d="M31 51 L45 64 L70 36" stroke="#e6e6e6" stroke-width="8" ' +
        'stroke-linecap="round" stroke-linejoin="round"/></svg>');

    /* ---------- DOM ---------- */
    const root = document.createElement('div');
    root.id = 'wxTfDetail';
    root.innerHTML = `
        <div class="tfd-back" id="tfdBack">
            <svg viewBox="0 0 15 26" fill="none">
                <path d="M13 2 L3 13 L13 24" stroke="#8b8b8b" stroke-width="2.8"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="tfd-clock">
            <svg viewBox="0 0 77 77" fill="none">
                <circle cx="38.5" cy="38.5" r="34" stroke="#0aa5fd" stroke-width="6.5"/>
                <path d="M38.5 38.5 L38.5 17.5" stroke="#0aa5fd" stroke-width="6.5" stroke-linecap="round"/>
                <path d="M38.5 38.5 L26 47.5" stroke="#0aa5fd" stroke-width="6.5" stroke-linecap="round"/>
            </svg>
        </div>
        <div class="tfd-check">
            <svg viewBox="0 0 40 40" fill="none">
                <path d="M9 21 L17.5 29 L31 11.5" stroke="#ffffff" stroke-width="4.6"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="tfd-line1">
            <span class="l-wait">待你收款</span>
            <span class="l-done">你已收款，资金已存入零钱</span>
        </div>
        <div class="tfd-amount"><span class="rmb">¥</span><span class="amt" id="tfdAmt">1.00</span></div>
        <div class="tfd-balance">零钱余额</div>
        <div class="tfd-hr tfd-hr-1"></div>
        <div class="tfd-hr tfd-hr-2"></div>
        <div class="tfd-hr tfd-hr-3"></div>
        <div class="tfd-hr tfd-hr-4"></div>
        <div class="tfd-rows" id="tfdRows">
            <div class="tfd-row">
                <span class="k">转账时间</span><span class="v" id="tfdTimeV"></span>
            </div>
            <div class="tfd-row tfd-row-recv">
                <span class="k">收款时间</span><span class="v" id="tfdRecvV"></span>
            </div>
        </div>
        <div class="tfd-licaitong">
            <div class="tfd-lct-icon">
                <svg viewBox="0 0 50 50" fill="none">
                    <path d="M13 7 H37 L47 20 L25 44 L3 20 Z" fill="#ffc300"/>
                    <path d="M13 7 L20 20 L3 20 Z" fill="#ffd54d"/>
                    <path d="M37 7 L30 20 L47 20 Z" fill="#f0a500"/>
                    <path d="M20 20 H30 L25 44 Z" fill="#ffd54d"/>
                    <path d="M13 7 H25 L20 20 Z" fill="#ffdb33"/>
                    <path d="M25 7 H37 L30 20 Z" fill="#f5b301"/>
                </svg>
            </div>
            <div class="tfd-lct-body">
                <div class="l1">零钱通 七日年化 0.92%</div>
                <div class="l2">转入零钱通，能赚又能花</div>
            </div>
            <button class="tfd-lct-btn" id="tfdLctBtn">转入</button>
        </div>
        <button class="tfd-accept" id="tfdAcceptBtn">收款</button>
        <div class="tfd-foot">
            <span class="f-wait">1天内未确认，将退还给对方。<span class="blue">退还</span></span>
            <span class="f-done">账单详情</span>
        </div>
        <div class="tfd-toast">
            <div class="spin"></div>
            <div class="tx">正在加载</div>
        </div>
    `;
    /* 裁剪容器：限制详情层的合成范围，防止 transform 滑入/滑出时
       合成器表面向右侧膨胀（膨胀帧会把录屏撑宽、触发补帧鬼影）。 */
    const clip = document.createElement('div');
    clip.id = 'wxTfClip';
    clip.appendChild(root);
    document.body.appendChild(clip);

    const els = {
        amt: root.querySelector('#tfdAmt'),
        timeV: root.querySelector('#tfdTimeV'),
        recvV: root.querySelector('#tfdRecvV'),
        accept: root.querySelector('#tfdAcceptBtn'),
    };

    let opened = false;
    let toastTimer = null;
    let cardEl = null;

    function showToast(ms) {
        clearTimeout(toastTimer);
        root.classList.add('loading');
        toastTimer = setTimeout(() => root.classList.remove('loading'), ms);
    }

    /* ---------- 数据填充 ---------- */
    function fillFromCard(card) {
        let amount = '1.00';
        try {
            const src = card || document.querySelector('.dialogue-section .row:not(.self) .text.msg-transfer');
            const a = src && src.querySelector('.tf-amount .amt');
            if (a && a.textContent.trim()) amount = a.textContent.trim();
        } catch (e) { /* 忽略 */ }
        els.amt.textContent = fmtAmount(amount);
        els.timeV.textContent = cnTime();
        els.recvV.textContent = '';
    }

    /* 接收后：聊天页卡片改为「已被接收」+ 对勾圆圈图标（参考 f0240） */
    function markCardAccepted(card) {
        try {
            const src = card || document.querySelector('.dialogue-section .row:not(.self) .text.msg-transfer');
            if (!src) return;
            const t = src.querySelector('.tf-title');
            if (t) t.textContent = '已被接收';
            const img = src.querySelector('.tf-icon');
            if (img) img.src = CHECK_ICON;
        } catch (e) { /* 忽略 */ }
    }

    /* ---------- 对外动作 ---------- */
    function open(card) {
        if (opened) return true;
        opened = true;
        cardEl = card || null;
        root.classList.remove('done');
        fillFromCard(cardEl);
        /* 两段式启动：
           1) 预热段——详情层全幅摆到位（transition:none + 近不可见透明度），
              强迫合成器立刻栅格化这层新内容，吃掉「首次栅格化卡顿」；
           2) rAF 里先在 transition:none 下把 transform 复位回起点（这次复位
              与恢复过渡必须分开两次样式提交，否则起点==终点，过渡不触发，
              动画会瞬跳），然后再单独恢复过渡并加类，正常滑入。 */
        root.style.transition = 'none';
        root.style.transform = 'translateX(0)';
        root.style.opacity = '0.02';
        void root.offsetWidth;          // 提交预热样式，开始栅格化
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                root.style.opacity = '';
                root.style.transform = '';      // 回到 translateX(100%) 起点
                void root.offsetWidth;          // 提交复位（仍在 transition:none 下）
                root.style.transition = '';     // 恢复样式表过渡
                void root.offsetWidth;
                document.body.classList.add('wx-tfd-open');
                root.classList.add('open');     // 100% -> 0，正常滑入
                showToast(900);                 // 推入同时「正在加载」（对齐参考 f0048）
            });
        });
        return true;
    }

    function accept() {
        if (!opened) return false;
        els.recvV.textContent = cnTime();
        showToast(900);                 // 「正在加载」→ 单帧切换（参考 f0160→f0180）
        clearTimeout(accept._t);
        accept._t = setTimeout(() => {
            root.classList.add('done');
            markCardAccepted(cardEl);
        }, 900);
        return true;
    }

    function close() {
        if (!opened) return true;
        opened = false;
        clearTimeout(toastTimer);
        root.classList.remove('loading');
        root.classList.remove('open');
        document.body.classList.add('wx-tfd-close');
        document.body.classList.remove('wx-tfd-open');
        setTimeout(() => document.body.classList.remove('wx-tfd-close'), 450);
        setTimeout(() => root.classList.remove('done'), 450);
        return true;
    }

    /* ---------- 交互绑定 ---------- */
    els.accept.addEventListener('click', accept);
    root.querySelector('#tfdBack').addEventListener('click', close);
    root.querySelector('#tfdLctBtn').addEventListener('click', () => {});
    root.querySelector('.tfd-balance').addEventListener('click', () => {});
    root.querySelector('.tfd-foot .f-done').addEventListener('click', () => {});

    // 点击聊天页「对方」转账卡片 → 打开详情（事件委托，store 渲染的卡片同样生效）
    document.addEventListener('click', (e) => {
        const card = e.target.closest('.dialogue-section .row:not(.self) .text.msg-transfer');
        if (card && !opened) {
            e.preventDefault();
            e.stopPropagation();
            open(card);
        }
    }, true);

    /* ---------- API ---------- */
    window.__wxTransferDetail = { open, accept, close, isOpen() { return opened; } };
})();
