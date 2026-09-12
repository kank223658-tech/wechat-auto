# -*- coding: utf-8 -*-
"""
scene.html 主舞台「真机画面」改造 · 不卡版（2026-09-11 二次修订）
====================================================================
第一版做了每 350ms 常驻轮询 + 每次 renderPhone 都推整份场景给真机，
结果把页面拖卡了（用户反馈「卡死」）。这一版把性能开销压到接近零：

  空闲时**零请求**。只在下面三种时机抓帧：
    1) 连接成功时抓一帧；
    2) 右边面板改了数据 → 防抖 900ms、且**序列化比对确认真的变了**才推给真机，
       推送成功后抓帧；
    3) 你在画面上操作（点击/滚动/返回/打字/点选改）→ 立刻抓一帧，
       并补 5 帧（每 260ms 一帧）等真机那边的过渡动画走完。
  没有 setInterval，没有常驻心跳。

外观与交互仍与第一版一致：真机画面 / 示意稿 可切换、点击=点手机、
滚轮=滚动真机（Ctrl/Shift+滚轮=缩放画布）、✎ 点选改、← 返回、打字发送。
"""
import io
import sys

from _live_stage2 import (                                # noqa: F401
    PATH, CSS_ANCHOR, CSS_NEW, PHONE_OLD, PHONE_NEW, JS_ANCHOR,
    RENDER_OLD, RENDER_NEW, BIND_OLD, BIND_NEW, INIT_OLD, INIT_NEW,
    HINT_OLD, HINT_NEW,
)

