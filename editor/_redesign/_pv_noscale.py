# -*- coding: utf-8 -*-
"""撤掉「自适应缩放」，改成：实时预览锁定 1:1 + 滚轮上下平移。

原因（实测，见 memory 2026-09-11）：
  Chrome 会把「被 CSS 缩放（transform:scale / zoom）的 iframe」渲染成黑屏 ——
  已用操作系统级真截图定性：1:1 亮度 53，缩到 0.58 只剩 10.9；
  各种缩放方式（transform / zoom / 提升合成层 / 改 transform-origin）都一样黑。
  而 iframe 内容一改尺寸就会重排（视口变了），画面不再忠实。

所以实时预览（真实界面 iframe）必须保持 1:1；看手机下半部分改用滚轮上下平移。
配套：预览里禁用缩放（点了会黑屏），示意稿仍可自由缩放。

第一步 = 完整反向 `_pv_fit.py` 的 9 处替换；第二步 = 加入上面的新行为。
锚点全部精确匹配、命中必须为 1。
"""
import io
import sys

P = r"G:\weixin-auto\editor\scene.html"

# ---------- 第一步：反向 _pv_fit.py ----------
REVERT = [
    ("缩放状态变量",
     "let zoom = 1, panX = 0, panY = 0;\n"
     "let zoomManual = false;   // 用户手动调过缩放/拖动后，窗口变化不再自动适应",
     "let zoom = 1, panX = 0, panY = 0;"),
    ("fitZoom/applyZoomFit", None, None),   # 占位，下面单独处理
    ("放大按钮",
     "  $('btnZoomIn').onclick = () => { zoomManual = true; zoom = Math.min(3, zoom + 0.1); applyZoom(); };",
     "  $('btnZoomIn').onclick = () => { zoom = Math.min(3, zoom + 0.1); applyZoom(); };"),
    ("缩小按钮",
     "  $('btnZoomOut').onclick = () => { zoomManual = true; zoom = Math.max(0.2, zoom - 0.1); applyZoom(); };",
     "  $('btnZoomOut').onclick = () => { zoom = Math.max(0.2, zoom - 0.1); applyZoom(); };"),
    ("适应按钮",
     "  $('btnZoomFit').onclick = () => { zoomManual = false; applyZoomFit(); };",
     "  $('btnZoomFit').onclick = () => { zoom = 1; panX = 0; panY = 0; applyZoom(); };"),
    ("滚轮缩放",
     "    zoomManual = true;\n"
     "    zoom = Math.max(0.2, Math.min(3, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));",
     "    zoom = Math.max(0.2, Math.min(3, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));"),
    ("拖动平移",
     "    if (!dragging) return;\n    zoomManual = true;\n",
     "    if (!dragging) return;\n"),
    ("init 应用自适应",
     "  renderPhone(); renderPanel(); applyZoomFit();   // 默认自适应：整台手机完整可见（不再被裁掉底部）",
     "  renderPhone(); renderPanel(); applyZoom();"),
    ("resize 监听",
     "  bindPhoneEvents(); bindTopbar(); bindDebug(); setupStage();\n"
     "  window.addEventListener('resize', () => { if (!zoomManual) applyZoomFit(); });",
     "  bindPhoneEvents(); bindTopbar(); bindDebug(); setupStage();"),
]

FIT_BLOCK = """

/* 自适应缩放：让整台手机（600×1300）完整落在舞台里，并避开底部工具条 */
function fitZoom() {
  const stage = $('stage');
  if (!stage) return 1;
  const bar = document.querySelector('.stage-live-bar');
  const reserve = (bar ? bar.offsetHeight : 46) + 76;      // 底部工具条 + 上下留白
  const byH = (stage.clientHeight - reserve) / 1300;
  const byW = (stage.clientWidth - 80) / 600;
  return Math.max(0.2, Math.min(1, Math.min(byH, byW)));
}
function applyZoomFit() {
  zoom = fitZoom();
  panX = 0;
  panY = 0;
  applyZoom();
}"""

