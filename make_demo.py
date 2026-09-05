# -*- coding: utf-8 -*-
"""生成演示视频：按顺序展示所有已换成现代深色皮肤的关键页面。

复用 WeChatAuto（自动注入皮肤 + 录屏 + 转 MP4），
依次演示：微信聊天列表 -> 对话页打字/回消息 -> 通讯录 -> 发现 ->
朋友圈(下滑+点赞) -> 我 -> 相册。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M

WAIT = 1.2
LONG = 2.2


def main():
    bot = M.WeChatAuto(headless=True)   # 后台运行（不弹窗），同时正常录屏
    try:
        bot.start()                      # 首页 = 微信聊天列表
        time.sleep(LONG)                 # 停留展示首页

        # 1) 打开一个会话并真人打字 + 对方回复
        # 联系人必须是 enhance/config.js DEFAULT_HOME 里真实存在的名字
        bot.open_chat("陆香儿")
        time.sleep(WAIT)
        bot.human_type(".chat-txt", "在吗，晚上一起吃饭？")
        bot.show_typing(1.2)
        bot.send_peer_message("好呀，万达那家怎么样")
        time.sleep(WAIT)

        # 2) 回到主页 -> 通讯录
        bot.go_back_home()
        time.sleep(WAIT)
        bot.switch_tab("通讯录")
        time.sleep(LONG)

        # 3) 发现页
        bot.switch_tab("发现")
        time.sleep(LONG)

        # 4) 朋友圈：下滑 + 点赞
        bot.enter_moments()
        time.sleep(LONG)
        bot.scroll_down(300)
        time.sleep(WAIT)
        bot.like()
        time.sleep(WAIT)

        # 5) 回主页 -> 我
        bot.go_back_home()
        time.sleep(WAIT)
        bot.switch_tab("我")
        time.sleep(LONG)

        # 6) 相册（我 -> 相册）
        bot.page.evaluate("location.hash = '#/self/album'")
        time.sleep(LONG)

        # 回「我」页收尾
        bot.page.evaluate("location.hash = '#/self'")
        time.sleep(WAIT)
    finally:
        mp4 = bot.stop()
        if mp4:
            size_mb = os.path.getsize(mp4) / 1024 / 1024
            print(f"\n[演示视频] 已生成：{mp4}（{size_mb:.1f} MB）")


if __name__ == "__main__":
    main()
