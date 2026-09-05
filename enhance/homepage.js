/* ============================================================
   首页像素级增强注入（配合 enhance/homepage_exact.css）
   ------------------------------------------------------------
   在录屏页面上补充规格里需要、但 Vue 组件不会渲染/隐藏掉的结构：
     1. 状态栏静音图标  #ios-statusbar .sb-mute（系统级，常驻）
     2. 标题栏右侧加号  #wx-home-plus（仅主页，route=/#/）
     3. 右侧悬浮胶囊    #wx-home-pill（仅主页，被屏幕右缘裁切）

   全部幂等：重复调用不会重复插入。加号与胶囊在非主页时隐藏，
   避免录屏切到聊天/朋友圈页后残留。
   ============================================================ */
(() => {
    if (window.__wxHomeEnhanced) return;
    window.__wxHomeEnhanced = true;

    /* ---- 状态栏静音图标：插入到 iphone_frame.js 创建好的 #ios-statusbar ---- */
    const addStatusbarMute = () => {
        let sb = document.getElementById('ios-statusbar');
        if (!sb) return null;
        if (sb.querySelector('.sb-mute')) return sb.querySelector('.sb-mute');
        let mute = document.createElement('span');
        mute.className = 'sb-mute';
        mute.innerHTML =
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '  <path d="M6.6 9.2a5.4 5.4 0 0 1 10.8 0c0 2.8.8 4.3 1.5 5.3H5.1c.7-1 1.5-2.5 1.5-5.3z"/>' +
            '  <path d="M9.5 17.5a1.4 1.4 0 0 0 5 0"/>' +
            '  <line x1="4.2" y1="4.2" x2="19.8" y2="19.8"/>' +
            '</svg>';
        // 放在时间右侧（spec 左 136）
        sb.appendChild(mute);
        return mute;
    };

    /* ---- 标题栏加号按钮 ---- */
    const addHomePlus = () => {
        if (document.getElementById('wx-home-plus')) return document.getElementById('wx-home-plus');
        let plus = document.createElement('span');
        plus.id = 'wx-home-plus';
        document.body.appendChild(plus);
        return plus;
    };

    /* ---- 右侧悬浮胶囊（三点） ---- */
    const addHomePill = () => {
        if (document.getElementById('wx-home-pill')) return document.getElementById('wx-home-pill');
        let pill = document.createElement('span');
        pill.id = 'wx-home-pill';
        pill.innerHTML = '<i></i><i></i><i></i>';
        document.body.appendChild(pill);
        return pill;
    };

    /* ---- 主页可见性：仅当路由为 /#/ 时显示加号与胶囊 ---- */
    const isHome = () => {
        // 优先读 Vue 实例的当前路由
        try {
            const root = document.getElementById('app');
            const vm = root && root.__vue__;
            if (vm && vm.$route) return vm.$route.path === '/';
        } catch (e) { /* 忽略 */ }
        const h = location.hash;
        return h === '' || h === '#' || h === '#/' || h === '#/index';
    };
    const applyVisibility = () => {
        const home = isHome();
        const plus = document.getElementById('wx-home-plus');
        const pill = document.getElementById('wx-home-pill');
        if (plus) plus.style.display = home ? '' : 'none';
        if (pill) pill.style.display = home ? '' : 'none';
    };

    /* ---- 注入 + 监听路由变化（hashchange + Vue afterEach + 兜底轮询） ---- */
    addStatusbarMute();
    addHomePlus();
    addHomePill();
    applyVisibility();
    window.addEventListener('hashchange', applyVisibility);

    // Vue 路由可能会改变 location.hash 而不总是触发 hashchange，注册 afterEach 更稳
    const tryHook = () => {
        const root = document.getElementById('app');
        const vm = root && root.__vue__;
        if (vm && vm.$router && !vm.$router.__wxHomeHooked) {
            vm.$router.__wxHomeHooked = true;
            vm.$router.afterEach(() => applyVisibility());
        }
    };
    tryHook();
    setInterval(tryHook, 500);
    setInterval(applyVisibility, 700);

    window.__wxHomeEnhanced = true;
})();
