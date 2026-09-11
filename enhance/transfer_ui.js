/* ============================================================
   转账全流程界面覆盖层（main.py 注入）
   ------------------------------------------------------------
   复现微信转账三步界面：
   1. 「+」功能面板（图片1）：底部弹出，含 照片/拍摄/视频通话/位置/
      红包/礼物/转账/语音输入，点「转账」进入转账金额页。
   2. 转账金额页（图片2）：「转账给 d(**康)」+ 微信号 + 头像 +
      「转账金额」大号 ¥ 输入框 + 「添加转账说明」 + 数字键盘(绿「转账」键)。
   3. 支付密码页：标题「请输入支付密码」+ 6 个密码圆点 + 数字键盘，
      输满 6 位自动确认，回到聊天页上屏橙色转账卡片。

   对外 API（幂等，可反复调用）：
   window.__wxTransfer
     .openPanel()                  —— 弹「+」功能面板（图片1）
     .openAmount(recipient, wxid)  —— 打开转账金额页（图片2）
     .getAmount()                  —— 返回当前金额（用于驱动/校验）
     .setAmount(text)              —— 直接设置金额
     .openPassword(amount, note)   —— 打开支付密码页
     .reset()                      —— 清空面板/金额/密码状态（每次转账前调用）
     .setRecipient(name, wxid)     —— 设置收款人标题

   命名空间要点：所有界面挂在 window.__wxTransfer 下；通过「状态守卫」
   (activeFlow 标记) 防止重复进入；每次转账前强制 reset()，避免上一次的
   金额/密码残留导致下次错乱。
   ============================================================ */
