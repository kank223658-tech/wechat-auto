# -*- coding: utf-8 -*-
"""补丁 3：操作图标改为参考图裁切 + 昵称行加入录制模糊。"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSS = r"G:\weixin-auto\enhance\peer_pages.css"
s = io.open(CSS, encoding="utf-8").read()

# 1) 用裁切图标替换手绘的 msg/call 图标 CSS（从 .wpp-ic 到 .wpp-ic-call::before 块尾）
start = s.index(".wpp-ic { width: 26px")
end_marker = '%3C/svg%3E");\n}'
end = s.index(end_marker) + len(end_marker)
new_block = (
    "/* 图标直接裁自参考图《对方的个人主页.png》（像素级标定流程），\n"
    "   裁切自带 #191919 底色，与操作卡底色一致；尺寸=参考图 ink bbox+1px 外扩 */\n"
    ".wpp-ic { display: inline-block; position: relative; }\n"
    ".wpp-ic-msg {\n"
    "    width: 28px;\n"
    "    height: 25px;\n"
    "    background: url(\"/images/peer/icon_msg.png\") center / 100% 100% no-repeat;\n"
    "}\n"
    ".wpp-ic-call {\n"
    "    width: 28px;\n"
    "    height: 26px;\n"
    "    background: url(\"/images/peer/icon_call.png\") center / 100% 100% no-repeat;\n"
    "}"
)
s = s[:start] + new_block + s[end:]

# 2) 昵称行加入常驻模糊组（用户要求：录制时微信号和昵称都要打码）
old_blur = ("body:not(.wx-peer-no-blur) .wpp-wxid,\n"
            "body:not(.wx-peer-no-blur) .wpp-area {")
new_blur = ("body:not(.wx-peer-no-blur) .wpp-wxid,\n"
            "body:not(.wx-peer-no-blur) .wpp-nick,\n"
            "body:not(.wx-peer-no-blur) .wpp-area {")
assert old_blur in s and new_blur not in s
s = s.replace(old_blur, new_blur, 1)

old_cmt = "/* ---- 隐私保护：对方主页的微信号 / 地区 常驻高斯模糊 ----"
new_cmt = "/* ---- 隐私保护：对方主页的微信号 / 昵称 / 地区 常驻高斯模糊 ----"
assert old_cmt in s
s = s.replace(old_cmt, new_cmt, 1)

io.open(CSS, "w", encoding="utf-8").write(s)
print("patched css (icons + nick blur)")
