/* ============================================================
   转账详情页（收款）—— 参考视频《接受转账的画面.mp4》像素级复刻
   ------------------------------------------------------------
   流程对齐参考视频：
   1. 点击聊天页对方发来的橙色转账卡片 → 详情页从右侧推入（420ms，
      聊天页内容同时左移 30%），推入同时出现「正在加载」toast，
      淡入 ~0.3s、~0.5s 后淡出；
   2. 待收款态：蓝色时钟 +「待你收款」+「¥ 金额」+「转账时间」行 +
      绿色「收款」按钮 +「1天内未确认，将退还给对方。退还」；
   3. 点「收款」→「正在加载」toast 淡入，~1.57s 后单帧瞬时切换已收款态：
      绿色对勾 +「你已收款，资金已存入零钱」+「零钱余额」链接 +
      转账/收款时间两行 + 零钱通推广行 +「账单详情」；
      同时聊天页卡片变为「已被接收」（对勾图标）；
   4. 点返回箭头：详情页右滑退出（420ms）。

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
        '<circle cx="50" cy="50" r="43" stroke="rgba(255,255,255,.42)" stroke-width="7"/>' +
        '<path d="M31 51 L45 64 L70 36" stroke="rgba(255,255,255,.42)" stroke-width="8" ' +
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
                <circle cx="38.5" cy="38.5" r="34" stroke="#2da7ef" stroke-width="5"/>
                <path d="M38.5 38.5 L38.5 17.5" stroke="#2da7ef" stroke-width="5" stroke-linecap="round"/>
                <path d="M38.5 38.5 L26 47.5" stroke="#2da7ef" stroke-width="5" stroke-linecap="round"/>
            </svg>
        </div>
        <div class="tfd-check">
            <svg viewBox="0 0 40 40" fill="none">
                <path d="M2.3 21 L14 32 L37.7 7.6" stroke="#181818" stroke-width="4.6"
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
                <!-- 零钱通钻石：参考 a_016 实测金色 #f6c531、带白色切面线
                     （原先只有色块分区、没有白线，且金色偏橙） -->
                <svg viewBox="0 0 50 50" fill="none">
                    <path d="M13 7 H37 L47 20 H3 Z" fill="#f6c531"/>
                    <path d="M3 20 H47 L25 44 Z" fill="#f6c531"/>
                    <path d="M3 20 H47" stroke="#fff" stroke-width="1.6"/>
                    <path d="M13 7 L20 20 L25 44 L30 20 L37 7" stroke="#fff"
                          stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round"/>
                    <path d="M20 20 H30" stroke="#fff" stroke-width="1.1"/>
                    <path d="M13 7 L3 20 M37 7 L47 20" stroke="#fff" stroke-width="1.1"/>
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
    let cardEl = null;

    /* 页面时钟探针：录制端（main.py）在每个动作后回读打印，用于核对
       成片时间轴与页面真实时序的偏差。 */
    window.__tfdLog = [];
    function tfdMark(tag) {
        try { window.__tfdLog.push(tag + '@' + Math.round(performance.now())); } catch (e) {}
    }

    /* 「正在加载」toast：WAAPI 预排淡入/淡出（而非 setTimeout+transition）。
       原因：确定性转场（_det_transition）会 pause/step 页面动画，wall-clock
       定时器在步进期间照跑，toast 会在转场帧列里闪没；WAAPI 动画能被一起
       重采进帧列，成片节奏与页面动画严格同轨。dataset.loading 供录制端
       轮询「加载是否结束」用。 */
    function playToast(startDelay, inMs, outDelay) {
        const toast = root.querySelector('.tfd-toast');
        toast.getAnimations().forEach(a => { try { a.cancel(); } catch (e) {} });
        toast.animate([{ opacity: 0 }, { opacity: 1 }],
                      { duration: inMs, delay: startDelay, fill: 'both', easing: 'ease' });
        toast.animate([{ opacity: 1 }, { opacity: 0 }],
                      { duration: 300, delay: outDelay, fill: 'forwards', easing: 'ease' });
        root.dataset.loading = '1';
    }
    function toastDone() { root.dataset.loading = ''; }

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

    /* 接收后（参考 f_238）：
       1) 对方卡片变暗橙 #a66123 +「已被接收」+ 半透明对勾圈图标；
       2) 我方同时上屏一条「已收款」暗橙回执卡（同款样式）。 */
    function styleAcceptedCard(card, title) {
        if (!card) return;
        card.classList.add('tf-accepted');
        const t = card.querySelector('.tf-title');
        if (t) t.textContent = title;
        const img = card.querySelector('.tf-icon');
        if (img) img.src = CHECK_ICON;
    }
    function markCardAccepted(card) {
        try {
            const src = card || document.querySelector('.dialogue-section .row:not(.self) .text.msg-transfer');
            if (!src) return;
            styleAcceptedCard(src, '已被接收');
            setTimeout(() => {
                try {
                    if (window.__wxChatExt) window.__wxChatExt.selfTransfer('', '', '', '已收款');
                } catch (e) { /* 忽略 */ }
                /* 等 store 渲染 + 气泡入场动画挂上后再补已接收样式 */
                setTimeout(() => {
                    const cards = document.querySelectorAll('.dialogue-section .row.self .text.msg-transfer');
                    const last = cards[cards.length - 1];
                    if (last && !last.classList.contains('tf-accepted')) {
                        styleAcceptedCard(last, '已收款');
                    }
                }, 420);
            }, 260);
        } catch (e) { /* 忽略 */ }
    }

    /* ---------- 对外动作 ---------- */
    function open(card) {
        if (opened) return true;
        opened = true;
        cardEl = card || null;
        accept._t = null;
        root.classList.remove('done');
        fillFromCard(cardEl);
        tfdMark('open:call');
        /* 两段式启动（同步 FLIP，无任何 setTimeout/rAF）：
           1) 预热段——transition:none 摆到位 + 近不可见透明度，强迫合成器
              立刻栅格化这层新内容，吃掉「首次栅格化卡顿」；
           2) 同一任务内靠 void offsetWidth 强制样式提交：复位起点 → 恢复
              过渡 → 加类滑入（无头实测两次 reflow 即可让过渡触发）。
              此前拆两级 setTimeout(34ms) 的写法在录制环境被推迟 ~3.4s 才
              触发（页面先无动画硬出现、之后才滑入+toast，看起来像凭空
              多一次转圈）；同步执行后推入与 toast 绑死同一时刻。 */
        root.style.transition = 'none';
        root.style.transform = 'translateX(0)';
        root.style.opacity = '0.02';
        void root.offsetWidth;          // 提交预热样式，开始栅格化
        root.style.opacity = '';
        root.style.transform = '';      // 回到 translateX(100%) 起点
        void root.offsetWidth;          // 提交复位（仍在 transition:none 下）
        root.style.transition = '';     // 恢复样式表过渡
        void root.offsetWidth;
        document.body.classList.add('wx-tfd-open');
        root.classList.add('open');     // 100% -> 0，正常滑入
        tfdMark('open:slide+toast');
        /* 参考 f_047-065：推入开始 ~0.1s 后淡入，~0.5s 后开始淡出 */
        playToast(100, 280, 520);
        return true;
    }

    function accept() {
        if (!opened) return false;
        tfdMark('accept:call');
        els.recvV.textContent = cnTime();
        /* 参考 f_120→f_167：toast 淡入 ~0.23s → 加载 ~1.57s → 单帧切已收款，
           切换瞬间 toast 开始淡出 ~0.3s（f_167-176）。 */
        /* 参考 f_120→f_167：淡入 ~0.23s → 加载 1.57s → 单帧切已收款，
           切换瞬间 toast 开始淡出 ~0.3s（f_167-176）。 */
        playToast(0, 230, 1570);
        clearTimeout(accept._t);
        accept._t = setTimeout(() => {
            tfdMark('accept:switch');
            root.classList.add('done');
            toastDone();
            markCardAccepted(cardEl);
        }, 1570);
        return true;
    }

    function close() {
        if (!opened) return true;
        tfdMark('close:call');
        opened = false;
        try {
            root.querySelector('.tfd-toast').getAnimations()
                .forEach(a => { try { a.cancel(); } catch (e) {} });
        } catch (e) { /* 忽略 */ }
        root.dataset.loading = '';
        root.classList.remove('done');
        root.classList.remove('open');
        document.body.classList.add('wx-tfd-close');
        document.body.classList.remove('wx-tfd-open');
        setTimeout(() => document.body.classList.remove('wx-tfd-close'), 480);
        setTimeout(() => root.classList.remove('done'), 480);
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
