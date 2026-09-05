# -*- coding: utf-8 -*-
"""双人聊天 + 双方发送图片的演示脚本，输出一条 MP4 视频。

流程：
    1. 打开与「陆香儿」的单聊
    2. 我方真人键盘打字发送一句话
    3. 对方打字回一句（模拟「对方正在输入」）
    4. 我方发送一张图片（右侧绿色气泡，图片消息）
    5. 对方发送一张图片（左侧白色气泡，图片消息）
    6. 再次文字来回，展示混合消息流

演示用图片来自项目自带相册（/images/album/...）。
运行方式（后台无窗口，但照常录屏）：
    py demo_chat_image.py
生成的视频在 ./videos/wx_<时间戳>.mp4。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M

# 每个环节之间的自然停顿（秒）
WAIT = 1.0
LONG = 1.8
PEER_TYPING = 1.5          # 「对方正在输入」展示时长

# 演示用的两张图片（我方发一张，对方发一张）
PIC_ME = "/images/album/baiqian/baiqian01.jpeg"
PIC_PEER = "/images/album/guanyu/guanyu02.jpeg"

CONTACT = "陆香儿"


def main():
    # headless=True：无窗口后台运行，视频照常录制
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        time.sleep(LONG)                 # 先停留在微信会话列表，看清首页

        print(f"\n==> 进入与【{CONTACT}】的双人聊天")
        bot.open_chat(CONTACT)
        time.sleep(WAIT)

        # ---- 文字来回 ----
        bot.human_type(".chat-txt", "给你看个好东西")        # 我方真人键盘打字发送
        bot.show_typing(PEER_TYPING)
        bot.send_peer_message("咦，什么呀？")                   # 对方整句回复
        time.sleep(WAIT)

        # ---- 我方发一张图片 ----
        print("\n==> 我方发送一张图片")
        bot.send_image(PIC_ME)
        time.sleep(WAIT)
        bot.send_peer_message("哇，这张拍得真好看")             # 对方看到图后回复
        time.sleep(WAIT)

        # ---- 对方发一张图片 ----
        print("\n==> 对方发送一张图片")
        bot.show_typing(PEER_TYPING)
        bot.peer_image(PIC_PEER)
        time.sleep(WAIT)
        bot.human_type(".chat-txt", "这张也不错，收图了")     # 我方回文字
        time.sleep(WAIT)

        print("\n==> 全部动作执行完成，正在保存视频……")
    finally:
        mp4 = bot.stop()                  # 关闭浏览器并转码 MP4
        if mp4:
            size_mb = os.path.getsize(mp4) / 1024 / 1024
            print(f"\n[演示视频-25fps] 已生成：{mp4}（{size_mb:.1f} MB）")
        if getattr(bot, "last_mp4_60", None):
            size60_mb = os.path.getsize(bot.last_mp4_60) / 1024 / 1024
            print(f"[演示视频-60fps] 已生成：{bot.last_mp4_60}（{size60_mb:.1f} MB）")
        if getattr(bot, "wall_seconds", None):
            print(f"[运行耗时] 本次共耗时 {bot.wall_seconds:.1f} 秒"
                  f"（含 60fps 密集采集带来的额外开销）")


if __name__ == "__main__":
    main()