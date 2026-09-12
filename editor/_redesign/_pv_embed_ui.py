# -*- coding: utf-8 -*-
"""scene.html：把「示意稿」换成「实时预览」——同源嵌入真实前端（与成片同一套 UI）。

- 新增 🖼 实时预览（默认）：iframe 挂 /wxpv/#/，就是真实界面，可直接点击操作；
- 📱 真机运行：原来的 playwright 实时画面（保留键盘打字 / 点选改元素）；
- 🎨 示意稿：原手写复刻，降级为离线备用；
- 场景变化 / 右侧选中项 → 同步到预览（防抖 + 序列化比对，没变不发请求）。
"""
import io
import sys

SCENE = r"G:\weixin-auto\editor\scene.html"


def patch(path, pairs, allow=1):
    s = io.open(path, encoding="utf-8").read()
    out = s
    for i, (old, new) in enumerate(pairs, 1):
        n = out.count(old)
        if n != allow:
            print("!! 第 %d 处锚点命中 %d 次（期望 %d）：%r" % (i, n, allow, old[:100]))
            sys.exit(1)
        out = out.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(out)
    print("OK %s（%d 处）" % (path, len(pairs)))


# ---------------- 1) 新增 iframe + 未就绪遮罩 ----------------
A_IMG = '            <img class="phone-live" id="stageLiveImg" alt="真机实时画面" hidden data-page-node-id="Yz3kLvPq1WmSdR8bTnQxHa">'
A_IMG_NEW = (
    A_IMG + "\n"
    '            <iframe class="phone-pv" id="stagePv" src="about:blank" title="实时预览（真实界面）"></iframe>'
)

A_ERR = ('              <div class="ple-err" id="stageLiveErr" hidden '
         'data-page-node-id="Lc7VdKx2JmQbTpNs5RfWyH"></div>\n            </div>')
A_ERR_NEW = A_ERR + '''
            <div class="phone-live-empty" id="stagePvEmpty" hidden>
              <div class="ple-ico">🖼</div>
              <div class="ple-t">实时预览还没就绪</div>
              <div class="ple-d">左边这块显示的就是最终视频里的那套界面（同一份代码渲染）<br>需要在后台运行「预览渲染器」，点下面按钮启动即可</div>
              <button type="button" class="ple-btn" id="btnStagePvStart">▶ 启动预览渲染器</button>
              <div class="ple-err" id="stagePvErr" hidden></div>
            </div>'''

# ---------------- 2) 工具条：加「实时预览」，原真机画面改叫「真机运行」 ----------------
A_BTN = ('          <button type="button" id="btnViewLive" class="active" title="显示真机实时画面'
         '（与最终视频同一套 UI，可点击操作）" data-page-node-id="Kq6WmJv3NdLxRpZb9TcYfA">📱 真机画面</button>')
A_BTN_NEW = (
    '          <button type="button" id="btnViewPv" class="active" title="实时预览：'
    '与最终视频完全同一套真实界面（同一份代码渲染），可直接点击操作，不用启动额外进程">🖼 实时预览</button>\n'
    '          <button type="button" id="btnViewLive" title="真机运行：由渲染器进程驱动，'
    '支持键盘打字 / 三面板动画 / 点选改元素" data-page-node-id="Kq6WmJv3NdLxRpZb9TcYfA">📱 真机运行</button>'
)

A_DRAFT_TITLE = 'title="显示编辑器内的静态示意稿（不参与渲染，仅用于看结构）"'
A_DRAFT_TITLE_NEW = 'title="静态示意稿：编辑器内置的离线备用画面（不参与渲染，仅在没有预览渲染器时看结构）"'

# ---------------- 3) 顶部说明文字 ----------------
A_HINT = ('<div class="hint" style="padding:0 14px 6px" data-page-node-id="MqyVf8GrdeKKJxMEAmhr7N">'
          '左：真机画面——就是最终视频里的那套界面，可直接点击操作（进聊天 / 翻朋友圈）；滚轮滚动真机，'
          'Ctrl 或 Shift + 滚轮缩放画布；点「✎ 点选改」后点画面上的文字 / 头像 / 背景即可直接改。'
          '右：结构化面板编辑联系人与消息，改动会实时同步到左边真机画面。「生成并运行」会保存场景、生成工作流并直接开跑。</div>')
