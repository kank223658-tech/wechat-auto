/* ============================================================
   真人行为增强层（main.py 注入）
   ------------------------------------------------------------
   1. imageViewer：全屏图片查看器，模拟真人「点开放大→手抖→
      停留→点击关掉」。放大动画在 .iv-stage，手抖在 .iv-img。
   2. peerTyping：对方消息「正在输入…」逐字打出（含打错回退），
      由 Python 逐字驱动。
   幂等，可反复调用。
   ============================================================ */
(() => {
    if (window.__wxHuman) return;

    /* 图片查看器 DOM（样式见 human_actions.css 的 #imageViewer） */
    const viewer = document.createElement('div');
    viewer.id = 'imageViewer';
    viewer.innerHTML =
        '<div class="iv-backdrop"></div>' +
        '<div class="iv-stage"><img class="iv-img" alt="" draggable="false"></div>' +
        '<span class="iv-caption">轻点关闭</span>';
    document.body.appendChild(viewer);

    const ivImg = viewer.querySelector('.iv-img');
    const ivStage = viewer.querySelector('.iv-stage');
    let currentImg = '';
    let closeTimer = null;

    /* ---- 真人式捏合缩放引擎：快速放大→细看微抖 ----
       不做匀速循环，而是像真人那样：
       1. 先快速放大（ease-out，带一点「冲过头再稳住」的手感），直奔想看清的点；
       2. 然后**慢慢调整细节**：围绕目标做 6~9 次极轻微的手抖（幅度小、节奏慢、原点和缩放都在微小游走）；
       3. 再停一小会儿「确认细节」；动画停在放大观察态，缩小关闭交给 closeImage。
       每次幅度 / 时长 / 聚焦点 / 抖动次数都随机；传 focus 则锚定在该点放大。 */
    let pinchRAF = null;
    let pinchStop = false;
    let activeFocus = null;    // 本次放大聚焦点（{x,y} 0~1；null=随机挑点）
    let lastScale = 1, lastOx = 0.5, lastOy = 0.5;  // 最后一次放大定格的状态，供「缩小退出」从当前状态开始
    let closeRAF = null;        // 「缩小退出」动画帧句柄（关闭/重新打开时需取消）
    let openDelayTimer = null;  // 「点开→放大」之间的停顿定时器（先完整打开图片再放大）
    const rnd = (a, b) => a + Math.random() * (b - a);
    const clampv = (v, a, b) => Math.min(b, Math.max(a, v));
    const easeOutCubic = (x) => 1 - Math.pow(1 - x, 3);
    const easeInOutCubic = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
    // 默认放大倍率：未指定时（如手动点击缩略图）捏合放大到的目标倍率。
    // 主动调用 openImage(src, null, {zoom}) 时会另有传入值覆盖它；
    // 全局默认值由 main.py 的 IMAGE_ZOOM_DEFAULT 每次注入时传下来。
    const DEFAULT_ZOOM = 1.6;
    const ZOOM_MIN = 1.0;     // 最小倍率（≈1 即回到原大，不再放大）
    const ZOOM_MAX = 4.5;     // 上限，防止倍率误设过大
    let pinchZoomDefault = DEFAULT_ZOOM;   // 可被 setZoomDefault() 覆盖
    // 解析「打开后放大到哪个位置」：支持 {x,y} 或 "x,y"（0~1），非法返回 null（走随机）
    function parseFocus(f) {
        if (f == null) return null;
        let x, y;
        if (typeof f === 'object') {
            x = Number(f.x); y = Number(f.y);
        } else if (typeof f === 'string') {
            const p = f.split(',');
            x = Number(p[0]); y = Number(p[1]);
        } else {
            return null;
        }
        if (!isFinite(x) || !isFinite(y)) return null;
        return { x: clampv(x, 0.03, 0.97), y: clampv(y, 0.03, 0.97) };
    }

    function buildPinchSeq(focus, zoom) {
        const seq = [];
        // 锚点：有焦点用焦点，否则随机挑一个「想看清的点」
        const ax = focus ? focus.x : rnd(0.30, 0.70);
        const ay = focus ? focus.y : rnd(0.32, 0.68);
        // 放大倍率：传了 zoom 就按它（只加 ±1% 随机手感，尽量贴近用户设定值）；
        // 没传（手动点图）则用默认倍率 pinchZoomDefault，仍带一点随机更有"真人感"。
        let target;
        if (zoom != null && isFinite(zoom) && zoom >= ZOOM_MIN) {
            target = clampv(zoom * rnd(0.99, 1.01), ZOOM_MIN, ZOOM_MAX);
        } else {
            target = clampv(pinchZoomDefault * rnd(0.97, 1.05), ZOOM_MIN, ZOOM_MAX);
        }

        // 1) 快速放大：真人先猛拉一把看清大概，略微冲过头再稳下来
        const over = target * (1 + rnd(0.02, 0.05));   // 冲过头一丢丢（更有人味儿）
        seq.push({ kind: 'in', s0: 1, s1: over, ox0: 0.5, oy0: 0.5, ox1: ax, oy1: ay,
                   dur: rnd(240, 400), ease: easeOutCubic });      // 快
        seq.push({ kind: 'hold', s0: over, s1: target,
                   ox0: ax, oy0: ay,
                   ox1: clampv(ax + rnd(-0.01, 0.01), 0.03, 0.97),
                   oy1: clampv(ay + rnd(-0.01, 0.01), 0.03, 0.97),
                   dur: rnd(160, 300), ease: easeInOutCubic });    // 回到目标，手稳下来

        // 2) 细看：真人最多小幅调整一两下（1~2 次），每次放慢、幅度轻柔，围绕目标小幅游走
        let cx = ax, cy = ay, cs = target;
        const jitterN = 1 + Math.floor(Math.random() * 2);     // 1~2 次，不一直抖
        for (let i = 0; i < jitterN; i++) {
            const ns = target * (1 + rnd(-0.014, 0.014));          // 缩放微抖（幅度更轻）
            const nx = clampv(cx + rnd(-0.018, 0.018), 0.03, 0.97); // 原点微移
            const ny = clampv(cy + rnd(-0.018, 0.018), 0.03, 0.97);
            seq.push({ kind: 'hold', s0: cs, s1: ns, ox0: cx, oy0: cy, ox1: nx, oy1: ny,
                       dur: rnd(220, 450), ease: easeInOutCubic });  // 放慢，像真人稳住细看
            cx = nx; cy = ny; cs = ns;
        }

        // 3) 停一小会儿确认细节（保持当前放大状态，不缩回；缩小交给「关闭」动作）
        seq.push({ kind: 'hold', s0: cs, s1: cs, ox0: cx, oy0: cy, ox1: cx, oy1: cy,
                   dur: rnd(320, 720), ease: (x) => x });
        return seq;
    }

    let pinchSeq = [];
    let pinchIdx = 0;
    let pinchT0 = 0;
    let _lastPinchMs = 0;      // 本次缩放动画总时长（供 Python 等它播完再关闭）
    function pinchLoop() {
        if (pinchStop) { pinchRAF = null; return; }
        const now = performance.now();
        let elapsed = now - pinchT0;
        let seg = pinchSeq[pinchIdx];
        if (elapsed >= seg.dur) {                 // 本段结束 → 下一段
            pinchIdx++;
            if (pinchIdx >= pinchSeq.length) {    // 全部看完 → 停在最后的放大观察态（缩小交给 closeImage）
                pinchRAF = null;
                return;
            }
            pinchT0 = now;
            elapsed = 0;
            seg = pinchSeq[pinchIdx];
        }
        const k = Math.min(1, elapsed / seg.dur);
        const e = seg.ease(k);
        const W = Math.max(ivImg.offsetWidth, 40);
        const H = Math.max(ivImg.offsetHeight, 40);
        const scale = seg.s0 + (seg.s1 - seg.s0) * e;
        const ox = seg.ox0 + (seg.ox1 - seg.ox0) * e;
        const oy = seg.oy0 + (seg.oy1 - seg.oy0) * e;
        lastScale = scale; lastOx = ox; lastOy = oy;   // 记住当前定格状态
        const tx = W * (0.5 - ox);
        const ty = H * (0.5 - oy);
        ivImg.style.transformOrigin = (ox * 100) + '% ' + (oy * 100) + '%';
        ivImg.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
        pinchRAF = requestAnimationFrame(pinchLoop);
    }
    function kickOffPinch(focus, delayMs = 0, zoom = null) {
        pinchStop = false;
        activeFocus = parseFocus(focus);
        if (pinchRAF) cancelAnimationFrame(pinchRAF);
        if (closeRAF) { cancelAnimationFrame(closeRAF); closeRAF = null; }   // 取消可能还在进行的缩小退出
        if (openDelayTimer) { clearTimeout(openDelayTimer); openDelayTimer = null; }
        pinchSeq = buildPinchSeq(activeFocus, zoom);
        _lastPinchMs = pinchSeq.reduce((s, x) => s + x.dur, 0);
        pinchIdx = 0;
        const start = () => {
            openDelayTimer = null;
            pinchStop = false;
            pinchT0 = performance.now();
            pinchRAF = requestAnimationFrame(pinchLoop);
        };
        if (delayMs > 0) {
            openDelayTimer = setTimeout(start, delayMs);   // 点开停顿：先完整打开图片，再开始放大
        } else {
            start();
        }
    }
    function stopPinch(resetTransform = true) {
        pinchStop = true;
        if (pinchRAF) cancelAnimationFrame(pinchRAF);
        pinchRAF = null;
        if (openDelayTimer) { clearTimeout(openDelayTimer); openDelayTimer = null; }   // 取消未开始的放大
        if (resetTransform) {
            ivImg.style.transformOrigin = '50% 50%';
            ivImg.style.transform = '';
            lastScale = 1; lastOx = 0.5; lastOy = 0.5;
        }
    }
    function startPinch(focus, delayMs, zoom) { kickOffPinch(focus, delayMs, zoom); }

    /* 点击遮罩关闭图片查看器：从当前放大状态快速捏合缩小，直接退出，不再回到原图 */
    function closeViewer() {
        if (!viewer.classList.contains('iv-open')) return;
        clearTimeout(closeTimer);
        if (closeRAF) cancelAnimationFrame(closeRAF);
        stopPinch(false);                        // 保留当前放大态作为缩小起点
        ivStage.classList.remove('iv-zoom-in', 'iv-zoom-out');
        // 快速缩小退出：从当前放大状态直接缩下去（scale→0），同时整层淡出，像真人双指一捏
        const s0 = lastScale, ox0 = lastOx, oy0 = lastOy;
        const ox1 = clampv(ox0 + rnd(-0.04, 0.04), 0.03, 0.97);
        const oy1 = clampv(oy0 + rnd(-0.04, 0.04), 0.03, 0.97);
        const dur = rnd(170, 260);               // 很快，像真人双指一捏
        const t0 = performance.now();
        viewer.style.transition = 'none';        // 关掉过渡，逐帧驱动透明
        function step() {
            const k = Math.min(1, (performance.now() - t0) / dur);
            const e = easeOutCubic(k);
            const scale = s0 + (0.0 - s0) * e;
            const ox = ox0 + (ox1 - ox0) * e;
            const oy = oy0 + (oy1 - oy0) * e;
            const W = Math.max(ivImg.offsetWidth, 40);
            const H = Math.max(ivImg.offsetHeight, 40);
            ivImg.style.transformOrigin = (ox * 100) + '% ' + (oy * 100) + '%';
            ivImg.style.transform = 'translate(' + (W * (0.5 - ox)) + 'px,' + (H * (0.5 - oy)) + 'px) scale(' + scale + ')';
            viewer.style.opacity = String(1 - e);
            if (k < 1) { closeRAF = requestAnimationFrame(step); return; }
            // 结束：隐藏查看器并复位
            closeRAF = null;
            viewer.style.transition = '';
            viewer.style.opacity = '';
            viewer.style.visibility = '';
            ivImg.style.transform = '';
            ivImg.style.transformOrigin = '50% 50%';
            // 释放解压后的图片纹理：清空 src 让浏览器 drop 那张大图(否则纹理+合成层长期驻留，
            // 会拖住「点击输入框后键盘弹出」等下一段动画的首帧，造成卡顿/掉帧)。
            ivImg.removeAttribute('src');
            // display:none 把查看器整个从渲染树拿掉，强制回收它的合成层。
            // 光靠 visibility:hidden 元素仍在渲染树中，之前放大过的图层不会立刻释放，
            // 会持续拖住「键盘弹出」等后续动画的首帧。（下一步打开时由 openImage 恢复 display）
            viewer.style.display = 'none';
            lastScale = 1; lastOx = 0.5; lastOy = 0.5;
            viewer.classList.remove('iv-open', 'iv-visible');
        }
        closeRAF = requestAnimationFrame(step);
    }
    viewer.addEventListener('click', (e) => {
        if (e.target === viewer || e.target.classList.contains('iv-backdrop')) {
            closeViewer();
        }
    });

    window.__wxHuman = {
        /* 打开图片查看器：src=图片路径；opts 可选：
             focus   {x,y} 或 "x,y"，指定放大聚焦点；
             zoom    放大倍率数字（如 2.0），缺省用全局默认倍率；
             noZoom  true 表示「只点开不放大」——打开到原图完整大小，不启动捏合放大。
           返回 true 表示已打开 */
        openImage(src, label, opts) {
            if (!src) return false;
            opts = opts || {};
            /* 恢复 display（上次关闭时 display:none 彻底卸载了查看器，强制释放合成层；
               再次打开时先恢复显示，否则 .iv-img src / 开场动画不会渲染） */
            viewer.style.display = '';
            const focus = parseFocus(opts.focus);
            const zoom = (opts.zoom == null || opts.zoom === "") ? null : Number(opts.zoom);
            const noZoom = !!opts.noZoom;
            currentImg = src;
            clearTimeout(closeTimer);
            if (closeRAF) { cancelAnimationFrame(closeRAF); closeRAF = null; }   // 重新打开时取消缩小退出
            ivImg.src = src;
            viewer.classList.add('iv-visible');
            // 先清零再强制 reflow，保证开场动画每次都重新播放
            ivStage.classList.remove('iv-zoom-in');
            void ivStage.offsetWidth;
            ivStage.classList.add('iv-zoom-in');
            viewer.classList.add('iv-open');
            if (label) ivImg.setAttribute('alt', label);
            // 点开：先把图片复位到完整显示（配合 .iv-zoom-in 开场放大动画）
            stopPinch(true);
            if (noZoom) {
                // 只点开不放大：停留在完整原图大小，不启动捏合放大（关闭交给 closeImage）
                _lastPinchMs = 0;
                return true;
            }
            // 等一个「点开」停顿（320~460ms）后再开始捏合放大 —— 先看见完整图片，再放大，更接近真人。
            startPinch(focus, rnd(320, 460), zoom);
            return true;
        },

        /* 设置全局默认放大倍率（main.py 的 IMAGE_ZOOM_DEFAULT 注入时调用） */
        setZoomDefault(z) {
            const v = Number(z);
            if (isFinite(v) && v > ZOOM_MIN) pinchZoomDefault = clampv(v, ZOOM_MIN, ZOOM_MAX);
        },

        closeImage() { closeViewer(); return true; },

        isImageOpen() { return viewer.classList.contains('iv-open'); },

        currentImage() { return currentImg; },

        /* 最近一次「放大细看」动画的总时长（毫秒），Python 用它确保动画播完再关闭 */
        lastPinchMs() { return _lastPinchMs; },
    };

    /* 可点开的图片：聊天气泡 + 对方朋友圈配图 / 主页缩略图。
       我的朋友圈（.moments__post）用自带的 PhotoSwipe 查看器，这里不重复绑定，避免双查看器冲突。
       视频封面（[data-wx-video-src]）由 peer_pages.js / moments_extra.js 自己绑定「播放视频」，这里跳过。 */
    const CLICKABLE_IMG_SELECTOR = [
        '.msg-image img',
        '#wxPeerMoments .wpm-imgs img',
        '#wxPeerProfile .wpp-thumbs img',
    ].join(',');

    /* 给图片绑定点击事件：点击即打开全屏查看器。
       这样「查看图片」动作即使不显式调用 openImage，也能由真实点击驱动。 */
    function bindImageClicks() {
        document.querySelectorAll(CLICKABLE_IMG_SELECTOR).forEach((img) => {
            if (img.dataset.wxHumanBound) return;
            if (img.dataset.wxVideoSrc || img.closest('[data-wx-video-src]')) return; // 视频封面：交给视频播放
            img.dataset.wxHumanBound = '1';
            img.style.cursor = 'zoom-in';
            img.addEventListener('click', (e) => {
                e.stopPropagation();
                window.__wxHuman.openImage(img.currentSrc || img.src);
            });
        });
    }
    const mo = new MutationObserver(bindImageClicks);
    mo.observe(document.body, { childList: true, subtree: true });
    bindImageClicks();
})();
