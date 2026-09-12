/*!
 * 朋友圈设置面板（moments_editor.js）
 * ---------------------------------------------------------------------------
 * 用途：工作流编辑器「⚙ 离线解析 / 🤖 AI 转译」后，如果解析出来的流程里
 *       有「进入朋友圈 / 进入对方朋友圈」，自动弹出本面板，让你：
 *         ① 全面编辑朋友圈内容（我的 / 对方，增删排序、文案、时间、配图、视频、点赞、评论）；
 *         ② 对每一张图 / 每一个视频单独决定「进朋友圈后打开它，停留多少秒」。
 *       点「应用到流程」后，内容写回 scene.json，并在 steps 里生成/更新一段
 *       朋友圈演示段： [编辑朋友圈] → [进入朋友圈] → [向下滚动] → [点开图片]/[播放视频]。
 *
 * 独立命名空间 window.__wxMomentsEditor，样式统一用 wxm- 前缀，避免污染页面。
 * 图片挑选走 editor/shared_picker.js 的 window.__wxPick.openPicker（有则用，无则手填路径）。
 */
(function () {
  'use strict';
  if (window.__wxMomentsEditor) return;

  /* ======================= 常量 ======================= */

  const DEFAULT_IMG_HOLD = 0.3;      // 与 main.py VIEW_IMAGE_HOLD_DEFAULT 对齐
  const DEFAULT_VID_HOLD = 1.5;      // 视频留空时后端按真实时长（最多 6s）自动决定
  const STEP_TAG = '_wxm';           // 本面板生成的步骤标记（仅本会话有效，落盘时被剥离）

  /* ======================= 小工具 ======================= */

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function num(v) {
    if (v === '' || v === null || v === undefined) return null;
    const n = Number(v);
    return isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null;
  }
  function fmtSec(v) {
    return num(v) == null ? '' : String(num(v));
  }
  function clone(o) {
    try { return JSON.parse(JSON.stringify(o)); } catch (e) { return null; }
  }
  function txt(v) { return String(v == null ? '' : v); }
  function arr(v) { return Array.isArray(v) ? v : []; }

  /* ======================= 数据归一化 ======================= */

  /* 单条动态 → 面板内部结构 */
  function normPost(raw) {
    const p = raw && typeof raw === 'object' ? raw : {};
    let video = p.video, cover = p.cover || '';
    if (video && typeof video === 'object') {           // {src, cover}
      cover = video.cover || video.poster || cover;
      video = video.src || video.视频 || '';
    }
    const images = arr(p.images).map((u) => (typeof u === 'string' ? u : (u && u.src) || '')).filter(Boolean);
    const holds = arr(p.imgHolds);
    return {
      author: txt(p.author || p.作者),
      avatar: txt(p.avatar || p.头像),
      text: txt(p.text || p.文案 || p.内容),
      time: txt(p.time || p.时间),
      source: txt(p.source || p.来源),
      images: images,
      imgHolds: images.map((_, j) => num(holds[j])),
      video: txt(video),
      cover: txt(cover),
      videoHold: num(p.videoHold),
      likes: arr(p.likes || p.点赞).map((x) => txt(typeof x === 'string' ? x : (x && x.name) || '')).filter(Boolean),
      comments: arr(p.comments || p.评论).map((c) => ({
        name: txt(c && (c.name || c.用户 || c.人)),
        text: txt(c && (c.text || c.内容))
      })).filter((c) => c.name || c.text)
    };
  }

  /* 面板内部结构 → 运行端数据（去掉空字段，保留 imgHolds / videoHold 供下次还原） */
  function dumpPost(p) {
    const out = {};
    const putIf = (k, v) => { if (v !== '' && v !== null && v !== undefined && !(Array.isArray(v) && !v.length)) out[k] = v; };
    putIf('author', p.author);
    putIf('avatar', p.avatar);
    putIf('text', p.text);
    putIf('time', p.time);
    putIf('source', p.source);
    putIf('images', p.images.slice());
    const holds = p.images.map((_, j) => num(p.imgHolds[j]));
    if (holds.some((h) => h != null)) out.imgHolds = holds;      // 只有真的设了才写，避免脏数据
    putIf('video', p.video);
    putIf('cover', p.video ? p.cover : '');
    if (p.video && num(p.videoHold) != null) out.videoHold = num(p.videoHold);
    putIf('likes', p.likes.slice());
    putIf('comments', p.comments.map((c) => ({ name: c.name, text: c.text })).filter((c) => c.name || c.text));
    return out;
  }

  /* 对方资料 → 面板内部结构（只取本面板关心的字段，其余原样保留回写） */
  function normPeer(raw) {
    const o = raw && typeof raw === 'object' ? raw : {};
    return {
      _raw: o,
      name: txt(o.name || o.昵称),
      avatar: txt(o.avatar || o.头像),
      cover: txt(o.cover || o.封面),
      signature: txt(o.signature || o.签名),
      posts: arr(o.posts || o.动态).map(normPost)
    };
  }
  function dumpPeer(pe) {
    const out = Object.assign({}, pe._raw);
    out.name = pe.name;
    out.avatar = pe.avatar;
    out.cover = pe.cover;
    out.signature = pe.signature;
    out.posts = pe.posts.map(dumpPost);
    return out;
  }

  /* ======================= 状态 ======================= */

  let root = null;
  let st = null;          // { tab, me:[post], peer:{...}|null, onApply }

  /* ======================= 样式 ======================= */

  const STYLE = `
.wxm-mask{
  position:fixed; inset:0; z-index:9000; background:rgba(15,17,21,.42);
  backdrop-filter:blur(3px); display:flex; align-items:center; justify-content:center; padding:22px;
  font-family:"PingFang SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
.wxm-panel{
  width:min(1080px,100%); height:min(860px,100%); display:flex; flex-direction:column;
  background:var(--panel,#fff); color:var(--text,#1c1e22);
  border:1px solid var(--line,rgba(17,24,39,.08)); border-radius:16px;
  box-shadow:var(--shadow,0 24px 64px rgba(17,24,39,.16)); overflow:hidden;
}
.wxm-head{
  display:flex; align-items:center; gap:10px; padding:14px 18px;
  border-bottom:1px solid var(--line,rgba(17,24,39,.08)); background:var(--panel,#fff); flex:0 0 auto;
}
.wxm-title{ font-size:16px; font-weight:700; }
.wxm-sub{ font-size:12px; color:var(--muted,#5c616b); }
.wxm-sp{ flex:1 1 auto; }
.wxm-close{
  width:30px; height:30px; border-radius:8px; border:1px solid var(--line-strong,rgba(17,24,39,.16));
  background:var(--panel-2,#f2f3f6); color:var(--muted,#5c616b); cursor:pointer; font-size:14px; line-height:1;
}
.wxm-close:hover{ background:var(--panel-3,#e9ebef); color:var(--text,#1c1e22); }

.wxm-tabs{ display:flex; gap:8px; padding:10px 18px 0; flex:0 0 auto; }
.wxm-tabs button{
  border:1px solid var(--line,rgba(17,24,39,.08)); border-bottom:none;
  background:var(--panel-2,#f2f3f6); color:var(--muted,#5c616b);
  padding:8px 16px; border-radius:10px 10px 0 0; cursor:pointer; font-size:13px; font-weight:600;
}
.wxm-tabs button b{
  display:inline-block; min-width:18px; padding:0 5px; margin-left:5px; border-radius:9px;
  background:var(--line,rgba(17,24,39,.08)); font-size:11px; font-weight:700;
}
.wxm-tabs button.on{ background:var(--panel,#fff); color:var(--accent,#0aac5f); border-color:var(--line-strong,rgba(17,24,39,.16)); }
.wxm-tabs button.on b{ background:var(--accent-soft,rgba(10,172,95,.10)); color:var(--accent,#0aac5f); }

.wxm-body{ flex:1 1 auto; overflow:auto; padding:14px 18px; background:var(--panel,#fff); border-top:1px solid var(--line-strong,rgba(17,24,39,.16)); }

.wxm-card{
  border:1px solid var(--line,rgba(17,24,39,.08)); border-radius:12px; background:var(--panel,#fff);
  box-shadow:var(--shadow-soft,0 6px 20px rgba(17,24,39,.06)); padding:12px; margin-bottom:12px;
}
.wxm-card > .wxm-row{ margin-bottom:8px; }

.wxm-rowline{ display:flex; align-items:center; gap:8px; }
.wxm-label{ font-size:12px; color:var(--muted,#5c616b); white-space:nowrap; }

.wxm-in, .wxm-ta{
  width:100%; border:1px solid var(--line-strong,rgba(17,24,39,.16)); border-radius:9px;
  background:var(--field,#f7f8fa); color:var(--text,#1c1e22); font-size:13px; padding:7px 9px;
  font-family:inherit; outline:none;
}
.wxm-in:focus, .wxm-ta:focus{ border-color:var(--accent-border,rgba(10,172,95,.38)); background:var(--panel,#fff); }
.wxm-ta{ resize:vertical; min-height:52px; line-height:1.55; }
.wxm-in::placeholder, .wxm-ta::placeholder{ color:var(--muted-2,#9095a0); }

.wxm-post{ border:1px solid var(--line,rgba(17,24,39,.08)); border-radius:12px; background:var(--panel-2,#f2f3f6); padding:10px; margin-bottom:10px; }
.wxm-post.acting{ border-color:var(--accent-border,rgba(10,172,95,.38)); box-shadow:0 0 0 2px var(--accent-soft,rgba(10,172,95,.10)); }
.wxm-ph{ display:flex; align-items:center; gap:6px; margin-bottom:8px; }
.wxm-no{
  width:22px; height:22px; flex:0 0 auto; border-radius:6px; background:var(--accent-soft,rgba(10,172,95,.10));
  color:var(--accent,#0aac5f); font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:center;
}
.wxm-ib{
  width:26px; height:26px; border-radius:7px; border:1px solid var(--line-strong,rgba(17,24,39,.16));
  background:var(--panel,#fff); color:var(--muted,#5c616b); cursor:pointer; font-size:12px; line-height:1; flex:0 0 auto;
}
.wxm-ib:hover{ background:var(--panel-3,#e9ebef); color:var(--text,#1c1e22); }
.wxm-ib.danger:hover{ background:var(--red-soft,rgba(213,73,65,.10)); color:var(--red,#d54941); border-color:var(--red-line,rgba(213,73,65,.32)); }

.wxm-imgs{ display:flex; flex-wrap:wrap; gap:8px; margin:8px 0; }
.wxm-tile{
  width:112px; border:1px solid var(--line-strong,rgba(17,24,39,.16)); border-radius:10px;
  background:var(--panel,#fff); overflow:hidden;
}
.wxm-tile.on{ border-color:var(--accent-border,rgba(10,172,95,.38)); box-shadow:0 0 0 2px var(--accent-soft,rgba(10,172,95,.10)); }
.wxm-thumb{
  position:relative; width:100%; height:84px; background:var(--panel-3,#e9ebef); cursor:pointer;
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}
.wxm-thumb img{ width:100%; height:100%; object-fit:cover; display:block; }
.wxm-thumb .wxm-ph-hint{ font-size:11px; color:var(--muted-2,#9095a0); padding:0 6px; text-align:center; }
.wxm-thumb .wxm-x{
  position:absolute; top:3px; right:3px; width:20px; height:20px; border-radius:6px; border:none;
  background:rgba(15,17,21,.62); color:#fff; font-size:11px; cursor:pointer; line-height:1;
}
.wxm-tile-foot{ padding:6px; display:flex; flex-direction:column; gap:5px; }
.wxm-check{ display:flex; align-items:center; gap:5px; font-size:12px; color:var(--muted,#5c616b); cursor:pointer; }
.wxm-check input{ accent-color:var(--accent,#0aac5f); width:14px; height:14px; margin:0; }
.wxm-sec{ display:flex; align-items:center; gap:4px; font-size:12px; color:var(--muted,#5c616b); }
.wxm-sec input{
  width:100%; border:1px solid var(--line-strong,rgba(17,24,39,.16)); border-radius:7px;
  background:var(--field,#f7f8fa); padding:4px 6px; font-size:12px; color:var(--text,#1c1e22); font-family:inherit;
}
.wxm-add{
  width:112px; min-height:112px; border:1px dashed var(--line-strong,rgba(17,24,39,.16)); border-radius:10px;
  background:transparent; color:var(--muted,#5c616b); cursor:pointer; font-size:12px; line-height:1.5;
}
.wxm-add:hover{ border-color:var(--accent-border,rgba(10,172,95,.38)); color:var(--accent,#0aac5f); background:var(--accent-soft,rgba(10,172,95,.10)); }

.wxm-vidbox{
  display:flex; gap:10px; align-items:flex-start; border:1px solid var(--line-strong,rgba(17,24,39,.16));
  border-radius:10px; background:var(--panel,#fff); padding:8px; margin:8px 0;
}
.wxm-vidbox.on{ border-color:var(--accent-border,rgba(10,172,95,.38)); box-shadow:0 0 0 2px var(--accent-soft,rgba(10,172,95,.10)); }
.wxm-vidthumb{
  position:relative; width:96px; height:72px; flex:0 0 auto; border-radius:8px; overflow:hidden;
  background:var(--panel-3,#e9ebef); display:flex; align-items:center; justify-content:center; cursor:pointer;
}
.wxm-vidthumb img{ width:100%; height:100%; object-fit:cover; }
.wxm-vidthumb .wxm-play{
  position:absolute; width:26px; height:26px; border-radius:50%; background:rgba(15,17,21,.55); color:#fff;
  font-size:11px; display:flex; align-items:center; justify-content:center;
}
.wxm-vidmain{ flex:1 1 auto; display:flex; flex-direction:column; gap:6px; min-width:0; }

.wxm-sect{ font-size:12px; font-weight:700; color:var(--muted,#5c616b); margin:14px 0 8px; }
.wxm-empty{ color:var(--muted-2,#9095a0); font-size:13px; text-align:center; padding:34px 12px; }
.wxm-hint{ font-size:12px; color:var(--muted,#5c616b); line-height:1.6; }
.wxm-hint code{ background:var(--panel-2,#f2f3f6); border:1px solid var(--line,rgba(17,24,39,.08)); border-radius:5px; padding:1px 5px; font-size:11px; }
.wxm-warn{ color:var(--amber,#b9791e); }

.wxm-cmt{ display:flex; gap:6px; margin-top:6px; }
.wxm-cmt input{ flex:1 1 auto; }

.wxm-foot{
  flex:0 0 auto; display:flex; align-items:center; gap:10px; padding:12px 18px;
  border-top:1px solid var(--line,rgba(17,24,39,.08)); background:var(--panel-2,#f2f3f6);
}
.wxm-btn{
  border:1px solid var(--line-strong,rgba(17,24,39,.16)); border-radius:9px; background:var(--panel,#fff);
  color:var(--text,#1c1e22); font-size:13px; font-weight:600; padding:8px 16px; cursor:pointer; font-family:inherit;
}
.wxm-btn:hover{ background:var(--panel-3,#e9ebef); }
.wxm-btn.primary{ background:var(--accent,#0aac5f); border-color:var(--accent,#0aac5f); color:#fff; }
.wxm-btn.primary:hover{ background:var(--accent-strong,#0a9d57); }
.wxm-btn.ghost{ background:transparent; }
@media (max-width:760px){
  .wxm-panel{ height:100%; }
  .wxm-sub{ display:none; }
}
`;

  function injectStyles() {
    if (document.getElementById('wxm-style')) return;
    const el = document.createElement('style');
    el.id = 'wxm-style';
    el.textContent = STYLE;
    document.head.appendChild(el);
  }

  /* ======================= 媒体挑选 ======================= */

  function pickImage(current, cb) {
    const P = window.__wxPick;
    if (P && typeof P.openPicker === 'function') {
      P.openPicker({ current: current || '', onPick: (path) => cb(path) });
      return;
    }
    const v = window.prompt('填写图片路径（如 /images/peer/xxx.jpg）：', current || '');
    if (v !== null) cb(String(v).trim());
  }

  /* 视频素材：/api/gallery 下发的 videos（vue-WeChat/public/videos 里的 mp4）。
     懒加载一次，失败就退回手填路径。 */
  let galleryVideos = null;
  function ensureVideos(cb) {
    if (galleryVideos) { cb(galleryVideos); return; }
    fetch('/api/gallery')
      .then((r) => r.json())
      .then((d) => {
        galleryVideos = arr(d && d.videos).filter((v) => v && v.path);
        cb(galleryVideos);
      })
      .catch(() => { galleryVideos = []; cb(galleryVideos); });
  }
  function askVideo(current, cb) {
    ensureVideos((list) => {
      if (!list.length) {
        const v = window.prompt(
          '还没有视频素材。填写视频路径（如 /videos/_test.mp4，也可填 http 地址）：', current || '');
        if (v !== null) cb(String(v).trim());
        return;
      }
      const cur = list.findIndex((v) => v.path === current);
      const lines = list.map((v, i) => (i + 1) + '. ' + v.name + '  (' + v.path + ')');
      const ans = window.prompt(
        '选择视频素材（填序号，留空=手动输入路径）：\n' + lines.join('\n'), cur >= 0 ? String(cur + 1) : '');
      if (ans === null) return;
      const s = ans.trim();
      if (!s) {
        const v = window.prompt('填写视频路径（如 /videos/_test.mp4，也可填 http 地址）：', current || '');
        if (v !== null) cb(String(v).trim());
        return;
      }
      const n = parseInt(s, 10);
      if (n >= 1 && n <= list.length) cb(list[n - 1].path);
    });
  }

  /* ======================= 渲染 ======================= */

  function currentPosts() {
    if (st.tab === 'me') return st.me;
    return st.peer ? st.peer.posts : [];
  }

  function hasWatch(p) {
    if (p.video && num(p.videoHold) != null) return true;
    return p.images.some((_, j) => num(p.imgHolds[j]) != null);
  }
  function watchCount(list) {
    return list.filter(hasWatch).length;
  }

  function renderTile(p, i, j) {
    const img = p.images[j];
    const on = num(p.imgHolds[j]) != null;
    return '' +
      '<div class="wxm-tile' + (on ? ' on' : '') + '">' +
        '<div class="wxm-thumb" data-op="pickimg" data-i="' + i + '" data-j="' + j + '" title="点击换图">' +
          (img ? '<img src="' + esc(img) + '" alt="" onerror="this.style.opacity=.2">' : '<span class="wxm-ph-hint">点击选图</span>') +
          '<button type="button" class="wxm-x" data-op="delimg" data-i="' + i + '" data-j="' + j + '" title="删掉这张">✕</button>' +
        '</div>' +
        '<div class="wxm-tile-foot">' +
          '<label class="wxm-check"><input type="checkbox" data-op="imgopen" data-i="' + i + '" data-j="' + j + '"' +
            (on ? ' checked' : '') + '> 打开这张</label>' +
          '<span class="wxm-sec">看 <input type="number" min="0" step="0.1" data-op="imgsec" data-i="' + i +
            '" data-j="' + j + '" value="' + esc(fmtSec(p.imgHolds[j])) + '" placeholder="' + DEFAULT_IMG_HOLD + '"> 秒</span>' +
        '</div>' +
      '</div>';
  }

  function renderVideo(p, i) {
    const on = num(p.videoHold) != null;
    return '' +
      '<div class="wxm-vidbox' + (on ? ' on' : '') + '">' +
        '<div class="wxm-vidthumb" data-op="pickcover" data-i="' + i + '" title="点击选封面">' +
          (p.cover ? '<img src="' + esc(p.cover) + '" alt="" onerror="this.style.opacity=.2">' : '<span class="wxm-ph-hint">封面</span>') +
          '<span class="wxm-play">▶</span>' +
        '</div>' +
        '<div class="wxm-vidmain">' +
          '<div class="wxm-rowline">' +
            '<span class="wxm-label">视频</span>' +
            '<input class="wxm-in" data-op="vidpath" data-i="' + i + '" value="' + esc(p.video) + '" placeholder="/videos/xxx.mp4">' +
            '<button type="button" class="wxm-ib" data-op="pickvid" data-i="' + i + '" title="从视频素材里选">🎞</button>' +
            '<button type="button" class="wxm-ib" data-op="delvid" data-i="' + i + '" title="删掉这条视频">✕</button>' +
          '</div>' +
          '<div class="wxm-rowline">' +
            '<label class="wxm-check"><input type="checkbox" data-op="vidopen" data-i="' + i + '"' +
              (on ? ' checked' : '') + '> 打开播放</label>' +
            '<span class="wxm-sec">看 <input type="number" min="0" step="0.1" data-op="vidsec" data-i="' + i +
              '" value="' + esc(fmtSec(p.videoHold)) + '" placeholder="' + DEFAULT_VID_HOLD + '"> 秒（留空＝按视频真实时长）</span>' +
          '</div>' +
        '</div>' +
      '</div>';
  }

  function renderPost(p, i) {
    const on = hasWatch(p);
    let h = '<article class="wxm-post' + (on ? ' acting' : '') + '" data-i="' + i + '">' +
      '<div class="wxm-ph">' +
        '<span class="wxm-no">' + (i + 1) + '</span>' +
        '<input class="wxm-in" style="max-width:180px" data-op="time" data-i="' + i + '" value="' + esc(p.time) + '" placeholder="时间，如 35分钟前">' +
        '<span class="wxm-sp"></span>' +
        '<button type="button" class="wxm-ib" data-op="up" data-i="' + i + '" title="上移">↑</button>' +
        '<button type="button" class="wxm-ib" data-op="down" data-i="' + i + '" title="下移">↓</button>' +
        '<button type="button" class="wxm-ib" data-op="dup" data-i="' + i + '" title="复制这条">⧉</button>' +
        '<button type="button" class="wxm-ib danger" data-op="delpost" data-i="' + i + '" title="删除这条">✕</button>' +
      '</div>' +
      '<textarea class="wxm-ta" data-op="text" data-i="' + i + '" placeholder="动态文案">' + esc(p.text) + '</textarea>';

    // 配图
    h += '<div class="wxm-imgs">';
    p.images.forEach((_, j) => { h += renderTile(p, i, j); });
    if (p.images.length < 9) {
      h += '<button type="button" class="wxm-add" data-op="addimg" data-i="' + i + '">＋ 添加图片<br><span style="font-size:11px">最多 9 张</span></button>';
    }
    h += '</div>';

    // 视频
    if (p.video) h += renderVideo(p, i);
    else h += '<div class="wxm-rowline" style="margin:6px 0"><button type="button" class="wxm-btn ghost" data-op="addvid" data-i="' + i + '">▶ 加视频（把这条变成视频动态）</button></div>';

    // 点赞 / 评论（我的朋友圈也支持）
    h += '<div class="wxm-sect" style="margin:10px 0 6px">点赞 · 评论</div>' +
      '<input class="wxm-in" data-op="likes" data-i="' + i + '" value="' + esc(p.likes.join('、')) + '" placeholder="点赞的人（顿号分隔，如：香儿、阿伟）">' +
      '<div style="margin-top:6px">';
    p.comments.forEach((c, j) => {
      h += '<div class="wxm-cmt">' +
        '<input class="wxm-in" style="flex:0 0 110px" data-op="cmtname" data-i="' + i + '" data-j="' + j + '" value="' + esc(c.name) + '" placeholder="谁说的">' +
        '<input class="wxm-in" data-op="cmttext" data-i="' + i + '" data-j="' + j + '" value="' + esc(c.text) + '" placeholder="评论内容">' +
        '<button type="button" class="wxm-ib danger" data-op="delcmt" data-i="' + i + '" data-j="' + j + '" title="删掉这条评论">✕</button>' +
        '</div>';
    });
    h += '</div>' +
      '<div class="wxm-rowline" style="margin-top:6px"><button type="button" class="wxm-btn ghost" data-op="addcmt" data-i="' + i + '">＋ 加评论</button></div>';

    h += '</article>';
    return h;
  }

  function renderMe() {
    let h = '<div class="wxm-card">' +
      '<div class="wxm-hint">这里是<b>我的朋友圈</b>（脚本里 <code>[进入朋友圈]</code> 看到的那一页）。' +
      '每条动态下方的「打开这张 / 打开播放 + 秒数」决定进朋友圈后<b>点开哪张图、哪个视频，各看多久</b>；不勾就是不打开。</div>' +
      '</div>';
    if (!st.me.length) {
      h += '<div class="wxm-empty">还没有动态，点下面「＋ 新建动态」开始编排。</div>';
    }
    st.me.forEach((p, i) => { h += renderPost(p, i); });
    h += '<div class="wxm-rowline"><button type="button" class="wxm-btn primary" data-op="addpost">＋ 新建动态</button></div>';
    return h;
  }

  function renderPeer() {
    const pe = st.peer;
    let h = '';
    if (!pe) {
      h += '<div class="wxm-empty">流程里没有配置「对方朋友圈」。<br>点下面按钮新建一份，编辑好后一起写进流程。</div>' +
        '<div class="wxm-rowline"><button type="button" class="wxm-btn primary" data-op="newpeer">＋ 新建对方朋友圈</button></div>';
      return h;
    }
    h += '<div class="wxm-card">' +
      '<div class="wxm-hint">这里是<b>对方朋友圈</b>（脚本里 <code>[进入对方朋友圈]</code> 看到的那一页）。' +
      '「打开这张 / 打开播放 + 秒数」同样决定点开哪个、看多久。</div>' +
      '<div class="wxm-rowline" style="margin-top:10px">' +
        '<span class="wxm-label">昵称</span><input class="wxm-in" data-op="peername" value="' + esc(pe.name) + '" placeholder="对方昵称">' +
      '</div>' +
      '<div class="wxm-rowline" style="margin-top:8px">' +
        '<span class="wxm-label">头像</span>' +
        '<input class="wxm-in" data-op="peeravatar" value="' + esc(pe.avatar) + '" placeholder="/images/avatar/xxx.png">' +
        '<button type="button" class="wxm-ib" data-op="pickpeeravatar" title="从图库选">🖼</button>' +
      '</div>' +
      '<div class="wxm-rowline" style="margin-top:8px">' +
        '<span class="wxm-label">封面</span>' +
        '<input class="wxm-in" data-op="peercover" value="' + esc(pe.cover) + '" placeholder="/images/xxx.jpg">' +
        '<button type="button" class="wxm-ib" data-op="pickpeercover" title="从图库选">🖼</button>' +
      '</div>' +
      '<div class="wxm-rowline" style="margin-top:8px">' +
        '<span class="wxm-label">签名</span><input class="wxm-in" data-op="peersign" value="' + esc(pe.signature) + '" placeholder="个性签名">' +
      '</div>' +
      '</div>';
    if (!pe.posts.length) {
      h += '<div class="wxm-empty">这个人的朋友圈还没有动态。</div>';
    }
    pe.posts.forEach((p, i) => { h += renderPost(p, i); });
    h += '<div class="wxm-rowline"><button type="button" class="wxm-btn primary" data-op="addpost">＋ 新建动态</button></div>';
    return h;
  }

  function render() {
    if (!root) return;
    const list = currentPosts();
    const n = watchCount(list);
    root.querySelector('.wxm-tabs').innerHTML =
      '<button type="button" data-op="tab" data-tab="me" class="' + (st.tab === 'me' ? 'on' : '') + '">我的朋友圈 <b>' + st.me.length + '</b></button>' +
      '<button type="button" data-op="tab" data-tab="peer" class="' + (st.tab === 'peer' ? 'on' : '') + '">对方朋友圈 <b>' + (st.peer ? st.peer.posts.length : 0) + '</b></button>';
    root.querySelector('.wxm-body').innerHTML = st.tab === 'me' ? renderMe() : renderPeer();

    let foot = '<span class="wxm-hint">当前「' + (st.tab === 'me' ? '我的朋友圈' : '对方朋友圈') + '」有 <b>' + n +
      '</b> 条动态会被打开演示。应用后会写入场景，并在流程里生成/更新：' +
      '<code>编辑朋友圈</code> + <code>进入朋友圈</code> → <code>向下滚动</code> → <code>点开图片 / 播放视频（带停留秒数）</code>。<br>' +
      '<label class="wxm-check" style="display:inline-flex;margin-top:4px">' +
        '<input type="checkbox" data-op="takeover"' + (st.takeover ? ' checked' : '') + '>' +
        '接管流程里已有的朋友圈动作（<code>进入朋友圈</code>／<code>向下滚动</code>／<code>点开图片</code>／<code>播放视频</code>…会被替换成上面这段，避免重复两遍）' +
      '</label></span>';
    if (st.tab === 'peer' && st.peer && !st.peer.name.trim()) {
      foot = '<span class="wxm-hint wxm-warn">⚠ 请先填「对方昵称」，否则无法写进流程。</span>';
    }
    foot += '<span class="wxm-sp"></span>' +
      '<button type="button" class="wxm-btn ghost" data-op="cancel">取消</button>' +
      '<button type="button" class="wxm-btn" data-op="saveonly">💾 只保存内容</button>' +
      '<button type="button" class="wxm-btn primary" data-op="apply">✅ 应用到流程</button>';
    root.querySelector('.wxm-foot').innerHTML = foot;
  }

  /* ======================= 交互 ======================= */

  function onInput(ev) {
    const t = ev.target;
    const op = t.dataset && t.dataset.op;
    if (!op) return;
    const i = t.dataset.i !== undefined ? Number(t.dataset.i) : -1;
    const j = t.dataset.j !== undefined ? Number(t.dataset.j) : -1;
    const posts = currentPosts();

    if (st.tab === 'peer' && st.peer) {
      if (op === 'peername') { st.peer.name = t.value; return; }
      if (op === 'peeravatar') { st.peer.avatar = t.value; return; }
      if (op === 'peercover') { st.peer.cover = t.value; return; }
      if (op === 'peersign') { st.peer.signature = t.value; return; }
    }
    const p = posts[i];
    if (!p) return;
    switch (op) {
      case 'time': p.time = t.value; break;
      case 'text': p.text = t.value; break;
      case 'likes':
        p.likes = t.value.split(/[、,，;；]+/).map((x) => x.trim()).filter(Boolean);
        break;
      case 'vidpath': p.video = t.value; break;
      case 'video-cov':
      case 'cover': p.cover = t.value; break;
      case 'cmtname': if (p.comments[j]) p.comments[j].name = t.value; break;
      case 'cmttext': if (p.comments[j]) p.comments[j].text = t.value; break;
      case 'imgsec': {
        const v = num(t.value);
        p.imgHolds[j] = v;
        break;
      }
      case 'vidsec': p.videoHold = num(t.value); break;
      case 'imgopen':
        if (t.checked) p.imgHolds[j] = num(p.imgHolds[j]) || DEFAULT_IMG_HOLD;
        else p.imgHolds[j] = null;
        render(); return;
      case 'vidopen':
        if (t.checked) p.videoHold = num(p.videoHold) || DEFAULT_VID_HOLD;
        else p.videoHold = null;
        render(); return;
      default: break;
    }
    // 勾选框样式跟随「这条路会不会被打开」实时更新（不整块重绘，避免输入焦点丢失）
    syncMarks(i);
  }

  /* 轻量同步：只改 tile / vidbox 的高亮与勾选态，不动输入框 */
  function syncMarks(i) {
    const p = currentPosts()[i];
    const card = root && root.querySelector('.wxm-post[data-i="' + i + '"]');
    if (!p || !card) return;
    card.classList.toggle('acting', hasWatch(p));
    card.querySelectorAll('[data-op="imgopen"]').forEach((cb) => {
      const j = Number(cb.dataset.j);
      const on = num(p.imgHolds[j]) != null;
      cb.checked = on;
      const tile = cb.closest('.wxm-tile');
      if (tile) tile.classList.toggle('on', on);
    });
    const vcb = card.querySelector('[data-op="vidopen"]');
    if (vcb) {
      const on = !!p.video && num(p.videoHold) != null;
      vcb.checked = on;
      const box = vcb.closest('.wxm-vidbox');
      if (box) box.classList.toggle('on', on);
    }
  }

  function onClick(ev) {
    const btn = ev.target.closest('[data-op]');
    if (!btn) {
      // 点遮罩空白处不关闭，避免误触丢失编辑
      return;
    }
    const op = btn.dataset.op;
    const i = btn.dataset.i !== undefined ? Number(btn.dataset.i) : -1;
    const j = btn.dataset.j !== undefined ? Number(btn.dataset.j) : -1;
    const posts = currentPosts();

    if (op === 'tab') { st.tab = btn.dataset.tab; render(); return; }
    if (op === 'takeover') { st.takeover = !!btn.checked; render(); return; }
    if (op === 'cancel') { close(); return; }
    if (op === 'apply' || op === 'saveonly') { doApply(op === 'apply'); return; }
    if (op === 'newpeer') {
      st.peer = { _raw: {}, name: '', avatar: '', cover: '', signature: '', posts: [] };
      render(); return;
    }
    if (st.tab === 'peer' && st.peer) {
      if (op === 'pickpeeravatar') {
        pickImage(st.peer.avatar, (p) => { st.peer.avatar = p; render(); });
        return;
      }
      if (op === 'pickpeercover') {
        pickImage(st.peer.cover, (p) => { st.peer.cover = p; render(); });
        return;
      }
    }

    const p = posts[i];
    if (!p && op !== 'addpost') return;

    switch (op) {
      case 'addpost':
        posts.push(normPost({ time: '', text: '' }));
        render(); break;
      case 'delpost':
        if (!confirm('删除第 ' + (i + 1) + ' 条动态？')) return;
        posts.splice(i, 1); render(); break;
      case 'dup': {
        const copy = clone(p) || normPost(p);
        posts.splice(i + 1, 0, copy); render(); break;
      }
      case 'up': if (i > 0) { const [x] = posts.splice(i, 1); posts.splice(i - 1, 0, x); render(); } break;
      case 'down': if (i < posts.length - 1) { const [x] = posts.splice(i, 1); posts.splice(i + 1, 0, x); render(); } break;
      case 'addimg':
        pickImage('', (path) => {
          if (!path) return;
          p.images.push(path);
          p.imgHolds.push(null);
          render();
        });
        break;
      case 'delimg':
        p.images.splice(j, 1); p.imgHolds.splice(j, 1); render(); break;
      case 'pickimg':
        pickImage(p.images[j], (path) => { if (path) { p.images[j] = path; } render(); });
        break;
      case 'addvid':
        askVideo('', (path) => {
          p.video = path || '/videos/_test.mp4';
          p.videoHold = null;
          render();
        });
        break;
      case 'pickvid':
        askVideo(p.video, (path) => { if (path) p.video = path; render(); });
        break;
      case 'delvid':
        p.video = ''; p.cover = ''; p.videoHold = null; render(); break;
      case 'pickcover':
        pickImage(p.cover, (path) => { p.cover = path; render(); });
        break;
      case 'addcmt':
        p.comments.push({ name: '', text: '' }); render(); break;
      case 'delcmt':
        p.comments.splice(j, 1); render(); break;
      default: break;
    }
  }

  function onKey(ev) {
    if (ev.key === 'Escape' && root) { ev.stopPropagation(); close(); }
  }

  /* ======================= 生成步骤 ======================= */

  /* 每个媒体在朋友圈列表里的落点：图片 = 第几条动态 + 第几张；视频 = 第几个视频动态 */
  function mediaTargets(posts) {
    const out = [];
    const videoOrdinal = {};
    let n = 0;
    posts.forEach((p, i) => { if (p.video) { n += 1; videoOrdinal[i] = n; } });
    posts.forEach((p, i) => {
      if (p.video && num(p.videoHold) != null) {
        out.push({ postIdx: i, type: 'video', sec: num(p.videoHold), ordinal: videoOrdinal[i] });
      }
      p.images.forEach((_, j) => {
        if (num(p.imgHolds[j]) != null) {
          out.push({ postIdx: i, type: 'image', imgIdx: j, sec: num(p.imgHolds[j]) });
        }
      });
    });
    return out;
  }

  /* 生成「进朋友圈 → 滚到 → 打开」这一段；没有要打开的就不生成导航 */
  function buildDemoSteps(scope, posts) {
    const targets = mediaTargets(posts);
    if (!targets.length) return [];
    const steps = [];
    if (scope === 'me') {
      steps.push({ action: '进入朋友圈', params: {} });
    } else {
      steps.push({ action: '打开对方主页', params: {} });
      steps.push({ action: '进入对方朋友圈', params: {} });
    }
    // 滚动量：一条动态按 300px 估，目标动态落在视口中部；
    // 打开动作本身还会做一次 scrollIntoView 兜底，所以估偏不会点空。
    let scrolled = 0;
    targets.forEach((t) => {
      const need = Math.max(0, 300 * t.postIdx + 240);
      if (need > scrolled) {
        steps.push({ action: '向下滚动', params: { 像素: need - scrolled } });
        scrolled = need;
      }
      if (t.type === 'video') {
        steps.push({ action: '播放视频', params: { 序号: t.ordinal, 停留: t.sec } });
      } else {
        steps.push({ action: '点开图片', params: { 序号: (t.postIdx + 1) + ',' + (t.imgIdx + 1), 停留: t.sec } });
      }
    });
    steps.forEach((s) => { s[STEP_TAG] = 1; });
    return steps;
  }

  function doApply(withSteps) {
    const me = st.me.map(dumpPost);
    const peer = st.peer ? dumpPeer(st.peer) : null;
    if (st.peer && !st.peer.name.trim() && st.peer.posts.length) {
      alert('请先填「对方昵称」，否则对方朋友圈没法写进流程。');
      st.tab = 'peer';
      render();
      return;
    }
    const result = {
      me: me,
      peer: peer,
      takeover: st.takeover !== false,
      demo: {
        me: withSteps ? buildDemoSteps('me', st.me) : null,
        peer: withSteps && peer ? buildDemoSteps('peer', st.peer.posts) : null
      }
    };
    if (typeof st.onApply === 'function') {
      try { st.onApply(result); } catch (e) { /* 交给调用方处理 */ }
    }
    close();
  }

  /* ======================= 打开 / 关闭 ======================= */

  function open(opts) {
    opts = opts || {};
    injectStyles();
    st = {
      tab: opts.tab === 'peer' ? 'peer' : 'me',
      me: arr(opts.me).map(normPost),
      peer: opts.peer ? normPeer(opts.peer) : null,
      takeover: opts.takeover !== false,
      onApply: opts.onApply || null
    };
    if (root && root.parentNode) root.parentNode.removeChild(root);
    root = document.createElement('div');
    root.className = 'wxm-mask';
    root.innerHTML = '' +
      '<div class="wxm-panel" role="dialog" aria-label="朋友圈设置">' +
        '<div class="wxm-head">' +
          '<span class="wxm-title">🍩 朋友圈设置</span>' +
          '<span class="wxm-sub">编辑朋友圈内容 · 决定进朋友圈后打开哪张图 / 哪个视频、各看多久</span>' +
          '<span class="wxm-sp"></span>' +
          '<button type="button" class="wxm-close" data-op="cancel" title="关闭（Esc）">✕</button>' +
        '</div>' +
        '<div class="wxm-tabs"></div>' +
        '<div class="wxm-body"></div>' +
        '<div class="wxm-foot"></div>' +
      '</div>';
    document.body.appendChild(root);
    root.addEventListener('click', onClick);
    root.addEventListener('input', onInput);
    document.addEventListener('keydown', onKey, true);
    render();
    return true;
  }

  function close() {
    if (root && root.parentNode) root.parentNode.removeChild(root);
    root = null;
    st = null;
    document.removeEventListener('keydown', onKey, true);
  }

  /* ======================= 探测 ======================= */

  /* 流程 / 剧本里有没有朋友圈相关的内容？供调用方决定是否自动弹面板。
     返回 { me, peer, any } */
  function detect(steps, text) {
    const res = { me: false, peer: false, any: false };
    arr(steps).forEach((s) => {
      const a = s && s.action;
      if (!a) return;
      if (a === '进入朋友圈' || a === '编辑朋友圈' || a === '发朋友圈') { res.me = true; res.any = true; }
      if (a === '进入对方朋友圈' || a === '编辑对方资料') { res.peer = true; res.any = true; }
      if (a === '点开图片' || a === '播放视频' || a === '点赞' || a === '评论' ||
          a === '滚动到' || a === '打开对方主页') res.any = true;
    });
    const t = txt(text);
    if (/朋友圈/.test(t)) {
      res.any = true;
      const peerHit = /对方朋友圈|他的朋友圈|她的朋友圈|TA的朋友圈|对方主页/.test(t);
      if (peerHit) res.peer = true;
      if (/进入朋友圈|我的朋友圈|我方朋友圈|发朋友圈|编辑朋友圈/.test(t) || !peerHit) res.me = true;
    }
    return res;
  }

  window.__wxMomentsEditor = {
    open: open,
    close: close,
    isOpen: function () { return !!root; },
    detect: detect,
    buildDemoSteps: buildDemoSteps,
    STEP_TAG: STEP_TAG,
    DEFAULTS: { image: DEFAULT_IMG_HOLD, video: DEFAULT_VID_HOLD }
  };
})();