A_HINT_NEW = ('<div class="hint" style="padding:0 14px 6px" data-page-node-id="MqyVf8GrdeKKJxMEAmhr7N">'
              '左：实时预览——和最终视频完全同一套界面（同一份代码渲染），可直接点击操作（进聊天 / 翻朋友圈 / 切 Tab）；'
              '需要打字、键盘、点选改元素时切到「📱 真机运行」。Ctrl 或 Shift + 滚轮缩放画布。'
              '右：结构化面板编辑联系人与消息，改动实时同步到左边画面。「生成并运行」会保存场景、生成工作流并直接开跑。</div>')

# ---------------- 4) CSS ----------------
A_CSS = "\n/* ---- 实时预览（同源嵌入真实前端，与成片同一套 UI）---- */\n" \
        ".phone-pv { position: absolute; left: 0; top: 0; width: 600px; height: 1300px;" \
        " border: 0; display: block; z-index: 39; background: #181818; }\n" \
        "#stageLiveBar:not(.live) .slb-sep,\n" \
        "#stageLiveBar:not(.live) #btnStagePick,\n" \
        "#stageLiveBar:not(.live) #btnStageBack,\n" \
        "#stageLiveBar:not(.live) #stageTypeInput,\n" \
        "#stageLiveBar:not(.live) #btnStageSend { display: none; }\n" \
        "</style>"

# ---------------- 5) JS ----------------
A_STATE = "let stageView = 'live';        // live = 真机画面 / draft = 静态示意稿"
A_STATE_NEW = """let stageView = 'pv';          // pv = 实时预览（真实界面） / live = 真机运行 / draft = 静态示意稿
let pvReady = false;           // 实时预览是否已就绪
let pvBooted = false;          // 是否已挂载过预览 iframe
let pvStarting = false;        // 预览渲染器是否正在启动
let _pvPushTimer = null;       // 场景 → 预览 的推送防抖
let _lastPvSceneJSON = '';     // 上次已应用的场景快照（没变就不推）
let _pvNavKey = '';            // 上次同步过的导航状态（避免重复跳转）"""

A_APPLY = """function applyLiveState() {
  const on = (stageView === 'live');
  $('phoneInner').style.visibility = on ? 'hidden' : '';
  $('stageLiveImg').hidden = !on || !liveUp;
  $('stageLiveBadge').hidden = !on || !liveUp;
  $('stageLiveEmpty').hidden = !on || liveUp;
  const b = $('stageLiveBadge');
  b.innerHTML = '<i></i>' + (liveUp ? '真机 LIVE' : '真机 未连接');
  b.classList.toggle('off', !liveUp);
  const st = $('stageLiveState');
  st.textContent = liveUp ? '真机已连接 · 600×1300' : '真机未连接';
  st.classList.toggle('ok', liveUp);
}

function setStageView(v) {
  stageView = (v === 'draft') ? 'draft' : 'live';
  $('btnViewLive').classList.toggle('active', stageView === 'live');
  $('btnViewDraft').classList.toggle('active', stageView === 'draft');
  applyLiveState();
  if (stageView === 'live' && liveUp) refreshStageLive(false);
}"""

A_APPLY_NEW = """function applyLiveState() {
  const v = stageView;
  const pv = (v === 'pv'), on = (v === 'live');
  $('phoneInner').style.visibility = (v === 'draft') ? '' : 'hidden';
  $('stagePv').hidden = !pv;
  $('stagePvEmpty').hidden = !pv || pvReady;
  $('stageLiveImg').hidden = !on || !liveUp;
  $('stageLiveBadge').hidden = !on || !liveUp;
  $('stageLiveEmpty').hidden = !on || liveUp;
  const bar = $('stageLiveBar');
  bar.classList.remove('pv', 'live', 'draft');
  bar.classList.add(v);
  const b = $('stageLiveBadge');
  b.innerHTML = '<i></i>' + (liveUp ? '真机 LIVE' : '真机 未连接');
  b.classList.toggle('off', !liveUp);
  const st = $('stageLiveState');
  if (pv) st.textContent = pvReady ? '实时预览 · 与成片同一套界面'
    : (pvStarting ? '预览渲染器启动中…' : '实时预览未就绪');
  else if (on) st.textContent = liveUp ? '真机已连接 · 600×1300' : '真机未连接';
  else st.textContent = '静态示意稿（离线备用）';
  st.classList.toggle('ok', pv ? pvReady : (on && liveUp));
  const pb = $('btnStagePvStart');
  if (pb) { pb.disabled = !!pvStarting; pb.textContent = pvStarting ? '正在启动预览渲染器…' : '▶ 启动预览渲染器'; }
}

function setStageView(v) {
  stageView = (v === 'pv') ? 'pv' : ((v === 'draft') ? 'draft' : 'live');
  $('btnViewPv').classList.toggle('active', stageView === 'pv');
  $('btnViewLive').classList.toggle('active', stageView === 'live');
  $('btnViewDraft').classList.toggle('active', stageView === 'draft');
  applyLiveState();
  if (stageView === 'live' && liveUp) refreshStageLive(false);
  if (stageView === 'pv') {
    if (!pvBooted) stagePvBoot();
    else { pushSceneToPv(true); pvSyncNav(true); }
  }
}"""

