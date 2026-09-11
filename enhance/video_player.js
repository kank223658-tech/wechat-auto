/* ============================================================
   全屏视频播放器（main.py 注入）
   ------------------------------------------------------------
   朋友圈里的视频动态点开后，全屏播放：
     · 深色沉浸背景，视频居中（竖屏画布下横向视频自动上下留黑边）
     · 左上角 ✕ 关闭；点画面暂停/继续（暂停时中央显示播放三角）
     · 底部进度条 + 当前/总时长，随播放实时推进
   对外 API：window.__wxVideo.open(src, {cover}) / close() / isOpen()
            toggle() / seek(秒) / currentTime() / duration()
   ============================================================ */
(() => {
    if (window.__wxVideo) return;

    const root = document.createElement('div');
    root.id = 'wxVideoPlayer';
    root.innerHTML =
        '<video class="wv-video" playsinline preload="auto" x5-video-player-type="h5"></video>' +
        '<span class="wv-pause-mark"></span>' +
        '<span class="wv-close"></span>' +
        '<div class="wv-bar">' +
        '  <span class="wv-time wv-cur">0:00</span>' +
        '  <i class="wv-track"><b class="wv-fill"></b></i>' +
        '  <span class="wv-time wv-dur">0:00</span>' +
        '</div>';
    document.body.appendChild(root);

    const video = root.querySelector('.wv-video');
    const fill = root.querySelector('.wv-fill');
    const curEl = root.querySelector('.wv-cur');
    const durEl = root.querySelector('.wv-dur');
    const closeBtn = root.querySelector('.wv-close');
    const pauseMark = root.querySelector('.wv-pause-mark');

    let rafId = null;
    let opened = false;

    const fmt = (s) => {
        if (!isFinite(s) || s < 0) s = 0;
        const m = Math.floor(s / 60);
        const r = Math.floor(s % 60);
        return m + ':' + (r < 10 ? '0' + r : r);
    };

    function tick() {
        if (!opened) { rafId = null; return; }
        const d = video.duration || 0;
        const t = video.currentTime || 0;
        if (d > 0) fill.style.width = Math.min(100, (t / d) * 100) + '%';
        curEl.textContent = fmt(t);
        if (d > 0) durEl.textContent = fmt(d);
        rafId = requestAnimationFrame(tick);
    }

    function startLoop() {
        if (rafId == null) rafId = requestAnimationFrame(tick);
    }

    function syncPauseMark() {
        pauseMark.classList.toggle('show', opened && video.paused);
    }

    function tryPlay() {
        const p = video.play();
        if (p && typeof p.catch === 'function') {
            p.catch(() => {
                // 自动播放被拦（带声）→ 静音再播，保证画面动起来
                video.muted = true;
                const q = video.play();
                if (q && typeof q.catch === 'function') q.catch(() => {});
            });
        }
    }

    function open(src, opts) {
        if (!src) return false;
        opts = opts || {};
        opened = true;
        video.muted = false;
        video.loop = !!opts.loop;
        if (opts.cover) video.poster = opts.cover;
        video.src = src;
        curEl.textContent = '0:00';
        durEl.textContent = '0:00';
        fill.style.width = '0%';
        root.classList.add('wv-open');
        tryPlay();
        startLoop();
        syncPauseMark();
        return true;
    }

    function close() {
        if (!opened) return false;
        opened = false;
        if (rafId != null) { cancelAnimationFrame(rafId); rafId = null; }
        try { video.pause(); } catch (e) { /* noop */ }
        root.classList.remove('wv-open');
        pauseMark.classList.remove('show');
        // 释放视频纹理与网络占用：清空 src 后重新 load
        try {
            video.removeAttribute('src');
            video.load();
        } catch (e) { /* noop */ }
        return true;
    }

    function toggle() {
        if (!opened) return false;
        if (video.paused) tryPlay(); else video.pause();
        syncPauseMark();
        return !video.paused;
    }

    closeBtn.addEventListener('click', (e) => { e.stopPropagation(); close(); });
    video.addEventListener('click', (e) => { e.stopPropagation(); toggle(); });
    video.addEventListener('ended', () => { syncPauseMark(); });
    video.addEventListener('play', () => syncPauseMark());
    video.addEventListener('pause', () => syncPauseMark());
    video.addEventListener('loadedmetadata', () => {
        durEl.textContent = fmt(video.duration || 0);
    });
    root.addEventListener('click', (e) => {
        // 点击视频以外的空白区域也关闭，贴近真机「轻点返回」
        if (e.target === root) close();
    });

    window.__wxVideo = {
        open,
        close,
        toggle,
        isOpen() { return opened; },
        isPaused() { return !!video.paused; },
        currentTime() { return video.currentTime || 0; },
        duration() { return video.duration || 0; },
        seek(t) { try { video.currentTime = Number(t) || 0; } catch (e) { /* noop */ } return true; },
    };
})();
