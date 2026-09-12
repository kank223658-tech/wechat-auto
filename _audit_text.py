# -*- coding: utf-8 -*-
"""文字色审计（终版）：每个元素取同一「贴合文字」的窗口比较参考帧与渲染帧。

指标 = 窗口内亮度前 3% 像素的 RGB 均值（两边同算法，ΔL 可直接判读）。
窗口必须贴合文字本身，否则会被背景稀释（早期的粗窗口曾误判成功页金额/详情页金额）。
"""
import numpy as np
from PIL import Image

BASE = r"G:\weixin-auto\_ref_tf2"
ROOT = r"G:\weixin-auto"


def load(path):
    im = Image.open(path).convert("RGB")
    if im.size != (600, 1300):
        im = im.resize((600, 1300), Image.LANCZOS)
    return np.asarray(im).astype(np.int32)


def stat(a, x0, y0, x1, y1, frac=.03):
    seg = a[y0:y1, x0:x1].reshape(-1, 3)
    L = seg[:, 0] * .299 + seg[:, 1] * .587 + seg[:, 2] * .114
    o = np.argsort(L)
    n = max(12, int(len(L) * frac))
    c = [int(round(v)) for v in seg[o[-n:]].mean(axis=0)]
    return c, (c[0] * .299 + c[1] * .587 + c[2] * .114), float(L.max()), float((L > L.max() - 70).mean() * 100)


def row(name, refimg, recimg, x0, y0, x1, y1):
    ra, na = load(BASE + "\\" + refimg), load(ROOT + "\\" + recimg)
    rc, rl, rmx, rink = stat(ra, x0, y0, x1, y1)
    nc, nl, nmx, nink = stat(na, x0, y0, x1, y1)
    d = nl - rl
    flag = "OK  " if abs(d) <= 10 else ("偏白" if d > 0 else "偏暗")
    print("  %s %-16s ref #%02x%02x%02x L=%3.0f | rec #%02x%02x%02x L=%3.0f | ΔL=%+3.0f" % (
        flag, name, rc[0], rc[1], rc[2], rl, nc[0], nc[1], nc[2], nl, d))


print("=== 金额页（ref b_012，金额已输入）===")
R, N = r"B\b_012.png", "_ph_filled.png"
row("标题", R, N, 50, 190, 380, 218)
row("微信号", R, N, 50, 228, 380, 250)
row("转账金额 label", R, N, 48, 327, 150, 349)
row("金额 ¥1", R, N, 48, 396, 200, 466)
row("添加转账说明", R, N, 48, 520, 200, 544)
row("键盘数字", R, N, 40, 926, 360, 960)
row("绿键「转账」", R, N, 478, 1096, 562, 1130)
print("=== 金额页 空态（占位符）===")
row("添加转账说明占位", R, "_ph_empty.png", 48, 520, 200, 544)
row("键盘数字", R, "_ph_empty.png", 40, 926, 360, 960)
print("=== 付款面板（ref b_021）===")
R, N = r"B\b_021.png", "_ph_sheet.png"
row("× 关闭", R, N, 30, 400, 70, 436)
row("使用面容", R, N, 470, 402, 576, 434)
row("向…转账", R, N, 130, 480, 470, 510)
row("¥1.00", R, N, 210, 528, 390, 586)
row("付款方式", R, N, 28, 653, 160, 680)
row("更改", R, N, 460, 653, 566, 680)
row("零钱", R, N, 100, 715, 290, 755)
row("密码格底", R, N, 30, 856, 570, 872)   # 避开参考帧已输入的 3 个密码点(y837-849)
row("键盘数字", R, N, 60, 930, 540, 972)
print("=== 成功页（ref b_027）===")
R, N = r"B\b_027.png", "_ph_success.png"
row("支付成功", R, N, 150, 105, 460, 145)
row("待X确认收款", R, N, 150, 290, 450, 322)
row("¥1.00", R, N, 150, 355, 450, 420)
row("完成按钮文字", R, N, 150, 1046, 450, 1086)
print("=== 转账详情页 待收款（ref a_006）===")
R, N = r"A\a_006.png", "_tfd_wait.png"
row("状态行 待你收款", R, N, 150, 362, 450, 394)
row("¥1.00", R, N, 170, 425, 430, 490)
row("时钟图标", R, N, 255, 226, 345, 306)
row("转账时间行", R, N, 40, 578, 560, 608)
row("收款按钮", R, N, 200, 1030, 400, 1070)
row("底部提示", R, N, 130, 1118, 470, 1150)
print("=== 转账详情页 已收款（ref a_016）===")
R, N = r"A\a_016.png", "_tfd_done.png"
row("状态行 你已收款", R, N, 150, 362, 450, 394)
row("¥1.00", R, N, 170, 425, 430, 490)
row("对勾图标", R, N, 255, 226, 345, 306)
row("零钱余额链接", R, N, 150, 524, 450, 550)
row("零钱通行", R, N, 150, 736, 450, 822)
row("底部链接", R, N, 150, 1170, 450, 1198)
print("DONE")
