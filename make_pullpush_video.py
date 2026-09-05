# -*- coding: utf-8 -*-
"""男追女「拉扯」剧情 + 录屏生成视频（实况微信录屏版）
=========================================================
剧情主线《拉扯：男生靠聊天技巧，两回合拿下两个女生》：

  男主角「我」先后在和「陆香儿」「妍」两个女生的聊天里运用推拉技巧，
  每次都用「打字不发」展示一段内心戏（也就是观众能看到的魅力值），
  打完删掉，再换一句更有姿态的话发出去 —— 这就是拉扯的核心：
  想说的话打出来给观众看，但按下发送前删掉，发出去的永远是更高级的那句。

  陆香儿：高冷、慢热、爱考验。男生用「冷一冷 → 再热回来 → 顺势邀约」拿下。
  妍    ：主动、嘴硬、口是心非。男生用「反撩 → 退半步再进前一步」拿下。

复用 WeChatAuto（键盘模拟 + 单条录屏 + 转 MP4），保证一镜到底。

用法：
    py make_pullpush_video.py            # 前台可见运行、正常真人节奏录屏
    py make_pullpush_video.py --speed2   # 2 倍速录更快出片
"""

import os
import sys
import time
import warnings

# 屏蔽弃用警告，避免污染录屏日志输出
warnings.filterwarnings("ignore")

# 让脚本能直接 import 同目录下的 main.py（WeChatAuto）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M

# 两位女生的头像（与首页会话列表保持一致，进入聊天后 open_chat 会带过来）
AVATAR_LUX = "/images/ref/luxianger.png"
AVATAR_YAN = "/images/ref/yan.png"


def _send(bot, text, hold=0.6):
    """我方发送一句话：真人键盘打字 + 回车发送。"""
    bot.human_type(".chat-txt", text)
    M._pump_wait(hold)


def _charm(bot, line, hold=1.8):
    """拉扯核心：把「内心戏/魅力值」打出来给观众看，但【不发】，删掉。

    line    —— 想展示的那句（观众看得见，女生看不见）
    hold    —— 停在输入框让观众读的秒数
    """
    bot.type_no_send(line, hold_seconds=hold)   # 打字不发，停留在输入框
    M._pump_wait(0.3)
    bot.delete_chars(-1)                        # 全部删掉，不发送
    M._pump_wait(0.3)


def _peer(bot, text, avatar=None, typing=1.0):
    """对方回消息：先闪现「对方正在输入...」，再【一整段】上屏。

    整段一次出现（不再逐字打字），更贴近真机一次性收到一条消息，
    也避免「一个字一个字蹦出来」的割裂感。
    """
    bot.show_typing(typing)                     # 头部「对方正在输入...」
    bot.send_peer_message(text, avatar)         # 整段上屏（一次成型）
    M._pump_wait(0.5)


def main():
    speed2 = "--speed2" in sys.argv
    M.SPEED = 2.0 if speed2 else 1.0

    M.ensure_frontend_running()      # 确保前端 dev server 已在 8080 运行
    bot = M.WeChatAuto(headless=True)
    try:
        bot.start()                  # 打开微信首页（会话列表）
        M._pump_wait(2.2)              # 首页停留，先让观众看清「陆香儿」「妍」两条会话

        # ================= 第一回合：陆香儿（高冷慢热） =================
        bot.open_chat("陆香儿")
        M._pump_wait(0.9)

        # 她先来一句半冷不热的，摆高姿态
        _peer(bot, "忙完了？", AVATAR_LUX)
        M._pump_wait(0.6)

        # 她说「忙完了」，我内心其实很想说想你——但不能秒回过于热络
        _charm(bot, "刚忙完，其实满脑子都是你")       # 这条观众看到了，她看不到
        _send(bot, "刚忙完，累到不想说话")            # 发出去的却是这句冷却的

        # 她以为我冷淡，往回撤；我偏不挽留，反而稳住姿态
        _peer(bot, "哦，那我不吵你了", AVATAR_LUX)
        M._pump_wait(0.5)
        _charm(bot, "别走啊，我正想着你呢")
        _send(bot, "没事，你吵我，我反而清醒些")       # 把「吵我」变成一种宠爱说法

        # 她开始测我：是不是海王？这是她上钩的信号
        _peer(bot, "你嘴这么会说，平时没少撩女生吧", AVATAR_LUX)
        M._pump_wait(0.5)
        _charm(bot, "撩过，但对别人都是假动作，对你是真心的")
        _send(bot, "只对你话多，别人我说三句就词穷")     # 顺承她的试探，反打一个唯一性

        # 她口是心非地服软，我见好就收，把兴趣变成具体邀约
        _peer(bot, "……你好讨厌", AVATAR_LUX)
        M._pump_wait(0.5)
        _send(bot, "讨厌就讨厌吧，周末有空吗，带你去个地方")

        # 她问「哪」，我本来想老实交代，但吊胃口才是拉扯
        _peer(bot, "哪？", AVATAR_LUX)
        M._pump_wait(0.5)
        _charm(bot, "怕你嫌远，我其实紧张得要命")
        _send(bot, "保密，去了你就知道")               # 留悬念，保持推拉张力

        _peer(bot, "好吧，我信你一回", AVATAR_LUX)
        M._pump_wait(1.2)                          # 第一回合收尾，停留半拍

        # ================= 第二回合：妍（主动嘴硬） =================
        bot.go_back_home()
        M._pump_wait(0.7)
        bot.open_chat("妍")
        M._pump_wait(0.9)

        # 她主动邀约，热情明显更高
        _peer(bot, "晚上有空吗？有部超好看的电影", AVATAR_YAN)
        M._pump_wait(0.6)
        _charm(bot, "你请我就有空")
        _send(bot, "跟谁看？")                       # 反客为主，先探她的底

        # 她直球，我偏要撩回去，让她口是心非
        _peer(bot, "就你呗，想什么呢", AVATAR_YAN)
        M._pump_wait(0.5)
        _charm(bot, "行啊，那我就勉为其难陪你")
        _send(bot, "这么主动？不像你哦")                # 点破她的主动，制造小别扭

        # 她急忙否认（拉扯到顶），我顺势退一步、给足面子的同时显得是「我请」
        _peer(bot, "谁主动了！我只是觉得那电影好看", AVATAR_YAN)
        M._pump_wait(0.5)
        _send(bot, "那我请你看，就当谢你替我挑片")

        # 她嘴上服气，我最后一句点到为止，撩而不腻，稳稳收尾
        _peer(bot, "哼，这还差不多", AVATAR_YAN)
        M._pump_wait(0.5)
        _charm(bot, "到时候盯着你笑，一定很好看")
        _send(bot, "不过我喜欢靠里的位置，刚好能看清你")   # 主动中带点暧昧，落落大方

        _peer(bot, "就你最会……", AVATAR_YAN)
        M._pump_wait(1.6)                          # 第二回合收尾，让观众看清楚对话

        bot._kb_hide()                           # 收起键盘，露出完整对话
        M._pump_wait(1.4)

        # 片尾停留，再结束录屏
        M._pump_wait(1.0)

    finally:
        mp4 = bot.stop()
        if mp4:
            size_mb = os.path.getsize(mp4) / 1024 / 1024
            print(f"\n[拉扯剧情视频] 已生成：{mp4}（{size_mb:.1f} MB）")


if __name__ == "__main__":
    main()
