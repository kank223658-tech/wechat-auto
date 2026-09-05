/* ============================================================
   图片发送预览页覆盖层（main.py 注入）
   ------------------------------------------------------------
   复刻微信「发送图片前一步」预览页（参考图）：
   点「+」功能面板后跳过选照片，直接进入本预览页；展示待发图片，
   底部「发送」按钮带按压缩放反馈；点发送后收起覆盖层并回调上屏。
   实现方式对齐转账金额页（display 切换 + fixed inset:0）。

   对外 API（幂等，可反复调用）：
   window.__wxSendImage
     .open(url, onSend)   —— 打开预览页，填充待发图片；自动发送后回调 onSend()
     .close()             —— 直接关闭预览页（不触发发送）
     .isOpen()            —— 当前是否打开
   命名空间要点：单例覆盖层只建一次，.sip-open 控制显示；
   onSend 回调只在「点发送」时触发一次，避免重复上屏。
   ============================================================ */
(() => {
    if (window.__wxSendImage) return;

    /* ---- 构建单例覆盖层 DOM（只建一次） ----
       关键：所有子元素都是 fixed 根的直接子元素（absolute 定位），
       避免用 flex:1 的大容器（该环境中部大容器不合成）。全屏黑图作底板。 */
    const root = document.createElement('div');
    root.id = 'sendImagePreview';
    root.innerHTML =
        '<img class="sip-bg" alt="">' +            // 全屏纯黑底板
        '<div class="sip-flash"></div>' +          // 闪黑幕
        '<div class="sip-top"></div>' +
        '<div class="sip-body"><img class="sip-image" alt=""></div>' +   // 待发图（flex 居中）
        '<div class="sip-bottom"></div>';          // 底栏（"编辑/原图/发送"贴图自带，不叠加按钮）
    document.body.appendChild(root);

    const sipBg = root.querySelector('.sip-bg');
    const sipImage = root.querySelector('.sip-image');
    if (sipBg) sipBg.src = '/images/sendpreview/mid_black.png';   // 全屏黑底板

    let onSendCb = null;   // 点发送时的上屏回调（只触发一次）
    let sendTimer = null;  // 自动发送计时器

    /* 关闭预览页：移除 .sip-open（display 归 none） */
    function close() {
        if (sendTimer) { clearTimeout(sendTimer); sendTimer = null; }
        root.classList.remove('sip-open', 'sip-fading');
    }

    /* 自动发送：收起预览页 -> 回调上屏。 */
    function doSend() {
        if (sendTimer) { clearTimeout(sendTimer); sendTimer = null; }
        const cb = onSendCb;
        onSendCb = null;
        // 收起预览页：直接关闭并回调，不再闪黑（进入预览时的闪黑在 open() 中保留）
        root.classList.remove('sip-open', 'sip-fading');
        if (cb) cb();
    }

    /* ---- 对外 API ---- */
    window.__wxSendImage = {
        /* 打开预览页：url=待发图片路径；onSend=点发送后上屏回调。
           打开后展示图片，约 0.9s 后自动发送（收起 -> 回调上屏）。 */
        open(url, onSend) {
            if (!url) return false;
            onSendCb = typeof onSend === 'function' ? onSend : null;
            // 待发图用 <img> 承载
            sipImage.src = url;
            // 打开预览页：先全黑（闪黑），内容随后显露
            root.classList.remove('sip-open', 'sip-fading');
            void root.offsetWidth;   // 强制 reflow，保证 display 切换生效
            root.classList.add('sip-open');
            // 停留约 0.9s 展示图片后自动发送
            clearTimeout(sendTimer);
            sendTimer = setTimeout(doSend, 900);
            return true;
        },

        /* 直接关闭预览页（不触发发送） */
        close,

        /* 当前是否打开 */
        isOpen() { return root.classList.contains('sip-open'); },
    };
})();