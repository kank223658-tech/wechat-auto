# -*- coding: utf-8 -*-
"""第二步：把 build_generation_prompt / build_critique_prompt / 两条 user 消息
改成「JSON 输出 + 定向补丁」，并给 set_generation_score 加「高分自动入参考库」。"""
import ast
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_generator.py")
src = io.open(P, encoding="utf-8").read()
done = []


def replace_func(text, name, new_src):
    tree = ast.parse(text)
    offs = [0]
    for ln in text.splitlines(keepends=True):
        offs.append(offs[-1] + len(ln))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return text[:offs[node.lineno - 1]] + new_src.rstrip("\n") + "\n" + text[offs[node.end_lineno]]
    raise SystemExit("找不到函数 " + name)


NEW_BUILD_GENERATION_PROMPT = '''def build_generation_prompt(actions=None, people_block: str = "", preferences: str = "",
                            reference_text: str = "", category: str = "",
                            skills=None) -> str:
    """构造「创作」系统提示词。

    与旧版的四处区别（全部由体检数据推动）：
      1) 输出改成 JSON（script_format.JSON_SPEC）：旧版让模型直接写 [指令] 文本，
         实测 2/39 条出现 `[为我方打字]`、`[返回主页`（括号缺失）这类行被
         main.parse_script_text 静默丢弃 → 剧本凭空变短 → 触发「对白不够」→ 重写死循环。
         改成「模型填 JSON、本地渲染成 [指令]」后，格式类失败一次性消失。
      2) 动作表只列可进剧本的 32 个动作，每个带「何时用」，并附【能力卡】给新功能配片段示例
         （旧版只有一行动作名，模型永远想不起来用「切换底部面板 / 发送emoji」）。
      3) 参考剧本分两层：整篇当风格模板（≤2 条）+ 片段示例（演的是什么）。
      4) 所有数字都来自 rule_numbers()，与校验器完全同一套；篇幅按预算配套给
         （步数上限 + 对白下限 + 打字不发 + 插话比例），不再出现把模型夹死的组合。
    """
    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\\n- 本剧本的角色以「{category}」类别为主，从【人物库】挑该类别人物；"
                    f"若类别里有多人，优先挑本剧本还没用过的那几个，避免同一张脸反复出现。")
    nums = rule_numbers(skills)
    action_text = _format_action_table_compact(actions)
    people_block = people_block or "（人物库为空，请用常见中文名）"
    pref_block = preferences or "（暂无历史沉淀）"
    ref_block = reference_text or "（暂无参考剧本，但请依聊天教学套路创作）"
    spec_block = writing_spec_block(skills)
    asset_block = _asset_block()
    cap_block = capability_block()
    budget_note = ""
    if nums.get("budget_notes"):
        budget_note = "\\n【篇幅预算已自动收敛（你只要按下面的数字写即可）】" + "；".join(nums["budget_notes"]) + "\\n"

    head = f"""你是「微信聊天视频仿真剧本」创作助手，专注【男生追女生 / 聊天教学】类剧本。用户给你一个创作主题和若干参考剧本，你要产出一整套【可直接运行】的聊天教学剧本。

【动作表】（只能使用下列动作；参数名就是 JSON 里 params 的键）
{action_text}"""

    hard = f"""【硬性要求 —— 必须全部遵守】
1. 输出只能是【输出格式】里那种 JSON 对象（history + steps 两个键）；不要任何解释文字、不要 markdown 围栏、不要写 [指令] 文本。steps 里每个 action 必须来自【动作表】，params 的键必须是该动作自己的参数名。
2. 主题：围绕用户给的创作主题，编排一段「男生追女生」的完整聊天教学：先 history 铺底（历史会话）→ 打开聊天 → 我方打字 → 对方插话/后台消息 → 逐步引导（共情/调动情绪/探知三观/拉高格局）→ 情绪到位后铺垫邀约或收尾。
3. 【历史会话像微信列表预览，不是一问一答】绝大多数会话只留对方最后 1~2 条消息、不写 who=me；整块里只有 1 个（最多 {nums['max_history_two_sided']} 个）会话出现 who=me，且夹在对方消息中间。会话按最后一条消息时间从新到旧排列、会话内部时间递增；同一人最多连续 {nums['max_history_streak']} 条。**同一会话内部相邻消息的时间间隔要错落**（同一条分钟内、差 2~3 分钟、偶尔隔十几分钟混着来），不要每条都整齐地 +1 分钟；但也不要密集到「一分钟一个时间点」。
4. 【打字不发 + 插话必须用够】整份剧本至少 {nums['min_typing_hold']} 处 `[打字不发]`、至少 {nums['min_interjections']} 处带「插话」。「打字不发」要密集（一个展开的会话里连打四五次很正常），**但插话不是每个 [打字不发] 都配**：参考剧本 44~50 处打字不发只配 15~18 处插话，约每 3 处配 1 处，配太多会显得对方一直在抢话。三条硬性约束：① `[打字不发]` 的正文（params.内容）必须是**写给观众看的技巧说明**（「这一步在做什么、为什么这样聊有效」，如「以退为进」「故意否定 引起注意」），**不能是马上要发出去的聊天话术草稿，也不能是对方的心理活动**；其后的 `[我方打字]` 内容必须与它不同；② 插话（params.插话）只能回应我已经发出去的上一条消息或对方自己起的新话题，**不能回应 [打字不发] 里还没发出去的内容**（对方看不到输入框）；③ 插话说过的话，不要再用一条 `[对方发消息]` 重复一遍。
5. 【绝不偷工减料】禁止出现：……、[省略]、【省略】、省略、此处省略、以下省略、内容自拟、自行发挥、待补充、xxx、等等、同上、余下类似 等任何占位/缩略。每一步都要写出真实、完整、具体的中文内容。
6. 【`[我方打字]` / `[打字不发]` 分工】`[我方打字]` 一律是自然、口语化的真实聊天话术，禁止把方法论/步骤/心理活动写进去；给观众看的技巧说明一律写在 `[打字不发]` 的 params.内容 里，而且**每个 `[打字不发]` 都要写技巧说明**。
7. 【保留节奏】`[打字不发]` 的 params.停留 写 0.3~0.8 之间的数字；写出的时长要保留，不要一律用默认值。
8. 【人物】只从【人物库】里挑人名，同一剧本里同一个对象不要换名字；历史会话（history）可以有 9 个左右联系人把列表铺满，但真正 `[打开聊天]` 展开对白的最多 3 个人（历史列表里出现过的名字不算出场人物）。
9. 【画面丰富】适当穿插 [发送表情]、[发送emoji]、[对方后台发消息]、[我方发链接]、[手机状态栏]，让画面真实有层次；图片/表情一律只写【可用素材】清单里的短名（如 `好显身材的连衣裙`、`害羞猫咪`），禁止写文件路径、扩展名、时间戳或来源后缀，也不要自创图库里没有的描述。同一个表情整份最多用 {nums['max_same_emoji']} 次。
10. 【新功能至少用 1~2 个】从【能力卡】里挑 1~2 个新动作真的用进剧本（切换底部面板 / 发送emoji / 朋友圈 / 手机状态栏），不要通篇只有打字和发消息。
11. 【篇幅预算】整份剧本的实时指令（steps 的条数）控制在 {nums['max_script_steps']} 条以内、实时对白不少于 {nums['min_realtime_lines']} 条，两条一起满足；不要靠多开来回、堆 [对方正在输入]/[等待] 把剧本拉到 300 步。{budget_note}
12. 结尾可以再来一条 [返回主页] + 一条 [等待] 收束，保持整段像一个完整教学短视频。"""

    return "\\n\\n".join([
        head,
        people_block + cat_note,
        "【必须遵守的规则 / 创作偏好】（由你过去的评价沉淀而来；其中硬性规则会在生成后被逐条校验，违反会被打回重写）\\n" + pref_block,
        "【剧本书写规范 —— 这套软件只认这一种写法，必须严格遵守】\\n" + spec_block,
        asset_block,
        cap_block,
        "【参考剧本】（整篇只当风格与结构模板；片段示例告诉你某个动作怎么演。人物名一律换成【人物库】里的，不要照抄参考里的人名）\\n" + ref_block,
        script_format_mod.JSON_SPEC,
        hard,
    ])


def build_critique_prompt(issues: list, actions=None, people_block: str = "",
                          reference_text: str = "", preferences: str = "",
                          category: str = "", violations=None, skills=None) -> str:
    """构造「纠错」系统提示词：问题清单 + 完整上下文 + 定向补丁格式。

    为什么改成补丁而不是整篇重写：
      - 整篇重写每轮都要重新生成 200 行，token 贵，而且模型经常「改好一处、弄坏两处」；
      - 补丁只动问题清单点到的地方，其余原样保留，本地还能逐条校验是否真的改到
        （find 找不到 / 命中多处就丢弃那条补丁，不会把剧本改坏）。
    """
    if not issues:
        return "请重新生成一版更完整、更符合要求的剧本。"
    nums = rule_numbers(skills)
    issue_lines = "\\n".join(f"- {x}" for x in issues[:20])
    violation_block = ""
    if violations:
        v_lines = "\\n".join(f"- {x}" for x in list(violations)[:10])
        violation_block = (
            "\\n【你上一版违反的硬性规则 —— 必须逐条改掉，这是本次修改的重点】\\n" + v_lines + "\\n")

    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\\n- 本剧本的角色以「{category}」类别为主，从【人物库】挑该类别人物；"
                    f"若类别里有多人，优先挑本剧本还没用过的那几个。")
    action_text = _format_action_table_compact(actions)
    people_block = people_block or "（人物库为空，请用常见中文名）"
    pref_block = preferences or "（暂无历史沉淀）"
    ref_block = reference_text or "（暂无参考剧本，但请依聊天教学套路创作）"
    spec_block = writing_spec_block(skills)
    asset_block = _asset_block()

    repair = f"""【修复要求】
- **只改问题清单点到的地方，其余行一字不动**；不要整篇重写，也不要顺手「优化」没被点名的地方。
- 每条问题都要有对应的一条补丁（patches 里的一对 find/with）；找不到原文的补丁会被本地丢弃，等于白改 —— 所以 find 必须从《当前剧本》里一字不差地抄。
- 需要新增对白/动作就写进 append_steps（结构化写法，见【动作表】）。
- 【打字不发 + 插话】按书写规范 C 补足：整份至少 {nums['min_typing_hold']} 处 `[打字不发]`、至少 {nums['min_interjections']} 处带插话。**重点改 `[打字不发]` 的正文**：必须是给观众看的技巧说明（「为什么这样聊有效」），
  不是聊天话术草稿、不是对方心理活动 —— 凡是像「那我陪你聊到天亮」「她其实在等你先低头」这类，全部改写成打法说明。同时检查：`[打字不发]` 的内容有没有在随后的 `[我方打字]` 里原样又发一遍；插话有没有在回答没发出去的内容；插话有没有被下一条 `[对方发消息]` 重复。
- 【历史会话】要像微信列表预览：绝大多数会话只留对方最后 1~2 条、不写 who=me；整块里最多 {nums['max_history_two_sided']} 个会话带 who=me；同一会话内部时间间隔错落（同一条分钟内、差 2~3 分钟、偶尔十几分钟），不要每条都 +1 分钟。
- 【篇幅】steps 条数控制在 {nums['max_script_steps']} 以内、实时对白不少于 {nums['min_realtime_lines']} 条；超长时优先砍重复的来回、多余的 [对方正在输入]/[等待]、同一句话的多次删改，不要为了压长度把话术删成摘要或省略。
- 【素材引用】图片/表情只写【可用素材】清单里的短名，禁止文件路径/扩展名/时间戳/来源后缀；同一个表情最多 {nums['max_same_emoji']} 次。
- 【节奏】多余的 [等待] 删掉，只保留真正要停一下的地方；至少有一段「一方连发 2~3 条」，不要严格一问一答。
- 输出仍是 JSON：只需要 patches + append_steps，不要输出整篇剧本。"""

    return "\\n\\n".join([
        "你是同一套「微信聊天视频仿真剧本」的纠错助手。下面这一版剧本存在问题，请**只做定向修补**。",
        "【上一步的问题】\\n" + issue_lines + violation_block,
        "【动作表】\\n" + action_text,
        people_block + cat_note,
        "【必须遵守的规则 / 创作偏好】\\n" + pref_block,
        "【剧本书写规范】\\n" + spec_block,
        asset_block,
        "【参考剧本】\\n" + ref_block,
        script_format_mod.PATCH_SPEC,
        repair,
    ])


def _gen_user_message(brief: str, category: str, ref_titles: list) -> str:
    """构造首次生成时的 user 消息。"""
    desc = str(brief or "").strip()
    cat = f"（人物类别：{category}）" if category in CATEGORIES else ""
    refs = f"参考剧本：{ '、'.join(ref_titles) }" if ref_titles else "无参考剧本"
    return (f"创作主题：{desc}\\n{cat}\\n{refs}\\n\\n"
            "请按【输出格式】直接产出 JSON（history + steps），不要写 [指令] 文本、不要任何解释。")


def _critique_user_message(current_text: str) -> str:
    """构造纠错轮次的 user 消息：把上一版剧本**带行号**交给模型，便于它精确引用。"""
    body = (current_text or "").strip()
    if not body:
        return ("请针对上面的问题，按【输出格式】给出一组 patches（find/with）来修复，"
                "不要输出整篇剧本。")
    return ("《当前剧本》如下（左侧是行号，只用来帮你定位，不要写进 find/with）：\\n\\n"
            "===== 当前剧本 开始 =====\\n" + script_format_mod.number_lines(body) +
            "\\n===== 当前剧本 结束 =====\\n\\n"
            "请针对上面的问题，输出 patches（要改的那几行）与 append_steps（要补的内容）。"
            "不要重写整篇。")'''

src = replace_func(src, "build_generation_prompt", NEW_BUILD_GENERATION_PROMPT)
done.append("build_generation_prompt + build_critique_prompt + user 消息")
src = replace_func(src, "build_critique_prompt", "_PLACEHOLDER_CRITIQUE_")   # 占位，稍后删
# 上面两个函数是连在一起替换的，把第二次替换产生的占位删掉，并去掉重复定义
src = src.replace('_PLACEHOLDER_CRITIQUE_\n', '', 1)
src = replace_func(src, "_gen_user_message", "_PLACEHOLDER_GEN_MSG_")
src = src.replace('_PLACEHOLDER_GEN_MSG_\n', '', 1)
src = replace_func(src, "_critique_user_message", "_PLACEHOLDER_CRIT_MSG_")
src = src.replace('_PLACEHOLDER_CRIT_MSG_\n', '', 1)

# 引入 script_format
src = src.replace("import action_registry as ar\n",
                  "import action_registry as ar\nimport script_format as script_format_mod\n", 1)

io.open(P, "w", encoding="utf-8").write(src)
print("已改:", "、".join(done))
