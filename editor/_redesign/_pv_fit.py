# -*- coding: utf-8 -*-
"""场景编辑器：舞台自适应缩放。

背景：手机画面固定 600×1300，而舞台可视高度只有约 780（overflow:hidden），
默认 zoom=1 时手机底部约 43% 被裁掉 —— 底部 tab 栏看不到也点不到。
本次改为「默认自适应」：整台手机完整落在舞台内（避开底部工具条），
窗口尺寸变化时自动重算；用户手动缩放/拖动后不再自动干预。

锚点全部为精确匹配，命中次数必须为 1，否则中止。
"""
import io
import sys

P = r"G:\weixin-auto\editor\scene.html"

A1_OLD = "let zoom = 1, panX = 0, panY = 0;"
A1_NEW = (
    "let zoom = 1, panX = 0, panY = 0;\n"
    "let zoomManual = false;   // 用户手动调过缩放/拖动后，窗口变化不再自动适应"
)

A2_OLD = """function applyZoom() {
  const wrap = $('phoneWrap');
  wrap.style.setProperty('--zoom', zoom);
  wrap.style.left = (50 + panX) + '%';
  wrap.style.top = (40 + panY) + 'px';
  $('zoomLabel').textContent = Math.round(zoom * 100) + '%';
}"""
A2_NEW = A2_OLD + """

/* 自适应缩放：让整台手机（600×1300）完整落在舞台里，并避开底部工具条 */
function fitZoom() {
  const stage = $('stage');
  if (!stage) return 1;
  const bar = document.querySelector('.stage-live-bar');
  const reserve = (bar ? bar.offsetHeight : 46) + 56;      // 底部工具条 + 上下留白
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

A3_OLD = "  $('btnZoomIn').onclick = () => { zoom = Math.min(3, zoom + 0.1); applyZoom(); };"
A3_NEW = "  $('btnZoomIn').onclick = () => { zoomManual = true; zoom = Math.min(3, zoom + 0.1); applyZoom(); };"

A4_OLD = "  $('btnZoomOut').onclick = () => { zoom = Math.max(0.2, zoom - 0.1); applyZoom(); };"
A4_NEW = "  $('btnZoomOut').onclick = () => { zoomManual = true; zoom = Math.max(0.2, zoom - 0.1); applyZoom(); };"

A5_OLD = "  $('btnZoomFit').onclick = () => { zoom = 1; panX = 0; panY = 0; applyZoom(); };"
A5_NEW = "  $('btnZoomFit').onclick = () => { zoomManual = false; applyZoomFit(); };"

A6_OLD = """    zoom = Math.max(0.2, Math.min(3, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
    applyZoom();"""
A6_NEW = """    zoomManual = true;
    zoom = Math.max(0.2, Math.min(3, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
    applyZoom();"""

A7_OLD = """    if (!dragging) return;
    panX = ox + (e.clientX - sx) / 4; panY = oy + (e.clientY - sy) / 4;"""
A7_NEW = """    if (!dragging) return;
    zoomManual = true;
    panX = ox + (e.clientX - sx) / 4; panY = oy + (e.clientY - sy) / 4;"""

A8_OLD = "  renderPhone(); renderPanel(); applyZoom();"
A8_NEW = "  renderPhone(); renderPanel(); applyZoomFit();   // 默认自适应：整台手机完整可见（不再被裁掉底部）"

A9_OLD = "  bindPhoneEvents(); bindTopbar(); bindDebug(); setupStage();"
A9_NEW = ("  bindPhoneEvents(); bindTopbar(); bindDebug(); setupStage();\n"
          "  window.addEventListener('resize', () => { if (!zoomManual) applyZoomFit(); });")

PATCHES = [
    ("缩放状态变量", A1_OLD, A1_NEW),
    ("fitZoom/applyZoomFit", A2_OLD, A2_NEW),
    ("放大按钮", A3_OLD, A3_NEW),
    ("缩小按钮", A4_OLD, A4_NEW),
    ("适应按钮", A5_OLD, A5_NEW),
    ("滚轮缩放", A6_OLD, A6_NEW),
    ("拖动平移", A7_OLD, A7_NEW),
    ("init 应用自适应", A8_OLD, A8_NEW),
    ("resize 监听", A9_OLD, A9_NEW),
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
