# -*- coding: utf-8 -*-
"""真实场景复现：打字不发 + 打字过程中对方插话 + 删除我的文字。

对标脚本指令：
    [打字不发] 直接戳穿 | 0.3 | 我感觉她挺喜欢你的；回来之后一直在夸你帅啊什么的

即 内容="直接戳穿"，停留=0.3s，插话=[「我感觉她挺喜欢你的」,「回来之后一直在夸你帅啊什么的」]。
本脚本用与 main.py 完全一致的 parse_script_text + execute_step 路径执行这条指令，
随后执行 [删除文字] 全部，逐帧落盘，再看：
  1) 打字过程中对方左侧气泡是否正确注入；
  2) 键盘按键高亮在 typing 期间是否可见（当前默认 30x 下应不可见）。

用法：
    python _repro_typing.py --speed 30 --> 默认倍速，复现「动画消失」
    python _repro_typing.py --speed 1  --> 真人节奏基准
    python _repro_typing.py --speed 30 --hold-min 60 --> 试探拉长高亮是否恢复可见
"""
import argparse
import os
import time

import main as M
import script_translator  # noqa: F401  (与真实编辑器一致，保证 parse 路径可用)


def build_command(content="直接戳穿", hold="0.3",
                  ij="我感觉她挺喜欢你的；回来之后一直在夸你帅啊什么的"):
    """拼回脚本行并用 main.parse_script_text 解析，保证与真实运行同一套解析。"""
    line = f"[打字不发] {content} | {hold} | {ij}"
    steps = M.parse_script_text(line)
    assert len(steps) == 1, steps
    return steps[0]


def run(typing_speed, hold_min=None, content="直接戳穿", hold="0.3",
        ij="我感觉她挺喜欢你的；回来之后一直在夸你帅啊什么的", contact="陆香儿"):
    M.TYPE_SPEED = max(0.1, float(typing_speed))
    if hold_min is not None:
        M.KEY_HOLD_MIN_MS = int(hold_min)
        print(f"[override] KEY_HOLD_MIN_MS={M.KEY_HOLD_MIN_MS}")
    M.FRAME_CAPTURE_ENABLED = True
    M.ENABLE_AUDIO = False
    M.ENABLE_BGM = False

    step = build_command(content, hold, ij)
    print(f"[指令] {step}")
    ij_list = M._parse_interjections(step["params"].get("插话"))
    print(f"[解析] 内容={step['params']['内容']!r}  停留={step['params']['停留']!r}  插话={ij_list!r}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_repro_out")
    os.makedirs(out_dir, exist_ok=True)
    tag = f"sc" + (f"_hm{int(hold_min)}" if hold_min is not None else "") + f"_s{int(typing_speed)}"

    bot = M.WeChatAuto(headless=True)
    M._LIVE_BOT["bot"] = bot
    bot._live_enabled = False
    try:
        M.ensure_frontend_running()
        bot.start()
        bot.open_chat(contact)
        M._pump_wait(0.6)

        with M._FRAME_LOCK:
            n0 = len(M._FRAMES)

        # ---- 打字不发（含插话） ----
        bot.type_no_send(step["params"]["内容"], M._num(step["params"].get("停留"), M._typing_hold_default()),
                         interjections=ij_list)
        # 键盘保持弹出状态拍一拍（真机打完不发会停一下再删）
        M._pump_wait(0.5)

        # ---- 删除我的文字（全部） ----
        bot.delete_chars(-1)
        M._pump_wait(0.6)

        with M._FRAME_LOCK:
            n1 = len(M._FRAMES)
            win = list(M._FRAMES[n0:n1])
        print(f"[采集] 场景窗口共 {len(win)} 帧")

        saved = 0
        for i, (_ts, jpeg) in enumerate(win):
            with open(os.path.join(out_dir, f"{tag}_{i:03d}.jpg"), "wb") as fh:
                fh.write(jpeg)
            saved += 1
        print(f"[已落盘] {saved} 帧到 {out_dir}（{tag}_*.jpg）")
        return len(win)
    finally:
        try:
            bot.stop()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=30.0)
    ap.add_argument("--hold-min", type=int, default=None)
    args = ap.parse_args()
    run(args.speed, hold_min=args.hold_min)


if __name__ == "__main__":
    main()
