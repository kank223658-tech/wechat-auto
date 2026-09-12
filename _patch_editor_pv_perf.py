# -*- coding: utf-8 -*-
# 编辑器实时预览提速：①只有对方主页/朋友圈数据变化时走快路径（只重绘对方页面，不整场景重放）
# ②实时预览盖住画布时跳过示意稿整页重建（打字卡顿大头），切回示意稿/真机再补渲染
import io

P = r'editor\scene.html'
s = io.open(P, encoding='utf-8').read()

pairs = []

# 1) pushSceneToPv send()：加 peer-only 快路径
old = """    let snap = '';
    try { snap = JSON.stringify(scene); } catch (e) { return; }
    if (snap === _lastPvSceneJSON) return;        // 场景没变：不发请求、不重渲染
    if (pvApplyScene(snap) && pvSceneLooksRight(snap)) {
      _lastPvSceneJSON = snap;
      _pvRetryLeft = 0;
      return;
    }
    /* 没套上（被前端重渲染覆盖）：有限次重试后放弃，绝不退化成轮询 */
    _lastPvSceneJSON = '';"""
new = """    let snap = '';
    try { snap = JSON.stringify(scene); } catch (e) { return; }
    if (snap === _lastPvSceneJSON) return;        // 场景没变：不发请求、不重渲染
    /* 快路径：只有对方主页/朋友圈数据变了 → 只重绘对方页面。
       整场景 applyScene 会全量重放主页/通讯录/朋友圈（Vue $forceUpdate），
       面板打一个字预览卡一下就是它造成的 */
    let cur = null; try { cur = JSON.parse(snap); } catch (e) {}
    if (cur && _lastPvSceneParsed && pvOnlyPeerChanged(_lastPvSceneParsed, cur)
        && pvFastApplyPeer(cur)) {
      _lastPvSceneJSON = snap; _lastPvSceneParsed = cur; _pvRetryLeft = 0;
      return;
    }
    if (pvApplyScene(snap) && pvSceneLooksRight(snap)) {
      _lastPvSceneJSON = snap;
      _lastPvSceneParsed = cur;
      _pvRetryLeft = 0;
      return;
    }
    /* 没套上（被前端重渲染覆盖）：有限次重试后放弃，绝不退化成轮询 */
    _lastPvSceneJSON = '';
    _lastPvSceneParsed = null;"""
pairs.append((old, new))

# 2) pvApplyScene：加统计 + 后面追加两个快路径帮手函数
old = """function pvApplyScene(snap) {
  const w = pvWin();
  if (!w || !w.__wxConfig) return false;
  try { w.__wxConfig.apply(); w.__wxConfig.applyScene(JSON.parse(snap)); return true; }
  catch (e) { return false; }
}"""
new = """function pvApplyScene(snap) {
  const w = pvWin();
  if (!w || !w.__wxConfig) return false;
  try { w.__wxConfig.apply(); w.__wxConfig.applyScene(JSON.parse(snap)); window.__pvStats.full++; return true; }
  catch (e) { return false; }
}

/* 除 peer/peers/peerPreset 外其余顶层键都相同 → 只有对方数据变了 */
function pvOnlyPeerChanged(a, b) {
  const PEER_KEYS = ['peer', 'peers', 'peerPreset'];
  const keys = new Set(Object.keys(a || {}).concat(Object.keys(b || {})));
  for (const k of keys) {
    if (PEER_KEYS.indexOf(k) >= 0) continue;
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) return false;
  }
  return true;
}

/* 快路径执行体：只把 peer 数据重绘进真实界面（__wxPeer.apply = setPeer+重绘已开页面） */
function pvFastApplyPeer(cur) {
  const w = pvWin();
  if (!w) return false;
  const data = cur.peer !== undefined ? cur.peer : null;
  if (!data) return true;                        // peer 相关键都没了：无需渲染，直接收下
  if (!w.__wxPeer || typeof w.__wxPeer.apply !== 'function') return false;
  try { w.__wxPeer.apply(data); window.__pvStats.peerFast++; return true; }
  catch (e) { return false; }
}"""
pairs.append((old, new))

# 3) renderPhone：pv 盖住画布时跳过示意稿重建
old = """function renderPhone() {
  /* 编辑器预览不是录制端：关掉真机的隐私模糊，昵称/微信号要看得清才好编辑 */
  document.body.classList.add('wx-peer-no-blur');
  const inner = $('phoneInner');
  let html = statusbar();"""
new = """function renderPhone() {
  /* 编辑器预览不是录制端：关掉真机的隐私模糊，昵称/微信号要看得清才好编辑 */
  document.body.classList.add('wx-peer-no-blur');
  const inner = $('phoneInner');
  if (stageView === 'pv' && pvReady) {
    /* 实时预览层盖住画布：示意稿不必整页重建（每次输入全量 innerHTML + MutationObserver
       全文档扫描是打字卡顿大头）。标脏即可，切回 示意稿/真机运行 时再补渲染 */
    window.__edDraftDirty = true;
    pushSceneToLive();
    pvSyncNav();
    return;
  }
  window.__edDraftDirty = false;
  let html = statusbar();"""
pairs.append((old, new))

# 4) setStageView：切回非 pv 视图时补渲染脏的示意稿
old = """  if (stageView === 'pv') {
    if (!pvBooted) stagePvBoot();
    else { pushSceneToPv(true); pvSyncNav(true); }
  }
}"""
new = """  if (stageView === 'pv') {
    if (!pvBooted) stagePvBoot();
    else { pushSceneToPv(true); pvSyncNav(true); }
  } else if (window.__edDraftDirty) {
    window.__edDraftDirty = false;   // pv 期间示意稿被跳过，切回来先补一次全量渲染
    renderPhone();
  }
}"""
pairs.append((old, new))

# 5) pv 启动失败：恢复示意稿渲染
old = """    if (waited >= 25000) { clearInterval(t); pvReady = false; applyLiveState(); }"""
new = """    if (waited >= 25000) { clearInterval(t); pvReady = false; applyLiveState(); renderPhone(); }"""
pairs.append((old, new))

for i, (old, new) in enumerate(pairs, 1):
    assert old in s, 'pair %d not found' % i
    assert new not in s, 'pair %d already applied' % i
    s = s.replace(old, new, 1)

io.open(P, 'w', encoding='utf-8').write(s)
print('patched', len(pairs), 'spots')
