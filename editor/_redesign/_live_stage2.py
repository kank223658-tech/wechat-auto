# -*- coding: utf-8 -*-
"""
scene.html 主舞台「真机画面」改造（2026-09-11）
================================================
把左边那台手写 HTML 复刻手机，换成 main.py --editmode 真实渲染出来的画面：
  · 与最终成片同一套 UI（vue-WeChat + enhance 层），天然不会再「跟不上新界面」
  · 点击 = 点手机（转发 /api/live/tap）—— 能进聊天、切页面、翻朋友圈
  · 滚轮 = 滚动真机页面；Ctrl/Shift+滚轮 = 缩放画布
  · 「✎ 点选改」= 点画面上的文字/头像/背景直接改
  · 右边面板随便改什么，都会防抖推送给真机（/api/live/scene），左边立刻跟着变
手写复刻保留为「🎨 示意稿」兜底（真机未连接时也能看结构）。
"""
import io
import sys

PATH = "G:/weixin-auto/editor/scene.html"

# ============================================================
# 1) 样式
# ============================================================
CSS_ANCHOR = ".hint.compacted.open .hint-body { display: block; }\n</style>"

CSS_NEW = """.hint.compacted.open .hint-body { display: block; }

/* ===== 真机画面（主舞台实时画面：与成片同一套 UI，可点击操作） ===== */
.phone-live { position: absolute; left: 0; top: 0; width: 600px; height: 1300px; display: block; z-index: 40; background: #000; cursor: pointer; -webkit-user-drag: none; }
.phone-live[hidden] { display: none; }
.phone-live.picking { cursor: crosshair; }
.phone-live.loading { opacity: .55; }
.phone .live-badge {
  position: absolute; right: 12px; top: 12px; z-index: 60;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 999px;
  background: rgba(10, 172, 95, .94); color: #fff;
  font-size: 11px; font-weight: 600; letter-spacing: .3px;
  box-shadow: 0 3px 10px rgba(0, 0, 0, .3);
}
.phone .live-badge[hidden] { display: none; }
.phone .live-badge.off { background: rgba(107, 114, 128, .92); }
.phone .live-badge i { width: 6px; height: 6px; border-radius: 50%; background: #fff; animation: lbPulse 1.6s ease-in-out infinite; }
.phone .live-badge.off i { animation: none; }
@keyframes lbPulse { 0%, 100% { opacity: 1; } 50% { opacity: .2; } }

.phone-live-empty {
  position: absolute; left: 0; top: 0; width: 600px; height: 1300px; z-index: 45;
  display: grid; place-content: center; justify-items: center; gap: 10px;
  padding: 0 60px; text-align: center; background: #12141a; color: #e5e7eb;
}
.phone-live-empty[hidden] { display: none; }
.phone-live-empty .ple-ico { font-size: 46px; line-height: 1; }
.phone-live-empty .ple-t { font-size: 18px; font-weight: 600; }
.phone-live-empty .ple-d { font-size: 13.5px; line-height: 1.8; color: #9ca3af; }
.phone-live-empty .ple-btn { margin-top: 8px; padding: 11px 24px; font-size: 14.5px; font-weight: 600; color: #fff; background: #0aac5f; border: 0; border-radius: 999px; cursor: pointer; }
.phone-live-empty .ple-btn:hover { background: #099455; }
.phone-live-empty .ple-btn:disabled { opacity: .65; cursor: default; }
.phone-live-empty .ple-err { font-size: 12px; line-height: 1.7; color: #f3a5a5; max-width: 400px; }
.phone-live-empty .ple-err[hidden] { display: none; }

.phone .edit-pop { z-index: 80; width: 236px; max-width: none; }
#stageEditPop[hidden] { display: none; }

/* 舞台底部浮动工具条 */
.stage-live-bar {
  position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%); z-index: 70;
  display: flex; align-items: center; gap: 8px; padding: 7px 11px;
  border-radius: 999px; background: rgba(255, 255, 255, .97);
  border: 1px solid rgba(17, 24, 39, .1); box-shadow: 0 12px 32px rgba(17, 24, 39, .18);
  backdrop-filter: blur(8px); font-size: 13px; white-space: nowrap;
}
.slb-group { display: inline-flex; background: #f2f3f6; border-radius: 999px; padding: 2px; }
.slb-group button { height: 26px; padding: 0 13px; border: 0; border-radius: 999px; background: transparent; color: #55606e; font-size: 12.5px; cursor: pointer; }
.slb-group button.active { background: #fff; color: #111827; font-weight: 600; box-shadow: 0 1px 3px rgba(17, 24, 39, .14); }
.slb-btn { height: 28px; padding: 0 12px; border: 1px solid rgba(17, 24, 39, .13); border-radius: 999px; background: #fff; color: #374151; font-size: 12.5px; cursor: pointer; }
.slb-btn:hover { background: #f6f7f9; }
.slb-btn.on { background: #0aac5f; border-color: #0aac5f; color: #fff; }
.slb-sep { width: 1px; height: 20px; background: rgba(17, 24, 39, .13); }
.stage-live-bar input { width: 200px; height: 28px; padding: 0 12px; border: 1px solid rgba(17, 24, 39, .15); border-radius: 999px; font-size: 12.5px; background: #fff; color: #111827; outline: none; }
.stage-live-bar input:focus { border-color: #0aac5f; }
.slb-state { font-size: 11.5px; color: #9ca3af; padding-right: 3px; }
.slb-state.ok { color: #0aac5f; font-weight: 600; }
</style>"""

