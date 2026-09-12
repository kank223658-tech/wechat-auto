# -*- coding: utf-8 -*-
"""把三份动作表接到 action_registry 上（一次性手术，幂等）。

  script_translator.ACTION_PARAMS  ← action_registry.param_defaults()
  script_translator.ACTION_SCHEMA  ← action_registry.schema()
  editor_server.ACTIONS            ← action_registry.editor_actions()
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def patch_translator():
    path = os.path.join(ROOT, "script_translator.py")
    src = open(path, encoding="utf-8").read()
    if "import action_registry as _ar" in src:
        print("script_translator: 已接过，跳过")
        return

    # 1) ACTION_PARAMS 字面量 -> 派生
    i = src.index("ACTION_PARAMS = {")
    j = src.index("\n}\n", i) + len("\n}\n")
    params_new = (
        "# ---- 动作表唯一来源：action_registry（见该文件头注释）----\n"
        "# 旧版这里手写 56 条，与 editor_server.ACTIONS(60) / ACTION_SCHEMA(47) 三份互有缺失，\n"
        "# 导致「发送emoji / 切换底部面板 / 转账」等 15 个动作在生成链路里被判非法。\n"
        "ACTION_PARAMS = _ar.param_defaults()\n"
    )
    src = src[:i] + params_new + src[j:]

    # 2) ACTION_SCHEMA 字面量 -> 派生
    i = src.index("ACTION_SCHEMA = [")
    j = src.index("\n]\n", i) + len("\n]\n")
    src = src[:i] + "ACTION_SCHEMA = _ar.schema()\n" + src[j:]

    # 3) 顶部加 import
    src = src.replace("import urllib.request\n",
                      "import urllib.request\n\nimport action_registry as _ar\n", 1)
    open(path, "w", encoding="utf-8").write(src)
    print("script_translator: 已接上 action_registry")


def patch_editor():
    path = os.path.join(ROOT, "editor_server.py")
    src = open(path, encoding="utf-8").read()
    if "from action_registry import editor_actions" in src:
        print("editor_server: 已接过，跳过")
        return
    start_mark = "# ============================================================\n# 动作清单（与 main.py 的 execute_step 一一对应）"
    i = src.index(start_mark)
    j = src.index("# action -> 动作定义 索引", i)
    new = (
        "# ============================================================\n"
        "# 动作清单（唯一来源 action_registry，与 main.py 的 execute_step 一一对应）\n"
        "# ------------------------------------------------------------\n"
        "# 旧版在这里手写 60 条，与 script_translator.ACTION_SCHEMA(47) / ACTION_PARAMS(56)\n"
        "# 三份口径不一致，新动作永远进不了生成链路。现在统一由 action_registry 派生。\n"
        "# ============================================================\n\n"
        "from action_registry import editor_actions as _editor_actions\n\n"
        "ACTIONS = _editor_actions()\n\n"
    )
    src = src[:i] + new + src[j:]
    open(path, "w", encoding="utf-8").write(src)
    print("editor_server: 已接上 action_registry")


if __name__ == "__main__":
    patch_translator()
    patch_editor()
