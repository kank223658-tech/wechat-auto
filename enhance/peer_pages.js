/* ============================================================
   对方个人主页 / 对方朋友圈（main.py 注入）
   ------------------------------------------------------------
   复刻参考视频「微信进入主页加入朋友圈」的界面与动作：

     聊天页点头像  →  #wxPeerProfile（对方个人资料页）
                        └─ 点「朋友圈」 →  #wxPeerMoments（对方朋友圈）

   数据来自 window.__wxConfig.get().peer（可由场景/脚本整体替换），
   结构见 config.js 的 PEER_PRESETS。全部幂等，可反复 open/close。

   对外 API（main.py / Playwright 调用）：
     window.__wxPeer.openProfile(contact?)  打开个人资料页
     window.__wxPeer.openMoments()          打开对方朋友圈（自动补资料页）
     window.__wxPeer.back()                 返回上一页（朋友圈→资料页→关闭）
     window.__wxPeer.close()                直接关闭
     window.__wxPeer.isOpen()               返回 {profile:bool, moments:bool}
     window.__wxPeer.apply(data)            局部更新数据并重绘
     window.__wxPeer.scrollBy(px)           朋友圈滚动指定像素（正=下，负=上）
     window.__wxPeer.scrollInfo()           返回 {top, max}
     window.__wxPeer.openImage(i, j)        点开第 i 条动态的第 j 张配图（默认 1,1）
     window.__wxPeer.imageCount(i?)         可点开的配图数量（省略 i 统计全部）
     window.__wxPeer.playVideo(index)       点开第 N 个视频动态（默认第 1 个）
     window.__wxPeer.videoCount()           朋友圈里视频动态数量
     window.__wxPeer.closeViewers()         关掉打开的图片查看器 / 视频播放器

   动态数据支持 post.video（字符串地址，或 {src, cover} 对象）：有视频时
   中列渲染「封面 + 播放角标」，点开走 window.__wxVideo 全屏播放。
   ============================================================ */
