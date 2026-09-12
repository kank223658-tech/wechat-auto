# -*- coding: utf-8 -*-
"""对方主页像素级标定补丁（参考图 2026-09-12：月亮/张小姐 主页截图）。

每条替换都 assert 旧串在、新串不在，写回后立即 grep 复核。
"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JS = r"G:\weixin-auto\enhance\peer_pages.js"
CSS = r"G:\weixin-auto\enhance\peer_pages.css"


def patch(path, pairs):
    with io.open(path, "r", encoding="utf-8") as fh:
        s = fh.read()
    for old, new in pairs:
        assert old in s, "缺少旧串: %r (%s)" % (old[:60], path)
        assert new not in s, "新串已存在: %r (%s)" % (new[:60], path)
        s = s.replace(old, new, 1)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("patched:", path, "(%d 处)" % len(pairs))


# ---------------- peer_pages.js ----------------
js_pairs = [
    # 1) 昵称行：插在名字行与微信号行之间
    (
        "'      <div class=\"wpp-wxid\"></div>' +",
        "'      <div class=\"wpp-nick\"></div>' +\n"
        "'      <div class=\"wpp-wxid\"></div>' +",
    ),
    # 2) 朋友资料 desc 文案：备忘 → 备注（参考图实测）
    (
        "添加朋友的备注名、电话、标签、备忘、照片等，并设置朋友权限。",
        "添加朋友的备注名、电话、标签、备注、照片等，并设置朋友权限。",
    ),
    # 3) 微信号冒号：全角 → 半角（参考图实测）
    (
        "root.querySelector('.wpp-wxid').textContent = '微信号：' + (p.wxid || '');",
        "root.querySelector('.wpp-wxid').textContent = '微信号:' + (p.wxid || '');",
    ),
    # 4) 地区行：冒号半角 + 空值隐藏（参考主页无地区行）
    (
        "root.querySelector('.wpp-area').textContent = '地区：' + (p.area || '');",
        "const areaEl = root.querySelector('.wpp-area');\n"
        "        areaEl.textContent = '地区:' + (p.area || '');\n"
        "        areaEl.style.display = p.area ? '' : 'none';",
    ),
    # 5) 昵称行渲染（有 nickname 才显示）
    (
        "root.querySelector('.wpp-wxid').textContent = '微信号:' + (p.wxid || '');",
        "const nickEl = root.querySelector('.wpp-nick');\n"
        "        if (p.nickname) { nickEl.textContent = '昵称:' + p.nickname; nickEl.style.display = ''; }\n"
        "        else { nickEl.textContent = ''; nickEl.style.display = 'none'; }\n"
        "        root.querySelector('.wpp-wxid').textContent = '微信号:' + (p.wxid || '');",
    ),
    # 6) 性别徽章：未设置性别时不渲染（参考主页名字后是 emoji，无徽章）
    (
        "g.classList.toggle('female', Number(p.gender) !== 1);",
        "g.classList.toggle('female', Number(p.gender) !== 1);\n"
        "        g.style.display = (Number(p.gender) === 1 || Number(p.gender) === 2) ? '' : 'none';",
    ),
]
patch(JS, js_pairs)

# ---------------- peer_pages.css ----------------
css_pairs = [
    # 1) 返回箭头：颜色 #d9d9d9（ref L217），整体下移 3px（ref 中心 y115 vs 111）
    (
        ".wpp-back {\n    width: 22px;\n    height: 22px;\n    display: inline-block;\n    cursor: pointer;\n}",
        ".wpp-back {\n    width: 22px;\n    height: 22px;\n    display: inline-block;\n    cursor: pointer;\n    position: relative;\n    top: 3px;\n}",
    ),
    (
        "    width: 15px;\n    height: 15px;\n    border-left: 2.4px solid #fff;\n    border-bottom: 2.4px solid #fff;\n    transform: rotate(45deg) translate(3px, -3px);\n    border-radius: 1px;\n}",
        "    width: 16px;\n    height: 16px;\n    border-left: 2.6px solid #d9d9d9;\n    border-bottom: 2.6px solid #d9d9d9;\n    transform: rotate(45deg) translate(3px, -3px);\n    border-radius: 1px;\n}",
    ),
    # 2) 更多点：#d5d5d5，5px，间距 6px，中心下移 2px
    (
        ".wpp-more {\n    position: absolute;\n    right: 25px;\n    top: 50%;",
        ".wpp-more {\n    position: absolute;\n    right: 25px;\n    top: calc(50% + 2px);",
    ),
    (
        "    display: flex;\n    gap: 7px;\n}",
        "    display: flex;\n    gap: 6px;\n}",
    ),
    (
        ".wpp-more i {\n    width: 6px;\n    height: 6px;\n    border-radius: 50%;\n    background: #fff;\n    display: block;\n}",
        ".wpp-more i {\n    width: 5px;\n    height: 5px;\n    border-radius: 50%;\n    background: #d5d5d5;\n    display: block;\n}",
    ),
    # 3) 名字：字号 29→32（ref 墨高30 vs 27），颜色 #e0e0e0（ref 纯文字区 L222）
    (
        ".wpp-name {\n    display: flex;\n    align-items: center;\n    font-size: 29px;\n    line-height: 36px;\n    font-weight: 400;\n    color: #fff;\n}",
        ".wpp-name {\n    display: flex;\n    align-items: center;\n    font-size: 32px;\n    line-height: 38px;\n    font-weight: 400;\n    color: #e0e0e0;\n}",
    ),
    # 4) 昵称行样式 + 有昵称时微信号行距收紧（ref 行距 34px）
    (
        ".wpp-wxid,\n.wpp-area {\n    font-size: 21px;\n    line-height: 33px;\n    color: #8e8e93;",
        ".wpp-nick {\n    font-size: 21px;\n    line-height: 33px;\n    color: #969696;\n    white-space: nowrap;\n    overflow: hidden;\n    text-overflow: ellipsis;\n    margin-top: 9px;\n}\n.wpp-nick + .wpp-wxid { margin-top: 2px; }\n.wpp-wxid,\n.wpp-area {\n    font-size: 21px;\n    line-height: 33px;\n    color: #969696;",
    ),
    # 5) cell 标题 #e8e8e8（ref L232）
    (
        ".wpp-cell-title {\n    font-size: 22px;\n    line-height: 30px;\n    color: #fff;\n}",
        ".wpp-cell-title {\n    font-size: 22px;\n    line-height: 30px;\n    color: #e8e8e8;\n}",
    ),
    # 6) desc：字号 20 / 行距 24 / 色 #68686b（ref L99）/ 上距 9
    (
        ".wpp-cell-desc {\n    font-size: 21px;\n    line-height: 31px;\n    color: #8e8e93;\n    margin-top: 6px;",
        ".wpp-cell-desc {\n    font-size: 20px;\n    line-height: 24px;\n    color: #68686b;\n    margin-top: 9px;",
    ),
    # 7) 朋友资料箭头与标题行对齐（ref 箭头中心 y≈384，与标题同行）
    (
        "/* 朋友资料：顶部 1px 内缩分隔线（x=40 起） */\n.wpp-friend-cell::before {",
        "/* 朋友资料：顶部 1px 内缩分隔线（x=40 起）；箭头与标题行对齐 */\n.wpp-friend-cell { align-items: flex-start; }\n.wpp-friend-cell .wpp-arrow { margin-top: 30px; }\n.wpp-friend-cell::before {",
    ),
    # 8) 操作区：bg #191919（ref 实测）、整块下移 4px、文字/图标 #8c9cb7（ref L154）
    (
        ".wpp-actions {\n    margin-top: 12px;\n    background: #1c1c1e;",
        ".wpp-actions {\n    margin-top: 16px;\n    background: #191919;",
    ),
    (
        "    gap: 12px;\n    background: #1c1c1e;\n    font-size: 25px;\n    color: #fff;",
        "    gap: 12px;\n    background: #191919;\n    font-size: 25px;\n    color: #8c9cb7;",
    ),
    (
        "    inset: 2px 0 5px 0;\n    border: 1.9px solid #fff;\n    border-radius: 50%;",
        "    inset: 2px 0 5px 0;\n    border: 1.9px solid #8c9cb7;\n    border-radius: 50%;",
    ),
    (
        "    background: #1c1c1e;\n    border-left: 1.9px solid #fff;\n    border-bottom: 1.9px solid #fff;",
        "    background: #191919;\n    border-left: 1.9px solid #8c9cb7;\n    border-bottom: 1.9px solid #8c9cb7;",
    ),
    (
        "stroke='%23ffffff' stroke-width='1.7'",
        "stroke='%238c9cb7' stroke-width='1.7'",
    ),
    # 9) 隐私模糊改为可关：body.wx-peer-no-blur 时清晰（默认仍模糊，保留录制防识别）
    (
        ".wpp-wxid,\n.wpp-area {\n    filter: blur(8px);",
        "body:not(.wx-peer-no-blur) .wpp-wxid,\nbody:not(.wx-peer-no-blur) .wpp-area {\n    filter: blur(8px);",
    ),
]
patch(CSS, css_pairs)
print("全部补丁完成")
