/*!
 * 朋友圈预览面板（moments_preview.js）
 * ---------------------------------------------------------------------------
 * 用途：解析完剧本后，如果流程里有「打开对方主页 / 进入对方朋友圈 / 进入朋友圈」，
 *       直接在编辑器里预览**成片会拍到的真实画面**——内嵌 /wxpv/ 反代的 vue-WeChat
 *       真前端（与运行时同一套 enhance 层、同一份图片数据），并按剧本里的朋友圈
 *       动作序列「走一遍」（进入 → 滚动 → 点开图片 → 闪回聊天），用于在合成前
 *       检查整体合理性：哪张图会被点开、换人有没有换对人、滚动节奏对不对。
 *
 * 数据源（与运行时完全同源）：
 *   · 对方朋友圈  → peer_presets.json 里 [打开对方主页] 指到的人（或剧本 [编辑对方资料]）
 *   · 我的朋友圈  → scene.json moments（或剧本 [编辑朋友圈]）
 *   · 图片查看器  → 注入 enhance/human_actions.js（embed 默认不带，预览需要点图看大图）
 *
 * 依赖后端：GET /api/wxapp/status、POST /api/wxapp/start（8080 未起时自动拉起）、
 *           GET /api/scene、GET /api/peer-presets、/wxpv/ 反代。
 *
 * 独立命名空间 window.__wxMomentsPreview，样式前缀 wxmp-。
 */
