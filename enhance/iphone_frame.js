/* ============================================================
   iPhone 屏幕录制仿真层（main.py 注入）
   ------------------------------------------------------------
   构建 iOS 状态栏 DOM（实时时间 / 信号 / WiFi / 电量 + 灵动岛）
   与 Home 指示条、圆角遮罩，并提供 window.__wxPhoneFrame
   API 供自动化控制（电量、显示/隐藏）。幂等，可反复调用。

   深色模式：状态栏图标统一为白色（iOS 深色状态栏）。
   右侧信号 / WiFi / 电量集中在同一行（真机状态栏布局）。
   电量图标固定为白色非充电（贴合 iPhone 15），无充电闪电。
   ============================================================ */
(() => {
    if (window.__wxPhoneFrame) return;

    /* ---- 状态栏 DOM（深色图标，浅色 App 主题） ---- */
    const sb = document.createElement('div');
    sb.id = 'ios-statusbar';
    sb.innerHTML =
        '<span class="sb-time">9:41</span>' +
        '<span class="sb-left-icon"></span>' +
        '<span class="sb-island">' +
        '  <span class="sb-island-app"></span>' +
        '  <span class="sb-recdot"><i></i></span>' +
        '</span>' +
        '<span class="sb-right">' +
        '  <span class="sb-signal">' +
        '    <i style="height:5px"></i><i style="height:7px"></i>' +
        '    <i style="height:9px"></i><i style="height:11px"></i>' +
        '  </span>' +
        '  <span class="sb-cell5g">5G</span>' +
        '  <span class="sb-wifi">' +
        '    <svg viewBox="0 0 16 12" width="17" height="13" aria-hidden="true">' +
        '      <g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">' +
        '        <path d="M1.7 4.4a9.3 9.3 0 0 1 12.6 0"/>' +
        '        <path d="M4.5 6.9a5.6 5.6 0 0 1 7 0"/>' +
        '        <path d="M7.1 9.3a2.3 2.3 0 0 1 1.8 0"/>' +
        '      </g>' +
        '      <circle cx="8" cy="11" r="1.2" fill="currentColor"/>' +
        '    </svg>' +
        '  </span>' +
        '  <span class="sb-batt-cell">' +
        '    <span class="sb-battery-txt">100%</span>' +
        '    <span class="sb-battery">' +
        '      <i class="sb-fill"></i>' +
        '    </span>' +
        '  </span>' +
        '</span>';
    document.body.appendChild(sb);

    /* ---- 左侧定位/静音图标（聊天页状态栏用；主页走 .sb-mute） ---- */
    const leftIconEl = sb.querySelector('.sb-left-icon');
    const LOC_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
        '<path d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>';
    const MUTE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M6.6 9.2a5.4 5.4 0 0 1 10.8 0c0 2.8.8 4.3 1.5 5.3H5.1c.7-1 1.5-2.5 1.5-5.3z"/>' +
        '<path d="M9.5 17.5a1.4 1.4 0 0 0 5 0"/>' +
        '<line x1="4.2" y1="4.2" x2="19.8" y2="19.8"/></svg>';

    /* ---- Home 指示条 ---- */
    const home = document.createElement('div');
    home.id = 'ios-home';
    document.body.appendChild(home);

    /* ---- 四角圆角遮罩 ---- */
    const mask = document.createElement('div');
    mask.id = 'ios-screen-mask';
    document.body.appendChild(mask);

    /* ---- 状态栏时钟：默认 18:36（参考图像素级复刻）。
       可由 __wxPhoneFrame.setTime() 覆盖（enhance/config.js 应用场景时同步
       「历史会话」最后时刻，与开场锁屏时钟对齐）；转账场景仍固定 03:14。 ---- */
    const timeEl = sb.querySelector('.sb-time');
    const TRANSFER_TIME = '03:14';
    let baseTime = '18:36';
    let transferScene = false;
    function renderTime() {
        timeEl.textContent = transferScene ? TRANSFER_TIME : baseTime;
    }
    renderTime();

    const batteryFill = sb.querySelector('.sb-fill');
    const batteryTxt = sb.querySelector('.sb-battery-txt');

    /* ---- 转账场景（灵动岛展开：微信绿标 + 录屏红点，时间 03:14） ---- */
    const WECHAT_GREEN_SVG = '<svg viewBox="0 0 36 30" fill="none" aria-hidden="true">' +
        '<path d="M13.2 1.5c-6.6 0-11.9 4.3-11.9 9.6 0 3 1.7 5.6 4.3 7.4l-1.1 3.4 3.9-2.1c1.5.4 3.1.7 4.8.7h.8a8.6 8.6 0 0 1-.4-2.6c0-5 4.9-9 10.9-9h.7c-1-4.2-5.8-7.4-12-7.4z" fill="#1ec862"/>' +
        '<path d="M34.8 18.2c0-4.4-4.5-8-9.9-8s-9.9 3.6-9.9 8 4.5 8 9.9 8c1.4 0 2.7-.2 3.9-.6l3.3 1.8-.9-2.9a7.6 7.6 0 0 0 3.6-6.3z" fill="#1ec862"/>' +
        '<circle cx="7.6" cy="8.6" r="1.2" fill="#0b3d1e"/><circle cx="18.8" cy="8.6" r="1.2" fill="#0b3d1e"/>' +
        '<circle cx="22" cy="16.4" r="1" fill="#0b3d1e"/><circle cx="29.8" cy="16.4" r="1" fill="#0b3d1e"/></svg>';

    /* ---- 对外 API（由 Playwright 调用） ---- */
    window.__wxPhoneFrame = {
        visible: true,
        charging: false,

        /* 设置电量百分比（0~100），填充条同步更新（图标始终为白色） */
        setBattery(pct) {
            pct = Math.max(0, Math.min(100, Math.round(Number(pct) || 100)));
            batteryFill.style.width = pct + '%';
            batteryTxt.textContent = pct + '%';
            batteryFill.classList.toggle('sb-fill-low', pct < 12);
        },

        /* 低电量红条：聊天页参考图电量极低，填充条固定为细红条 */
        setBatteryLow(on) {
            batteryFill.classList.toggle('sb-fill-low', !!on);
            batteryFill.style.width = on ? '' : batteryFill.style.width;
            const b = sb.querySelector('.sb-battery');
            if (b) b.classList.toggle('sb-batt-low', !!on);
        },

        /* 状态栏左侧图标：'' 无 / 'loc' 定位 / 'mute' 静音（聊天页用） */
        setLeftIcon(type) {
            if (!leftIconEl) return;
            if (type === 'loc' || type === 'location') {
                leftIconEl.innerHTML = LOC_SVG;
            } else if (type === 'mute') {
                leftIconEl.innerHTML = MUTE_SVG;
            } else {
                leftIconEl.innerHTML = '';
            }
        },

        /* 保留充电状态标记（不影响白色图标外观，仅作状态记录） */
        setCharging(on) {
            this.charging = !!on;
        },

        /* 状态栏时钟：同步「历史会话」最后时刻（HH:MM）。
           转账场景期间只记录不显示，切回 default 后生效。 */
        setTime(hhmm) {
            const s = String(hhmm || '').trim();
            if (!/^\d{1,2}:\d{2}$/.test(s)) return false;
            baseTime = s;
            if (!transferScene) renderTime();
            return true;
        },

        /* 当前状态栏时钟（转账场景返回其固定的 03:14） */
        getTime() {
            return transferScene ? TRANSFER_TIME : baseTime;
        },

        /* 场景切换：
           'transfer' —— 参考视频《接受转账的画面》：时间 03:14、灵动岛展开
                         （微信绿标 + 录屏红点）、右侧仅信号+电池（无 5G/WiFi）、
                         状态栏加高 61px、满电白电池、隐藏左侧定位图标；
           'default'  —— 恢复默认（常规灵动岛；时间为 setTime 同步值或 18:36）。 */
        setScene(mode) {
            const tf = mode === 'transfer';
            transferScene = tf;
            sb.classList.toggle('sb-scene-tf', tf);
            document.body.classList.toggle('wx-sb-tall', tf);
            renderTime();
            sb.querySelector('.sb-island-app').innerHTML = tf ? WECHAT_GREEN_SVG : '';
            if (tf) {
                this.setBattery(100);
                this.setBatteryLow(false);
                this.setLeftIcon('');
            }
            return true;
        },

        /* 显示整个仿真层 */
        show() {
            this.visible = true;
            sb.style.display = '';
            home.style.display = '';
            mask.style.display = '';
        },

        /* 隐藏整个仿真层 */
        hide() {
            this.visible = false;
            sb.style.display = 'none';
            home.style.display = 'none';
            mask.style.display = 'none';
        },
    };

    /* 电量图标始终为白色（贴合 iPhone 15 非充电状态） */
    window.__wxPhoneFrame.setCharging(false);
})();