# ---------- 第二步：新行为 ----------
APPLY_OLD = """function applyZoom() {
  const wrap = $('phoneWrap');
  wrap.style.setProperty('--zoom', zoom);"""

APPLY_NEW = """/* 实时预览是真实界面 iframe —— 被缩放过会被浏览器渲染成黑屏（实测），
   所以预览下把缩放锁死在 1:1，靠滚轮上下平移看整台手机 */
function isPvScaleBlocked() {
  return stageView === 'pv';
}
function warnPvNoZoom() {
  toast('实时预览是 1:1 的真实界面（缩放会黑屏）：滚轮可上下移动画面，需要缩放请切到「示意稿」');
}

function applyZoom() {
  if (isPvScaleBlocked()) zoom = 1;
  const wrap = $('phoneWrap');
  wrap.style.setProperty('--zoom', zoom);"""

WHEEL_OLD = """  stage.addEventListener('wheel', e => {
    e.preventDefault();
    zoom = Math.max(0.2, Math.min(3, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
    applyZoom();
  }, { passive: false });"""

WHEEL_NEW = """  stage.addEventListener('wheel', e => {
    e.preventDefault();
    if (isPvScaleBlocked()) {
      /* 实时预览：滚轮 = 上下平移（手机 1300 高，舞台只有几百高，移下去才看得到底部 tab 栏） */
      panY = Math.max(-620, Math.min(60, panY - e.deltaY * 0.6));
      applyZoom();
      return;
    }
    zoom = Math.max(0.2, Math.min(3, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
    applyZoom();
  }, { passive: false });"""

ZOOMIN_OLD = "  $('btnZoomIn').onclick = () => { zoom = Math.min(3, zoom + 0.1); applyZoom(); };"
ZOOMIN_NEW = ("  $('btnZoomIn').onclick = () => { if (isPvScaleBlocked()) { warnPvNoZoom(); return; }\n"
              "    zoom = Math.min(3, zoom + 0.1); applyZoom(); };")
ZOOMOUT_OLD = "  $('btnZoomOut').onclick = () => { zoom = Math.max(0.2, zoom - 0.1); applyZoom(); };"
ZOOMOUT_NEW = ("  $('btnZoomOut').onclick = () => { if (isPvScaleBlocked()) { warnPvNoZoom(); return; }\n"
               "    zoom = Math.max(0.2, zoom - 0.1); applyZoom(); };")

# 切换视图时把平移归零（换视图不要停在半截）
SWITCH_ANCHOR = "function applyLiveState() {"


def patch(s, pairs, label):
    for name, old, new in pairs:
        if old is None:
            continue
        n = s.count(old)
        if n != 1:
            print("中止[%s]：%s 命中 %d 次（期望 1）" % (label, name, n))
            sys.exit(1)
        s = s.replace(old, new, 1)
        print("OK  [%s] %s" % (label, name))
    return s


def main():
    s = io.open(P, encoding="utf-8").read()

    # 第一步
    s = patch(s, REVERT, "撤掉自适应")
    if s.count(FIT_BLOCK) != 1:
        print("中止：find 不到 fitZoom 代码块")
        sys.exit(1)
    s = s.replace(FIT_BLOCK, "", 1)
    print("OK  [撤掉自适应] fitZoom/applyZoomFit 代码块")

    # 第二步
    s = patch(s, [
        ("预览锁 1:1", APPLY_OLD, APPLY_NEW),
        ("滚轮平移", WHEEL_OLD, WHEEL_NEW),
        ("放大按钮提示", ZOOMIN_OLD, ZOOMIN_NEW),
        ("缩小按钮提示", ZOOMOUT_OLD, ZOOMOUT_NEW),
    ], "预览锁 1:1")

    # 切视图时不额外处理（panY 由用户滚轮控制；切到预览时 applyZoom 会把 zoom 锁回 1）

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("\n完成")


main()