# ============================================================
# 2) HTML：手机里加真机画面层 + 舞台底部工具条
# ============================================================
PHONE_OLD = """          <div class="phone" data-page-node-id="l7DjpI2rnS5Q2KrvwCExv2">
            <div class="phone-inner" id="phoneInner" data-page-node-id="cW6kV9yKwyUzsuEEAWnWEl"></div>
          </div>
        </div>
      </div>"""

PHONE_NEW = """          <div class="phone" data-page-node-id="l7DjpI2rnS5Q2KrvwCExv2">
            <div class="phone-inner" id="phoneInner" data-page-node-id="cW6kV9yKwyUzsuEEAWnWEl"></div>
            <img class="phone-live" id="stageLiveImg" alt="真机实时画面" hidden data-page-node-id="Yz3kLvPq1WmSdR8bTnQxHa">
            <div class="live-badge" id="stageLiveBadge" hidden data-page-node-id="Mv7TpKs2JdQnLcV9ZaWrEy"><i></i>真机 LIVE</div>
            <div class="edit-pop" id="stageEditPop" hidden data-page-node-id="Jp4RwNc8YbHmTqsZ6LfVdA"></div>
            <div class="phone-live-empty" id="stageLiveEmpty" hidden data-page-node-id="Qd9XcVm3LbTzRpWsN7JkHy">
              <div class="ple-ico" data-page-node-id="Rb2WnJx7PcVqLmTs9ZfDkA">📱</div>
              <div class="ple-t" data-page-node-id="Te5KmQs3NvLxJpRw8BcYdZ">真机画面未连接</div>
              <div class="ple-d" data-page-node-id="Mw8LsPd4RtQnVbXz2JfKcY">左边这块显示的就是最终生成视频里的那套界面<br data-page-node-id="Xn6TqJr9LdWmVpZb3KcRfA">连接后可以直接点击操作（进聊天 / 翻朋友圈 / 改文字）</div>
              <button type="button" class="ple-btn" id="btnStageLiveConnect" data-page-node-id="Vf3NqLm6WpTzRsXd8JbKcE">▶ 连接真机画面</button>
              <div class="ple-err" id="stageLiveErr" hidden data-page-node-id="Lc7VdKx2JmQbTpNs5RfWyH"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="stage-live-bar" id="stageLiveBar" data-page-node-id="Hg4ZtRv8KmXcJpLb6NwYdQ">
        <div class="slb-group" data-page-node-id="Pd2NvLq7KmZxJbTc5RwYfM">
          <button type="button" id="btnViewLive" class="active" title="显示真机实时画面（与最终视频同一套 UI，可点击操作）" data-page-node-id="Kq6WmJv3NdLxRpZb9TcYfA">📱 真机画面</button>
          <button type="button" id="btnViewDraft" title="显示编辑器内的静态示意稿（不参与渲染，仅用于看结构）" data-page-node-id="Rb8LdPk2NvQmJxTz5WcYfS">🎨 示意稿</button>
        </div>
        <span class="slb-sep" data-page-node-id="Tz9NqWd4LmKvJpRx7BcYfG"></span>
        <button type="button" class="slb-btn" id="btnStagePick" title="点选模式：点画面上的文字 / 头像 / 背景即可直接修改" data-page-node-id="Wj3RmKx9LdPvNqTb6ZcYfH">✎ 点选改</button>
        <button type="button" class="slb-btn" id="btnStageBack" title="真机返回上一页" data-page-node-id="Lm5TpQv8NdKxJbRz2WcYfJ">← 返回</button>
        <input id="stageTypeInput" placeholder="先在真机上点一下输入框，再在这里打字" aria-label="向真机输入文字" data-page-node-id="Nq7VdKx3LmPvJbTz9RcYfB">
        <button type="button" class="slb-btn" id="btnStageSend" data-page-node-id="Px4LmJv9NdQbKtRz7WcYfC">发送</button>
        <span class="slb-state" id="stageLiveState" data-page-node-id="Qr2NmKx8LdPvJbTz5WcYfD">真机未连接</span>
      </div>"""

# ============================================================
# 3) JS：真机画面控制块（插在 bindDebug 之前）
# ============================================================
JS_ANCHOR = "function bindDebug() {"

