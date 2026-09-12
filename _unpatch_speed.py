# -*- coding: utf-8 -*-
"""由「当前（已提速）」文件反向生成「旧节奏」副本，用于 A/B 对照录制。

产物落在 _tf_old/ 下（只有 4 个转账相关文件）。
注意：只回退「时间/曲线/微动效」，保留颜色标定与 pointerdown 去重修复 ——
这样左右两版除了动画节奏以外完全一致，对比才干净。

用法: py _unpatch_speed.py
"""
import io
import os
import sys

ROOT = r"G:\weixin-auto"
ENH = os.path.join(ROOT, "enhance")
DST = os.path.join(ROOT, "_tf_old")
os.makedirs(DST, exist_ok=True)
FAIL = []


def unpatch(name, pairs, cut_marker=None):
    src = io.open(os.path.join(ENH, name), encoding="utf-8").read()
    if cut_marker:
        i = src.find(cut_marker)
        if i < 0:
            FAIL.append("%s: 找不到待切除块 %r" % (name, cut_marker))
        else:
            src = src[:i].rstrip() + "\n"
    for new, old, cnt in pairs:
        got = src.count(new)
        if got != cnt:
            FAIL.append("%s: 期望 %d 处 %r，实际 %d" % (name, cnt, new[:60], got))
            continue
        src = src.replace(new, old)
    io.open(os.path.join(DST, name), "w", encoding="utf-8").write(src)
    print("wrote:", name)


# ---------------- transfer_ui.css ----------------
unpatch("transfer_ui.css", [
    ("transition: opacity .16s ease, visibility .16s ease;",
     "transition: opacity .22s ease, visibility .22s ease;", 1),
    (".26s cubic-bezier(.22, 1, .36, 1);  /* 提速：260ms 先快后缓（原 333ms 对称缓动，观感偏匀速） */",
     ".33s cubic-bezier(.45, .05, .55, .95);  /* 实测 333ms 先慢后快再慢 */", 1),
    ("transition: transform .26s cubic-bezier(.22, 1, .36, 1) !important;",
     "transition: transform .33s cubic-bezier(.45, .05, .55, .95) !important;", 1),
    ("transition: transform .18s cubic-bezier(.22, 1, .36, 1), visibility .18s;",
     "transition: transform .26s cubic-bezier(.32, .72, .35, 1), visibility .26s;", 1),
    ("transition: transform .22s cubic-bezier(.2, 1, .32, 1), visibility .22s;",
     "transition: transform .3s cubic-bezier(.25, .46, .45, .94), visibility .3s;", 1),
    ("transition: transform .18s cubic-bezier(.5, 0, .78, .35), visibility .18s;",
     "transition: transform .28s cubic-bezier(.32, .72, .35, 1), visibility .28s;", 1),
    ("transition: opacity .14s ease, visibility .14s ease;\n}\n#wxPayToast.show",
     "transition: opacity .2s ease, visibility .2s ease;\n}\n#wxPayToast.show", 1),
    ("    transform: scale(.86);\n    transition: transform .22s cubic-bezier(.18, 1.5, .4, 1);",
     "    transform: scale(.92);\n    transition: transform .2s ease;", 1),
    ("animation: wxPayDot .92s ease-in-out infinite;",
     "animation: wxPayDot 1.2s ease-in-out infinite;", 1),
    (".pay-toast-dots i:nth-child(2) { animation-delay: .15s; }",
     ".pay-toast-dots i:nth-child(2) { animation-delay: .2s; }", 1),
    (".pay-toast-dots i:nth-child(3) { animation-delay: .3s; }",
     ".pay-toast-dots i:nth-child(3) { animation-delay: .4s; }", 1),
    ("#wxPaySheet .pay-mid {\n    transition: opacity .14s ease, visibility .14s ease;\n}",
     "#wxPaySheet .pay-mid {\n    transition: opacity .2s ease, visibility .2s ease;\n}", 1),
    ("    opacity: 0;\n    transition: opacity .18s ease;\n}",
     "    opacity: 0;\n    transition: opacity .28s ease;\n}", 1),
    ("transition: transform .24s cubic-bezier(.22, 1, .36, 1);",
     "transition: transform .3s cubic-bezier(.32, .72, .35, 1);", 1),
    ("transition: background .09s ease;", "transition: background .12s ease;", 1),
    ("    /* 落位微动效：.35→1.22→1 的过冲弹出，替代原来的「瞬间出现」（观感像匀速铺满） */\n"
     "    animation: wxPwDotPop .16s cubic-bezier(.25, 1, .4, 1) both;\n", "", 1),
    ("transition: transform .24s cubic-bezier(.22, 1, .36, 1), visibility .24s;",
     "transition: transform .32s cubic-bezier(.32, .72, .35, 1), visibility .32s;", 1),
    ("transition: background .08s ease, transform .14s cubic-bezier(.25, 1, .4, 1);",
     "transition: background .1s ease;", 2),
], cut_marker="/* ============================================================\n   动画提速补丁（2026-09-11）")

