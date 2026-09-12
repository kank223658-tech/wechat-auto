# -*- coding: utf-8 -*-
"""回滚 scene.html 的「真机画面」改造（用户反馈：接入实时画面后卡死）。

把 _live_stage2.py 的 7 处替换原样倒回，scene.html 恢复为纯静态示意稿 + 原交互。
main.py / editor_server.py 里新增的 /api/live/scene|scroll|back 属于既有「编辑模式」
的可选指令，不参与常驻轮询，保留（不影响性能）。
"""
import io
import sys

sys.path.insert(0, "G:/weixin-auto/editor/_redesign")
import _live_stage2 as P   # noqa: E402  复用同一批锚点，反向替换

PATH = P.PATH
pairs = [
    ("css", P.CSS_NEW, P.CSS_ANCHOR),
    ("phone-html", P.PHONE_NEW, P.PHONE_OLD),
    ("stage-js", P.JS_NEW, P.JS_ANCHOR),
    ("renderPhone-push", P.RENDER_NEW, P.RENDER_OLD),
    ("bindDebug-bind", P.BIND_NEW, P.BIND_OLD),
    ("init-boot", P.INIT_NEW, P.INIT_OLD),
    ("top-hint", P.HINT_NEW, P.HINT_OLD),
]

s = io.open(PATH, encoding="utf-8").read()
for name, new, old in pairs:
    n = s.count(new)
    if n != 1:
        print("!! 回滚锚点命中 %d 次（应为 1）：%s" % (n, name))
        sys.exit(1)
    s = s.replace(new, old, 1)

# 兜底：确认没有任何真机残留
for junk in ("stageLiveImg", "pushSceneToLive", "btnViewLive", "stage-live-bar",
             "stageLiveBoot", "onStageLiveWheel", "liveUp"):
    if junk in s:
        print("!! 仍有残留：%s（%d 处）" % (junk, s.count(junk)))
        sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write(s)
print("OK  已回滚 %s（7 处），无残留" % PATH)
