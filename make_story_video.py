# -*- coding: utf-8 -*-
"""完整故事情节模拟 + 录屏生成视频（实况微信录屏版）
=====================================================
剧情主线《周末看海之约》：我和「陆香儿」约好周六一起去看海。
按真人真实手速逐步操作，覆盖用户要求的全部桥段：

   0. 微信首页停留
   1. 打开和「陆香儿」的聊天
   2. 对方发了一句话 + 一张照片（海边照）
   3. 我方点开图片 → 放大 → 晃动（真人持机细看）
   4. 打错字退回（手滑打错，退格重来）
   5. 打了字展示出来不发（停在输入框，不发送）
   6. 切到朋友圈，评论她的动态
   7. 回到主页，给「陆香儿」发一条消息 + 发一张照片
   8. 对方回复（带「对方正在输入...」）
   9. 我方转账（报销车票）+ 撤回一条发错的消息

复用 WeChatAuto（键盘模拟 + 单条录屏 + 转 MP4），保证一镜到底。

用法：
    py make_story_video.py           # 前台可见运行、正常真人节奏录屏
    py make_story_video.py --speed2  # 2 倍速录更快出片
"""

import os
import sys
import time
import warnings

# 屏蔽 jieba 等三方库的弃用警告，避免污染录屏日志输出
warnings.filterwarnings("ignore")

# 让脚本能直接 import 同目录下的 main.py（WeChatAuto）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M

# 故事里用到的图片素材（务必使用 vue-WeChat/public/images 下已存在的路径）
PHOTO_BEACH = "/images/album/baiqian/baiqian01.jpeg"   # 陆香儿发来的海边照片
PHOTO_MINE = "/images/album/guanyu/guanyu01.jpeg"      # 我方发送的照片

# 朋友圈动态（进入朋友圈后注入，保证有一条「陆香儿」的动态可评论）
MOMENTS_POSTS = [{
    "author": "陆香儿", "avatar": "/images/ref/luxianger.png",
    "text": "周末约了人看海，现在已经开始期待了 🏖️",
    "images": [PHOTO_BEACH],
    "time": "10分钟前", "likes": ["阿荡", "妍"],
    "comments": [
        {"name": "妍", "text": "带我一个！"},
        {"name": "陆香儿", "text": "行程我定，放心"},
    ],
}]


def main():
    # 是否 2 倍速（缩短片长）
    speed2 = "--speed2" in sys.argv
    M.SPEED = 2.0 if speed2 else 1.0

    # headless=True：后台无头运行，稳定录屏不弹窗
    M.ensure_frontend_running()      # 确保前端 dev server 已在 8080 运行，避免连不上页面
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()                      # 打开微信首页（会话列表）
        M._pump_wait(2.0)                  # 首页停留，先让观众看清列表

        # 让聊天里「陆香儿」的头像与首页列表保持一致（解决头像不同/穿模）
        bot.page.evaluate("window.__wxConfig && window.__wxConfig.setPeerAvatar('/images/ref/luxianger.png')")
        M._pump_wait(0.5)

        # ========== 1) 打开和「陆香儿」的聊天 ==========
        bot.open_chat("陆香儿")
        M._pump_wait(0.9)

        # ========== 2) 对方发来一句话 + 一张海边照片 ==========
        bot.show_typing(1.0)                       # 对方正在输入...
        bot.send_peer_message("周末一起去看海吧，我拍了几张照片给你")  # 一整段上屏
        M._pump_wait(0.6)
        bot.peer_image(PHOTO_BEACH)                # 对方发送图片
        M._pump_wait(0.9)

        # ========== 3) 真人点开图片：放大 → 双指捏合缩放 → 关闭 ==========
        # view_image 内部是「点开放大动画 → 双指张合放大缩小(带指痕) → 关闭」
        bot.view_image(PHOTO_BEACH, hold_seconds=5.6)
        M._pump_wait(0.5)

        # ========== 4) 打错字退回：手滑打错，退格重来 ==========
        bot.type_no_send("啊哈哈", hold_seconds=0.8)    # 手忙脚乱打错
        bot.delete_chars(3)                        # 逐字退回（清空输入框）
        M._pump_wait(0.4)

        # ========== 5) 打字不发：重新打正确内容，展示但不发送 ==========
        bot.type_no_send("那太好了吧", hold_seconds=1.6)   # 停在输入框，不发送
        M._pump_wait(0.6)

        # ========== 6) 切到朋友圈，评论陆香儿的动态 ==========
        bot.go_back_home()                         # 收起键盘、回到主页
        M._pump_wait(0.6)
        bot.switch_tab("发现")
        M._pump_wait(0.6)
        bot.enter_moments()                        # 进入朋友圈
        M._pump_wait(1.0)
        bot.edit_moments(MOMENTS_POSTS)            # 注入一条陆香儿的动态
        M._pump_wait(0.8)
        bot.scroll_down(120)                       # 自然下滑浏览
        M._pump_wait(0.5)
        bot.like()                                 # 顺手点个赞
        M._pump_wait(0.6)
        bot.comment("周末海边见，等我拍照 😎")        # 评论（键盘动画打字）
        M._pump_wait(0.8)

        # ========== 7) 回到主页，给陆香儿发一条消息 + 一张照片 ==========
        bot.go_back_home()
        M._pump_wait(0.6)
        bot.open_chat("陆香儿")
        M._pump_wait(0.8)
        bot.human_type(".chat-txt", "我想说，这周六我刚好有空，我们一大早出发吧")
        M._pump_wait(0.6)
        bot.send_image(PHOTO_MINE)                 # 我方发送照片
        M._pump_wait(0.8)

        # ========== 8) 对方回复（整段上屏） ==========
        bot.show_typing(1.2)
        bot.send_peer_message("行啊，那我订九点的高铁，你记得带伞 ☔")  # 一整段上屏
        M._pump_wait(0.8)

        # ========== 9) 转账 + 撤回一次发错的消息 ==========
        bot.transfer("陆香儿", "66.00", "车票钱我先转你")   # 我方转账
        M._pump_wait(0.9)
        bot.human_type(".chat-txt", "我先把票钱转给你了")     # 先发送一句（稍后撤回）
        M._pump_wait(0.5)
        bot.withdraw()                                     # 发现发错了，撤回这条消息
        M._pump_wait(0.9)
        bot.human_type(".chat-txt", "刚给你转了66，下高铁记得收")  # 更正后重新发送
        M._pump_wait(0.5)
        bot._kb_hide()                                     # 收起键盘，露出完整对话
        M._pump_wait(1.2)

        # 片尾停留，再结束录屏
        M._pump_wait(1.0)

    finally:
        mp4 = bot.stop()
        if mp4:
            size_mb = os.path.getsize(mp4) / 1024 / 1024
            print(f"\n[完整剧情视频] 已生成：{mp4}（{size_mb:.1f} MB）")
        if bot.last_mp4_60:
            sb = os.path.getsize(bot.last_mp4_60) / 1024 / 1024
            print(f"[真 60fps 片] {bot.last_mp4_60}（{sb:.1f} MB）    输出帧率：{M.FRAME_CAPTURE_FPS}fps")


if __name__ == "__main__":
    main()