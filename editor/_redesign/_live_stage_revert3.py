# -*- coding: utf-8 -*-
"""回滚 scene.html 的「真机画面 · 不卡版」改造（对应 _live_stage3.py）。"""
import io
import sys

import _live_stage3 as P

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

for junk in ("stageLiveImg", "pushSceneToLive", "btnViewLive", "stage-live-bar",
             "stageLiveBoot", "onStageLiveWheel", "refreshStageLive", "liveUp"):
    if junk in s:
        print("!! 仍有残留：%s（%d 处）" % (junk, s.count(junk)))
        sys.exit(1)

io.open(PATH, "w", encoding="utf-8", newline="").write(s)
print("OK  已回滚 %s（7 处），无残留" % PATH)
