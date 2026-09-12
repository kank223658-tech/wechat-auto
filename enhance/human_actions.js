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
    let flyRAF = null;          // 「从缩略图飞入」动画帧句柄
    let activeAnchor = null;    // 本次打开的来源缩略图矩形（关闭时飞回原位）
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

    /* ---- 共享元素锚点：像真微信一样，打开时从聊天里的缩略图原位飞入，
       关闭时捏合飞回缩略图原位（而不是从屏幕中央凭空弹出/缩成一个点） ---- */
    function _normUrl(u) {
        try { return decodeURIComponent(String(u || '').split('?')[0].split('#')[0]); } catch (e) { return String(u || ''); }
    }
    /* 在当前画面里找 src 对应的可见缩略图，返回它的视口矩形（找不到返回 null） */
    function findAnchorRect(src) {
        const target = _normUrl(src);
        if (!target) return null;
        const file = target.split('/').pop();
        let best = null;
        document.querySelectorAll('img').forEach((im) => {
            const r = im.getBoundingClientRect();
            if (r.width < 10 || r.height < 10) return;
            const cs = getComputedStyle(im);
            if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return;
            const u = _normUrl(im.currentSrc || im.src);
            // 完整 URL 相等即可；文件名兜底只限聊天/对方主页/对方朋友圈这几个可信容器
            const hit = (u === target) ||
                (u.endsWith(file) && im.closest('.msg-image, #wxPeerMoments, #wxPeerProfile'));
            if (!hit) return;
            const area = r.width * r.height;
            if (!best || area > best.area) best = { r, area };
        });
        return best ? best.r : null;
    }
    /* 图片从缩略图位置飞入查看器原位；返回 false 表示布局未就绪（调用方走居中弹出兜底） */
    function flyInFrom(anchor) {
        const T = ivImg.getBoundingClientRect();
        if (T.width < 8 || T.height < 8) return false;
        const s0 = clampv(anchor.width / T.width, 0.05, 1);
        const dx0 = (anchor.left + anchor.width / 2) - (T.left + T.width / 2);
        const dy0 = (anchor.top + anchor.height / 2) - (T.top + T.height / 2);
        const dur = rnd(280, 360);
        const t0 = performance.now();
        ivImg.style.transformOrigin = '50% 50%';
        function step() {
            const k = Math.min(1, (performance.now() - t0) / dur);
            const e = easeOutCubic(k);
            const s = s0 + (1 - s0) * e;
            ivImg.style.transform = 'translate(' + (dx0 * (1 - e)) + 'px,' + (dy0 * (1 - e)) + 'px) scale(' + s + ')';
            if (k < 1) { flyRAF = requestAnimationFrame(step); return; }
            flyRAF = null;
            ivImg.style.transform = '';
            lastScale = 1; lastOx = 0.5; lastOy = 0.5;
        }
        flyRAF = requestAnimationFrame(step);
        return true;
    }
    /* 等图片完成布局（缓存命中立即回调；否则等 load，超时兜底） */
    function whenImgLaidOut(cb) {
        if (ivImg.complete && ivImg.naturalWidth > 0) { cb(); return; }
        let done = false;
        const go = () => { if (done) return; done = true; cb(); };
        ivImg.addEventListener('load', go, { once: true });
        ivImg.addEventListener('error', go, { once: true });
        setTimeout(go, 300);
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
        //    （手指捏合总会带一点无意识的微旋转，rot 记录这个手感）
        const over = target * (1 + rnd(0.02, 0.05));   // 冲过头一丢丢（更有人味儿）
        const r1 = rnd(-0.3, 0.3);                     // 拉一把时的微旋转
        seq.push({ kind: 'in', s0: 1, s1: over, ox0: 0.5, oy0: 0.5, ox1: ax, oy1: ay,
                   rot0: 0, rot1: r1,
                   dur: rnd(240, 400), ease: easeOutCubic });      // 快
        seq.push({ kind: 'hold', s0: over, s1: target,
                   ox0: ax, oy0: ay,
                   ox1: clampv(ax + rnd(-0.01, 0.01), 0.03, 0.97),
                   oy1: clampv(ay + rnd(-0.01, 0.01), 0.03, 0.97),
                   rot0: r1, rot1: rnd(-0.12, 0.12),
                   dur: rnd(160, 300), ease: easeInOutCubic });    // 回到目标，手稳下来

        // 2) 细看：真人最多小幅调整一两下（1~2 次），每次放慢、幅度轻柔，围绕目标小幅游走
        let cx = ax, cy = ay, cs = target, cr = seq[seq.length - 1].rot1;
        const jitterN = 1 + Math.floor(Math.random() * 2);     // 1~2 次，不一直抖
        for (let i = 0; i < jitterN; i++) {
            const ns = target * (1 + rnd(-0.014, 0.014));          // 缩放微抖（幅度更轻）
            const nx = clampv(cx + rnd(-0.018, 0.018), 0.03, 0.97); // 原点微移
            const ny = clampv(cy + rnd(-0.018, 0.018), 0.03, 0.97);
            const nr = rnd(-0.2, 0.2);                             // 微旋转游走
            seq.push({ kind: 'hold', s0: cs, s1: ns, ox0: cx, oy0: cy, ox1: nx, oy1: ny,
                       rot0: cr, rot1: nr,
                       dur: rnd(220, 450), ease: easeInOutCubic });  // 放慢，像真人稳住细看
            cx = nx; cy = ny; cs = ns; cr = nr;
        }

        // 3) 停一小会儿确认细节（保持当前放大状态，转正归零，缩小交给「关闭」动作）
        seq.push({ kind: 'hold', s0: cs, s1: cs, ox0: cx, oy0: cy, ox1: cx, oy1: cy,
                   rot0: cr, rot1: 0,
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
        const rot = (seg.rot0 || 0) + ((seg.rot1 || 0) - (seg.rot0 || 0)) * e;   // 手指微旋转
        lastScale = scale; lastOx = ox; lastOy = oy;   // 记住当前定格状态
        const tx = W * (0.5 - ox);
        const ty = H * (0.5 - oy);
        ivImg.style.transformOrigin = (ox * 100) + '% ' + (oy * 100) + '%';
        ivImg.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')' +
            (rot ? ' rotate(' + rot.toFixed(3) + 'deg)' : '');
        pinchRAF = requestAnimationFrame(pinchLoop);
    }
    function kickOffPinch(focus, delayMs = 0, zoom = null) {
        pinchStop = false;
        activeFocus = parseFocus(focus);
        if (pinchRAF) cancelAnimationFrame(pinchRAF);
        if (closeRAF) { cancelAnimationFrame(closeRAF); closeRAF = null; }   // 取消可能还在进行的缩小退出
        if (openDelayTimer) { clearTimeout(openDelayTimer); openDelayTimer = null; }
        // 注意：飞入动画（flyRAF）不能在这里取消——延迟只是「点开停顿」，
        // 提前取消会把还没播完的飞入杀掉（图片已缓存时 whenImgLaidOut 同步回调，flyRAF 刚启动）。
        pinchSeq = buildPinchSeq(activeFocus, zoom);
        _lastPinchMs = pinchSeq.reduce((s, x) => s + x.dur, 0);
        pinchIdx = 0;
        const start = () => {
            openDelayTimer = null;
            pinchStop = false;
            if (flyRAF) { cancelAnimationFrame(flyRAF); flyRAF = null; ivImg.style.transform = ''; }   // 飞入仍未结束才归位
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
        if (flyRAF) { cancelAnimationFrame(flyRAF); flyRAF = null; }
        if (openDelayTimer) { clearTimeout(openDelayTimer); openDelayTimer = null; }   // 取消未开始的放大
        if (resetTransform) {
            ivImg.style.transformOrigin = '50% 50%';
            ivImg.style.transform = '';
            lastScale = 1; lastOx = 0.5; lastOy = 0.5;
        }
    }
    function startPinch(focus, delayMs, zoom) { kickOffPinch(focus, delayMs, zoom); }

    /* 点击遮罩关闭图片查看器：
       有锚点（打开时来自缩略图）→ 从当前放大状态捏合飞回缩略图原位，背景同步淡出（真微信手感）；
       无锚点 → 从当前放大状态快速捏合缩小淡出。 */
    function closeViewer() {
        if (!viewer.classList.contains('iv-open')) return;
        clearTimeout(closeTimer);
        if (closeRAF) cancelAnimationFrame(closeRAF);
        if (flyRAF) { cancelAnimationFrame(flyRAF); flyRAF = null; }
        stopPinch(false);                        // 保留当前放大态作为缩小起点
        ivStage.classList.remove('iv-zoom-in', 'iv-zoom-out');
        const b0 = viewer.querySelector('.iv-backdrop');
        const finish = () => {
            closeRAF = null;
            viewer.style.transition = '';
            viewer.style.opacity = '';
            viewer.style.visibility = '';
            b0.style.transition = '';
            b0.style.opacity = '';
            ivImg.style.transform = '';
            ivImg.style.transformOrigin = '50% 50%';
            // 释放解压后的图片纹理：清空 src 让浏览器 drop 那张大图(否则纹理+合成层长期驻留，
            // 会拖住「点击输入框后键盘弹出」等下一段动画的首帧，造成卡顿/掉帧)。
            ivImg.removeAttribute('src');
            // display:none 把查看器整个从渲染树拿掉，强制回收它的合成层。
            viewer.style.display = 'none';
            lastScale = 1; lastOx = 0.5; lastOy = 0.5;
            activeAnchor = null;
            viewer.classList.remove('iv-open', 'iv-visible');
            // 退出沉浸：状态栏恢复显示
            const _sb2 = document.getElementById('ios-statusbar');
            if (_sb2) _sb2.classList.remove('sb-iv-hidden');
        };
        // 有锚点：读当前渲染框（带 transform），复位后拿基准框，做「当前框 → 缩略图框」的飞回
        if (activeAnchor) {
            const cur = ivImg.getBoundingClientRect();      // 当前视觉矩形（含放大/平移）
            ivImg.style.transform = '';
            ivImg.style.transformOrigin = '50% 50%';
            const T0 = ivImg.getBoundingClientRect();       // 未变换基准框
            if (T0.width > 8 && T0.height > 8 && cur.width > 4) {
                const sA = cur.width / T0.width;
                const txA = cur.left - T0.left, tyA = cur.top - T0.top;
                const sB = clampv(activeAnchor.width / T0.width, 0.05, 1);
                const txB = activeAnchor.left - T0.left, tyB = activeAnchor.top - T0.top;
                const dur = rnd(240, 320);                  // 像真人双指一捏收回去
                const t0 = performance.now();
                viewer.style.transition = 'none';
                viewer.style.opacity = '1';
                viewer.style.visibility = 'visible';
                b0.style.transition = 'none';
                b0.style.opacity = '1';
                void b0.offsetWidth;
                b0.style.transition = 'opacity ' + Math.round(dur) + 'ms ease';
                b0.style.opacity = '0';
                ivImg.style.transformOrigin = '0 0';
                function step() {
                    const k = Math.min(1, (performance.now() - t0) / dur);
                    const e = easeInOutCubic(k);
                    const s = sA + (sB - sA) * e;
                    const tx = txA + (txB - txA) * e;
                    const ty = tyA + (tyB - tyA) * e;
                    ivImg.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + s + ')';
                    if (k < 1) { closeRAF = requestAnimationFrame(step); return; }
                    finish();
                }
                closeRAF = requestAnimationFrame(step);
                return;
            }
            activeAnchor = null;   // 布局异常 → 退回居中缩小
        }
        // 无锚点：从当前放大状态直接缩下去（scale→0），同时整层淡出
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
            finish();
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
            if (flyRAF) { cancelAnimationFrame(flyRAF); flyRAF = null; }
            ivImg.src = src;
            ivImg.style.transform = '';
            ivImg.style.transformOrigin = '50% 50%';
            // 真机行为：进入图片查看器即全屏沉浸，状态栏（时间/电量）隐藏，关闭时恢复
            const _sb = document.getElementById('ios-statusbar');
            if (_sb) _sb.classList.add('sb-iv-hidden');
            ivStage.classList.remove('iv-zoom-in');
            stopPinch(true);
            if (label) ivImg.setAttribute('alt', label);
            // 共享元素锚点：优先用调用方传入的元素，否则按 src 在画面里找缩略图
            const anchor = (opts.anchorEl && opts.anchorEl.getBoundingClientRect)
                ? opts.anchorEl.getBoundingClientRect() : findAnchorRect(src);
            if (anchor && anchor.width > 4) {
                /* 有锚点 → 真微信式打开：
                   查看器本体立即不透明（飞入的图片不跟着整层渐显），
                   黑背景由 backdrop 自己淡入，图片从缩略图原位飞入。 */
                activeAnchor = anchor;
                viewer.style.transition = 'none';
                viewer.style.opacity = '1';
                viewer.style.visibility = 'visible';
                // backdrop 单独淡入（真微信：图已可见，黑背景渐显压暗画面）
                const b0 = viewer.querySelector('.iv-backdrop');
                b0.style.transition = 'none';
                b0.style.opacity = '0';
                void b0.offsetWidth;
                b0.style.transition = 'opacity 300ms ease';
                b0.style.opacity = '1';
                viewer.classList.add('iv-visible');
                viewer.classList.add('iv-open');
                whenImgLaidOut(() => {
                    if (currentImg !== src || !viewer.classList.contains('iv-open')) return;
                    if (!flyInFrom(anchor)) ivStage.classList.add('iv-zoom-in');   // 布局兜底：居中弹出
                });
            } else {
                /* 无锚点 → 居中弹出兜底 */
                activeAnchor = null;
                viewer.classList.add('iv-visible');
                void ivStage.offsetWidth;
                ivStage.classList.add('iv-zoom-in');
                viewer.classList.add('iv-open');
            }
            if (noZoom) {
                // 只点开不放大：停留在完整原图大小，不启动捏合放大（关闭交给 closeImage）
                _lastPinchMs = 0;
                return true;
            }
            // 等一个「点开」停顿后再开始捏合放大——先看清完整图片，再放大，更接近真人。
            // 有飞入动画时把停顿排在飞入之后，避免两段动画打架。
            startPinch(focus, anchor ? rnd(420, 560) : rnd(320, 460), zoom);
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
                // 传 anchorEl：精确从被点的缩略图原位飞入（找不到 DOM 里同 src 的图时也能命中）
                window.__wxHuman.openImage(img.currentSrc || img.src, null, { anchorEl: img });
            });
        });
    }
    const mo = new MutationObserver(bindImageClicks);
    mo.observe(document.body, { childList: true, subtree: true });
    bindImageClicks();
})();
