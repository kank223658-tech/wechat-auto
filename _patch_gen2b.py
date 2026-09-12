# -*- coding: utf-8 -*-
"""第二步（修订版）：把生成/纠错提示词换成「JSON 输出 + 定向补丁」。

做法：先把老的 build_critique_prompt / _gen_user_message / _critique_user_message
整体删掉，再把含四个新函数的整块代码写到 build_generation_prompt 原来的位置。
（顺序不能反，否则文件里会有两份同名定义，按名定位会打到新的那一份上。）
"""
import ast
import io
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "script_generator.py")


def load_new_code():
    """从 _patch_gen2.py 里取出 NEW_BUILD_GENERATION_PROMPT 这段新代码。"""
    src = io.open(os.path.join(HERE, "_patch_gen2.py"), encoding="utf-8").read()
    i = src.index("NEW_BUILD_GENERATION_PROMPT = '''") + len("NEW_BUILD_GENERATION_PROMPT = '''")
    j = src.index("'''", i)
    return src[i:j]


def replace_func(text, name, new_src):
    tree = ast.parse(text)
    offs = [0]
    for ln in text.splitlines(keepends=True):
        offs.append(offs[-1] + len(ln))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return text[:offs[node.lineno - 1]] + (new_src.strip("\n") + "\n" if new_src.strip("\n") else "") + text[offs[node.end_lineno]]
    raise SystemExit("找不到函数 " + name)


def main():
    text = io.open(P, encoding="utf-8").read()
    if "script_format_mod.JSON_SPEC" in text:
        print("已经改过，跳过")
        return
    new_code = load_new_code()
    for name in ("_critique_user_message", "_gen_user_message", "build_critique_prompt"):
        text = replace_func(text, name, "")
    text = replace_func(text, "build_generation_prompt", new_code)
    if "import script_format as script_format_mod" not in text:
        text = text.replace("import action_registry as ar\n",
                            "import action_registry as ar\nimport script_format as script_format_mod\n", 1)
    ast.parse(text)                      # 写之前先确认语法
    io.open(P, "w", encoding="utf-8").write(text)
    print("已写入；新定义：",
          {n: text.count("def %s(" % n)
           for n in ("build_generation_prompt", "build_critique_prompt",
                     "_gen_user_message", "_critique_user_message")})


if __name__ == "__main__":
    main()
