# -*- coding: utf-8 -*-
"""多轮操作演示脚本：聊天 + 切换聊天 + 朋友圈评论，输出一条 MP4 视频。

专门用来走一遍「多轮聊天 → 切换聊天 → 朋友圈点赞评论」的完整链路，
同时顺带演示几个容易被忽略的动作（打字不发、删除文字、对方发图片、语音），
方便你对照视频看哪些功能表现正常、哪些需要优化改进。

联系人必须用 enhance/config.js DEFAULT_HOME 里真实存在的名字
（首页聊天列表会被它覆盖成：微信支付 / 梓康群 / 陆香儿 / 服务号 / 公众号 /
微信团队 / 沉默光环 / D / 妍）。旧示例里的「孙权 / 孙尚香2」已不存在。

运行方式（后台运行，不弹窗口，但照样录屏）：
    py demo_multi.py

生成的视频在 ./videos/wx_<时间戳>.mp4，用 ffmpeg 转码。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M

# 每个环节之间的自然停顿（秒）
WAIT = 1.0
LONG = 1.8
PEER_TYPING = 1.5          # 「对方正在输入」展示时长
PIC = "/images/album/baiqian/baiqian01.jpeg"   # 演示用配图

# 真实存在的联系人（来自 enhance/config.js DEFAULT_HOME）
CONTACT_1 = "陆香儿"       # 第一个聊天对象
CONTACT_2 = "妍"           # 第二个聊天对象（切换聊天用）


def main():
    parser = argparse.ArgumentParser(description="多轮操作演示脚本")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="倍速：>1 更快（缩短视频时长），如 2 表示 2 倍速")
    args = parser.parse_args()
    M.SPEED = max(0.1, float(args.speed))

    # headless=True：无窗口后台运行，视频照常录制（和 make_demo 一致）
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()
        time.sleep(LONG)                 # 先停留在微信会话列表，让大家看清首页

        # ============ 第 1 段：与「陆香儿」多轮聊天 ============
        print("\n==>> 第 1 段：与【%s】多轮聊天" % CONTACT_1)
        bot.open_chat(CONTACT_1)
        time.sleep(WAIT)
        bot.human_type(".chat-txt", "在吗，晚上一起吃饭？")          # 我方真人键盘打字发送
        bot.show_typing(PEER_TYPING)
        bot.send_peer_message("好呀，万达那家怎么样")              # 对方整句回复
        time.sleep(WAIT)
        bot.human_type(".chat-txt", "可以，周五晚上7点不见不散")
        bot.show_typing(PEER_TYPING)
        bot.send_peer_message("收到，那我订位子")
        time.sleep(WAIT)
        bot.peer_image(PIC)               # 对方发一张图片（看图片消息渲染）
        bot.send_voice(2)                 # 我方发一条语音（看语音气泡）
        time.sleep(WAIT)

        # ============ 第 2 段：切到「妍」聊天（切换聊天） ============
        print("\n==>> 第 2 段：切换到【%s】聊天" % CONTACT_2)
        bot.go_back_home()                # 从对话页返回会话列表主页
        time.sleep(WAIT)
        bot.open_chat(CONTACT_2)
        time.sleep(WAIT)
        bot.human_type(".chat-txt", "周末的电影票我买好了")
        bot.show_typing(PEER_TYPING)
        bot.send_peer_message("太棒了！几点的场")
        time.sleep(WAIT)
        bot.type_no_send("我想看IMAX那场的")        # 打字不发：停在输入框（键盘弹出）
        bot.delete_chars(-1)              # 删除全部输入框文字（演示删除功能）
        time.sleep(WAIT)
        bot.human_type(".chat-txt", "下午三点，万达店")   # 重新真正发送
        time.sleep(WAIT)

        # ============ 第 3 段：朋友圈点赞 + 评论 ============
        print("\n==>> 第 3 段：进入朋友圈点赞并评论")
        bot.go_back_home()
        time.sleep(WAIT)
        bot.switch_tab("发现")             # 切到发现 Tab
        time.sleep(WAIT)
        bot.enter_moments()               # 进入朋友圈
        time.sleep(LONG)
        bot.scroll_down(300)              # 往下刷一屏
        time.sleep(WAIT)
        bot.like()                        # 给最后一条动态点赞
        time.sleep(WAIT)
        bot.comment("这张图拍得真不错！")   # 键盘动画打字发表评论
        time.sleep(LONG)

        print("\n==>> 全部动作执行完成，正在保存视频……")
    finally:
        mp4 = bot.stop()                  # 关闭浏览器并转码 MP4（旧 25fps + 新 60fps 双片）
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