JS_NEW = """/* ---------- 真机画面：主舞台 = 真实渲染（与成片同一套 UI，可点击操作） ----------
   性能约定：**不常驻轮询**。只在「连接成功 / 场景真的变了 / 每次操作后」抓帧，
   操作后额外补几帧等动画走完；空闲时完全不发请求。 */
let stageView = 'live';        // live = 真机画面 / draft = 静态示意稿
let liveUp = false;            // 真机画面是否已连上
let livePicking = false;       // 点选模式（点画面 = 拾取元素改属性）
let stageEditInfo = null;
let _livePushTimer = null;     // 场景推送防抖
let _liveBurstTimer = null, _liveBurstLeft = 0;
let _lastLiveSceneJSON = '';   // 上次已推给真机的场景快照（没变就不推）
let _wheelAcc = 0, _wheelFlush = null;

function probeLive() {
  return new Promise(resolve => {
    const im = new Image();
    let done = false;
    const fin = v => { if (!done) { done = true; resolve(v); } };
    im.onload = () => fin(true);
    im.onerror = () => fin(false);
    setTimeout(() => fin(false), 4000);
    im.src = '/api/live?probe=' + Date.now();
  });
}

function applyLiveState() {
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
}

function tickStageLive() {
  const img = $('stageLiveImg');
  if (!img) return;
  img.onload = () => {
    img.classList.remove('loading');
    if (!liveUp) { liveUp = true; applyLiveState(); pushSceneToLive(true); }
  };
  img.onerror = () => {
    img.classList.remove('loading');
    if (liveUp) { liveUp = false; applyLiveState(); }
  };
  if (!liveUp) img.classList.add('loading');
  img.src = '/api/live?t=' + Date.now();
}

/* 抓帧：burst=true 时补 5 帧（每 260ms），等真机页面的过渡动画走完 */
function refreshStageLive(burst) {
  if (stageView !== 'live') return;
  tickStageLive();
  if (!burst) return;
  _liveBurstLeft = 5;
  if (!_liveBurstTimer) _liveBurstTimer = setTimeout(stepLiveBurst, 260);
}
function stepLiveBurst() {
  _liveBurstTimer = null;
  if (_liveBurstLeft <= 0) return;
  _liveBurstLeft -= 1;
  if (stageView === 'live') tickStageLive();
  if (_liveBurstLeft > 0) _liveBurstTimer = setTimeout(stepLiveBurst, 260);
}

async function stageLiveBoot() {
  setStageView('live');
  liveUp = await probeLive();
  applyLiveState();
  if (liveUp) { refreshStageLive(false); pushSceneToLive(true); }
}

async function stageLiveConnect() {
  const btn = $('btnStageLiveConnect'), err = $('stageLiveErr');
  if (btn) { btn.disabled = true; btn.textContent = '正在启动真机画面…（首次约 10 秒）'; }
  if (err) { err.hidden = true; }
  try {
    const r = await api('/api/editmode/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    if (!r.ok) throw new Error(r.msg || '启动失败');
    toast('真机画面正在启动…');
    let waited = 0;
    const wait = setInterval(async () => {
      waited += 1;
      const ok = await probeLive();
      if (ok) {
        clearInterval(wait);
        liveUp = true; applyLiveState();
        _lastLiveSceneJSON = '';
        if (btn) { btn.disabled = false; btn.textContent = '▶ 连接真机画面'; }
        pushSceneToLive(true);        // 推送成功后会补帧，这里不再重复刷
        toast('真机画面已连接，可以直接点击操作');
      } else if (waited >= 25) {
        clearInterval(wait);
        if (btn) { btn.disabled = false; btn.textContent = '▶ 重试连接'; }
        if (err) { err.hidden = false; err.textContent = '启动超时。请确认前端服务（8080 端口）在运行，稍后重试。'; }
      }
    }, 800);
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = '▶ 连接真机画面'; }
    if (err) { err.hidden = false; err.textContent = (e && e.message) || '启动失败'; }
  }
}

/* 屏幕坐标 → 真机视口坐标（真机画面固定 600×1300，与 .phone 同尺寸，1:1 映射） */
function stageXY(event) {
  const rect = $('stageLiveImg').getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * 600;
  const y = (event.clientY - rect.top) / rect.height * 1300;
  return { x: Math.max(0, Math.min(599, x)), y: Math.max(0, Math.min(1299, y)) };
}

async function onStageLiveClick(event) {
  if (event.target.closest('#stageEditPop')) return;
  if (!liveUp) { toast('真机画面未连接，点画面中间的「连接真机画面」'); return; }
  const p = stageXY(event);
  if (livePicking) {
    try {
      const res = await api('/api/live/pick?x=' + p.x.toFixed(1) + '&y=' + p.y.toFixed(1));
      if (!res.ok) { toast(res.msg || '该位置没有可改的元素'); return; }
      showStageEditPop(res, p.x, p.y);
    } catch (e) { toast('拾取元素失败'); }
    return;
  }
  try {
    const res = await api('/api/live/tap', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ x: Math.round(p.x), y: Math.round(p.y) }) });
    if (res.ok) refreshStageLive(true); else toast(res.msg || '点击未生效');
  } catch (e) { toast('点击失败'); }
}

function onStageLiveWheel(event) {
  if (stageView !== 'live' || !liveUp) return;      // 真机没连上：交给舞台缩放
  if (event.ctrlKey || event.shiftKey) return;      // Ctrl / Shift + 滚轮 = 缩放画布
  event.preventDefault();
  event.stopPropagation();                          // 别让舞台的滚轮缩放也处理一次
  const p = stageXY(event);
  _wheelAcc += event.deltaY;
  if (_wheelFlush) return;
  _wheelFlush = setTimeout(() => {
    _wheelFlush = null;
    const dy = Math.round(_wheelAcc);
    _wheelAcc = 0;
    if (!dy) return;
    api('/api/live/scroll', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ x: Math.round(p.x), y: Math.round(p.y), dy: dy, dx: 0 }) })
      .then(() => refreshStageLive(false)).catch(() => {});
  }, 110);
}

function showStageEditPop(info, x, y) {
  stageEditInfo = info;
  const meta = KIND_META[info.kind] || KIND_META.text;
  const value = (info.kind === 'text' || info.kind === 'me_name') ? (info.text || '') : (info.src || '');
  const pop = $('stageEditPop');
  pop.innerHTML =
    '<div class="ep-kind">' + esc(meta.label) + '</div>' +
    '<input id="sepValue" value="' + esc(value) + '" placeholder="' + esc(meta.label) + '">' +
    '<div class="ep-actions"><button type="button" class="ep-cancel" id="sepCancel">取消</button>' +
    '<button type="button" class="ep-save" id="sepSave">保存</button></div>' +
    '<div class="ep-hint">' + esc(meta.hint || '') + '</div>';
  pop.hidden = false;
  let left = x, top = y + 8;
  const pw = pop.offsetWidth || 236, phh = pop.offsetHeight || 132;
  if (left + pw > 594) left = 594 - pw;
  if (left < 6) left = 6;
  if (top + phh > 1294) top = y - phh - 8;
  if (top < 6) top = 6;
  pop.style.left = Math.round(left) + 'px';
  pop.style.top = Math.round(top) + 'px';
  const input = $('sepValue'); input.focus(); input.select();
  $('sepSave').onclick = saveStageEdit;
  $('sepCancel').onclick = () => { pop.hidden = true; stageEditInfo = null; };
}

async function saveStageEdit() {
  if (!stageEditInfo) return;
  const meta = KIND_META[stageEditInfo.kind] || KIND_META.text;
  const value = $('sepValue').value.trim();
  try {
    const res = await api('/api/live/edit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: stageEditInfo.id, prop: meta.prop, value: value }) });
    if (res.ok) { toast('已修改' + meta.label + '：' + (value || '（已清空）')); $('stageEditPop').hidden = true; stageEditInfo = null; refreshStageLive(true); }
    else toast('修改失败：' + (res.msg || '未知错误'));
  } catch (e) { toast('修改失败'); }
}

async function stageLiveBack() {
  if (!liveUp) { toast('真机画面未连接'); return; }
  try {
    const res = await api('/api/live/back', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    if (res.ok) refreshStageLive(true); else toast(res.msg || '返回失败');
  } catch (e) { toast('返回失败'); }
}

async function stageTypeSend() {
  const input = $('stageTypeInput'), text = input.value;
  if (!text) return;
  if (!liveUp) { toast('真机画面未连接'); return; }
  try {
    const res = await api('/api/live/type', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
    if (res.ok) { input.value = ''; refreshStageLive(true); }
    else { toast(res.msg || '输入失败：先在真机上点一下输入框'); }
  } catch (e) { toast('输入失败'); }
}

/* 把当前编辑的场景推给真机。挂在 renderPhone 末尾 + 900ms 防抖，
   并且**序列化比对**：内容没变就一个请求都不发。
   于是「右边面板改一个字，左边真机画面跟着变」，但不会打字就卡。 */
function pushSceneToLive(immediate) {
  if (!liveUp) return;
  if (_livePushTimer) { clearTimeout(_livePushTimer); _livePushTimer = null; }
  const send = () => {
    _livePushTimer = null;
    let snap = '';
    try { snap = JSON.stringify(scene); } catch (e) { return; }
    if (snap === _lastLiveSceneJSON) return;      // 场景没变：不推、不刷，零开销
    _lastLiveSceneJSON = snap;
    api('/api/live/scene', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scene: scene }) })
      .then(r => { if (r && r.ok) refreshStageLive(true); })
      .catch(() => { _lastLiveSceneJSON = ''; });
  };
  if (immediate) send(); else _livePushTimer = setTimeout(send, 900);
}

function bindStageLive() {
  $('btnViewLive').onclick = () => setStageView('live');
  $('btnViewDraft').onclick = () => setStageView('draft');
  $('btnStageLiveConnect').onclick = stageLiveConnect;
  $('btnStageBack').onclick = stageLiveBack;
  $('btnStageSend').onclick = stageTypeSend;
  $('stageTypeInput').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); stageTypeSend(); } });
  $('btnStagePick').onclick = () => {
    livePicking = !livePicking;
    $('btnStagePick').classList.toggle('on', livePicking);
    $('stageLiveImg').classList.toggle('picking', livePicking);
    toast(livePicking ? '点选模式：点画面上的文字 / 头像 / 背景即可改' : '已切回操作模式：点画面 = 点手机');
  };
  $('stageLiveImg').addEventListener('click', onStageLiveClick);
  $('stageLiveImg').addEventListener('wheel', onStageLiveWheel, { passive: false });
}

function bindDebug() {"""


def main():
    s = io.open(PATH, encoding="utf-8").read()
    pairs = [
        ("css", CSS_ANCHOR, CSS_NEW),
        ("phone-html", PHONE_OLD, PHONE_NEW),
        ("stage-js", JS_ANCHOR, JS_NEW),
        ("renderPhone-push", RENDER_OLD, RENDER_NEW),
        ("bindDebug-bind", BIND_OLD, BIND_NEW),
        ("init-boot", INIT_OLD, INIT_NEW),
        ("top-hint", HINT_OLD, HINT_NEW),
    ]
    for name, old, new in pairs:
        n = s.count(old)
        if n != 1:
            print("!! %s 锚点命中 %d 次（应为 1）" % (name, n))
            sys.exit(1)
        s = s.replace(old, new, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("OK  %s  (%d 处 · 不卡版)" % (PATH, len(pairs)))


if __name__ == "__main__":
    main()