# ---------------- transfer_ui.js ----------------
unpatch("transfer_ui.js", [
    ("}, 270);", "}, 340);", 1),
    ("kbTimer = setTimeout(() => { taKeyboardEl.classList.add('kb-up'); }, 300);",
     "kbTimer = setTimeout(() => { taKeyboardEl.classList.add('kb-up'); }, 430);", 1),
    ("}, 240);", "}, 320);", 1),
    ("        }, 1200);", "        }, 1800);", 1),
    ("        }, 200);", "        }, 350);", 1),
    ("            }, 680);", "            }, 950);", 1),
    ("        }, 280);", "        }, 330);", 1),
    ("        e.preventDefault();\n        const k = key.dataset.key;\n        pressFx(key);",
     "        e.preventDefault();\n        const k = key.dataset.key;", 1),
    # 整块删除 pressFx 函数（旧版没有「落指」反馈）
    ("    /* 按键「落指」反馈：加 .tkr-press → 动画跑完自动摘掉。\n"
     "       pointerdown 与 click 会成对触发（真人一次点击），150ms 内忽略第二次；\n"
     "       程序化 click 只有一次，照样有反馈。 */\n"
     "    function pressFx(el) {\n"
     "        if (!el) return;\n"
     "        const now = (window.performance && performance.now) ? performance.now() : Date.now();\n"
     "        if (el._fxAt && now - el._fxAt < 60) return;\n"
     "        el._fxAt = now;\n"
     "        el.classList.remove('tkr-press');\n"
     "        void el.offsetWidth;                 // 强制回流：同一个键连点也能重放动画\n"
     "        el.classList.add('tkr-press');\n"
     "        clearTimeout(el._fxTimer);\n"
     "        el._fxTimer = setTimeout(() => el.classList.remove('tkr-press'), 160);\n"
     "    }\n", "", 1),
])

# ---------------- transfer_detail.css ----------------
unpatch("transfer_detail.css", [
    ("transform .28s cubic-bezier(.22, 1, .36, 1)",
     "transform .4s cubic-bezier(.32, .72, .35, 1)", 3),
    ("    /* 硬出现 → 轻微弹出，避免「瞬间蹦出」的均质感 */\n"
     "    animation: wxtPop .2s cubic-bezier(.2, 1.45, .4, 1);\n", "", 1),
    ("animation: tfdSpin .7s linear infinite;", "animation: tfdSpin .9s linear infinite;", 1),
], cut_marker="/* 详情页「正在加载」toast 弹出（2026-09-11 提速补丁） */")

# ---------------- transfer_detail.js ----------------
unpatch("transfer_detail.js", [
    ("showToast(700);                 // 推入同时「正在加载」（提速 900→700ms）",
     "showToast(900);                 // 推入同时「正在加载」（对齐参考 f0048）", 1),
    ("        showToast(700);                 // 「正在加载」→ 单帧切换（提速 900→700ms）",
     "        showToast(900);                 // 「正在加载」→ 单帧切换（参考 f0160→f0180）", 1),
    ("        }, 700);", "        }, 900);", 1),
    ("setTimeout(() => document.body.classList.remove('wx-tfd-close'), 340);",
     "setTimeout(() => document.body.classList.remove('wx-tfd-close'), 450);", 1),
    ("setTimeout(() => root.classList.remove('done'), 340);",
     "setTimeout(() => root.classList.remove('done'), 450);", 1),
])

if FAIL:
    print("\n!!! 反向替换未全部命中 !!!")
    for x in FAIL:
        print("  -", x)
    sys.exit(1)
print("\nUNPATCH OK ->", DST)