A_PUSH = """function pushSceneToLive(immediate) {
  if (!liveUp) return;"""
A_PUSH_NEW = """function pushSceneToLive(immediate) {
  pushSceneToPv(immediate);          // 预览永远跟着场景走（哪怕当前没显示）
  if (!liveUp) return;"""

A_PV_FUNCS = """/* ---------- 实时预览：同源嵌入真实前端（与成片同一套 UI，逐像素同源） ----------
   性能约定：不常驻轮询、不启动额外进程。只在「iframe 就绪 / 场景真的变了 /
   右侧选中项变化」时做事；空闲期零请求（实测静置 6 秒 0 请求）。 */
function pvEl() { return $('stagePv'); }
function pvWin() {
  const f = pvEl();
  try { return f ? f.contentWindow : null; } catch (e) { return null; }
}

function mountPv() {
  const f = pvEl();
  if (!f) return;
  pvReady = false;
  applyLiveState();
  try { f.src = '/wxpv/#/'; } catch (e) { /* 忽略 */ }
  let waited = 0;
  const t = setInterval(() => {
    waited += 350;
    const w = pvWin();
    if (w && w.__wxConfig && !_lastPvSceneJSON) {
      /* 尽早把场景套上，避免先闪一下默认参考数据 */
      try {
        const snap = JSON.stringify(scene);
        if (pvApplyScene(snap)) _lastPvSceneJSON = snap;
      } catch (e) { /* 忽略 */ }
    }
    if (w && w.__wxEmbedReady) {
      clearInterval(t);
      pvReady = true;
      _lastPvSceneJSON = '';
      _pvNavKey = '';
      applyLiveState();
      pushSceneToPv(true);
      pvSyncNav(true);
      return;
    }
    if (waited >= 25000) { clearInterval(t); pvReady = false; applyLiveState(); }
  }, 350);
}

async function stagePvBoot() {
  pvBooted = true;
  if (pvReady) return;
  let up = false;
  try { const r = await api('/api/wxapp/status'); up = !!(r && r.up); } catch (e) { up = false; }
  if (!up) { applyLiveState(); return; }   // 渲染器没在跑：显示「启动预览渲染器」按钮
  mountPv();
}

async function stagePvStart() {
  if (pvStarting) return;
  pvStarting = true;
  const err = $('stagePvErr');
  if (err) err.hidden = true;
  applyLiveState();
  try {
    const r = await api('/api/wxapp/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (!r || !r.ok) throw new Error((r && r.msg) || '启动失败');
    toast('预览渲染器正在启动…（首次编译约 20~60 秒）');
    let waited = 0;
    const t = setInterval(async () => {
      waited += 1;
      let up = false;
      try { const s = await api('/api/wxapp/status'); up = !!(s && s.up); } catch (e) { up = false; }
      if (up) { clearInterval(t); pvStarting = false; mountPv(); toast('预览渲染器已启动'); }
      else if (waited >= 90) {
        clearInterval(t); pvStarting = false; applyLiveState();
        if (err) { err.hidden = false; err.textContent = '启动超时。详情见 vue-WeChat/dev-server.log'; }
      }
    }, 1000);
  } catch (e) {
    pvStarting = false; applyLiveState();
    if (err) { err.hidden = false; err.textContent = (e && e.message) || '启动失败'; }
  }
}

function pvApplyScene(snap) {
  const w = pvWin();
  if (!w || !w.__wxConfig) return false;
  try { w.__wxConfig.apply(); w.__wxConfig.applyScene(JSON.parse(snap)); return true; }
  catch (e) { return false; }
}

function pushSceneToPv(immediate) {
  if (!pvReady) return;
  if (_pvPushTimer) { clearTimeout(_pvPushTimer); _pvPushTimer = null; }
  const send = () => {
    _pvPushTimer = null;
    if (!pvReady) return;
    let snap = '';
    try { snap = JSON.stringify(scene); } catch (e) { return; }
    if (snap === _lastPvSceneJSON) return;        // 场景没变：不发请求、不重渲染
    if (pvApplyScene(snap)) _lastPvSceneJSON = snap;
    else _lastPvSceneJSON = '';
  };
  if (immediate) send(); else _pvPushTimer = setTimeout(send, 700);
}

/* 右侧面板选中项 / 相机工具条 → 驱动左边真实界面导航（和真人点一样） */
function pvSyncNav(force) {
  if (!pvReady) return;
  const w = pvWin();
  if (!w) return;
  const key = camView + '|' + (selIdx == null ? '' : selIdx);
  if (!force && key === _pvNavKey) return;
  _pvNavKey = key;
  try {
    const hash = String(w.location.hash || '#/');
    const inChat = hash.indexOf('/wechat/dialogue') >= 0;
    const inSub = hash.indexOf('/contact') >= 0 || hash.indexOf('/explore') >= 0;
    if (camView === 'moments') {
      if (hash.indexOf('/explore/moments') < 0) w.location.hash = '#/explore/moments';
      return;
    }
    if (camView === 'peer' || camView === 'peer-moments') {
      if (w.__wxPeer && w.__wxPeer.openProfile) {
        const st = (w.__wxPeer.isOpen && w.__wxPeer.isOpen()) || {};
        if (!st.profile) w.__wxPeer.openProfile();
        if (camView === 'peer-moments' && !st.moments) {
          setTimeout(() => { try { w.__wxPeer.openMoments(); } catch (e) { /* 忽略 */ } }, 420);
        }
      }
      if (inSub || inChat) w.location.hash = '#/';
      return;
    }
    if (inSub) {
      w.location.hash = '#/';
      if (selIdx != null) setTimeout(() => pvOpenRow(selIdx), 420);
      return;
    }
    if (selIdx == null) { if (inChat) w.location.hash = '#/'; return; }
    if (inChat) { w.location.hash = '#/'; setTimeout(() => pvOpenRow(selIdx), 420); }
    else pvOpenRow(selIdx);
  } catch (e) { /* 忽略：导航失败不影响编辑 */ }
}

function pvOpenRow(i) {
  const w = pvWin();
  if (!w || !pvReady) return;
  try {
    const rows = w.document.querySelectorAll('.wechat-list li.list-row');
    if (rows[i]) rows[i].click();
  } catch (e) { /* 忽略 */ }
}

"""