(function () {
  'use strict';
  if (window.__wxMomentsPreview) return;

  /* ======================= 小工具 ======================= */

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  /* ======================= 剧本动作识别 ======================= */

  const NAV_ACTS = ['打开对方主页', '进入对方朋友圈', '进入朋友圈', '打开对方设置'];
  const PAGE_ACTS = ['向下滚动', '向上滚动', '滚动到', '点开图片', '播放视频'];
  const EXIT_ACTS = ['闪回聊天', '返回主页', '退出朋友圈', '打开聊天', '返回微信'];

  /* 扫描步骤，产出按顺序的朋友圈动作段：
     segments: [{ person, page:'peer'|'mine', items:[{action, params}] }] */
  function detect(steps) {
    const segments = [];
    let cur = null;              // 当前段
    let curChat = '';            // 最近一次 [打开聊天] 的联系人
    let peerOpen = '';           // 最近一次 [打开对方主页] 的人
    (steps || []).forEach((step) => {
      const act = step && step.action;
      const p = (step && step.params) || {};
      if (!act) return;
      if (act === '打开聊天') {
        curChat = String(p['联系人'] || '').trim();
        cur = null;
        return;
      }
      if (act === '打开对方主页') {
        peerOpen = String(p['对方'] || p['联系人'] || p['预设'] || '').trim() || curChat;
        cur = { person: peerOpen, page: 'peer', items: [] };
        cur.items.push({ action: act, params: p });
        segments.push(cur);
        return;
      }
      if (act === '进入对方朋友圈' || act === '打开对方设置') {
        if (!cur || cur.page !== 'peer') {
          cur = { person: peerOpen || curChat, page: 'peer', items: [] };
          segments.push(cur);
        }
        cur.items.push({ action: act, params: p });
        return;
      }
      if (act === '进入朋友圈') {
        cur = { person: '', page: 'mine', items: [{ action: act, params: p }] };
        segments.push(cur);
        return;
      }
      if (PAGE_ACTS.indexOf(act) >= 0 && cur) {
        cur.items.push({ action: act, params: p });
        return;
      }
      if (EXIT_ACTS.indexOf(act) >= 0) {
        if (cur) { cur.items.push({ action: act, params: p }); cur = null; }
        return;
      }
    });
    // 过滤：只剩「退出」没有进入动作的段没有预览价值
    const useful = segments.filter((s) => s.items.some((it) => NAV_ACTS.indexOf(it.action) >= 0));
    return { any: useful.length > 0, segments: useful };
  }

  /* 从步骤里提取 [编辑朋友圈]/[编辑对方资料] 带的数据（有则优先于 scene.json/人设库） */
  function extractDataOverrides(steps) {
    const out = { moments: null, peer: null };
    (steps || []).forEach((step) => {
      const d = step && step.params && step.params['数据'];
      if (!d || typeof d !== 'object') return;
      if (step.action === '编辑朋友圈' && Array.isArray(d)) out.moments = d;
      if (step.action === '编辑对方资料' && !Array.isArray(d)) out.peer = d;
    });
    return out;
  }

  /* ======================= 样式（浅色，对齐 shared_picker 面板） ======================= */

  function initStyles() {
    if (document.getElementById('wxmp-style')) return;
    const st = document.createElement('style');
    st.id = 'wxmp-style';
    st.textContent = `
.wxmp-mask { position: fixed; inset: 0; background: rgba(17, 24, 39, .45); z-index: 150; display: none; align-items: center; justify-content: center; }
.wxmp-mask.show { display: flex; }
.wxmp-modal { width: 1080px; max-width: 96vw; height: min(92vh, 900px); background: #ffffff; color: #1f2328; border: 1px solid rgba(17,24,39,.12); border-radius: 14px; box-shadow: 0 24px 60px rgba(17,24,39,.25); display: flex; flex-direction: column; overflow: hidden; }
.wxmp-head { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-bottom: 1px solid rgba(17,24,39,.08); }
.wxmp-head b { font-size: 15px; }
.wxmp-target { font-size: 12px; color: #6b7280; }
.wxmp-spacer { flex: 1; }
.wxmp-head select { font: inherit; font-size: 12px; border: 1px solid rgba(17,24,39,.2); border-radius: 7px; padding: 4px 6px; background: #fff; color: inherit; }
.wxmp-head button { cursor: pointer; border: 1px solid rgba(17,24,39,.2); background: #fff; color: #1f2328; border-radius: 7px; padding: 5px 12px; font: inherit; font-size: 12px; white-space: nowrap; }
.wxmp-head button:hover { border-color: rgba(10,172,95,.4); color: #0aac5f; }
.wxmp-head .wxmp-run { background: #0aac5f; border-color: #0aac5f; color: #fff; font-weight: 600; }
.wxmp-head .wxmp-run:hover { background: #099a55; color: #fff; }
.wxmp-status { padding: 6px 14px; font-size: 12px; color: #6b7280; background: #f7f8fa; border-bottom: 1px solid rgba(17,24,39,.06); min-height: 18px; }
.wxmp-status.ok { color: #0a8a52; }
.wxmp-status.err { color: #d5493f; }
.wxmp-body { flex: 1; display: flex; min-height: 0; }
.wxmp-stage { flex: 1; min-width: 0; display: flex; align-items: flex-start; justify-content: center; padding: 14px; overflow: auto; background: #f1f3f5; }
.wxmp-phone { width: 600px; height: 1300px; transform-origin: top left; border-radius: 18px; overflow: hidden; box-shadow: 0 8px 30px rgba(17,24,39,.28); background: #000; }
.wxmp-frame { width: 600px; height: 1300px; border: 0; display: block; }
.wxmp-side { width: 320px; flex: none; border-left: 1px solid rgba(17,24,39,.08); display: flex; flex-direction: column; min-height: 0; }
.wxmp-side-title { padding: 10px 12px 6px; font-size: 12px; font-weight: 600; color: #4b5563; }
.wxmp-seq { flex: 1; overflow: auto; padding: 0 10px 10px; }
.wxmp-seg-div { font-size: 11px; color: #9aa0a6; text-align: center; padding: 6px 0 2px; }
.wxmp-item { display: flex; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 9px; border: 1px solid transparent; }
.wxmp-item + .wxmp-item { margin-top: 2px; }
.wxmp-item.on { border-color: rgba(10,172,95,.45); background: #e8f7ef; }
.wxmp-item-ic { flex: none; font-size: 14px; }
.wxmp-item-main { flex: 1; min-width: 0; font-size: 12px; }
.wxmp-item-main b { font-weight: 600; }
.wxmp-item-main i { display: block; font-style: normal; color: #6b7280; font-size: 11px; margin-top: 1px; word-break: break-all; }
.wxmp-item-main i.wxmp-item-note { color: #b26a06; }
.wxmp-item-thumb { flex: none; width: 40px; height: 40px; border-radius: 6px; overflow: hidden; background: #f1f3f5; display: flex; align-items: center; justify-content: center; }
.wxmp-item-thumb img { max-width: 100%; max-height: 100%; object-fit: cover; }
.wxmp-tip { padding: 10px 12px; font-size: 11px; line-height: 1.6; color: #9aa0a6; border-top: 1px solid rgba(17,24,39,.06); }
@media (max-width: 1100px) { .wxmp-modal { width: 96vw; } .wxmp-side { width: 240px; } }
`;
    document.head.appendChild(st);
  }

  /* ======================= 面板 ======================= */

  let modalEl = null;
  let iframeEl = null;
  let statusEl = null;
  let seqListEl = null;
  let stopFlag = false;
  let bootToken = 0;                 // 每次打开/重置自增，作废旧的异步流程
  let running = false;               // 正在按剧本走

  const ACT_META = {
    '打开对方主页':   { icon: '👤', label: '打开对方主页' },
    '进入对方朋友圈': { icon: '🌐', label: '进入对方朋友圈' },
    '进入朋友圈':     { icon: '🖼', label: '进入我的朋友圈' },
    '打开对方设置':   { icon: '⚙', label: '打开对方设置' },
    '向下滚动':       { icon: '⬇️', label: '向下滚动' },
    '向上滚动':       { icon: '⬆️', label: '向上滚动' },
    '滚动到':         { icon: '🎯', label: '滚动到' },
    '点开图片':       { icon: '🔍', label: '点开图片' },
    '播放视频':       { icon: '▶️', label: '播放视频' },
    '闪回聊天':       { icon: '💬', label: '闪回聊天' },
    '返回主页':       { icon: '🏠', label: '返回主页' },
    '退出朋友圈':     { icon: '↩', label: '退出朋友圈' },
  };

  function paramsText(action, p) {
    const parts = [];
    Object.keys(p || {}).forEach((k) => {
      const v = p[k];
      if (v === '' || v == null || (typeof v === 'object')) return;
      parts.push(k + '=' + v);
    });
    return parts.join('　');
  }

  /* 点开图片/播放视频会在预览里看到的图（按当前段的人的数据解析） */
  function resolveSeqThumb(item, peerData, mineMoments) {
    const p = item.params || {};
    if (item.action === '点开图片' || item.action === '播放视频') {
      const parts = String(p['序号'] || '1').split(/[,，]/);
      const ni = Math.max(1, parseInt(parts[0], 10) || 1);
      const mi = Math.max(1, parseInt(parts[1], 10) || 1);
      let post = null;
      if (item.page === 'peer' && peerData && Array.isArray(peerData.posts)) {
        post = peerData.posts[ni - 1] || peerData.posts[0] || null;
      } else if (item.page === 'mine' && Array.isArray(mineMoments)) {
        post = mineMoments[ni - 1] || mineMoments[0] || null;
      }
      if (!post) return { thumb: '', note: '（该序号在数据里不存在，运行时会点空）' };
      const vid = post.video && (typeof post.video === 'string' ? post.video : (post.video.src || post.video.url || ''));
      const imgs = Array.isArray(post.images) ? post.images : [];
      if (item.action === '播放视频') {
        return { thumb: post.cover || imgs[0] || '', note: '视频：' + String(post.text || '').slice(0, 16) };
      }
      return {
        thumb: imgs[mi - 1] || imgs[0] || (vid ? (post.cover || '') : ''),
        note: '第 ' + ni + ' 条「' + String(post.text || '').slice(0, 16) + '」' + (imgs[mi - 1] ? '' : '（没有第 ' + mi + ' 张图，会点第 1 张/点空）'),
      };
    }
    return { thumb: '', note: '' };
  }

  function open(opts) {
    const o = opts || {};
    initStyles();
    close();
    stopFlag = false;
    const token = ++bootToken;

    const segs = o.segments && o.segments.length ? o.segments : (detect(o.steps).segments);
    const peerSeg = segs.find((s) => s.page === 'peer');
    const person = peerSeg ? peerSeg.person : '';
    const presets = o.presets || {};
    const peerData = o.peerData || (person && presets[person]) || null;

    const mask = document.createElement('div');
    mask.className = 'wxmp-mask show';
    mask.innerHTML =
      '<div class="wxmp-modal">' +
        '<div class="wxmp-head">' +
          '<b>📱 朋友圈预览</b>' +
          '<span class="wxmp-target">' +
            (peerData ? esc('对方：' + (peerData.name || person) + ' · 人设库数据') : '我的朋友圈 · scene.json 数据') +
          '</span>' +
          '<span class="wxmp-spacer"></span>' +
          '<select class="wxmp-scale" title="画面缩放">' +
            '<option value="0.42">42%</option>' +
            '<option value="0.52" selected>52%</option>' +
            '<option value="0.7">70%</option>' +
            '<option value="1">100%</option>' +
          '</select>' +
          '<button type="button" class="wxmp-run">▶ 按剧本走一遍</button>' +
          '<button type="button" class="wxmp-reset">↻ 重置</button>' +
          (o.onEditContent ? '<button type="button" class="wxmp-edit">⚙ 编辑内容</button>' : '') +
          '<button type="button" class="wxmp-close" title="关闭">✕</button>' +
        '</div>' +
        '<div class="wxmp-status">正在连接预览渲染器…</div>' +
        '<div class="wxmp-body">' +
          '<div class="wxmp-stage"><div class="wxmp-phone"><iframe class="wxmp-frame" src="about:blank"></iframe></div></div>' +
          '<div class="wxmp-side">' +
            '<div class="wxmp-side-title">剧本里的朋友圈动作（' +
              segs.reduce((n, s) => n + s.items.length, 0) + ' 步）</div>' +
            '<div class="wxmp-seq"></div>' +
            '<div class="wxmp-tip">预览画面 = 成片会拍到的真实渲染（同一套前端与图片数据）。' +
              '点「按剧本走一遍」会照剧本顺序演示：进入 → 滚动 → 点开图片 → 闪回聊天。' +
              '也可以直接在画面里点、滚轮滚动，手动检查每一张图。</div>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(mask);
    modalEl = mask;
    iframeEl = mask.querySelector('.wxmp-frame');
    statusEl = mask.querySelector('.wxmp-status');
    seqListEl = mask.querySelector('.wxmp-seq');

    /* ---- 动作序列列表 ---- */
    let seqNo = 0;
    segs.forEach((seg, si) => {
      if (si) {
        const div = document.createElement('div');
        div.className = 'wxmp-seg-div';
        div.textContent = '— 下一段 —';
        seqListEl.appendChild(div);
      }
      seg.items.forEach((it) => {
        const meta = ACT_META[it.action] || { icon: '•', label: it.action };
        const th = resolveSeqThumb(it, peerData, o.scene && o.scene.moments);
        const row = document.createElement('div');
        row.className = 'wxmp-item';
        row.innerHTML =
          '<span class="wxmp-item-ic">' + meta.icon + '</span>' +
          '<span class="wxmp-item-main"><b>' + esc(meta.label) + '</b>' +
            (paramsText(it.action, it.params) ? '<i>' + esc(paramsText(it.action, it.params)) + '</i>' : '') +
            (th.note ? '<i class="wxmp-item-note">' + esc(th.note) + '</i>' : '') +
          '</span>' +
          (th.thumb ? '<span class="wxmp-item-thumb"><img src="' + esc(th.thumb) + '" loading="lazy" onerror="this.parentNode.style.opacity=.2"></span>' : '');
        row.dataset.idx = String(seqNo++);
        seqListEl.appendChild(row);
      });
    });

    /* ---- 控件 ---- */
    mask.querySelector('.wxmp-close').onclick = () => close();
    mask.querySelector('.wxmp-reset').onclick = () => { open(o); };
    const runBtn = mask.querySelector('.wxmp-run');
    runBtn.onclick = async () => {
      if (running) return;
      running = true;
      runBtn.textContent = '⏳ 演示中…';
      try { await replay(segs, presets, o); } catch (e) { setStatus('演示中断：' + e.message); }
      running = false;
      runBtn.textContent = '▶ 按剧本走一遍';
      markSeq(-1);
    };
    const editBtn = mask.querySelector('.wxmp-edit');
    if (editBtn) editBtn.onclick = () => { close(); o.onEditContent(); };
    const scaleSel = mask.querySelector('.wxmp-scale');
    const applyScale = () => {
      const v = parseFloat(scaleSel.value) || 0.52;
      const phone = mask.querySelector('.wxmp-phone');
      phone.style.transform = 'scale(' + v + ')';
      phone.parentNode.style.width = (600 * v) + 'px';
      phone.parentNode.style.height = (1300 * v) + 'px';
    };
    scaleSel.onchange = applyScale;
    applyScale();
    mask.addEventListener('click', (e) => { if (e.target === mask) close(); });

    /* ---- 启动预览渲染器 + 装载画面 ---- */
    boot(o, token);
  }

  function close() {
    bootToken++;
    stopFlag = true;
    running = false;
    if (modalEl) { modalEl.remove(); modalEl = null; }
    iframeEl = null; statusEl = null; seqListEl = null;
  }

  function setStatus(text, cls) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = 'wxmp-status' + (cls ? ' ' + cls : '');
  }

  function markSeq(idx) {
    if (!seqListEl) return;
    seqListEl.querySelectorAll('.wxmp-item.on').forEach((n) => n.classList.remove('on'));
    if (idx >= 0) {
      const row = seqListEl.querySelector('.wxmp-item[data-idx="' + idx + '"]');
      if (row) {
        row.classList.add('on');
        if (row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
      }
    }
  }

  /* ======================= 渲染器启动与画面装载 ======================= */

  async function api(path, opts) {
    const r = await fetch(path, opts);
    return r.json();
  }

  async function ensureFrontend() {
    try {
      const st = await api('/api/wxapp/status');
      if (st && st.up) return true;
      if (st && st.conflict) { setStatus('8080 端口被其他程序占用，预览起不来。请关掉占用 8080 的程序后重试。', 'err'); return false; }
    } catch (e) { /* 继续尝试启动 */ }
    setStatus('预览渲染器未运行，正在启动（首次编译约 20~60 秒）…');
    try { await api('/api/wxapp/start', { method: 'POST' }); } catch (e) { /* 轮询见分晓 */ }
    const t0 = Date.now();
    while (Date.now() - t0 < 120000) {
      if (stopFlag) return false;
      await sleep(2000);
      try {
        const st = await api('/api/wxapp/status');
        if (st && st.up) return true;
        if (st && st.conflict) { setStatus('8080 端口被其他程序占用，预览起不来。', 'err'); return false; }
      } catch (e) { /* 忽略，继续等 */ }
    }
    setStatus('预览渲染器启动超时。可到「场景编辑器」确认 8080 预览是否可用后重试。', 'err');
    return false;
  }

  async function boot(o, token) {
    const up = await ensureFrontend();
    if (token !== bootToken || !modalEl) return;
    if (!up) return;
    setStatus('预览渲染器已连接，正在装载画面…');
    iframeEl.src = '/wxpv/#/';
    try {
      await new Promise((res, rej) => {
        iframeEl.onload = res;
        iframeEl.onerror = () => rej(new Error('iframe 加载失败'));
        setTimeout(() => rej(new Error('iframe 加载超时')), 60000);
      });
    } catch (e) {
      if (token === bootToken) setStatus('画面装载失败：' + e.message, 'err');
      return;
    }
    if (token !== bootToken) return;
    const win = iframeEl.contentWindow;
    const t0 = Date.now();
    while (!(win && win.__wxEmbedReady === true)) {
      if (token !== bootToken || stopFlag) return;
      if (Date.now() - t0 > 90000) { setStatus('预览层加载超时（__wxEmbedReady）。', 'err'); return; }
      await sleep(300);
    }
    // 注入真人图片查看器（embed 默认不带；预览要点开图看大图，与成片同一套查看器）
    try {
      const code = await (await fetch('/enhance/human_actions.js')).text();
      const s = win.document.createElement('script');
      s.textContent = code;
      win.document.body.appendChild(s);
    } catch (e) { /* 查看器缺位时点图退化为新窗口打开，不影响整体预览 */ }
    // 应用场景（我的资料 / 我的朋友圈 / 对方数据）——与运行时「应用场景」同一入口
    try {
      win.__wxConfig.applyScene(o.scene || {});
    } catch (e) {
      setStatus('场景数据应用失败：' + e.message, 'err');
      return;
    }
    await sleep(300);
    if (token !== bootToken) return;
    // 应用对方人设数据：scene.peer 若是空对象会把对方冲回默认人设，
    // 这里按「剧本 [打开对方主页] 指到的人」从人设库取整份数据盖回去（与运行时同源）。
    const segs0 = o.segments && o.segments.length ? o.segments : (detect(o.steps).segments);
    const peerSeg0 = segs0.find((s) => s.page === 'peer');
    if (peerSeg0) {
      const person0 = peerSeg0.person;
      const pd = o.peerData || (person0 && o.presets && o.presets[person0]) || null;
      if (pd) {
        try { win.__wxPeer.apply(pd); } catch (e) { /* openMoments 仍可看默认人设，不阻断 */ }
      } else if (person0) {
        setStatus('人设库里没有「' + person0 + '」的资料 —— 预览的是默认人设；运行时也会是空朋友圈，请先在「🍩 朋友圈」里编辑对方内容。', 'err');
      }
    }
    await sleep(300);
    if (token !== bootToken) return;
    // 初始画面：有对方段就落「对方朋友圈」，否则落「我的朋友圈」
    const segs = segs0;
    const firstPeer = segs.find((s) => s.page === 'peer');
    if (firstPeer) {
      try {
        win.__wxPeer.openMoments();
        setStatus('✅ 已打开「' + ((firstPeer.person && o.presets[firstPeer.person] && o.presets[firstPeer.person].name) || firstPeer.person || '对方') + '」的朋友圈 —— 可点「按剧本走一遍」照剧本演示，或直接在画面里检查。', 'ok');
      } catch (e) {
        setStatus('打开对方朋友圈失败：' + e.message, 'err');
      }
    } else {
      const ok = await openMyMoments(win);
      setStatus(ok ? '✅ 已打开我的朋友圈。' : '已装载画面，但没找到「朋友圈」入口（可在画面里手动点「发现 → 朋友圈」）。', ok ? 'ok' : '');
    }
  }

  /* ---- 我的朋友圈：照运行时的真机路径（发现 Tab → 朋友圈入口） ---- */
  async function openMyMoments(win) {
    const doc = win.document;
    const tabs = doc.querySelectorAll('#wx-nav nav dl');
    for (const it of tabs) {
      const dd = it.querySelector('dd');
      if (dd && dd.textContent.trim() === '发现') { it.click(); break; }
    }
    const sels = ['[data-wx-action="moments"]', '#explore .disc-cell', '.weui-cell'];
    const t0 = Date.now();
    while (Date.now() - t0 < 5000) {
      for (const sel of sels) {
        const cells = doc.querySelectorAll(sel);
        for (const c of cells) {
          if ((c.textContent || '').indexOf('朋友圈') >= 0 && c.offsetParent !== null) { c.click(); await sleep(600); return true; }
        }
      }
      await sleep(250);
    }
    return false;
  }

  /* ======================= 按剧本走一遍 ======================= */

  async function replay(segs, presets, o) {
    const win = iframeEl && iframeEl.contentWindow;
    if (!win || !win.__wxPeer) { setStatus('预览画面还没就绪，等装载完成再演示。', 'err'); return; }
    stopFlag = false;
    let appliedPerson = null;
    let seqIdx = -1;

    const curPerson = () => appliedPerson;
    async function ensurePerson(name) {
      if (!name || name === curPerson()) return true;
      const d = presets[name];
      if (!d) return false;
      win.__wxPeer.apply(d);
      appliedPerson = name;
      return true;
    }
    const peerMomentsOpen = () => {
      const el = win.document.getElementById('wxPeerMoments');
      return !!(el && el.classList.contains('open'));
    };
    const mineMomentsOpen = () => !!win.document.getElementById('moments');
    const scrollBy = (px) => {
      if (peerMomentsOpen() && win.__wxPeer.scrollBy) return win.__wxPeer.scrollBy(px);
      if (win.__wxMoments && win.__wxMoments.scrollBy) return win.__wxMoments.scrollBy(px);
      return false;
    };
    const openImage = (i, j) => {
      if (peerMomentsOpen()) return win.__wxPeer.openImage(i, j);
      if (win.__wxMoments && win.__wxMoments.openImage) return win.__wxMoments.openImage(i, j);
      return false;
    };
    const playVideo = (n) => {
      if (peerMomentsOpen() && win.__wxPeer.playVideo) return win.__wxPeer.playVideo(n);
      if (win.__wxMoments && win.__wxMoments.playVideo) return win.__wxMoments.playVideo(n);
      return false;
    };
    const closeViewers = () => {
      try { win.__wxPeer && win.__wxPeer.closeViewers(); } catch (e) { /* noop */ }
      try { win.__wxMoments && win.__wxMoments.closeViewers(); } catch (e) { /* noop */ }
    };
    const num = (v, dft) => {
      const n = parseFloat(String(v == null ? '' : v));
      return isFinite(n) && n > 0 ? n : dft;
    };

    for (const seg of segs) {
      for (const it of seg.items) {
        if (stopFlag) return;
        seqIdx++;
        markSeq(seqIdx);
        const p = it.params || {};
        switch (it.action) {
          case '打开对方主页': {
            await ensurePerson(String(p['对方'] || p['联系人'] || p['预设'] || seg.person || '').trim());
            closeViewers();
            win.__wxPeer.openProfile();
            break;
          }
          case '进入对方朋友圈':
            win.__wxPeer.openMoments();
            break;
          case '进入朋友圈':
            closeViewers();
            win.__wxPeer.close();
            await openMyMoments(win);
            break;
          case '向下滚动':
            scrollBy(num(p['像素'], 300));
            break;
          case '向上滚动':
            scrollBy(-num(p['像素'], 300));
            break;
          case '滚动到': {
            const pos = String(p['位置'] || '底部');
            // 借 scrollBy 大步进实现（容器内滚到顶/底）
            const info = (peerMomentsOpen() && win.__wxPeer.scrollInfo) ? win.__wxPeer.scrollInfo()
              : ((win.__wxMoments && win.__wxMoments.scrollInfo) ? win.__wxMoments.scrollInfo() : null);
            if (info) scrollBy(pos.indexOf('顶') >= 0 ? -info.top - 50 : (info.max - info.top + 50));
            break;
          }
          case '点开图片': {
            const parts = String(p['序号'] || '1').split(/[,，]/);
            openImage(Math.max(1, parseInt(parts[0], 10) || 1), Math.max(1, parseInt(parts[1], 10) || 1));
            await sleep(num(p['停留'], 0.3) * 1000);
            closeViewers();
            break;
          }
          case '播放视频': {
            playVideo(Math.max(1, parseInt(String(p['序号'] || '1'), 10) || 1));
            await sleep(num(p['停留'], 2.0) * 1000);
            closeViewers();
            break;
          }
          case '闪回聊天':
          case '返回主页':
          case '退出朋友圈':
            closeViewers();
            if (peerMomentsOpen() || win.document.getElementById('wxPeerProfile')) win.__wxPeer.back();
            else if (mineMomentsOpen()) { try { iframeEl.contentWindow.history.back(); } catch (e) { /* noop */ } }
            break;
          default:
            break;
        }
        await sleep(700);
      }
    }
  }

  /* ======================= 导出 ======================= */

  window.__wxMomentsPreview = {
    detect,
    extractDataOverrides,
    open,
    close,
  };
})();
