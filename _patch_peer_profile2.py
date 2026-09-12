# -*- coding: utf-8 -*-
"""第二轮微调补丁（依据 _cmp_profile_audit.py 第二次数值）。"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSS = r"G:\weixin-auto\enhance\peer_pages.css"


def patch(path, pairs):
    with io.open(path, "r", encoding="utf-8") as fh:
        s = fh.read()
    for old, new in pairs:
        assert old in s, "缺少旧串: %r" % old[:60]
        assert new not in s, "新串已存在: %r" % new[:60]
        s = s.replace(old, new, 1)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("patched:", path, "(%d 处)" % len(pairs))


pairs = [
    # 1) 返回箭头提亮（#d9d9d9 渲染后 top3% 只有195，ref 217）
    (
        "border-left: 2.6px solid #d9d9d9;\n    border-bottom: 2.6px solid #d9d9d9;",
        "border-left: 2.6px solid #ebebeb;\n    border-bottom: 2.6px solid #ebebeb;",
    ),
    # 2) 更多点左移 4px（ref 右缘 x570 vs 574）
    (
        ".wpp-more {\n    position: absolute;\n    right: 25px;\n    top: calc(50% + 2px);",
        ".wpp-more {\n    position: absolute;\n    right: 29px;\n    top: calc(50% + 2px);",
    ),
    # 3) 头部下留白 48→43（朋友资料标题 ref y374 vs 379）
    (
        "    padding: 37px 25px 48px;      /* 下留白 48px：量测参考帧「地区」底→「朋友资料」顶 */",
        "    padding: 37px 25px 43px;      /* 下留白 43px：对齐参考图「朋友资料」标题 y374 */",
    ),
    # 4) meta 行（昵称/微信号/地区）字号 21→23（ref 墨高21 vs 19）
    (
        ".wpp-nick {\n    font-size: 21px;",
        ".wpp-nick {\n    font-size: 23px;",
    ),
    (
        ".wpp-wxid,\n.wpp-area {\n    font-size: 21px;\n    line-height: 33px;\n    color: #969696;",
        ".wpp-wxid,\n.wpp-area {\n    font-size: 23px;\n    line-height: 33px;\n    color: #969696;",
    ),
    (
        ".wpp-nick + .wpp-wxid { margin-top: 2px; }",
        ".wpp-nick + .wpp-wxid { margin-top: 1px; }",
    ),
    # 5) desc 上距 9→11（ref desc 顶 y413）
    (
        "    color: #68686b;\n    margin-top: 9px;",
        "    color: #68686b;\n    margin-top: 11px;",
    ),
    # 6) 朋友圈行下移 7px（ref 标题 y526 / 缩略图 y522）
    (
        ".wpp-moments-cell { cursor: pointer; padding: 37px 25px 21px; align-items: flex-start; }",
        ".wpp-moments-cell { cursor: pointer; padding: 44px 25px 21px; align-items: flex-start; }",
    ),
    # 7) 资料页底色 #181818→#191919（ref 定点采样 #191919）
    (
        "    padding: 0 25px;\n    position: relative;\n    background: #181818;\n}",
        "    padding: 0 25px;\n    position: relative;\n    background: #191919;\n}",
    ),
    (
        "    -webkit-overflow-scrolling: touch;\n    background: #181818;\n}\n\n/* 头像 + 名字 + 微信号 + 地区 */",
        "    -webkit-overflow-scrolling: touch;\n    background: #191919;\n}\n\n/* 头像 + 名字 + 微信号 + 地区 */",
    ),
]
patch(CSS, pairs)
print("第二轮补丁完成")
