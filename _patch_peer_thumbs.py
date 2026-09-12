# -*- coding: utf-8 -*-
# 对方主页朋友圈缩略图改为从人物实际动态取图（p.posts → 场景 moments 同名 author → momentsThumbs 兜底）
import io

P = r'enhance\peer_pages.js'
s = io.open(P, encoding='utf-8').read()

old = """        // 朋友圈缩略图（参考视频：最多 5 张，74px 方图）
        const thumbs = root.querySelector('.wpp-moments-cell .wpp-thumbs');
        thumbs.innerHTML = '';
        (p.momentsThumbs || []).slice(0, 5).forEach((src) => {
            const im = el('img');
            im.src = src;
            thumbs.appendChild(im);
        });"""

new = """        // 朋友圈缩略图（参考视频：最多 5 张，74px 方图）
        // 与人物实际朋友圈联动，保证脚本前后一致：
        //   1) 人物自己的动态 p.posts（对方朋友圈页同一数据源）
        //   2) 全场景朋友圈里 author==本人物名的帖子（脚本跑视频前加入的图片）
        //   3) 显式 momentsThumbs 兜底（旧脚本兼容）
        const thumbs = root.querySelector('.wpp-moments-cell .wpp-thumbs');
        thumbs.innerHTML = '';
        const thumbSrcs = (function () {
            const out = [];
            const push = function (src) {
                src = String(src || '');
                if (src && out.indexOf(src) < 0) out.push(src);
            };
            const fromPosts = function (posts) {
                (posts || []).forEach(function (post) {
                    const v = postVideo(post);
                    if (v && v.cover) push(v.cover);
                    (post.images || []).forEach(function (im) {
                        push(typeof im === 'string' ? im : (im && (im.src || im.url || '')));
                    });
                });
            };
            fromPosts(p.posts);
            if (!out.length && p.name && window.__wxConfig &&
                    typeof window.__wxConfig.getMomentsPosts === 'function') {
                const all = window.__wxConfig.getMomentsPosts();
                if (Array.isArray(all)) {
                    fromPosts(all.filter(function (m) {
                        return String((m && (m.author || m.name)) || '') === p.name;
                    }));
                }
            }
            if (!out.length) (p.momentsThumbs || []).forEach(push);
            return out;
        })();
        thumbSrcs.slice(0, 5).forEach((src) => {
            const im = el('img');
            im.src = src;
            thumbs.appendChild(im);
        });"""

assert old in s and new not in s
s = s.replace(old, new, 1)
io.open(P, 'w', encoding='utf-8').write(s)
print('patched')