(() => {
    if (window.__wxPeer) return;

    const NS = 'wxPeer';
    const PROFILE_ID = 'wxPeerProfile';
    const MOMENTS_ID = 'wxPeerMoments';

    /* ---------- 数据 ---------- */
    const FALLBACK_AVATAR = '/images/header/header01.png';

    const defaults = () => ({
        name: '陆香儿',
        wxid: 'luxianger',
        area: '广东 深圳',
        gender: 0,
        avatar: FALLBACK_AVATAR,
        signature: '',
        cover: '/images/bg/cover.jpg',
        momentsThumbs: [],
        video: null,
        posts: [],
    });

    function cfg() {
        const c = (window.__wxConfig && window.__wxConfig.get()) || {};
        return c;
    }

    function peer() {
        const c = cfg();
        if (window.__wxConfig && window.__wxConfig.getPeer) {
            return Object.assign(defaults(), window.__wxConfig.getPeer() || {});
        }
        return Object.assign(defaults(), (c && c.peer) || {});
    }

    /* ---------- DOM 工具 ---------- */
    const el = (tag, cls, text) => {
        const n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    };

    function thumbRow(srcs, cls) {
        const box = el('div', cls || 'wpp-thumbs');
        (srcs || []).forEach((src) => {
            const im = el('img');
            im.src = src;
            box.appendChild(im);
        });
        return box;
    }

    /* ---------- 个人资料页 ---------- */
    function ensureProfile() {
        let root = document.getElementById(PROFILE_ID);
        if (root) return root;
        root = el('div', 'wx-peer-page');
        root.id = PROFILE_ID;
        root.setAttribute('aria-hidden', 'true');
        root.innerHTML =
            '<div class="wpp-nav">' +
            '  <span class="wpp-back" data-peer-back></span>' +
            '  <span class="wpp-more"><i></i><i></i><i></i></span>' +
            '</div>' +
            '<div class="wpp-scroll">' +
            '  <div class="wpp-head">' +
            '    <img class="wpp-avatar" alt="">' +
            '    <div class="wpp-meta">' +
            '      <div class="wpp-name"><span class="wpp-name-t"></span><i class="wpp-gender"></i></div>' +
            '      <div class="wpp-wxid"></div>' +
            '      <div class="wpp-area"></div>' +
            '    </div>' +
            '  </div>' +
            '  <div class="wpp-group">' +
            '    <div class="wpp-cell wpp-friend-cell">' +
            '      <div class="wpp-cell-main">' +
            '        <div class="wpp-cell-title">朋友资料</div>' +
            '        <div class="wpp-cell-desc">添加朋友的备注名、电话、标签、备忘、照片等，并设置朋友权限。</div>' +
            '      </div>' +
            '      <span class="wpp-arrow"></span>' +
            '    </div>' +
            '  </div>' +
            '  <div class="wpp-group">' +
            '    <div class="wpp-cell wpp-moments-cell" data-peer-moments-entry>' +
            '      <div class="wpp-cell-title wpp-title-fixed">朋友圈</div>' +
            '      <div class="wpp-thumbs"></div>' +
            '      <span class="wpp-arrow"></span>' +
            '    </div>' +
            '  </div>' +
            '  <div class="wpp-group">' +
            '    <div class="wpp-cell wpp-video-cell">' +
            '      <div class="wpp-cell-title wpp-title-fixed">视频号</div>' +
            '      <div class="wpp-video">' +
            '        <div class="wpp-video-name"></div>' +
            '        <div class="wpp-thumbs wpp-video-thumbs"></div>' +
            '      </div>' +
            '      <span class="wpp-arrow"></span>' +
            '    </div>' +
            '  </div>' +
            '  <div class="wpp-group wpp-actions">' +
            '    <div class="wpp-action"><i class="wpp-ic wpp-ic-msg"></i><span>发消息</span></div>' +
            '    <div class="wpp-action"><i class="wpp-ic wpp-ic-call"></i><span>音视频通话</span></div>' +
            '  </div>' +
            '</div>';
        document.body.appendChild(root);
        void root.offsetWidth;   // 强制先以「关闭态」计算样式，保证后续加 .open 能触发滑入

        // 点「朋友圈」行 → 打开对方朋友圈
        const entry = root.querySelector('[data-peer-moments-entry]');
        if (entry) entry.addEventListener('click', () => openMoments());
        // 返回箭头 → 关闭
        const back = root.querySelector('[data-peer-back]');
        if (back) back.addEventListener('click', () => back());
        return root;
    }

    function renderProfile() {
        const root = ensureProfile();
        const p = peer();
        root.querySelector('.wpp-avatar').src = p.avatar || FALLBACK_AVATAR;
        root.querySelector('.wpp-name-t').textContent = p.name || '';
        const g = root.querySelector('.wpp-gender');
        g.classList.toggle('male', Number(p.gender) === 1);
        g.classList.toggle('female', Number(p.gender) !== 1);
        root.querySelector('.wpp-wxid').textContent = '微信号：' + (p.wxid || '');
        root.querySelector('.wpp-area').textContent = '地区：' + (p.area || '');
        // 朋友圈缩略图（参考视频：最多 5 张，74px 方图）
        const thumbs = root.querySelector('.wpp-moments-cell .wpp-thumbs');
        thumbs.innerHTML = '';
        (p.momentsThumbs || []).slice(0, 5).forEach((src) => {
            const im = el('img');
            im.src = src;
            thumbs.appendChild(im);
        });
        // 视频号
        const vcell = root.querySelector('.wpp-video-cell');
        const v = p.video;
        if (v && (v.name || (v.thumbs || []).length)) {
            vcell.style.display = '';
            root.querySelector('.wpp-video-name').textContent = v.name || '';
            const vt = root.querySelector('.wpp-video-thumbs');
            vt.innerHTML = '';
            (v.thumbs || []).slice(0, 5).forEach((src) => {
                const im = el('img');
                im.src = src;
                vt.appendChild(im);
            });
        } else {
            vcell.style.display = 'none';
        }
        return root;
    }

    /* ---------- 对方朋友圈页 ---------- */
    function ensureMoments() {
        let root = document.getElementById(MOMENTS_ID);
        if (root) return root;
        root = el('div', 'wx-peer-page');
        root.id = MOMENTS_ID;
        root.setAttribute('aria-hidden', 'true');
        root.innerHTML =
            '<div class="wpm-scroll">' +
            '  <div class="wpm-cover">' +
            '    <img class="wpm-cover-img" alt="">' +
            '    <span class="wpm-back" data-peer-back></span>' +
            '    <div class="wpm-cover-bottom">' +
            '      <div class="wpm-name"></div>' +
            '      <img class="wpm-avatar" alt="">' +
            '    </div>' +
            '  </div>' +
            '  <div class="wpm-signature"></div>' +
            '  <div class="wpm-list"></div>' +
            '</div>';
        document.body.appendChild(root);
        void root.offsetWidth;   // 同上：首次创建时也要能从右侧滑入，而不是直接弹出
        const back = root.querySelector('[data-peer-back]');
        if (back) back.addEventListener('click', () => back());
        return root;
    }

    /* 解析一条动态里的视频：支持 post.video 为字符串（视频地址）或
       {src, cover} 对象；封面缺省取 post.cover 或第一张配图。无视频返回 null。 */
    function postVideo(post) {
        const v = post && post.video;
        if (!v) return null;
        if (typeof v === 'string') {
            return { src: v, cover: post.cover || (post.images || [])[0] || '' };
        }
        const src = v.src || v.url || v.path || v.视频 || v.地址 || '';
        if (!src) return null;
        return {
            src: String(src),
            cover: v.cover || v.封面 || v.poster || post.cover || (post.images || [])[0] || '',
        };
    }

    /* 打开一张朋友圈配图：复用真人图片查看器（打开 + 捏合放大 + 轻点关闭）。
       查看器未注入时退回浏览器原生打开，保证「点得开」。 */
    function openImageAt(src) {
        if (!src) return false;
        if (window.__wxHuman && window.__wxHuman.openImage) {
            return !!window.__wxHuman.openImage(src, null, {});
        }
        window.open(src, '_blank');
        return true;
    }

    /* 一条动态：日期 | 图片/视频 | 文字（与参考视频一致的三段横排） */
    function buildPost(post) {
        const row = el('div', 'wpm-post');
        // 日期：把 "10 6月" 拆成 大字数字 + 小字月份
        const date = el('div', 'wpm-date');
        const raw = String(post.date == null ? '' : post.date).trim();
        const m = /^(\d{1,2})\s*(.*)$/.exec(raw);
        if (m) {
            date.appendChild(el('b', null, m[1]));
            if (m[2]) date.appendChild(el('span', null, m[2]));
        } else if (raw) {
            date.appendChild(el('b', null, raw));
        }
        row.appendChild(date);

        // 中列：视频动态优先渲染「封面 + 播放角标」，否则按图片网格
        const vid = postVideo(post);
        const imgs = (post.images || []).slice(0, 9);
        if (vid) {
            const box = el('div', 'wpm-imgs wpm-imgs-video');
            const wrap = el('div', 'wpm-video-wrap');
            wrap.setAttribute('data-wx-video-src', vid.src);
            const cover = el('img', 'wpm-video-cover');
            if (vid.cover) cover.src = vid.cover;
            wrap.appendChild(cover);
            wrap.appendChild(el('span', 'wpm-play'));
            wrap.addEventListener('click', (e) => {
                e.stopPropagation();
                if (window.__wxVideo) window.__wxVideo.open(vid.src, { cover: vid.cover });
            });
            box.appendChild(wrap);
            row.appendChild(box);
        } else if (imgs.length) {
            const grid = el('div', 'wpm-imgs wpm-imgs-' + Math.min(imgs.length, 9));
            imgs.forEach((src, idx) => {
                const im = el('img');
                im.src = src;
                im.setAttribute('data-wx-img-index', String(idx + 1));
                // 点开配图 → 全屏图片查看器（复用真人查看器：打开 + 捏合放大 + 轻点关闭）
                im.addEventListener('click', (e) => {
                    e.stopPropagation();
                    openImageAt(src);
                });
                grid.appendChild(im);
            });
            row.appendChild(grid);
        } else {
            row.appendChild(el('div', 'wpm-imgs wpm-imgs-empty'));
        }

        // 文字
        const texts = el('div', 'wpm-texts');
        String(post.text == null ? '' : post.text)
            .split('\n')
            .forEach((line) => texts.appendChild(el('p', null, line)));
        row.appendChild(texts);

        // 点赞 / 评论（posts[].likes = [名字...]，posts[].comments = [{name, text}]，可省略）
        const likes = (post.likes || []).filter(Boolean);
        const cmts = post.comments || [];
        if (likes.length || cmts.length) {
            const social = el('div', 'wpm-social');
            if (likes.length) {
                const lk = el('div', 'wpm-likes');
                lk.appendChild(el('i', 'wpm-like-ic', '♥'));
                lk.appendChild(el('span', null, likes.join('，') + ' 觉得很赞'));
                social.appendChild(lk);
            }
            if (likes.length && cmts.length) social.appendChild(el('div', 'wpm-social-div'));
            cmts.forEach((c) => {
                const line = el('div', 'wpm-cmt');
                line.appendChild(el('span', 'wpm-cmt-name', String(c && c.name || '')));
                line.appendChild(el('span', null, '：' + String(c && c.text || '')));
                social.appendChild(line);
            });
            texts.appendChild(social);
        }
        return row;
    }

    function renderMoments() {
        const root = ensureMoments();
        const p = peer();
        root.querySelector('.wpm-cover-img').src = p.cover || '';
        root.querySelector('.wpm-name').textContent = p.name || '';
        root.querySelector('.wpm-avatar').src = p.avatar || FALLBACK_AVATAR;
        const sig = root.querySelector('.wpm-signature');
        sig.textContent = p.signature || '';
        sig.style.display = p.signature ? '' : 'none';
        const list = root.querySelector('.wpm-list');
        list.innerHTML = '';
        (p.posts || []).forEach((post) => list.appendChild(buildPost(post)));
        return root;
    }

    /* ---------- 打开 / 关闭 / 转场 ----------
       iOS 推入转场：底层页面（#app）左移并压暗，新页从右侧滑入；
       朋友圈叠在资料页之上时，资料页也左移让位（视差）。 */

    const DIM_ID = 'wxPeerDim';

    function dim() {
        let d = document.getElementById(DIM_ID);
        if (!d) {
            d = el('div');
            d.id = DIM_ID;
            d.className = 'wx-peer-dim';
            document.body.appendChild(d);
        }
        return d;
    }

    function setOpen(node, open) {
        if (!node) return;
        node.classList.toggle('open', !!open);
        node.setAttribute('aria-hidden', open ? 'false' : 'true');
    }

    function isOpen() {
        const prof = document.getElementById(PROFILE_ID);
        const mom = document.getElementById(MOMENTS_ID);
        return {
            profile: !!(prof && prof.classList.contains('open')),
            moments: !!(mom && mom.classList.contains('open')),
        };
    }

    /* 同步底层视差：资料页/朋友圈任一打开时，底层左移压暗 */
    function syncBackdrop() {
        const st = isOpen();
        const app = document.getElementById('app');
        const anyOpen = st.profile || st.moments;
        if (app) app.classList.toggle('wx-peer-pushing', anyOpen);
        dim().classList.toggle('on', anyOpen);
        const prof = document.getElementById(PROFILE_ID);
        if (prof) prof.classList.toggle('leaving', st.moments);
        document.body.classList.toggle('wx-peer-open', anyOpen);
    }

    /* 打开对方个人资料页（可选 contact / 预设名，用于切换不同人设） */
    function openProfile(contact) {
        if (contact && window.__wxConfig && window.__wxConfig.setPeer) {
            const presets = window.__wxConfig.getPeerPresets
                ? window.__wxConfig.getPeerPresets() : null;
            if (presets && presets[contact]) window.__wxConfig.setPeer(contact);
        }
        renderProfile();
        setOpen(document.getElementById(PROFILE_ID), true);
        syncBackdrop();
        return true;
    }

    function openMoments() {
        // 朋友圈叠在资料页之上；若资料页还没开，先补上（真机路径：资料页 → 朋友圈）
        if (!isOpen().profile) {
            renderProfile();
            setOpen(document.getElementById(PROFILE_ID), true);
        }
        renderMoments();
        setOpen(document.getElementById(MOMENTS_ID), true);
        syncBackdrop();
        return true;
    }

    function back() {
        // 联系人设置页（__wxBlock）叠在资料页之上：开着时先退它
        if (window.__wxBlock && window.__wxBlock.backFromSettings &&
                window.__wxBlock.backFromSettings()) {
            return "settings";
        }
        const st = isOpen();
        if (st.moments) {
            setOpen(document.getElementById(MOMENTS_ID), false);
            syncBackdrop();
            return "profile";
        }
        if (st.profile) {
            setOpen(document.getElementById(PROFILE_ID), false);
            syncBackdrop();
            return "chat";
        }
        return false;
    }

    function close() {
        setOpen(document.getElementById(PROFILE_ID), false);
        setOpen(document.getElementById(MOMENTS_ID), false);
        syncBackdrop();
        return true;
    }

    /* 局部更新数据并重绘 */
    function apply(data) {
        if (!data || typeof data !== 'object') return false;
        if (window.__wxConfig && window.__wxConfig.setPeer) {
            window.__wxConfig.setPeer(data);
        }
        if (document.getElementById(PROFILE_ID)) renderProfile();
        if (document.getElementById(MOMENTS_ID)) renderMoments();
        return true;
    }

    /* 朋友圈滚动辅助：供 main.py 的滚动动作定位到朋友圈滚动容器，
       也可在脚本里直接滚到顶/底。 */
    function momentsScrollEl() {
        return document.querySelector('#wxPeerMoments .wpm-scroll');
    }
    function scrollBy(px) {
        const n = momentsScrollEl();
        if (!n) return false;
        n.scrollTop += Number(px) || 0;
        return Math.round(n.scrollTop);
    }
    function scrollInfo() {
        const n = momentsScrollEl();
        if (!n) return null;
        return { top: Math.round(n.scrollTop),
                 max: Math.max(0, Math.round(n.scrollHeight - n.clientHeight)) };
    }
    /* 点开朋友圈里的第 index 个视频（默认第 1 个），等价于真人点播放角标 */
    function playVideo(index) {
        const list = Array.prototype.slice.call(
            document.querySelectorAll('#wxPeerMoments [data-wx-video-src]'));
        if (!list.length) return false;
        let i = Number(index) || 1;
        i = Math.max(1, Math.min(list.length, i)) - 1;
        list[i].click();
        return true;
    }
    function videoCount() {
        return document.querySelectorAll('#wxPeerMoments [data-wx-video-src]').length;
    }

    /* 点开对方朋友圈里第 postIndex 条动态的第 imgIndex 张配图（默认第 1 条第 1 张） */
    function openImage(postIndex, imgIndex) {
        const rows = document.querySelectorAll('#wxPeerMoments .wpm-post');
        if (!rows.length) return false;
        let i = Math.max(1, Number(postIndex) || 1) - 1;
        i = Math.min(i, rows.length - 1);
        const imgs = rows[i].querySelectorAll('.wpm-imgs:not(.wpm-imgs-video):not(.wpm-imgs-empty) img');
        if (!imgs.length) return false;
        let j = Math.max(1, Number(imgIndex) || 1) - 1;
        j = Math.min(j, imgs.length - 1);
        /* 不要 scrollIntoView：与 moments_extra.openImage 同理，列表不该自己挪动
           （会额外滚动且关图后不还原，成片里位置对不上）。JS click 不需要可见。 */
        imgs[j].click();
        return true;
    }

    /* 对方朋友圈里可点开的配图数量（postIndex 省略则统计全部） */
    function imageCount(postIndex) {
        const rows = document.querySelectorAll('#wxPeerMoments .wpm-post');
        if (!rows.length) return 0;
        const pick = postIndex == null ? null : Math.max(1, Number(postIndex) || 1) - 1;
        let total = 0;
        rows.forEach((row, idx) => {
            if (pick != null && idx !== pick) return;
            total += row.querySelectorAll(
                '.wpm-imgs:not(.wpm-imgs-video):not(.wpm-imgs-empty) img').length;
        });
        return total;
    }

    /* 关闭对方朋友圈里打开的图片查看器 / 视频播放器 */
    function closeViewers() {
        if (window.__wxVideo) window.__wxVideo.close();
        if (window.__wxHuman && window.__wxHuman.isImageOpen && window.__wxHuman.isImageOpen()) {
            window.__wxHuman.closeImage();
        }
        return true;
    }

    window.__wxPeer = {
        openProfile,
        openMoments,
        back,
        close,
        isOpen,
        apply,
        renderProfile,
        renderMoments,
        scrollBy,
        scrollInfo,
        openImage,
        imageCount,
        playVideo,
        videoCount,
        closeViewers,
    };
})();
