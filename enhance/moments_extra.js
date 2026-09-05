/* ============================================================
   朋友圈扩展（main.py 注入）
   ------------------------------------------------------------
   1. renderPosts：按配置数据重建朋友圈动态列表（可编辑朋友圈内容）
   2. openCompose / submit：发朋友圈（发表文字页 + 键盘打字 + 发表）
   ============================================================ */
(() => {
    if (window.__wxMoments) return;

    const me = () => (window.__wxConfig.get().me);

    /* ---- 构建一条朋友圈动态 DOM（复用 weui 原生样式）---- */
    function buildPost(p) {
        const cell = document.createElement('div');
        cell.className = 'weui-cell moments__post';
        const hd = document.createElement('div');
        hd.className = 'weui-cell__hd';
        const hdImg = document.createElement('img');
        hdImg.src = p.avatar || '/images/header/yehua.jpg';
        hd.appendChild(hdImg);
        const bd = document.createElement('div');
        bd.className = 'weui-cell__bd';

        const title = document.createElement('a');
        title.className = 'title';
        const nameSpan = document.createElement('span');
        nameSpan.textContent = p.author || '夜华';
        title.appendChild(nameSpan);

        const para = document.createElement('p');
        para.className = 'paragraph';
        para.textContent = p.text || '';

        const thumbs = document.createElement('div');
        const imgs = (p.images || []).slice(0, 9);
        thumbs.className = 'thumbnails my-gallery thumb-' + Math.min(Math.max(1, imgs.length), 9);
        imgs.forEach(src => {
            const fig = document.createElement('figure');
            fig.className = 'thumbnail';
            const a = document.createElement('a');
            a.href = src;
            a.setAttribute('data-size', '400x400');
            const img = document.createElement('img');
            img.src = src;
            img.alt = 'Image';
            a.appendChild(img);
            fig.appendChild(a);
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

        // 菜单默认隐藏；点击「···」在按钮上方切换显示，点击其它区域收起
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
                toggleLike();   // 针对当前动态点赞
                hide();
            });
            if (commentBtn) commentBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                hide();
                openComment(cell);   // 针对当前动态打开底部评论输入条
            });
        };

        // 针对当前动态点赞：无点赞栏则先创建，再追加我的昵称 + 高亮赞按钮
        const meName = () => (window.__wxConfig && window.__wxConfig.get().me.name) || '阿荡';
        const toggleLike = () => {
            const nm = meName();
            let like = cell.querySelector('.liketext');
            if (!like) {
                like = document.createElement('p');
                like.className = 'liketext';
                like.style.display = 'block';
                like.innerHTML = '<i class="icon icon-96"></i>';
                bd.appendChild(like);
            }
            like.style.display = 'block';
            if (!like.textContent.includes(nm)) {
                const s = document.createElement('span');
                s.className = 'nickname';
                s.textContent = (like.textContent.trim() && !like.textContent.endsWith('</i>') ? ',' : '') + nm;
                like.appendChild(s);
            }
            const btn = cell.querySelector('.btn-like');
            if (btn) btn.classList.add('liked');
        };

        // 针对当前动态打开底部评论输入条（复用 #commentBar 结构）
        const openComment = (targetPost) => {
            const old = document.getElementById('commentBar');
            if (old) old.remove();
            const bar = document.createElement('div');
            bar.id = 'commentBar';
            bar.innerHTML = '<input id="momentCommentInput" type="text" placeholder="评论">';
            document.body.appendChild(bar);
            const input = bar.querySelector('input');
            if (input) input.focus();
            const submit = () => {
                const text = (input.value || '').trim();
                if (!text) return;
                const bd = targetPost.querySelector('.weui-cell__bd') || targetPost;
                const cp = document.createElement('p');
                cp.className = 'comment-entry';
                const b = document.createElement('b');
                b.textContent = meName() + '：';
                cp.appendChild(b);
                cp.appendChild(document.createTextNode(text));
                bd.appendChild(cp);
                input.value = '';
                bar.remove();
            };
            // 回车提交；stopImmediatePropagation 避免 main.py 捕获层监听器干扰
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.keyCode === 13) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    submit();
                }
            }, true);
            // 提供「发送」按钮，点击也可提交（真机键盘回车之外的双保险）
            const send = document.createElement('span');
            send.className = 'comment-send';
            send.textContent = '发送';
            send.addEventListener('click', () => submit());
            bar.appendChild(send);
        };

        const likeText = document.createElement('p');
        likeText.className = 'liketext';
        likeText.innerHTML = '<i class="icon icon-96"></i>' + (p.likes || []).map(n =>
            '<span class="nickname">' + n + '</span>').join(',');

        bd.appendChild(title);
        bd.appendChild(para);
        if (p.images && p.images.length) bd.appendChild(thumbs);
        if (sourceEl) bd.appendChild(sourceEl);
        bd.appendChild(toolbar);
        if (p.likes && p.likes.length) bd.appendChild(likeText);
        (p.comments || []).forEach(c => {
            const cp = document.createElement('p');
            cp.className = 'comment-entry';
            const b = document.createElement('b');
            b.textContent = c.name + '：';
            cp.appendChild(b);
            cp.appendChild(document.createTextNode(c.text));
            bd.appendChild(cp);
        });

        cell.appendChild(hd);
        cell.appendChild(bd);
        bindMenu();
        return cell;
    }

    /* ---- 按数据重建朋友圈动态列表 ---- */
    function renderPosts(posts) {
        const root = document.getElementById('moments');
        if (!root) return false;
        const pswp = root.querySelector('.pswp');
        root.querySelectorAll('.moments__post').forEach(el => el.remove());
        posts.forEach(p => root.insertBefore(buildPost(p), pswp));
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
        post.scrollIntoView({ block: 'center' });
        return true;
    }

    window.__wxMoments = {
        renderPosts,
        openCompose,
        closeCompose,
        submit,
    };
})();