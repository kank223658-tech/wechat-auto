# -*- coding: utf-8 -*-
"""场景编辑器：预览套场景的「应用后校验 + 有限次重试」。

问题：`__wxEmbedReady` 之后的 push 偶尔失效 —— 真实前端在「欢迎页 → 首页」路由
切换期会重渲染列表，把刚套上的场景覆盖回默认参考数据。原实现失败后
`_lastPvSceneJSON` 被清空，但**不会再重试**，于是预览就一直显示默认数据。

修法：推完立刻校验（对比预览首几行名字是否 = 场景首几行），不对就有限次重试
（最多 8 次 × 900ms，约 8 秒），成功即停 —— 绝不变成常驻轮询。
"""
import io
import sys

P = r"G:\weixin-auto\editor\scene.html"

# 1) 状态变量
P1_OLD = "let _lastPvSceneJSON = '';     // 上次已应用的场景快照（没变就不推）"
P1_NEW = ("let _lastPvSceneJSON = '';     // 上次已应用的场景快照（没变就不推）\n"
          "let _pvRetryTimer = null;      // 套场景失败后的重试定时器（有限次）\n"
          "let _pvRetryLeft = 0;          // 剩余重试次数")

# 2) pvApplyScene 之后追加校验函数
P2_OLD = """function pvApplyScene(snap) {
  const w = pvWin();
  if (!w || !w.__wxConfig) return false;
  try { w.__wxConfig.apply(); w.__wxConfig.applyScene(JSON.parse(snap)); return true; }
  catch (e) { return false; }
}"""
P2_NEW = P2_OLD + """

/* 校验预览里真的是这份场景（首几行名字对得上）。
   只有「真套上了」才算成功 —— 否则前端在路由切换期会把它覆盖回去。 */
function pvSceneLooksRight(snap) {
  const w = pvWin();
  if (!w) return false;
  let want = [];
  try { want = (JSON.parse(snap).home || []).slice(0, 3).map(it => it.name || '').filter(Boolean); }
  catch (e) { return false; }
  if (!want.length) return true;
  try {
    const names = [...w.document.querySelectorAll('.wechat-list li.list-row .desc-author')]
      .map(e => e.textContent.trim());
    if (!names.length) return false;
    const hit = want.filter(n => names.indexOf(n) >= 0).length;
    return hit >= Math.min(2, want.length);
  } catch (e) { return false; }
}"""

# 3) pushSceneToPv：失败重试
P3_OLD = """function pushSceneToPv(immediate) {
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
}"""
P3_NEW = """function pushSceneToPv(immediate, isRetry) {
  if (!pvReady) return;
  if (_pvPushTimer) { clearTimeout(_pvPushTimer); _pvPushTimer = null; }
  if (!isRetry) _pvRetryLeft = 8;               // 新一轮同步：重置重试额度
  const send = () => {
    _pvPushTimer = null;
    if (!pvReady) return;
    let snap = '';
    try { snap = JSON.stringify(scene); } catch (e) { return; }
    if (snap === _lastPvSceneJSON) return;        // 场景没变：不发请求、不重渲染
    if (pvApplyScene(snap) && pvSceneLooksRight(snap)) {
      _lastPvSceneJSON = snap;
      _pvRetryLeft = 0;
      return;
    }
    /* 没套上（被前端重渲染覆盖）：有限次重试后放弃，绝不退化成轮询 */
    _lastPvSceneJSON = '';
    if (_pvRetryLeft > 0) {
      _pvRetryLeft--;
      if (!_pvRetryTimer) {
        _pvRetryTimer = setTimeout(() => {
          _pvRetryTimer = null;
          if (pvReady) pushSceneToPv(true, true);
        }, 900);
      }
    }
  };
  if (immediate) send(); else _pvPushTimer = setTimeout(send, 700);
}"""

# 4) 早期套场景也走校验
P4_OLD = """        const snap = JSON.stringify(scene);
        if (pvApplyScene(snap)) _lastPvSceneJSON = snap;"""
P4_NEW = """        const snap = JSON.stringify(scene);
        if (pvApplyScene(snap) && pvSceneLooksRight(snap)) _lastPvSceneJSON = snap;"""

# 5) 就绪时清空重试计数
P5_OLD = """      clearInterval(t);
      pvReady = true;
      _lastPvSceneJSON = '';"""
P5_NEW = """      clearInterval(t);
      pvReady = true;
      _lastPvSceneJSON = '';
      _pvRetryLeft = 0;"""

# 6) 自适应留出底部工具条的间隙
P6_OLD = "  const reserve = (bar ? bar.offsetHeight : 46) + 56;      // 底部工具条 + 上下留白"
P6_NEW = "  const reserve = (bar ? bar.offsetHeight : 46) + 76;      // 底部工具条 + 上下留白"

PATCHES = [
    ("重试状态变量", P1_OLD, P1_NEW),
    ("场景校验函数", P2_OLD, P2_NEW),
    ("推送失败重试", P3_OLD, P3_NEW),
    ("早期套场景校验", P4_OLD, P4_NEW),
    ("就绪清计数", P5_OLD, P5_NEW),
    ("自适应留间隙", P6_OLD, P6_NEW),
]


def main():
    s = io.open(P, encoding="utf-8").read()
    for name, old, new in PATCHES:
        n = s.count(old)
        if n != 1:
            print("中止：%s 命中 %d 次（期望 1）" % (name, n))
            sys.exit(1)
        s = s.replace(old, new, 1)
        print("OK  %s" % name)
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("\n全部 %d 处替换完成" % len(PATCHES))


main()