(() => {
    if (window.__wxTransfer) return;

    /* ------------------------------------------------------------
       状态：activeFlow 标记当前转账是否进行中；其余为复用状态
       ------------------------------------------------------------ */
    let activeFlow = false;          // 转账流程进行中保险丝
    let recipient = 'd';
    let recipientWxId = '';
    let amount = '';                 // 金额字符串，如 "50.00"（仅数字和小数点）
    let note = '';
    let password = '';               // 6 位密码
    let kbTimer = null;              // 键盘延迟升起计时器

    /* ------------------------------------------------------------
       「+」功能面板定义（两行四列，顺序对齐图片1）
       图标优先用微信官方 SVG（从 ipa 拆解），黑/白硬编码统一改为
       currentColor / 去绿底，灰色图标块上显示为白色线条。实在没有
       官方图的（红包/转账）保留自绘描边。色随 .tp-icon 继承。
       ------------------------------------------------------------ */
    const PANEL_ITEMS = [
        { id: 'photo',   label: '照片' },
        { id: 'camera',  label: '拍摄' },
        { id: 'video',   label: '视频通话' },
        { id: 'location',label: '位置' },
        { id: 'redpack', label: '红包' },
        { id: 'gift',    label: '礼物' },
        { id: 'transfer',label: '转账' },
        { id: 'voicein', label: '语音输入' },
    ];

    /* ============================================================
       一、构建 DOM
       ============================================================ */
    const root = document.createElement('div');
    root.id = 'wxTransferRoot';
    root.style.display = 'none';
    root.innerHTML = `
      <!-- 「+」功能面板 -->
      <div id="wxTransferPanel" class="wx-transfer-mask">
        <div class="tp-grid">
          ${PANEL_ITEMS.map(it => `
            <div class="tp-item ${it.id === 'transfer' ? 'tp-transfer' : 'tp-disabled'}"
                 data-id="${it.id}">
              <div class="tp-icon"><img src="/images/wxpanel/tp_${it.id}.png" alt=""></div>
              <div class="tp-label">${it.label}</div>
            </div>`).join('')}
        </div>
        <div class="tp-dots"><i class="on"></i><i></i></div>
      </div>

      <!-- 转账金额页 -->
      <div id="wxTransferAmount">
        <div class="ta-top">
          <span class="ta-back"><img src="/images/wxpanel/amt_back.png" alt="返回"></span>
        </div>
        <div class="ta-recipient">
          <div class="ta-info">
            <div class="ta-title" id="taTitle">转账给 <b class="ta-name">d</b></div>
            <div class="ta-wxid" id="taWxId">微信号：</div>
          </div>
          <img class="ta-avatar" id="taAvatar" alt="">
        </div>
        <div class="ta-amount-box">
          <div class="ta-amount-label">转账金额</div>
          <div class="ta-amount-row">
            <span class="ta-rmb"><img src="/images/wxpanel/amt_yen.png" alt="¥"></span>
            <input class="ta-input" id="taInput" inputmode="decimal"
                   autocomplete="off" maxlength="10">
          </div>
        </div>
        <div class="ta-divider"></div>
        <div class="ta-note">
          <input id="taNote" placeholder="添加转账说明" autocomplete="off" maxlength="30">
        </div>
        <div class="ta-spacer"></div>
        <div id="taKeyboard"></div>
      </div>

      <!-- ① 微信支付 loading toast（居中，对齐真机：气泡打勾图标 + 微信支付 + 三点轮播） -->
      <div id="wxPayToast">
        <div class="pay-toast-card">
          <svg class="pay-toast-icon" viewBox="0 0 24 24">
            <path fill="#fff" d="M12 2C6.5 2 2 5.9 2 10.7c0 2.6 1.3 4.9 3.4 6.5-.1.9-.5 2.3-1.6 3.4 0 0 2.7-.2 4.6-1.6.9.2 1.9.4 3.6.4 5.5 0 10-3.9 10-8.7S17.5 2 12 2z"/>
            <path d="M7.6 10.9l2.9 2.9 5.9-5.4" stroke="#373737" stroke-width="2.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <div class="pay-toast-text">微信支付</div>
          <div class="pay-toast-dots"><i></i><i></i><i></i></div>
        </div>
      </div>

      <!-- ② 付款面板（底部滑出，对齐真机：×/使用面容 + 向X转账 + ¥金额 +
              付款方式·零钱✓ + 6 格密码 + 数字键盘；保持 #pwKeyboard/.tkr-key 供 main.py 驱动） -->
      <div id="wxPaySheet">
        <div class="pay-sheet-mask"></div>
        <div class="pay-sheet">
          <div class="pay-sheet-header">
            <span class="pay-close">×</span>
            <span class="pay-faceid">使用面容</span>
          </div>
          <div class="pay-sheet-title" id="payTitle">向 d(**康) 转账</div>
          <div class="pay-sheet-amount" id="payAmount">¥1.00</div>
          <div class="pay-sheet-divider"></div>
          <div class="pay-mid">
            <div class="pay-way-label">
              <span>付款方式</span>
              <span class="pay-change">更改 <i>⌄</i></span>
            </div>
            <div class="pay-wallet-row">
              <span class="pay-coin">¥</span>
              <span class="pay-wallet-name">零钱</span>
              <svg class="pay-check" viewBox="0 0 24 24"><path d="M4 12.5l5.2 5.2L20 6.5" fill="none" stroke="#07c160" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="pay-boxes" id="payBoxes">
              <i></i><i></i><i></i><i></i><i></i><i></i>
            </div>
          </div>
          <div class="pay-loading" id="payLoading">
            <svg class="pay-loading-icon" viewBox="0 0 24 24">
              <path fill="#98989d" d="M12 2C6.5 2 2 5.9 2 10.7c0 2.6 1.3 4.9 3.4 6.5-.1.9-.5 2.3-1.6 3.4 0 0 2.7-.2 4.6-1.6.9.2 1.9.4 3.6.4 5.5 0 10-3.9 10-8.7S17.5 2 12 2z"/>
              <path d="M7.6 10.9l2.9 2.9 5.9-5.4" stroke="#26262a" stroke-width="2.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div class="pay-loading-text">微信支付</div>
            <div class="pay-toast-dots"><i></i><i></i><i></i></div>
          </div>
          <div id="pwKeyboard"></div>
        </div>
      </div>

      <!-- ③ 支付成功整页（对齐真机：绿色对勾+支付成功 + 待X确认收款 + ¥金额 + 完成） -->
      <div id="wxPaySuccess">
        <div class="ps-head">
          <svg class="ps-icon" viewBox="0 0 24 24">
            <path fill="#3eb575" d="M12 2C6.5 2 2 5.9 2 10.7c0 2.6 1.3 4.9 3.4 6.5-.1.9-.5 2.3-1.6 3.4 0 0 2.7-.2 4.6-1.6.9.2 1.9.4 3.6.4 5.5 0 10-3.9 10-8.7S17.5 2 12 2z"/>
            <path d="M7.6 10.9l2.9 2.9 5.9-5.4" stroke="#141416" stroke-width="2.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span class="ps-title">支付成功</span>
        </div>
        <div class="ps-body">
          <div class="ps-wait" id="psWait">待对方确认收款</div>
          <div class="ps-amount" id="psAmount">¥1.00</div>
        </div>
        <div class="ps-footer">
          <button class="ps-done" id="payDoneBtn">完成</button>
        </div>
      </div>
    `;
    document.body.appendChild(root);

    const panel = root.querySelector('#wxTransferPanel');
    const amountPage = root.querySelector('#wxTransferAmount');
    const payToast = root.querySelector('#wxPayToast');
    const paySheet = root.querySelector('#wxPaySheet');
    const paySuccess = root.querySelector('#wxPaySuccess');
    const taInput = root.querySelector('#taInput');
    const taNote = root.querySelector('#taNote');
    const taTitleName = root.querySelector('.ta-name');
    const taWxId = root.querySelector('#taWxId');
    const taAvatar = root.querySelector('#taAvatar');
    const payBoxes = root.querySelectorAll('#payBoxes i');
    const payTitle = root.querySelector('#payTitle');
    const payAmountEl = root.querySelector('#payAmount');
    const psWait = root.querySelector('#psWait');
    const psAmount = root.querySelector('#psAmount');
    /* 「完成」与付款面板 × 关闭 */
    root.querySelector('#payDoneBtn').addEventListener('click', finishSuccess);
    root.querySelector('.pay-close').addEventListener('click', () => {
        // 中途取消：面板下滑 + 成功链路全部收起，不上屏
        paySheet.classList.remove('open', 'loading');
        paySuccess.classList.remove('open');
        amountPage.classList.remove('open');
        taKeyboardEl.classList.remove('kb-down');
        activeFlow = false;
        amount = ''; note = ''; password = '';
        refreshPwDots(); syncAmountInput();
    });

    /* ============================================================
       二、数字键盘构建（金额页带绿色「转账」键；密码页 0-9）
       ------------------------------------------------------------
       金额页布局（对齐图片2）：4 列网格，右侧为动作列
         1 2 3   | ⌫
         4 5 6   | [转账 绿]
         7 8 9   | [转账   ]
         . 0     | [转账   ]
       密码页布局：
         1 2 3
         4 5 6
         7 8 9
         (空) 0 ⌫
       ============================================================ */
    function buildNumericKeypad(container, mode) {
        container.innerHTML = '';
        const isAmount = mode === 'amount';
        container.classList.add('tkr-grid');
        // 金额页：真机 4 等列平铺（1-9 / 0 跨两列 . / 删除右列首行 / 转账绿键右列跨三行）
        if (isAmount) {
            const addKey = (html, key, cls) => {
                const k = document.createElement('div');
                k.className = 'tkr-key' + (cls ? ' ' + cls : '');
                k.innerHTML = html;
                k.dataset.key = key;
                container.appendChild(k);
            };
            ['1','2','3','4','5','6','7','8','9'].forEach(d => addKey(d, d));
            addKey('0', '0', 'tkr-zero');
            addKey('.', '.');
            addKey('<img src="/images/wxpanel/amt_del.png" alt="删除">', 'del', 'tkr-del');
            addKey('转账', 'ok', 'tkr-ok disabled');
            return;
        }
        // 密码页：3 列网格 + 右侧动作列（付款面板内尺寸较小，保持原布局）
        const grid = document.createElement('div');
        grid.className = 'tkr-grid-inner';

        const addKey = (text, key, cls) => {
            const k = document.createElement('div');
            k.className = 'tkr-key' + (cls ? ' ' + cls : '');
            k.textContent = text;
            k.dataset.key = key;
            grid.appendChild(k);
        };

        // 前三列内容（密码：1-9 + 0）
        const digitRow = (a, b, c) => { addKey(a, a); addKey(b, b); addKey(c, c); };
        digitRow('1', '2', '3');
        digitRow('4', '5', '6');
        digitRow('7', '8', '9');
        addKey('', '', 'tkr-hide');
        addKey('0', '0');

        // 动作列：退格
        const actionCol = document.createElement('div');
        actionCol.className = 'tkr-action-col';
        const del = document.createElement('div');
        del.className = 'tkr-key tkr-del tkr-action';
        del.textContent = '⌫';
        del.dataset.key = 'del';
        actionCol.appendChild(del);

        container.appendChild(grid);
        container.appendChild(actionCol);
    }

    /* 金额键盘 + 密码键盘 */
    const taKeyboardEl = root.querySelector('#taKeyboard');
    const pwKeyboardEl = root.querySelector('#pwKeyboard');
    buildNumericKeypad(taKeyboardEl, 'amount');
    buildNumericKeypad(pwKeyboardEl, 'password');

    /* ============================================================
       三、数字键盘点击分发（即支持真机 pointerdown，也支持程序化 click 驱动）
       ============================================================ */
    function handleKeyEvent(e) {
        const key = e.target.closest('.tkr-key');
        if (!key || !key.dataset.key) {
            // 非键盘区域：处理「+」面板条目点击（之前被提前 return 挡成死代码）
            if (panel.classList.contains('open')) {
                const item = e.target.closest('.tp-item');
                if (item && item.dataset.id === 'transfer') {
                    closePanel();
                    // 传递当前收款人（从聊天标题取）
                    const name = getPeerName() || recipient;
                    openAmount(name, recipientWxId);
                } else if (item) {
                    // 其它项为占位：轻微反馈，不跳转
                    item.classList.add('tp-press');
                    setTimeout(() => item.classList.remove('tp-press'), 180);
                }
            }
            return;
        }
        e.preventDefault();
        const k = key.dataset.key;

        // 付款面板密码输入
        if (paySheet.classList.contains('open')) {
            if (/^\d$/.test(k)) {
                if (password.length < 6) {
                    password += k;
                    refreshPwDots();
                    if (password.length === 6) { confirmPassword(); }
                }
            } else if (k === 'del') {
                password = password.slice(0, -1);
                refreshPwDots();
            }
            return;
        }

        // 金额页输入
        if (amountPage.classList.contains('open')) {
            if (/^\d$/.test(k) || k === '.') {
                // 防止以 "." 开头前导零问题：首个字符若为 '0' 且后面还有则不再加前导 0
                if (amount === '0' && k !== '.') {
                    amount = k;                     // 去掉前导零
                } else if (amount.includes('.') && k === '.') {
                    return;                         // 已有点，忽略再点
                } else if (amount === '' && k === '.') {
                    amount = '0.';                  // 空金额直接点小数点 → 0.
                } else {
                    amount += k;
                }
                // 限两位小数
                const dot = amount.indexOf('.');
                if (dot >= 0 && amount.length - dot > 3) amount = amount.slice(0, dot + 3);
                if (amount.length > 10) amount = amount.slice(0, 10);
                syncAmountInput();
            } else if (k === 'del') {
                amount = amount.slice(0, -1);
                syncAmountInput();
            } else if (k === 'ok') {
                if (!amount || /^\.$/.test(amount)) return;   // 无有效金额
                // 从界面输入框读取说明（可能由 main.py 直接注入），保证备注不丢
                const noteVal = taNote.value != null ? String(taNote.value).trim() : '';
                openPassword(amount, noteVal);
            }
            return;
        }
    }
    // pointerdown 负责真人点击；click 负责被 main.py/编辑器程序化驱动
    root.addEventListener('pointerdown', handleKeyEvent);
    root.addEventListener('click', handleKeyEvent);

    /* ============================================================
       四、内部工具
       ============================================================ */
    function getPeerName() {
        // 尝试从聊天页导航栏读取对方名字（#wx-header .center）
        try {
            const c = document.querySelector('#wx-header .center');
            if (c) {
                const span = c.querySelector('span:not(.parentheses):not(.peer-typing)');
                if (span && span.textContent.trim()) return span.textContent.trim();
            }
        } catch (e) { /* 忽略 */ }
        return recipient;
    }
    function getPeerAvatar() {
        try {
            const av = document.querySelector('.dialogue-section .row:not(.self) .header');
            if (av && av.getAttribute('src')) return av.getAttribute('src');
        } catch (e) { /* 忽略 */ }
        return '/images/header/yehua.jpg';
    }
    function syncAmountInput() {
        taInput.value = amount;
        const ok = taKeyboardEl.querySelector('.tkr-ok');
        if (ok) ok.classList.toggle('disabled', !(amount && !/^\.$/.test(amount)));
        /* ¥ 与金额同色：空态灰色占位、有值变白（对齐真机） */
        const row = taInput.closest('.ta-amount-row');
        if (row) row.classList.toggle('has-amt', !!(amount && amount !== '.'));
    }
    function refreshPwDots() {
        payBoxes.forEach((d, i) => d.classList.toggle('filled', i < password.length));
    }

    /* ============================================================
       五、对外动作
       ============================================================ */
    function openPanel() {
        // 关键时序：先显示 root 并强制回流，让面板以 translateY(100%) 的初始态完成首次渲染，
        // 之后再加 .open。否则 Chrome 对 display:none 子树把 transform 解析为 none，
        // 面板首帧即终态（瞬现），只剩输入栏在升 → 视觉上"面板先出、输入栏后到、中间穿模"。
        root.style.display = 'block';
        if (!activeFlow) {
            // 面板需要在聊天页可见；若不在聊天页则提示
            const sec = document.querySelector('.dialogue-section');
            if (!sec) { root.style.display = 'none'; console.warn('[转账] 当前不在聊天页，无法打开功能面板。'); return false; }
        } else {
            // 已在转账流程中，强制重置再开
            reset();
        }
        void panel.offsetWidth;   // 强制回流：锁定滑入起始态
        panel.classList.add('open');
        // 输入工具栏与面板同时、同曲线上移（真机实测一体刚性升降）
        document.body.classList.add('wxp-open');
        return true;
    }
    function closePanel() {
        panel.classList.remove('open');
        document.body.classList.remove('wxp-open');
        setTimeout(() => { if (!amountPage.classList.contains('open') && !paySheet.classList.contains('open')) { root.style.display = 'none'; } }, 340);
    }
    function openAmount(name, wxid) {
        activeFlow = true;
        recipient = name || recipient;
        recipientWxId = wxid || recipientWxId;
        panel.classList.remove('open');
        taTitleName.textContent = recipient + ' (**康)';
        taWxId.textContent = '微信号：' + (recipientWxId || 'AAi' + (recipient || 'd').charCodeAt(0).toString(16).toUpperCase() + '201');
        taAvatar.src = getPeerAvatar();
        amount = ''; note = '';
        syncAmountInput();
        taNote.value = '';
        paySheet.classList.remove('open', 'loading');
        payToast.classList.remove('show');
        paySuccess.classList.remove('open');
        taKeyboardEl.classList.remove('kb-down', 'kb-up');
        // 与 openPanel 同理：先渲染初始态（右侧屏外）再推入，保证滑入动画不被跳过
        root.style.display = 'block';
        void amountPage.offsetWidth;
        amountPage.classList.add('open');
        // 真机时序：页面先滑入(~260ms)→停顿→键盘单独升起(~300ms)
        clearTimeout(kbTimer);
        kbTimer = setTimeout(() => { taKeyboardEl.classList.add('kb-up'); }, 430);
        // 聚焦金额输入框（配合数字键盘）
        requestAnimationFrame(() => { try { taInput.focus(); } catch (e) { /* ignore */ } });
        return true;
    }
    function closeAmount() {
        amountPage.classList.remove('open');
        activeFlow = false;
        setTimeout(() => { if (!paySheet.classList.contains('open')) root.style.display = 'none'; }, 320);
    }
    /* 金额格式化：'1' → '1.00' */
    function fmtAmount(v) {
        const n = parseFloat(v);
        return isNaN(n) ? String(v || '1.00') : n.toFixed(2);
    }
    /* 点绿键「转账」后：键盘下滑 → 微信支付 toast（~1.8s）→ 付款面板底部滑起 */
    function openPassword(amt, nt) {
        amount = amt != null ? String(amt) : amount;
        note = nt != null ? String(nt) : note;
        password = '';
        refreshPwDots();
        paySheet.classList.remove('loading');
        payTitle.textContent = '向' + recipient + '(**康) 转账';
        const fa = fmtAmount(amount);
        payAmountEl.textContent = '¥' + fa;
        psWait.textContent = '待' + recipient + '确认收款';
        psAmount.textContent = '¥' + fa;
        amountPage.classList.add('open');           // 金额页留在底层（被压暗）
        clearTimeout(kbTimer);
        taKeyboardEl.classList.add('kb-down');      // 键盘下滑
        payToast.classList.add('show');             // 居中 toast
        root.style.display = 'block';
        setTimeout(() => {
            payToast.classList.remove('show');
            paySheet.classList.add('open');         // 面板滑起
        }, 1800);
        return true;
    }
    /* 密码输满 6 位：停 0.35s → 面板加载态 0.95s → 面板下滑 → 成功页滑入 */
    function confirmPassword() {
        setTimeout(() => {
            paySheet.classList.add('loading');
            setTimeout(() => {
                paySheet.classList.remove('open', 'loading');
                paySuccess.classList.add('open');
            }, 950);
        }, 350);
    }
    /* 「完成」：成功页下滑 + 金额页右滑退出 → 聊天页上屏橙色卡片 */
    function finishSuccess() {
        const amt = amount;
        const nt = note;
        const who = recipient;
        paySuccess.classList.remove('open');
        amountPage.classList.remove('open');
        taKeyboardEl.classList.remove('kb-down');
        activeFlow = false;
        amount = ''; note = ''; password = '';      // 清空，防下次错乱
        setTimeout(() => {
            try {
                if (window.__wxChatExt && window.__wxChatExt.selfTransfer) {
                    window.__wxChatExt.selfTransfer(who, amtOr(amt), nt);
                    return;
                }
            } catch (e) { /* 忽略 */ }
            console.warn('[转账] 未找到 __wxChatExt.selfTransfer，无法上屏。');
        }, 330);
    }
    function amtOr(v) { return v && /[0-9.]/.test(v) ? v : '1.00'; }

    function reset() {
        amount = ''; note = ''; password = '';
        activeFlow = false;
        clearTimeout(kbTimer);
        panel.classList.remove('open');
        amountPage.classList.remove('open');
        paySheet.classList.remove('open', 'loading');
        payToast.classList.remove('show');
        paySuccess.classList.remove('open');
        taKeyboardEl.classList.remove('kb-down', 'kb-up');
        document.body.classList.remove('wxp-open');
        refreshPwDots();
        syncAmountInput();
    }

    /* 退款人改名（供外部/页面导航同步） */
    function setRecipient(name, wxid) {
        recipient = name || recipient;
        recipientWxId = wxid || recipientWxId;
    }
    function getAmount() { return amount; }
    function setAmount(text) { amount = String(text != null ? text : ''); syncAmountInput(); }

    /* ============================================================
       六、暴露 API
       ============================================================ */
    window.__wxTransfer = {
        openPanel,
        closePanel,
        openAmount,
        closeAmount,
        openPassword,
        reset,
        setRecipient,
        getAmount,
        setAmount,
        getState() {
            return { activeFlow, recipient, recipientWxId, amount, note, password };
        },
    };
})();