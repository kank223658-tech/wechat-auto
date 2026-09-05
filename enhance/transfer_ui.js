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
              <div class="tp-icon" style="background-image:url('/images/wxpanel/tp_${it.id}.png')"></div>
              <div class="tp-label">${it.label}</div>
            </div>`).join('')}
        </div>
        <div class="tp-dots"><i class="on"></i><i></i></div>
      </div>

      <!-- 转账金额页 -->
      <div id="wxTransferAmount">
        <div class="ta-top">
          <span class="ta-back">‹</span>
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
            <span class="ta-rmb">¥</span>
            <input class="ta-input" id="taInput" inputmode="decimal"
                   autocomplete="off" maxlength="10">
          </div>
        </div>
        <div class="ta-note">
          <input id="taNote" placeholder="添加转账说明" autocomplete="off" maxlength="30">
        </div>
        <div class="ta-spacer"></div>
        <div id="taKeyboard"></div>
      </div>

      <!-- 支付密码页 -->
      <div id="wxTransferPassword">
        <div class="pw-box">
          <div class="pw-title">请输入支付密码</div>
          <div class="pw-sub" id="pwAmount"></div>
          <div class="pw-dots">
            <i></i><i></i><i></i><i></i><i></i><i></i>
          </div>
          <div id="pwKeyboard"></div>
        </div>
      </div>
    `;
    document.body.appendChild(root);

    const panel = root.querySelector('#wxTransferPanel');
    const amountPage = root.querySelector('#wxTransferAmount');
    const passPage = root.querySelector('#wxTransferPassword');
    const taInput = root.querySelector('#taInput');
    const taNote = root.querySelector('#taNote');
    const taTitleName = root.querySelector('.ta-name');
    const taWxId = root.querySelector('#taWxId');
    const taAvatar = root.querySelector('#taAvatar');
    const pwDots = root.querySelectorAll('.pw-dots i');
    const pwAmount = root.querySelector('#pwAmount');

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
        // 4 列网格：前三列数字，最后一列为动作列
        container.classList.add('tkr-grid');
        const grid = document.createElement('div');
        grid.className = 'tkr-grid-inner';

        const addKey = (text, key, cls) => {
            const k = document.createElement('div');
            k.className = 'tkr-key' + (cls ? ' ' + cls : '');
            k.textContent = text;
            k.dataset.key = key;
            grid.appendChild(k);
        };

        // 前三列内容（金额：1-9 + . 0；密码：1-9 + 0）
        const digitRow = (a, b, c) => { addKey(a, a); addKey(b, b); addKey(c, c); };
        digitRow('1', '2', '3');
        digitRow('4', '5', '6');
        digitRow('7', '8', '9');
        if (isAmount) {
            addKey('.', '.');
            addKey('0', '0');
        } else {
            addKey('', '', 'tkr-hide');
            addKey('0', '0');
        }

        // 动作列：退格 + (金额) 转账确认键；密码页只退格
        const actionCol = document.createElement('div');
        actionCol.className = 'tkr-action-col';
        // 首行退格
        const del = document.createElement('div');
        del.className = 'tkr-key tkr-del tkr-action';
        del.textContent = '⌫';
        del.dataset.key = 'del';
        actionCol.appendChild(del);
        if (isAmount) {
            const ok = document.createElement('div');
            ok.className = 'tkr-key tkr-ok disabled';
            ok.textContent = '转账';
            ok.dataset.key = 'ok';
            actionCol.appendChild(ok);
        }

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
        if (!key || !key.dataset.key) return;
        e.preventDefault();
        const k = key.dataset.key;

        // 密码页输入
        if (passPage.classList.contains('open')) {
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

        // 面板点击
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
    }
    function refreshPwDots() {
        pwDots.forEach((d, i) => d.classList.toggle('filled', i < password.length));
    }

    /* ============================================================
       五、对外动作
       ============================================================ */
    function openPanel() {
        if (!activeFlow) {
            panel.classList.add('open');
            // 面板需要在聊天页可见；若不在聊天页则提示
            const sec = document.querySelector('.dialogue-section');
            if (!sec) { console.warn('[转账] 当前不在聊天页，无法打开功能面板。'); return false; }
        } else {
            // 已在转账流程中，强制重置再开
            reset();
            panel.classList.add('open');
        }
        root.style.display = 'block';
        return true;
    }
    function closePanel() {
        panel.classList.remove('open');
        setTimeout(() => { if (!amountPage.classList.contains('open') && !passPage.classList.contains('open')) { root.style.display = 'none'; } }, 260);
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
        passPage.classList.remove('open');
        amountPage.classList.add('open');
        root.style.display = 'block';
        // 聚焦金额输入框（配合数字键盘）
        requestAnimationFrame(() => { try { taInput.focus(); } catch (e) { /* ignore */ } });
        return true;
    }
    function closeAmount() {
        amountPage.classList.remove('open');
        activeFlow = false;
        setTimeout(() => { if (!passPage.classList.contains('open')) root.style.display = 'none'; }, 200);
    }
    function openPassword(amt, nt) {
        amount = amt != null ? String(amt) : amount;
        note = nt != null ? String(nt) : note;
        amountPage.classList.remove('open');
        passPage.classList.add('open');
        password = '';
        refreshPwDots();
        pwAmount.textContent = '¥ ' + amount + (note ? ' · ' + note : '');
        root.style.display = 'block';
        return true;
    }
    function confirmPassword() {
        // 密码输满 6 位：稍作停顿后收起，回聊天上屏转账卡片
        // 先把金额/备注/接收人存到局部变量，避免清空后丢失（防错乱的关键）
        const amt = amount;
        const nt = note;
        const who = recipient;
        setTimeout(() => {
            passPage.classList.remove('open');
            amountPage.classList.remove('open');
            activeFlow = false;
            root.style.display = 'none';
            amount = ''; note = ''; password = '';      // 清空，防下次错乱
            // 上屏橙色转账卡片（复用 __wxChatExt 的橙色卡片）
            try {
                if (window.__wxChatExt && window.__wxChatExt.selfTransfer) {
                    window.__wxChatExt.selfTransfer(who, amtOr(amt), nt);
                    return;
                }
            } catch (e) { /* 忽略 */ }
            console.warn('[转账] 未找到 __wxChatExt.selfTransfer，无法上屏。');
        }, 300);
    }
    function amtOr(v) { return v && /[0-9.]/.test(v) ? v : '1.00'; }

    function reset() {
        amount = ''; note = ''; password = '';
        activeFlow = false;
        panel.classList.remove('open');
        amountPage.classList.remove('open');
        passPage.classList.remove('open');
        root.style.display = 'none';
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