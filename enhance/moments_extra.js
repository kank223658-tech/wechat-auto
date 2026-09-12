/* ============================================================
   朋友圈扩展（main.py 注入）
   ------------------------------------------------------------
   1. renderPosts：按配置数据重建朋友圈动态列表（可编辑朋友圈内容）
   2. openCompose / submit：发朋友圈（发表文字页 + 键盘打字 + 发表）
   ============================================================ */
(() => {
    if (window.__wxMoments) return;

    const me = () => (window.__wxConfig.get().me);
    /* 动态作者头像缺省：用一张确实存在的通用头像，避免 /images/header/* 这类
       已被清空的历史路径导致破图。脚本里给 posts[].avatar 时以脚本为准。 */
    const DEFAULT_POST_AVATAR = '/images/avatar/2_20260831_184618_874.jpg';

    /* ============================================================
       赞 / 评论（复刻参考视频《朋友圈点赞后评论.mp4》）
       ------------------------------------------------------------
       · 「···」→ 深色两格菜单 [♥赞 | 💬评论]：胶囊左侧垂直居中弹出（120ms）
       · 点「赞」：菜单 ~90ms 收起 + 点赞/评论深灰条弹出（蓝心 + 蓝名）
       · 点「评论」：菜单收起 + 底部输入条随键盘一起滑入（打字引擎
         target = 当前聚焦输入框，与聊天打字同一套 __wxKeyboard）
       · 点「发送」：键盘滑出 + 输入条滑出 + 评论「名字：内容」弹进深灰条
       真人点击（bindMenu）与脚本 API（openMenu/tapLike/tapComment/
       submitComment）共用同一套实现，动画完全一致。
       ============================================================ */
    const meName = () => (window.__wxConfig && window.__wxConfig.get().me.name) || '微信用户';

    let commentTargetCell = null;   // 「评论」时记录目标动态；发送时评论进它的深灰条

    /* 脚本序号 -> 动态元素：缺省/空 = 最后一条（兼容旧「给最后一条点赞」语义） */
    function postByIndex(postIndex) {
        const posts = document.querySelectorAll('#moments .moments__post');
        if (!posts.length) return null;
        if (postIndex == null || postIndex === '') return posts[posts.length - 1];
        const i = Math.min(Math.max(1, Number(postIndex) || 1) - 1, posts.length - 1);
        return posts[i];
    }

    /* 命中「赞/评论」后菜单快速收起（~90ms 淡出，真机几乎瞬时消失） */
    function hideMenuFast(menu) {
        if (!menu || !menu.classList.contains('open')) return;
        menu.classList.add('closing');
        setTimeout(() => menu.classList.remove('open', 'closing'), 95);
    }

    /* 点赞/评论深灰条容器（真机：点赞与评论同条），首次出现带弹出动画
       （moment-meta-pop 只在脚本/点击点赞时加，renderPosts 初始渲染不加） */
    function ensureMeta(bd) {
        let meta = bd.querySelector(':scope > .moment-meta');
        if (!meta) {
            meta = document.createElement('div');
            meta.className = 'moment-meta moment-meta-pop';
            bd.appendChild(meta);
            setTimeout(() => meta.classList.remove('moment-meta-pop'), 320);
        }
        return meta;
    }

    function likePost(cell) {
        const bd = cell.querySelector('.weui-cell__bd') || cell;
        const meta = ensureMeta(bd);
        let like = meta.querySelector('.liketext');
        if (!like) {
            like = document.createElement('p');
            like.className = 'liketext';
            like.innerHTML = '<i class="icon icon-96"></i>';
            meta.insertBefore(like, meta.firstChild);
        }
        const nm = meName();
        if (!like.textContent.includes(nm)) {
            const s = document.createElement('span');
            s.className = 'nickname';
            s.textContent = (like.querySelector('.nickname') ? ',' : '') + nm;
            like.appendChild(s);
        }
        const btn = cell.querySelector('.btn-like');
        if (btn) btn.classList.add('liked');
        return true;
    }

    function closeCommentBarSoft() {
        const old = document.getElementById('commentBar');
        if (!old) return;
        if (old.classList.contains('in')) {
            old.classList.remove('in');
            old.classList.add('out');
            setTimeout(() => { if (old.parentNode) old.parentNode.removeChild(old); }, 360);
        } else {
            old.remove();
        }
    }

    /* 点「评论」：底部输入条滑入 + 键盘弹出（同一节奏，复刻真机）
       输入条照搬聊天页打字框：大圆角深色输入框 + 右侧 😊/🖼 图标（无条内发送钮，
       发送=键盘右下蓝键，Enter 由 main.py 统一提交；组合态绿下划线由 keyboard.js 覆盖层绘制）。 */
    const CB_SMILE_SVG =
        '<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">' +
        '<circle cx="24" cy="24" r="20" stroke="#fff" stroke-width="2.6"/>' +
        '<circle cx="17" cy="19.5" r="2.6" fill="#fff"/>' +
        '<circle cx="31" cy="19.5" r="2.6" fill="#fff"/>' +
        '<path d="M14.5 28.5c2.2 3.6 5.5 5.6 9.5 5.6s7.3-2 9.5-5.6" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></svg>';
    const CB_IMG_SVG =
        '<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">' +
        '<rect x="6" y="9" width="36" height="30" rx="5" stroke="#fff" stroke-width="2.6"/>' +
        '<circle cx="17.5" cy="19.5" r="3.4" stroke="#fff" stroke-width="2.4"/>' +
        '<path d="M9 34.5l10.2-9.8c1-1 2.6-1 3.6 0l7.4 7.2 4.2-4c1-1 2.6-1 3.6 0L42 31.6" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    function startComment(cell) {
        closeCommentBarSoft();
        commentTargetCell = cell || null;
        const bar = document.createElement('div');
        bar.id = 'commentBar';
        bar.innerHTML =
            '<div class="cb-way">' +
                '<input id="momentCommentInput" type="text" placeholder="发表评论:">' +
            '</div>' +
            '<span class="cb-ico cb-emoji">' + CB_SMILE_SVG + '</span>' +
            '<span class="cb-ico cb-img">' + CB_IMG_SVG + '</span>';
        document.body.appendChild(bar);
        const input = bar.querySelector('input');
        /* 下一帧滑入（transition 由内嵌 CSS #commentBar 提供，.32s 与键盘同节奏）；
           可见后再聚焦 —— visibility:hidden 的元素拿不到焦点，键盘引擎
           （target = activeElement）也就找不到输入框。 */
        requestAnimationFrame(() => requestAnimationFrame(() => {
            bar.classList.add('in');
            try { input.focus(); } catch (e) { /* noop */ }
            if (window.__wxKeyboard) {
                try { window.__wxKeyboard.show(); } catch (e) { /* noop */ }
            }
        }));
        return true;
    }

    /* 点「发送」：评论「名字：内容」弹进深灰条 + 键盘/输入条一起滑出 */
    function submitComment(forcedText) {
        const input = document.getElementById('momentCommentInput');
        const text = String(forcedText != null ? forcedText :
                            (input && input.value) || '').trim();
        if (!text) return false;
        const cell = commentTargetCell || postByIndex(null);
        if (!cell) return false;
        const bd = cell.querySelector('.weui-cell__bd') || cell;
        const meta = ensureMeta(bd);
        const cp = document.createElement('p');
        cp.className = 'comment-entry comment-pop';
        const b = document.createElement('b');
        b.textContent = meName() + '：';
        cp.appendChild(b);
        cp.appendChild(document.createTextNode(text));
        meta.appendChild(cp);
        if (window.__wxKeyboard) {
            try { window.__wxKeyboard.hide(); } catch (e) { /* noop */ }
        }
        closeCommentBarSoft();
        commentTargetCell = null;
        return true;
    }

    /* ---- 脚本 API：与真人点击同一套动画 ---- */
    function openMenu(postIndex) {
        const cell = postByIndex(postIndex);
        const menu = cell && cell.querySelector('.actionMenu');
        if (!menu) return false;
        if (!menu.classList.contains('open')) menu.classList.add('open');
        return true;
    }
    function tapLike(postIndex) {
        const cell = postByIndex(postIndex);
        if (!cell) return false;
        hideMenuFast(cell.querySelector('.actionMenu'));
        return likePost(cell);
    }
    function tapComment(postIndex) {
        const cell = postByIndex(postIndex);
        if (!cell) return false;
        hideMenuFast(cell.querySelector('.actionMenu'));
        setTimeout(() => startComment(cell), 100);   // 菜单收起后输入条+键盘滑入
        return true;
    }

    /* 动态重建后重新绑定 PhotoSwipe（由 moments.vue 暴露）。
       不重新绑定的话，脚本用 [编辑朋友圈] 插入的图片点不开。 */
    function refreshGallery() {
        if (window.__wxMomentsInitGallery) {
            try { window.__wxMomentsInitGallery(); } catch (e) { /* noop */ }
        }
    }

    /* 解析一条动态里的视频：支持 p.video 为字符串或 {src, cover} 对象 */
    function normalizeVideo(p) {
        const v = p && p.video;
        if (!v) return null;
        if (typeof v === 'string') {
            return { src: v, cover: p.cover || (p.images || [])[0] || '' };
        }
        const src = v.src || v.url || v.path || v.视频 || v.地址 || '';
        if (!src) return null;
        return {
            src: String(src),
            cover: v.cover || v.封面 || v.poster || p.cover || (p.images || [])[0] || '',
        };
    }

    /* 视频缩略图：封面 + 播放角标，点开走全屏播放器。
       外层用 <a data-size> 包住，保持朋友圈自带 PhotoSwipe 解析器不报错；
       点击时 preventDefault + stopPropagation，避免再触发 PhotoSwipe 打开封面图。 */
    function buildVideoThumb(vid) {
        const fig = document.createElement('figure');
        fig.className = 'thumbnail video-thumb';
        const a = document.createElement('a');
        a.className = 'wmp-video-wrap';
        a.href = vid.cover || vid.src;
        a.setAttribute('data-size', '400x400');
        a.setAttribute('data-wx-video-src', vid.src);
        const img = document.createElement('img');
        img.className = 'wmp-video-cover';
        img.alt = 'Video';
        if (vid.cover) img.src = vid.cover;
        const play = document.createElement('span');
        play.className = 'wmp-play';
        a.appendChild(img);
        a.appendChild(play);
        a.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (window.__wxVideo) window.__wxVideo.open(vid.src, { cover: vid.cover });
        });
        fig.appendChild(a);
        return fig;
    }

    /* ---- 配图：真机尺寸回填 + 点开前置加载 ----
       1) PhotoSwipe 4 只用 <a data-size> 决定全屏图的宽高，不会用图片的真实尺寸覆盖它。
          写死 "400x400" 会让全屏大图被压成正方形，而且首帧缩放动画的形状也是错的。
          所以图片加载完就把真实宽高写回 data-size。
       2) 单图按真实宽高比挑裁切档位（对应 moments_exact.css 的 thumb-wide / thumb-ultrawide）。
       3) 视口里出现过的配图，提前把原图拉进浏览器缓存 —— 点开时不再先看到糊掉的缩略图，
          这也是「点开图片很慢」的根因之一。 */
    function bindThumb(a, img, thumbs, single) {
        const apply = () => {
            const nw = img.naturalWidth, nh = img.naturalHeight;
            if (!nw || !nh) return;
            a.setAttribute('data-size', nw + 'x' + nh);
            if (!single) return;
            const r = nw / nh;
            thumbs.classList.toggle('thumb-wide', r > 2.5 && r <= 3);
            thumbs.classList.toggle('thumb-ultrawide', r > 3);
        };
        if (img.complete) apply();
        img.addEventListener('load', apply);
    }

    /* 原图预加载队列（并发 2，避免一次拉爆带宽/内存）
       必须用 fetch 只热 HTTP 缓存，禁止 new Image()：
       new Image() 会把原图按自然尺寸放进解码缓存，Chromium 之后给
       112px object-fit:cover 缩略图光栅化时错误复用这份解码，把贴片
       画成"整图拉伸填充"而非 cover 裁剪（开关大图后幽灵贴片的根源）。 */
    const _pfSeen = new Set();
    let _pfQueue = [], _pfRunning = 0;
    function _pfPump() {
        while (_pfRunning < 2 && _pfQueue.length) {
            const src = _pfQueue.shift();
            _pfRunning++;
            const done = () => { _pfRunning--; _pfPump(); };
            if (typeof fetch !== 'function') { done(); return; }
            fetch(src, { cache: 'force-cache' })
                .then(r => (r && r.ok ? r.blob() : null))
                .then(done, done);
        }
    }
    function prefetchSrc(src) {
        if (!src || _pfSeen.has(src)) return;
        _pfSeen.add(src);
        _pfQueue.push(src);
        _pfPump();
    }
    let _pfObserver = null;
    function prefetchGallery(root) {
        if (!root) return;
        const links = Array.prototype.slice.call(root.querySelectorAll('.my-gallery a[href]'));
        if (!links.length) return;
        if (_pfObserver) { _pfObserver.disconnect(); _pfObserver = null; }
        if (!('IntersectionObserver' in window)) {
            links.forEach(l => prefetchSrc(l.getAttribute('href')));
            return;
        }
        // 视口上下各留 400px：滑到附近就先把原图备好
        _pfObserver = new IntersectionObserver((ents) => {
            ents.forEach(en => {
                if (!en.isIntersecting) return;
                prefetchSrc(en.target.getAttribute('href'));
                _pfObserver.unobserve(en.target);
            });
        }, { rootMargin: '400px 0px 400px 0px' });
        links.forEach(l => _pfObserver.observe(l));
    }

    /* 兜底：万一某张图还没触发 load 就被点开，点击捕获阶段再回填一次真实尺寸 */
    document.addEventListener('click', (e) => {
        const t = e.target;
        const a = t && t.closest ? t.closest('.my-gallery a') : null;
        if (!a) return;
        const img = a.querySelector('img');
        if (img && img.naturalWidth) {
            a.setAttribute('data-size', img.naturalWidth + 'x' + img.naturalHeight);
        }
    }, true);

    /* 图片查看器（PhotoSwipe）开关动画时长：真机偏干脆，这里比默认 333ms 快一档。
       moments.vue 在每次打开时读取这个全局值（读不到就退回 333）。 */
    window.__wxMomentsViewerOpts = { show: 120, hide: 100 };

    /* ---- 构建一条朋友圈动态 DOM（复用 weui 原生样式）---- */
    function buildPost(p) {
        const cell = document.createElement('div');
        cell.className = 'weui-cell moments__post';
        const hd = document.createElement('div');
        hd.className = 'weui-cell__hd';
        const hdImg = document.createElement('img');
        hdImg.src = p.avatar || DEFAULT_POST_AVATAR;
        hd.appendChild(hdImg);
        const bd = document.createElement('div');
        bd.className = 'weui-cell__bd';

        const title = document.createElement('a');
        title.className = 'title';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'wx-name';
        nameSpan.textContent = p.author || '微信用户';
        title.appendChild(nameSpan);
        // 企业微信来源：昵称后跟金色「@公司名」+ 右侧折叠箭头（真机观感）
        if (p.company) {
            const co = document.createElement('span');
            co.className = 'post-company';
            co.textContent = '@' + p.company;
            title.appendChild(co);
            const caret = document.createElement('i');
            caret.className = 'post-caret';
            title.appendChild(caret);
        }

        const para = document.createElement('p');
        para.className = 'paragraph';
        para.textContent = p.text || '';
        // 长文折叠容器：超 6 行折叠 + 「全文 / 收起」（真机观感）
        const paraWrap = document.createElement('div');
        paraWrap.className = 'paragraph-wrap';
        if (p.foldLines) paraWrap.dataset.foldLines = String(p.foldLines);
        if (p.noFold) paraWrap.dataset.foldLines = '0';
        paraWrap.appendChild(para);

        const thumbs = document.createElement('div');
        const vid = normalizeVideo(p);
        const imgs = (p.images || []).slice(0, 9);
        const total = Math.min(Math.max(1, imgs.length + (vid ? 1 : 0)), 9);
        thumbs.className = 'thumbnails my-gallery thumb-' + total;
        if (vid) thumbs.appendChild(buildVideoThumb(vid));
        // 单图（且没有视频）才走「按原比例 + 宽图裁切」那套档位
        const single = !vid && imgs.length === 1;
        imgs.forEach(src => {
            const fig = document.createElement('figure');
            fig.className = 'thumbnail';
            const a = document.createElement('a');
            a.href = src;
            a.setAttribute('data-size', '400x400');   // 占位；图片加载完按真实宽高改写
            const img = document.createElement('img');
            img.src = src;
            img.alt = 'Image';
            a.appendChild(img);
            fig.appendChild(a);
            bindThumb(a, img, thumbs, single);
            thumbs.appendChild(fig);
        });

        // 参考图：配图下方的来源标注（如「视频号 · xxx」）作为灰色小字
        let sourceEl = null;
        if (p.source) {
            sourceEl = document.createElement('p');
            sourceEl.className = 'post-source';
            sourceEl.textContent = p.source;
        }

        const toolbar = document.createElement('div');
        toolbar.className = 'toolbar';
        const ts = document.createElement('p');
        ts.className = 'timestamp';
        ts.textContent = p.time || '刚刚';
        // 真机微信：右下角「···」按钮，点击在其上方弹出「赞 / 评论」浮动菜单
        const tAction = document.createElement('div');
        tAction.className = 'action-menu actionMenu slideIn';
        tAction.innerHTML =
            '<p class="actionBtn btn-like"><i class="icon icon-96"></i><span>赞</span></p>' +
            '<p class="actionBtn btn-comment"><i class="icon icon-3"></i><span>评论</span></p>';
        const toggle = document.createElement('span');
        toggle.className = 'actionToggle';
        toggle.textContent = '···';
        toolbar.appendChild(ts);
        toolbar.appendChild(tAction);
        toolbar.appendChild(toggle);

        // 菜单默认隐藏；点击「···」弹出，点击其它区域收起。
        // 「赞 / 评论」命中走模块级 likePost / startComment —— 与脚本 API 同一套动画。
        const bindMenu = () => {
            const menu = cell.querySelector('.actionMenu');
            const hide = () => menu.classList.remove('open');
            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                menu.classList.toggle('open');
            });
            menu.addEventListener('click', (e) => e.stopPropagation());
            cell.addEventListener('click', () => hide());
            document.addEventListener('click', () => hide());

            const likeBtn = menu.querySelector('.btn-like');
            const commentBtn = menu.querySelector('.btn-comment');
            if (likeBtn) likeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                hideMenuFast(menu);   // 命中「赞」：菜单 ~90ms 快速收起
                likePost(cell);
            });
            if (commentBtn) commentBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                hideMenuFast(menu);
                setTimeout(() => startComment(cell), 100);   // 菜单收起后输入条+键盘滑入
            });
        };

        /* 点赞/评论进同一个深灰条容器（真机形态，见 moment-meta 样式）；
           两者都为空则不建容器。初始渲染不加 moment-meta-pop（不播弹出动画）。 */
        let metaEl = null;
        const metaOf = () => {
            if (!metaEl) {
                metaEl = document.createElement('div');
                metaEl.className = 'moment-meta';
            }
            return metaEl;
        };
        if (p.likes && p.likes.length) {
            const likeText = document.createElement('p');
            likeText.className = 'liketext';
            likeText.innerHTML = '<i class="icon icon-96"></i>' + p.likes.map(n =>
                '<span class="nickname">' + n + '</span>').join(',');
            metaOf().appendChild(likeText);
        }
        (p.comments || []).forEach(c => {
            const cp = document.createElement('p');
            cp.className = 'comment-entry';
            const b = document.createElement('b');
            b.textContent = c.name + '：';
            cp.appendChild(b);
            cp.appendChild(document.createTextNode(c.text));
            metaOf().appendChild(cp);
        });

        bd.appendChild(title);
        bd.appendChild(paraWrap);
        if ((p.images && p.images.length) || vid) bd.appendChild(thumbs);
        if (sourceEl) bd.appendChild(sourceEl);
        bd.appendChild(toolbar);
        if (metaEl) bd.appendChild(metaEl);

        cell.appendChild(hd);
        cell.appendChild(bd);
        bindMenu();
        return cell;
    }

    /* ---- 长文折叠：超过 6 行（行高 34）则折叠，并挂「全文 / 收起」---- */
    const TEXT_MAX_LINES = 5;
    const TEXT_LINE_H = 34;
    function applyTextCollapse(cell) {
        const wrap = cell && cell.querySelector('.paragraph-wrap');
        if (!wrap) return;
        const para = wrap.querySelector('.paragraph');
        if (!para) return;
        const old = wrap.querySelector('.paragraphExtender');
        if (old) old.remove();
        wrap.classList.remove('is-collapsed');
        // 单条动态可用 p.noFold=true 关闭折叠，或用 p.foldLines=N 指定行数
        const lines = wrap.dataset.foldLines
            ? parseInt(wrap.dataset.foldLines, 10) : TEXT_MAX_LINES;
        if (!lines || para.scrollHeight <= lines * TEXT_LINE_H + 4) return;
        wrap.style.setProperty('--fold-lines', String(lines));
        wrap.classList.add('is-collapsed');
        const more = document.createElement('a');
        more.className = 'paragraphExtender';
        more.textContent = '全文';
        more.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const collapsed = wrap.classList.toggle('is-collapsed');
            more.textContent = collapsed ? '全文' : '收起';
        });
        wrap.appendChild(more);
    }

    /* ---- 朋友圈页标识 + 导航栏随滚动淡入（真机：封面滚出后标题才出现）---- */
    let _mScrollEl = null;
    function onMomentsScroll() {
        if (!_mScrollEl) return;
        const y = _mScrollEl.scrollTop || 0;
        /* 真机节奏（朋友圈下滑.mp4）：淡入窗口对准「封面底边扫过导航条」——
           封面底 598、导航底 124 → y=474 时封面彻底离开导航区，窗口取 380..480 */
        const a = Math.max(0, Math.min(1, (y - 380) / 100));
        _mScrollEl.style.setProperty('--nav-a', a.toFixed(3));
    }
    function syncMomentsChrome() {
        const el = document.getElementById('moments');
        const on = !!el;
        if (document.body.classList.contains('wx-on-moments') !== on) {
            document.body.classList.toggle('wx-on-moments', on);
        }
        if (el && el !== _mScrollEl) {
            if (_mScrollEl) _mScrollEl.removeEventListener('scroll', onMomentsScroll);
            _mScrollEl = el;
            el.addEventListener('scroll', onMomentsScroll, { passive: true });
            onMomentsScroll();
            prefetchGallery(el);   // 进页面就把已在视口附近的配图原图备好
        } else if (!el && _mScrollEl) {
            _mScrollEl.removeEventListener('scroll', onMomentsScroll);
            _mScrollEl = null;
        }
    }
    setInterval(syncMomentsChrome, 250);

    /* ---- 按数据重建朋友圈动态列表 ---- */
    function renderPosts(posts) {
        const root = document.getElementById('moments');
        if (!root) return false;
        const pswp = root.querySelector('.pswp');
        root.querySelectorAll('.moments__post').forEach(el => el.remove());
        (Array.isArray(posts) ? posts : []).forEach(p => root.insertBefore(buildPost(p), pswp));
        refreshGallery();
        root.querySelectorAll('.moments__post').forEach(applyTextCollapse);
        prefetchGallery(root);
        syncMomentsChrome();
        return true;
    }

    /* ---- 发朋友圈：发表文字编辑页（previewImage 可选配图） ---- */
    let composeImage = null;
    function openCompose(previewImage) {
        composeImage = previewImage || null;
        closeCompose();
        const ov = document.createElement('div');
        ov.id = 'momentCompose';
        const imgHtml = composeImage
            ? '<div class="mc-img"><img src="' + composeImage + '" data-me-avatar></div>'
            : '';
        ov.innerHTML =
            '<div class="mc-top">' +
            '<span class="mc-cancel">取消</span>' +
            '<b>发表文字</b>' +
            '<span class="mc-send mc-disabled" id="mcSend">发表</span>' +
            '</div>' +
            '<div class="mc-body">' +
            '<textarea id="mcText" placeholder="这一刻的想法..."></textarea>' +
            imgHtml +
            '</div>';
        document.body.appendChild(ov);
        return true;
    }

    function closeCompose() {
        const old = document.getElementById('momentCompose');
        if (old) old.remove();
    }

    /* 发表：把文字追加为一条自己的朋友圈动态（纯文字时无配图） */
    function submit() {
        const textEl = document.getElementById('mcText');
        const text = textEl ? textEl.value.trim() : '';
        if (!text) return false;
        const root = document.getElementById('moments');
        if (!root) return false;
        const post = buildPost({
            author: me().name,
            avatar: me().avatar,
            text: text,
            images: composeImage ? [composeImage] : [],
            time: '刚刚',
            likes: [],
            comments: [],
        });
        const pswp = root.querySelector('.pswp');
        root.insertBefore(post, pswp);
        closeCompose();
        refreshGallery();
        applyTextCollapse(post);
        prefetchGallery(root);
        post.scrollIntoView({ block: 'center' });
        return true;
    }

    /* ---- 朋友圈滚动容器（供 main.py 的滚动动作定位） ---- */
    function scrollEl() {
        return document.querySelector('#moments.sub-page') || document.getElementById('moments');
    }
    function scrollBy(px) {
        const n = scrollEl();
        if (!n) return false;
        n.scrollTop += Number(px) || 0;
        return Math.round(n.scrollTop);
    }
    function scrollInfo() {
        const n = scrollEl();
        if (!n) return null;
        return { top: Math.round(n.scrollTop),
                 max: Math.max(0, Math.round(n.scrollHeight - n.clientHeight)) };
    }

    /* ---- 点开朋友圈里第 postIndex 条动态的第 imgIndex 张配图（默认第 1 条第 1 张） ----
       走原生 PhotoSwipe 全屏画廊（可左右滑动切图），等价于真人点缩略图。 */
    function openImage(postIndex, imgIndex) {
        const posts = document.querySelectorAll('#moments .moments__post');
        if (!posts.length) return false;
        let i = Math.max(1, Number(postIndex) || 1) - 1;
        i = Math.min(i, posts.length - 1);
        const gal = posts[i].querySelector('.my-gallery');
        if (!gal) return false;
        // 视频缩略图不是画廊成员，按图片顺序过滤后再取第 imgIndex 张
        const figures = Array.prototype.filter.call(gal.children, (n) =>
            n.nodeType === 1 && !(n.classList && n.classList.contains('video-thumb')));
        if (!figures.length) return false;
        let j = Math.max(1, Number(imgIndex) || 1) - 1;
        j = Math.min(j, figures.length - 1);
        /* 不要 scrollIntoView：真人点的是眼前看到的格子，列表不该自己挪动；
           之前它会额外滚动列表（实测能把 scrollTop 从 420 挪到 150）且关图后不还原，
           成片里表现为「开图前列表先跳一下、关图后位置对不上」。JS click 不需要可见。 */
        window.__pswpSeq = (window.__pswpSeq || 0) + 1;   // 开图推进序列，防关图兜底误伤重开
        /* 上一次关闭留下的淡出标记必须先摘掉，否则本次开图动画里 zoom-wrap 仍是透明的 */
        const p0 = document.querySelector('.pswp');
        if (p0) p0.classList.remove('pswp--wx-closing');
        const a = figures[j].querySelector('a') || figures[j];
        a.click();
        return true;
    }

    /* ---- 关闭当前打开的全屏图片画廊（PhotoSwipe） ---- */
    function closeImage() {
        const btn = document.querySelector('.pswp--open .pswp__button--close');
        if (btn) {
            const seq = (window.__pswpSeq = (window.__pswpSeq || 0) + 1);
            btn.click();
            /* 关闭瞬间给根节点挂淡出标记：zoom-wrap 随关闭动画 120ms 淡出（CSS 见
               moments_exact.css 第九节）。pswp 自己的收尾（setTimeout/rAF 隐藏根节点）
               录屏负载下迟到 0.2~0.4s 也不再有残影可画 —— 根治「关图后格子裁切错误、
               下次滚动开始瞬间才消失（闪一下/淡入淡出）」。 */
            const p0 = document.querySelector('.pswp');
            if (p0) p0.classList.add('pswp--wx-closing');
            /* 兜底回收（序列号防误伤：期间有新的开/关动作则跳过）：
               · 根节点还开着（destroy 迟到）→ 先把根节点切回「未打开态」（纯类机制，
                 等价 destroy 的显示效果，无内联样式残留，恢复点击穿透）。wx-closing
                 必须留着 —— 它是残影保险，提前摘掉会让 zoom-wrap 在 destroy 执行前复活。
               · 根节点已隐藏（destroy 已跑）→ 摘掉 wx-closing，恢复初始类名。
               两条路最终都会被 destroy 的 className 重置或下次 openImage 摘标记兜住。 */
            const dur = (window.__wxMomentsViewerOpts && window.__wxMomentsViewerOpts.hide) || 333;
            setTimeout(() => {
                if (window.__pswpSeq !== seq) return;
                const p = document.querySelector('.pswp');
                if (!p) return;
                if (p.classList.contains('pswp--open')) {
                    p.classList.remove('pswp--open');
                } else {
                    p.classList.remove('pswp--wx-closing');
                }
            }, dur + 150);
            return true;
        }
        const pswp = document.querySelector('.pswp--open');
        if (pswp) { pswp.classList.remove('pswp--open', 'pswp--wx-closing'); return true; }
        return false;
    }

    /* ---- 点开朋友圈里第 index 个视频动态（默认第 1 个） ---- */
    function playVideo(index) {
        const list = Array.prototype.slice.call(
            document.querySelectorAll('#moments [data-wx-video-src]'));
        if (!list.length) return false;
        let i = Number(index) || 1;
        i = Math.max(1, Math.min(list.length, i)) - 1;
        const wrap = list[i];
        if (wrap.scrollIntoView) wrap.scrollIntoView({ block: 'center' });
        wrap.click();
        return true;
    }
    function videoCount() {
        return document.querySelectorAll('#moments [data-wx-video-src]').length;
    }

    /* ---- 关闭朋友圈里打开的覆盖层（视频 / 图片查看器 / 图片画廊） ---- */
    function closeViewers() {
        if (window.__wxVideo) window.__wxVideo.close();
        closeImage();
        if (window.__wxHuman && window.__wxHuman.isImageOpen && window.__wxHuman.isImageOpen()) {
            window.__wxHuman.closeImage();
        }
        return true;
    }

    /* ---- 朋友圈里可点开的配图数量（供脚本判断/校验序号） ---- */
    function imageCount(postIndex) {
        const posts = document.querySelectorAll('#moments .moments__post');
        if (!posts.length) return 0;
        const pick = postIndex == null ? null : Math.max(1, Number(postIndex) || 1) - 1;
        let total = 0;
        posts.forEach((post, idx) => {
            if (pick != null && idx !== pick) return;
            const gal = post.querySelector('.my-gallery');
            if (!gal) return;
            total += Array.prototype.filter.call(gal.children, (n) =>
                n.nodeType === 1 && !(n.classList && n.classList.contains('video-thumb'))).length;
        });
        return total;
    }

    window.__wxMoments = {
        renderPosts,
        openCompose,
        closeCompose,
        submit,
        refreshGallery,
        scrollEl,
        scrollBy,
        scrollInfo,
        openImage,
        closeImage,
        imageCount,
        playVideo,
        videoCount,
        closeViewers,
        prefetchGallery,
        /* 赞 / 评论（复刻真机：弹窗菜单 → 点赞条/键盘动画 → 评论上屏） */
        openMenu,
        tapLike,
        tapComment,
        submitComment,
    };
})();