JS_NEW = """/* ---------- 真机画面：主舞台 = 真实渲染（与成片同一套 UI，可点击操作） ---------- */
let stageView = 'live';        // live = 真机画面 / draft = 静态示意稿
let liveUp = false;            // 真机画面是否已连上
let stageLiveTimer = null;
let livePicking = false;       // 点选模式（点画面 = 拾取元素改属性）
let stageEditInfo = null;
let _livePushTimer = null;
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
  if (stageView === 'live') startStageLivePoll(); else stopStageLivePoll();
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

function startStageLivePoll() {
  stopStageLivePoll();
  const loop = () => {
    stageLiveTimer = setTimeout(loop, liveUp ? 350 : 1200);
    if (stageView === 'live') tickStageLive();
  };
  loop();
}
function stopStageLivePoll() { if (stageLiveTimer) { clearTimeout(stageLiveTimer); stageLiveTimer = null; } }

async function stageLiveBoot() {
  setStageView('live');
  liveUp = await probeLive();
  applyLiveState();
  startStageLivePoll();
  if (liveUp) pushSceneToLive(true);
}

async function stageLiveConnect() {
  const btn = $('btnStageLiveConnect'), err = $('stageLiveErr');
  if (btn) { btn.disabled = true; btn.textContent = '正在启动真机画面…（首次约 10 秒）'; }
  if (err) { err.hidden = true; }
  try {
    const r = await api('/api/editmode/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    if (!r.ok) throw new Error(r.msg || '启动失败');
    toast('真机画面正在启动…');
    startStageLivePoll();
    let waited = 0;
    const wait = setInterval(async () => {
      waited += 1;
      const ok = await probeLive();
      if (ok) {
        clearInterval(wait);
        liveUp = true; applyLiveState();
        if (btn) { btn.disabled = false; btn.textContent = '▶ 连接真机画面'; }
        pushSceneToLive(true);
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
    if (!res.ok) toast(res.msg || '点击未生效');
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
    api('/api/live/scroll', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ x: Math.round(p.x), y: Math.round(p.y), dy: dy, dx: 0 }) }).catch(() => {});
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
    if (res.ok) { toast('已修改' + meta.label + '：' + (value || '（已清空）')); $('stageEditPop').hidden = true; stageEditInfo = null; }
    else toast('修改失败：' + (res.msg || '未知错误'));
  } catch (e) { toast('修改失败'); }
}

async function stageLiveBack() {
  if (!liveUp) { toast('真机画面未连接'); return; }
  try {
    const res = await api('/api/live/back', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    if (!res.ok) toast(res.msg || '返回失败');
  } catch (e) { toast('返回失败'); }
}

async function stageTypeSend() {
  const input = $('stageTypeInput'), text = input.value;
  if (!text) return;
  if (!liveUp) { toast('真机画面未连接'); return; }
  try {
    const res = await api('/api/live/type', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) });
    if (res.ok) { input.value = ''; } else { toast(res.msg || '输入失败：先在真机上点一下输入框'); }
  } catch (e) { toast('输入失败'); }
}

/* 把当前编辑的场景推给真机。挂在 renderPhone 末尾 + 防抖，
   于是「右边面板改一个字，左边真机画面立刻跟着变」。 */
function pushSceneToLive(immediate) {
  if (!liveUp) return;
  if (_livePushTimer) { clearTimeout(_livePushTimer); _livePushTimer = null; }
  const send = () => {
    _livePushTimer = null;
    api('/api/live/scene', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scene: scene }) }).catch(() => {});
  };
  if (immediate) send(); else _livePushTimer = setTimeout(send, 420);
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

RENDER_OLD = """    html += tabbarHtml();
  }
  inner.innerHTML = html;
}"""

RENDER_NEW = """    html += tabbarHtml();
  }
  inner.innerHTML = html;
  /* 场景一变就推给真机画面（真机未连接时内部直接返回） */
  pushSceneToLive();
}"""

BIND_OLD = "  $('liveImg').addEventListener('click', onScreenClick);"

BIND_NEW = """  $('liveImg').addEventListener('click', onScreenClick);
  bindStageLive();"""

INIT_OLD = "  bindPhoneEvents(); bindTopbar(); bindDebug(); setupStage();"

INIT_NEW = """  bindPhoneEvents(); bindTopbar(); bindDebug(); setupStage();
  stageLiveBoot();"""

HINT_OLD = "左：手机画面（固定 600×1300，滚轮缩放、拖拽平移，点任意元素即改）。右：结构化面板编辑联系人与消息。「生成并运行」会保存场景、生成工作流并直接开跑，实时画面随执行自动刷新。"
HINT_NEW = "左：真机画面——就是最终视频里的那套界面，可直接点击操作（进聊天 / 翻朋友圈）；滚轮滚动真机，Ctrl 或 Shift + 滚轮缩放画布；点「✎ 点选改」后点画面上的文字 / 头像 / 背景即可直接改。右：结构化面板编辑联系人与消息，改动会实时同步到左边真机画面。「生成并运行」会保存场景、生成工作流并直接开跑。"


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
    print("OK  %s  (%d 处)" % (PATH, len(pairs)))


if __name__ == "__main__":
    main()