A_BIND = """function bindStageLive() {
  $('btnViewLive').onclick = () => setStageView('live');
  $('btnViewDraft').onclick = () => setStageView('draft');"""
A_BIND_NEW = """function bindStageLive() {
  $('btnViewPv').onclick = () => setStageView('pv');
  $('btnViewLive').onclick = () => setStageView('live');
  $('btnViewDraft').onclick = () => setStageView('draft');
  $('btnStagePvStart').onclick = stagePvStart;"""

A_RENDER = """  inner.innerHTML = html;
  /* 场景一变就推给真机画面（真机未连接时内部直接返回） */
  pushSceneToLive();
}"""
A_RENDER_NEW = """  inner.innerHTML = html;
  /* 场景一变就推给真机画面（真机未连接时内部直接返回）与实时预览 */
  pushSceneToLive();
  pvSyncNav();
}"""

A_BOOT = """async function stageLiveBoot() {
  setStageView('live');
  liveUp = await probeLive();"""
A_BOOT_NEW = """async function stageLiveBoot() {
  liveUp = await probeLive();"""

A_INIT = "  stageLiveBoot();"
A_INIT_NEW = "  stageLiveBoot();\n  stagePvBoot();      // 默认视图：实时预览（真实界面）"

s = io.open(SCENE, encoding="utf-8").read()
assert s.count(A_CSS.split("</style>")[0]) == 0, "CSS 已存在，勿重复打补丁"
assert s.rfind("</style>") > 0, "找不到 </style>"
# CSS 追加到最后一个 style 块末尾
head = s[:s.rfind("</style>")]
tail = s[s.rfind("</style>"):]
s = head + A_CSS + tail[len("</style>"):]
io.open(SCENE, "w", encoding="utf-8", newline="").write(s)
print("OK CSS 已追加")

patch(SCENE, [
    (A_IMG, A_IMG_NEW),
    (A_ERR, A_ERR_NEW),
    (A_BTN, A_BTN_NEW),
    (A_DRAFT_TITLE, A_DRAFT_TITLE_NEW),
    (A_HINT, A_HINT_NEW),
    (A_STATE, A_STATE_NEW),
    (A_APPLY, A_APPLY_NEW),
    (A_PUSH, A_PUSH_NEW),
    (A_BIND, A_PV_FUNCS + A_BIND_NEW),
    (A_RENDER, A_RENDER_NEW),
    (A_BOOT, A_BOOT_NEW),
    (A_INIT, A_INIT_NEW),
])
