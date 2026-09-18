# -*- coding: utf-8 -*-
"""
剧本创作生成器（男生追女生 / 聊天教学）
=========================================
在已有「脚本模式」转译之上，新增一层"创作"能力：用户输入主题 + 参考剧本，
由大模型直接产出一整套符合 [指令] 标准、内容为"男生追女生技巧"的完整剧本；
随后经「完整性检查 → 结构化校验 → critique 重写」自我纠错，落地到可运行步骤。

与 script_translator 的关系：
  - 复用其 人物库(people.json) / 动作表(ACTION_SCHEMA/ACTION_PARAMS) / call_deepseek /
    设置读写(settings.json)，保证人物与动作口径一致。
  - 这里的生成走「大模型输出 [指令] 文本 + 离线归一」：生成结果本身就是标准 [指令]，
    用 main.parse_script_text 归一即可，避免二次调用大模型。

数据文件（项目根目录）：
  reference_scripts.json   用户的可参考剧本库
  feedback.json            每次生成的打分/留言 + 长期偏好块
  generate_history.json    每次「创作生成」的结果存档（供历史面板回看/复用）
"""

import json
import os
import re

import action_registry as ar
import script_format as script_format_mod
import create_store as store
import script_translator as st

# ============================================================
# 路径
# ============================================================

ROOT = os.path.dirname(os.path.abspath(__file__))
REFERENCE_PATH = os.path.join(ROOT, "reference_scripts.json")
FEEDBACK_PATH = os.path.join(ROOT, "feedback.json")
HISTORY_PATH = os.path.join(ROOT, "generate_history.json")

MAX_CRITIQUE_ROUNDS = 3  # 生成轮数：1 次初稿 + 最多 2 次 critique 重写
HISTORY_LIMIT = 60       # 生成历史最多保留多少条（最新在前，超出丢弃最旧）

# 判定人物类别（学员/美女），与 script_translator 一致
CATEGORIES = ("学员", "美女")


# ============================================================
# 参考剧本库读写
# ============================================================

def _load_raw(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save_raw(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_reference_scripts() -> list:
    """读取参考剧本库（SQLite）。"""
    return store.list_references()


def save_reference_scripts(scripts: list):
    """兼容旧接口：不再整文件覆盖，改为逐条 upsert（一般无需调用）。"""
    for s in scripts or []:
        if not isinstance(s, dict):
            continue
        if s.get("id") and store.get_reference(s.get("id")):
            store.update_reference(s["id"], {
                "title": s.get("title"), "category": s.get("category"),
                "text": s.get("text"), "summary": s.get("summary"),
                "topics": s.get("topics"), "tags": s.get("tags"),
            })
        else:
            store.add_reference(title=s.get("title") or "", text=s.get("text") or "",
                                category=s.get("category") or "")


def _new_id(prefix: str) -> str:
    import time
    return f"{prefix}-{int(time.time() * 1000)}"


def add_reference_script(title: str, text: str, category: str = "") -> dict:
    """新增一条参考剧本（标题为空或旧式「[历史会话]…」时自动重命名）。"""
    return store.add_reference(title=title or "", text=text or "", category=category or "")


def delete_reference_script(ref_id: str) -> bool:
    return store.delete_reference(ref_id)


def get_reference_scripts_by_ids(ids) -> list:
    """按 id 列表取参考剧本（保持挑选顺序），匹配不到则忽略。"""
    return store.get_references_by_ids(ids)


def format_references(references: list, category: str = "") -> str:
    """把选中的参考剧本拼成提示词里的 few-shot 文本块（分层）。

    体检结论：库里只有 3 条整篇参考，其中一条是「对方 0 条」的纯单边剧本，
    另一条我方 62 / 对方 6 —— 整篇堆多了只会教出「自言自语」；
    而新功能在整篇参考里一处都没演过，模型从参考这条路也学不到。

    所以分两层：
      - 【风格模板】整篇参考最多 2 条，学「每句话背后带什么策略、节奏怎么排」；
      - 【片段示例】短片段（kind=snippet，含系统内置的新功能片段），
        每条标注「演的是什么」，直接示范某个动作怎么用。
    """
    if not references:
        return "（本次未提供参考剧本，请依你掌握的聊天教学套路直接创作）"
    fulls = [r for r in references if (r.get("kind") or "full") == "full"][:2]
    snips = [r for r in references if (r.get("kind") or "full") == "snippet"][:6]

    parts = []
    if fulls:
        blocks = []
        for i, r in enumerate(fulls, start=1):
            tags = "、".join(r.get("tags") or []) or "无"
            summary = str(r.get("summary") or "")
            head = "参考剧本%d《%s》\n手法标签：%s\n结构摘要：%s" % (
                i, str(r.get("title", "未命名")), tags, summary)
            blocks.append(head + "\n" + str(r.get("text", "")))
        parts.append(
            "【风格模板】以下整篇参考用来学「每句话背后带什么策略、如何编排节奏」，"
            "重点模仿结构与打法，而不是照抄句子；人物名一律换成【人物库】里的。\n"
            "参考剧本里 `[打字不发]` 的正文都是「写给观众看的字幕」，你的成稿里**每一处** "
            "`[打字不发]` 都要写字幕而不是聊天话术。字幕两型并存：粉丝/学员会话写**打法型**"
            "（「这一步在做什么、为什么这样聊有效」）；主线女主会话两种混用——打法型之外，"
            "至少 1 处写**我方心里失守型**（「？？？」「完了 别多想」「这谁敢答应」），"
            "让观众看到主角也被撩到。绝不能写成马上要发出去的聊天话术，也不能写成对方的心理活动。\n"
            "[打字不发] 的正文是短语标签，不是解释句：主线字幕主体 2~10 字（硬上限 14），"
            "结构是「动作短语 + 空格 + 三五字补充」，如「礼貌开场」「勾起好奇心」「顺着结论走」"
            "「她等你追 你偏不追」「暗示见面」；禁止写成 15 字以上的完整因果句"
            "（如「她回头了 慢半拍才显你不在围着她转」这种=过长，砍成「回头也慢半拍」）。"
            "引流 CTA 和下课字幕可放宽到 16~20 字。写完逐条数字数，超 10 字先尝试砍成两三个词。\n"
            "参考剧本的 [历史会话] 是最好的学习对象：像微信列表预览，绝大多数会话只留对方最后 1~2 条、"
            "每条都带钩子、时间标注错落，整块里只让 1 个会话带「我：」的回复。\n\n"
            "【历史会话=列表页小剧场 —— 但列表页每行只显示该会话【最后一条】消息！】\n"
            "★渲染事实（vue-WeChat msg-item.vue 只渲染 msg[最后一条].text）：未被打开的会话，列表页只看得到【最后一条】——\n"
            "  图片消息显示成「[图片]」、链接显示成「[链接]」，前面几条在列表页【完全看不到】。所以：\n"
            "  · 每个会话【只写 1 条】（就是列表页唯一可见的那条）；粉丝会话可保留「链接 + 我：+ 最后一条」的固定结构；\n"
            "  · 钩子/擦边/信息必须【单句自带】，不能「上一句铺垫、下一句反转」——前一句白写（唯一作用是未读角标数字）；\n"
            "  · 想让列表页出现「[图片]」「[链接]」字样，就把那个图/链接放在该会话的【最后一条】；\n"
            "  · 历史块的图在列表页看不到，不用为它准备素材（描述随手写个意思即可）。\n"
            "  金样：`蓝莓酸奶：我那里不舒服 你什么时候来陪我 | 18:19`、`桃桃乌龙：你什么时候来陪我 | 18:27`、`叶喵喵：散场了 你来接我吧 | 20:41`\n"
            "  `一颗甜莓：我把他删了 他又加回来了 | 17:50`、`软软的雪：[对方发图片] 图片=工位上堆成山的外卖盒 | 17:40`（列表页显示「[图片]」）。\n"
            "  禁止：把一个会话写成两句（第一句看不到）、或整块都是同构的「吐槽+抱怨」单句。\n"
            "\n"
            "★【三层分工：引流 / 趣味 / 历史块，各司其职，不要混】\n"
            "- ①引流层（开局 0~5 秒，目标=让人停下来）：钩子优先「性感氛围图」或「擦边暗示话题」——她开场发一张刚洗完澡的对镜自拍 / 吊带裙 / 健身马甲线 / 微湿头发（性感靠氛围穿搭，不露点），或第一句就是擦边暗示（「刚洗完澡」「你觉得我这种身材好追吗」「一个人在家有点怕」「你猜我现在穿什么」）。\n"
            "- ②趣味层（正文，目标=让人看完 + 学到东西）：靠智斗——你来我往的博弈、图梗错位暴击、挑逗对攻、金句反差；★引流是钩眼球、智斗才是留存，分工清楚：正文里不要再堆性感（会显得低俗又没料），要让人服气。\n"
            "③历史块层（列表页预览，目标=让观众觉得「这列表里好多故事」）：**未打开的会话，列表页只看得到最后一条**——"
            "擦边就写【一句半截话，留想象空间】：点到为止、不给结果、不带「你来…」式邀约，让人看一眼就自己脑补 ——"
            "「半夜睡不着」「一个人在家 有点冷」「刚洗完澡 头发还湿着」「我那里不舒服」「加班到腿软」；"
            "★不要「上一句铺垫 + 下一句收」，不要「别想歪 是XX」式自我解释，更**不要把话说完**："
            "「半夜睡不着 你来陪我聊会儿」只取前半句「半夜睡不着」就刚好——后半句一出，想象空间就没了。"
            "**被打开（打开=是）的会话没有这个限制：擦边可以写多条、展开成一来一回**（全屏看得见，多条才有过程感）。\n"
            "- 铁律：擦边只做「钩子」不做「内容」——露骨描写、性行为细节一律禁止；擦边只出现在历史块未打开的会话（1 条、半截话、留白），正文以智斗为主；若要擦边展开，放进「打开聊天」的会话（可多条）。擦边是引流手段，不是内容本身。"
            
            
            "【正文要有互相挑逗的拉扯，不是单方面输出】每篇至少 3 处挑逗类互动：\n"
            "- 图片梗（首选）：她说喜欢高高瘦瘦的 → 我方「认识个兄弟就符合」→ [发送图片] 图片=几根电线杆（注意：我方发图不写 打开=是），先给预期再自嘲反转，配她笑骂回复；\n"
            "- 【我方发图不打开】[发送图片] 一律不写 打开=是——发出去时我方已有预期，再全屏打开很奇怪；要全屏暴击就让 [对方发图片] 来做。\n"
            "- 【纯情绪反应用贴纸不用图片】我方发「反应类」内容（被摸头/害羞/无语这类纯情绪，没有剧情画面）优先 [发送表情] 贴纸或内嵌 3D emoji；[发送图片] 只用于剧情必需的具体画面（有人物/物品/场景的照片，能推动剧情或制造反转，如电线杆/奶茶/外卖堆成山）。\n"
            
            "【梗密度=有趣的硬指标，每篇 ≥4 处梗、至少覆盖 3 种梗型】\n"
            
            "- ★★图梗·错位暴击（最强梗型，每篇 ≥1 处，比一切嘴上机灵都好笑）—— 先立预期，再砸一张完全对不上的沙雕图：\n"
            "- 金样A（择偶标准型）：她说喜欢高高瘦瘦的 → 我方「正好认识一个特别符合的」→ [发送图片] 图片=路边三根又细又高的电线杆并排 竖屏实拍 → 她笑骂「你拿电线杆糊弄我」；\n"
            "- 金样B（性感预期型）：她问「jk大奈看吗」→ 发过来的却是一张奶龙穿JK校服裙的照片 → 双方笑作一团；\n"
            "- 结构四步：① 台词先立预期（不能凭空发图）② 我方顺杆接（「有啊」「这就给你看」）③ 图错位（要美→电线杆，要性感→奶龙）④ 她笑骂/拆台收尾；\n"
            "- 最好双向：对方也发梗图（自嘲式/沙雕图），我方接梗再反打一次；\n"
            "- 梗图角色池（网搜「角色+动作」就有）：奶龙、卡皮巴拉、柴犬、悲伤蛙、汤姆猫、doge、奥特曼、黑人问号、旺仔、猫猫虫、葫芦娃；\n"
            "- 忌：发一张正经好看的图（那不是梗，是秀图）；梗图也不能连发超过 2 张、全篇梗图 ≤3 张（多了变图库）。\n"
            "- 土味金句梗（≥1 处，参考案例的灵魂，全库此前为零）：押韵对仗式情话/比喻，\n"
            "  金样：「撒网是姐姐的本事 入网是我的荣幸」「女人就像红酒 在不同的年份打开 都会有不一样的芬芳」「没抓住姐姐的心 就别说姐姐花心」；\n"
            "- 反差自嘲梗（全篇 ≥1 处、但只许用一次）：前面撩得飞起突然装腼腆——「我平时不这样的 平常很腼腆」，等她拆台「腼腆的人会这么说话？」；\n"
            "  ★换个块必须换一句（可换「换个人我早不接这话了」）——实测两个块都写同一句，观众一眼看出是模板；\n"
            "- 网络热梗点缀（2~4 处，贴语境不硬塞）：栓Q/纯爱战士/舔狗/画大饼/破防/拿捏/上头/发疯文学/卑微文学/已老实/那咋了/显眼包/搭子；\n"
            "- 装傻曲解梗、正话反说、表情包斗嘴也算梗型（沿用前文规则）；\n"
            "- 禁忌：梗不能盖过教学主线，字幕仍是短语标签；同一梗词全篇 ≤2 次。\n"
            "- 正话反说：她发自拍问好看吗 → 「我觉得不好看 / 毕竟衣服哪有人好看」；★落点必须锚在她发的东西上（照片→她本人/照片本身），严禁把结论落到自己身上——「显得我不够帅」「把我拍得」=照片里根本没有我，逻辑断裂、观众一眼看出瞎写，校验器 3.11 直接判问题；\n"
            "- 抬杠式撩 + 曲解装傻：「不喜欢干嘛老找你聊天 是游戏不香还是电影不好看」→「是没有我陪的电影 才不好看」；\n"
            "- 对方也要反撩至少 2 次（「怕了吗」「光吃饭看电影吗[脸红]」），不能只有我方输出、她只接招。\n"
            
                        "【图片描述=用户的找素材清单，必须清晰到照着就能搜图/拍图】\n"
            "- 公式：主体+细节+画面形式（实拍/竖屏/特写/氛围…），去空格后 ≥10 字；\n"
            "- 反例：「夜跑路上」「情侣杯的两只杯子」（校验器 3.5b 直接硬卡）；\n"
            "- 正例：「夜晚城市江边跑步道 路灯下一双运动鞋特写 竖屏实拍」「一对粉色情侣马克杯并排摆在木桌上 杯身印着牵手小人 实拍特写」。"
            
            "【截图/长图类描述必须写清内容】（校验器 3.5b 对该类要求 ≥16 字）公式「谁的截图 + 截图上什么内容 + 形式」\n"
            "- 反例：「聊天记录截图拼成的一张长图」（用户不知道用什么图，做不出来）；\n"
            "- 正例：「微信聊天界面截图 我方连发几条话术 对方只回一个表情 手机截屏」（单屏自截，别拼接别加框）。\n"
            "【台词说人话，禁行话黑话】主线/支线/带线/闪着/复盘/闭环这类圈内词（游戏、直播、教学行话）一律不许进台词——\n"
            "普通观众和用户要一眼看懂；写完逐句过一遍「不看教学背景能懂吗」。\n"
            "- 反例：「回去练 主线那边还闪着」→ 正例：「你先练着 那边的姑娘还等我回话」。\n"
            "- 例外：教学段向粉丝讲方法可以说「套路/话术/翻盘/挑刺」这类已成大众词的术语。"
            
            "【图片要少而精——图一多用户配不过来】（2026-09-16 用户定调）\n"
            "- 开场钩子图必须保留（硬性要求 17）；除此之外，需要用户上传的图全篇不超过 5 张（校验器硬卡）；\n"
            "- 只有剧情必需才发图：图梗错位、证物道具、邀约画面；纯情绪反应一律贴纸 / 内嵌 emoji；\n"
            "- 能用【可用素材】清单里图库已有的短名就用（零上传，不计入上限）；可发可不发的图一律不发。\n"

            "【图片素材必须「好弄」——用户要一分钟内拿到】（2026-09-14 用户定标：图片不要那么难找，校验器 3.5c 硬卡）\n"
            "- 首选 A 档（随手拍/相册翻/网上一搜就有）：一杯奶茶、外卖盒堆成山、猫在腿上、窗外晚霞、衣架上的裙子、\n"
            "  工位绿萝、对镜自拍、美甲、快递箱、电影票根——这些用户随手就能弄到；\n"
            "- 可接受 B 档（单张手机截图，两秒能截）：自己的聊天界面——单屏、不加工；\n"
            "- 禁止 C 档：① 要加工制作的（拼成长图、加红框标注、多图合成、「裁出单人照」）；\n"
            "  ② 要造场景的（朋友圈截图、弹窗截图、转账截图、群聊截图、推销话术截图——用户手上根本没有）；\n"
            "- 例外：粉丝会话（引流图/脱单教程/案例解析）不受此限；\n"
            "- 描述末尾带上获取线索（「竖屏实拍」「手机随手拍」「网图」），让用户一眼知道去哪弄。"
            
            "【★配图注释：每个图片槽都要自带「找图说明书」】（2026-09-15 用户硬要求）\n"
            "- 在每一个图片/照片/表情槽位的【正上方紧挨着】写一行以 # 开头的注释，四段式：\n"
            "  # 【照片N·我发/她发｜用途】效果＝画面主体+细节+画面形式 ｜ 找图＝随手拍或网搜关键词 ｜ 呼应＝前后哪两句台词\n"
            "- 「效果」要写拍出来长什么样（对镜自拍 / 台灯暖光 / 竖屏特写 / 白天窗边），"
            "不要写「体现 xxx 情绪」这种没法照着拍的词；「找图」要给出用户一分钟能拿到的方式；\n"
            "- 这类槽位同样要注释（写清「不用找」并说明原因）：\n"
            "  · [点开图片] 朋友圈点图 —— 写明是哪个人的第几条动态、配文是什么、为什么不用找；\n"
            "  · ★连着写两条 [点开图片]（引用一条、再点一条）时，【每条上方各写一行注释】，"
            "别只给第一条写——否则第二条在配图清单里是空白，用户看不出点开的是谁的哪张；\n"
            "  · 历史块里的 [图片] 占位 —— 写明该会话全程不打开、列表页只会显示「[图片]」、不用准备素材；\n"
            "  · 粉丝引流固定图（脱单教程/案例解析等）—— 写明直接用图库里哪一张，"
            "且「效果＝」也要写封面的实际画面（如红底大字报「男生脱单其实超简单」）；\n"
            "- ⚠️ 注释行内【禁止出现中文冒号「：」和英文冒号「:」】——历史块解析把「xx：yy」当成一条对白，"
            "注释里带冒号会凭空多出一条消息直接上屏；分隔一律用「＝」「｜」；\n"
            "- 注释以 # 开头，运行时会被整行跳过，不影响成片与步数统计。"
            + "\n\n".join(blocks))
    if snips:
        lines = []
        for r in snips:
            note = str(r.get("note") or r.get("summary") or "").strip()
            lines.append("· %s%s\n%s" % (
                str(r.get("title", "片段")),
                ("（%s）" % note) if note else "",
                str(r.get("text", ""))))
        parts.append("【片段示例】这些是「某个动作该怎么演」的短示范，"
                     "成稿里用到对应动作时照着写。\n" + "\n".join(lines))
    if not parts:
        return "（本次未提供参考剧本，请依你掌握的聊天教学套路直接创作）"
    return "\n\n".join(parts)


# ============================================================
# 生成历史读写（供「历史生成」面板回看 / 复用）
# ============================================================

def load_generation_history() -> list:
    """读取生成历史，最新在前，返回 list[dict]。"""
    data = _load_raw(HISTORY_PATH, {}) or {}
    items = data.get("history", [])
    return items if isinstance(items, list) else []


def save_generation_history(items: list):
    _save_raw(HISTORY_PATH, {"history": items or []})


def add_generation_history(entry: dict) -> dict:
    """把一次生成结果存进历史（最新在前，超出上限截断），返回入库后的条目。"""
    import time as _t
    items = load_generation_history()
    item = dict(entry or {})
    item.setdefault("id", _new_id("gen"))
    item.setdefault("created_at", _t.time())
    items.insert(0, item)
    if len(items) > HISTORY_LIMIT:
        items = items[:HISTORY_LIMIT]
    save_generation_history(items)
    return item


def history_summary(item: dict) -> dict:
    """历史列表用的摘要：不含剧本全文，避免列表接口体积过大。"""
    item = item if isinstance(item, dict) else {}
    report = item.get("report") if isinstance(item.get("report"), dict) else {}
    issues = report.get("issues") or []
    steps = item.get("steps") if isinstance(item.get("steps"), list) else []
    text = str(item.get("text") or "")
    return {
        "id": str(item.get("id") or ""),
        "brief": str(item.get("brief") or ""),
        "category": str(item.get("category") or ""),
        "ref_titles": [str(x) for x in (item.get("ref_titles") or []) if x],
        "created_at": item.get("created_at") or 0,
        "steps": len(steps),
        "chars": len(text),
        "attempts": int(report.get("attempts") or 1),
        "passed": bool(report.get("passed")),
        "issues": len(issues),
        "score": int(item.get("score") or 0),
        "model": str(item.get("model") or ""),
    }


def list_generation_history() -> list:
    """历史摘要列表（最新在前）。"""
    return [history_summary(x) for x in load_generation_history() if isinstance(x, dict)]


def get_generation_history(gen_id: str):
    for x in load_generation_history():
        if isinstance(x, dict) and str(x.get("id")) == str(gen_id):
            return x
    return None


def delete_generation_history(gen_id: str) -> bool:
    items = load_generation_history()
    before = len(items)
    items = [x for x in items if str((x or {}).get("id")) != str(gen_id)]
    if len(items) != before:
        save_generation_history(items)
        return True
    return False


def clear_generation_history() -> int:
    n = len(load_generation_history())
    save_generation_history([])
    return n


def set_generation_score(gen_id: str, score: int) -> bool:
    """把评价星级回写到对应历史条目，让历史列表也能显示打分。"""
    items = load_generation_history()
    ok = False
    for x in items:
        if isinstance(x, dict) and str(x.get("id")) == str(gen_id):
            x["score"] = int(score)
            ok = True
            break
    if ok:
        save_generation_history(items)
    return ok


# ============================================================
# 反馈库读写 / 偏好蒸馏
# ============================================================

def load_feedback() -> dict:
    return _load_raw(FEEDBACK_PATH, {"feedback": [], "preferences": ""})


def save_feedback(data: dict):
    _save_raw(FEEDBACK_PATH, data or {})


def add_feedback(score: int, comment: str, brief: str = "", title: str = "") -> dict:
    """追加一次评价，返回新条目。"""
    data = load_feedback()
    feedback = data.get("feedback", [])
    import time as _t
    item = {
        "id": _new_id("fb"),
        "brief": (brief or "").strip(),
        "title": (title or "").strip(),
        "score": int(score),
        "comment": (comment or "").strip(),
        "created_at": _t.time(),
    }
    feedback.append(item)
    data["feedback"] = feedback
    save_feedback(data)
    return item


def load_enabled_skills() -> list:
    """读取启用的规则/风格条目（生成与校验共用）。"""
    _repair_invalid_action_rules_once()
    return store.list_skills(enabled_only=True)


# 校验器只认「动作表里的动作名」；LLM 常把抽象要求（插话/话题推进/精彩）
# 误拆成 required_action，导致规则永远判不过、每次生成都被打回。
_rules_repaired = False


def _valid_action_names() -> set:
    """合法动作名 = action_registry 的 64 个动作（唯一来源）+ 别名。

    旧版只读 script_translator.ACTION_SCHEMA（47 条），而它比前端动作表少 15 条，
    于是「发送emoji / 切换底部面板 / 转账 / 手机状态栏」等新动作被判非法动作名，
    用户在评价里写「以后多用表情」沉淀出的 required_action=发送表情 会被静默降级成
    style，永远不生效。现在三份表已经合并，这里也就不再丢新动作。
    """
    names = set(ar.names())
    names.update(str(k) for k in (getattr(st, "ACTION_ALIASES", {}) or {}))
    return names


def _is_valid_action(value) -> bool:
    v = str(value or "").strip()
    if not v:
        return False
    names = _valid_action_names()
    return v in names or v in (getattr(st, "ACTION_ALIASES", {}) or {})


def _normalize_candidate(c: dict) -> dict:
    """把抽出来的候选规则修正成校验器真正能用的形式。

    无法机械校验的要求（如「插话用起来」「对话要精彩」）降级成 style，
    只注入提示词、不参与校验，避免制造永远无法满足的硬规则。
    """
    if not isinstance(c, dict):
        return c
    kind = str(c.get("kind") or "").strip()
    value = c.get("value")

    def _as_style():
        return {
            "type": "style",
            "title": str(c.get("title") or c.get("prompt_hint") or "").strip()[:40],
            "kind": None,
            "value": None,
            "prompt_hint": str(c.get("prompt_hint") or c.get("title") or "").strip()[:200],
        }

    if kind in ("required_action", "banned_action"):
        vals = value if isinstance(value, (list, tuple)) else [value]
        keep = [v for v in vals if _is_valid_action(v)]
        if not keep:
            return _as_style()
        return {**c, "type": "rule", "kind": kind,
                "value": keep if isinstance(value, (list, tuple)) else keep[0]}

    if kind in ("min_sessions", "min_history_messages", "min_realtime_lines",
                "max_message_chars", "max_people", "max_annotations",
                "max_history_streak", "min_interjections", "min_typing_hold",
                "max_script_steps", "max_history_two_sided", "max_same_emoji",
                "max_emoji_total", "min_distinct_emoji", "max_time_marks",
                "min_burst"):
        try:
            num = int(float(value))
        except (TypeError, ValueError):
            return _as_style()
        if num <= 0:
            return _as_style()
        return {**c, "type": "rule", "kind": kind, "value": num}

    if kind == "max_wait_ratio":
        # 占比上限是小数（0.6 这类），不能像其它数值规则那样取整
        try:
            num = float(value)
        except (TypeError, ValueError):
            return _as_style()
        if not (0 < num <= 1):
            return _as_style()
        return {**c, "type": "rule", "kind": kind, "value": num}

    if kind in ("opening_image", "forbid_annotation_as_message", "history_two_sided"):
        return {**c, "type": "rule", "kind": kind, "value": True}

    if kind in ("forbid_text",):
        vals = value if isinstance(value, (list, tuple)) else [value]
        keep = [str(v).strip() for v in vals if str(v).strip()]
        if not keep:
            return _as_style()
        return {**c, "type": "rule", "kind": kind,
                "value": keep if isinstance(value, (list, tuple)) else keep[0]}

    if kind and kind not in store.RULE_KINDS:
        return _as_style()
    if not kind:
        return _as_style()
    return c


def _repair_invalid_action_rules_once():
    """一次性修掉库里已经存在的「假动作」规则（如 required_action=插话）。"""
    global _rules_repaired
    if _rules_repaired:
        return
    _rules_repaired = True
    try:
        for s in store.list_skills():
            if (s.get("type") or "rule") != "rule":
                continue
            if s.get("kind") not in ("required_action", "banned_action"):
                continue
            vals = s.get("value")
            vals = vals if isinstance(vals, list) else [vals]
            if all(_is_valid_action(v) for v in vals if str(v or "").strip()):
                continue
            store.update_skill(s["id"], {
                "type": "style", "kind": None, "value": None,
                "prompt_hint": s.get("prompt_hint") or s.get("title") or "",
                "source_note": (s.get("source_note") or "") + "（非动作名，已转为风格偏好）",
            })
    except Exception:  # noqa: BLE001
        pass


# 规则库里的这两条旧文案把 `[打字不发]` 的正文说成「内容 | 停留 | 对方插话」，
# 与新语义（正文一律是给观众看的技巧说明）冲突，渲染提示词时统一换成新说法，
# 否则旧规则文案会把模型带偏。
_CANONICAL_HINTS = {
    "min_typing_hold": (
        "整份剧本至少 {value} 处 [打字不发]：第 1 段一律写「键盘上打给观众看的技巧字幕/博弈内容」"
        "（为什么这样聊有效，如「以退为进」「故意否定 引起注意」，这是整条视频最精彩的卖点，"
        "观众看的就是这段字被打出来再删掉的过程），停留常规写 `| 0.5`"
        "（用户实测的利落手感：带插话的常规窗口就停 0.5，不要写 1.0 拖节奏；"
        "只有合并长字幕、需要观众读完的博弈大窗口才用 1.0~1.5）；"
        "插话是可选的第三段（对方边看你打字边发的消息，不支持对字幕内容做心理描写）。"
        "展开的会话里要密集出现（连打好几次、删掉再打）"
    ),
    "min_interjections": (
        "整份剧本至少 {value} 处带「插话」，每个展开的会话至少 3 处；"
        "插话必须是对方真发出来的一句口语——【视角铁律】她的气泡里「我」只能指她自己、「你」指我；"
        "绝不能把我方心理活动、我方教学策略（如「见好就收」「看你怎么圆」「吊着我」）、"
        "对她刚发的东西的点评（如「就这光线 也敢发？」）写进插话，也不要复述她上一条已说过的话"
        "（用户实测反例：`[打字不发] … | 0.5 | 大半夜发这个；这是明着钓我`——图是她自己发的，"
        "她不可能说自己发图来「钓我」，画面前后矛盾）；三种合法来源：回应我已经发出去的上一条消息、"
        "对方自己的新话题、预演「我正打的这条若发出去她此刻会怎么回」"
        "（预演后 [我方打字] 的真实话术要错开方向）；严禁回应剧本里没发生过的剧情；"
        "【承接铁律 2026-09-14】插话的锚点只能是「我上一条**已发送**的消息」或她自己起的话题——"
        "**还停在输入框里的草稿她看不到，不能当她的锚点**；她这句说完，我删掉草稿发的那句必须直接答她。"
        "校验器 3.13 判问题：回应型孤立句（关你什么事／管得着吗／要你管，而上文没人管过她）、"
        "认责句空降（这事怪我／都怪我／是我的问题，而前文她没怪过我）、答非所问；"
        "带插话的窗口停留写 0.5；"
        "插话支持全部消息格式（行首标记路由，写在插话段里而非独立动作行）："
        "文字直接写（文字里的 [微笑] 按内嵌 emoji 渲染）；`[对方表情] 素材短名`=贴纸；"
        "`[对方图片] 素材短名`=图片；`[对方链接] 标题 | 封面 | 来源`=链接卡；"
        "`[对方emoji] 微笑`=3D黄脸（名称/编号/随机）；`[对方转账] 金额 | 备注`=转账卡。素材短名必须是【可用素材】清单里真实存在的"
        "（语音功能已禁用，插话里禁止出现）"
    ),
    # 「篇幅」两条规则在库里长期互相打架（130 条对白 ⟂ 200 步），
    # 校验时已按参考比例收敛（见 _apply_budget），提示词里也必须给同一个口径，
    # 否则提示词要 130 条、校验器只认 140 条，模型照样会被打回。
    "min_realtime_lines": (
        "实时对白（历史会话块以外的 [我方打字]/[对方发消息]/[打字不发]）不少于 {value} 条；"
        "整份剧本的实时指令不超过配套的步数上限，两条要一起满足"
    ),
    "max_script_steps": (
        "整份剧本的实时指令（[历史会话] 块以外所有 [动作] 行）控制在 {value} 步以内；"
        "节奏靠「打字不发 → 删除 → 再打字」，不要靠多开来回、堆 [对方正在输入]/[等待] 拉长"
    ),
    "max_emoji_total": (
        "整份剧本发出的表情（贴纸表情包 + 3D emoji）合计不超过 {value} 个，"
        "表情是调味料，不要在整段里一直发表情"
    ),
    "min_distinct_emoji": (
        "整份剧本至少用 {value} 种**不同**的表情（贴纸表情包 + 3D emoji 合计去重），"
        "同一个表情仍最多 2 次。按情绪从【可用素材】里挑，不要整份只围着一张「猫咪捂脸」转——"
        "害羞/脸红→害羞猫咪、[害羞]、[脸红]；无语/翻白眼→翻白眼、猫咪翻白眼、[无语]、[翻白眼]；"
        "认怂/词穷→溜了溜了、[Emm]、[捂脸]；没眼看/绷不住→没眼看、[裂开]；点赞/认可→认可表情包、"
        "猫咪抱拳、[赞]、[666]、[好的]、[收到]；晚安→晚安表情包、[月亮睡了]；撒娇/卖萌→女生撒娇表情包、"
        "嘟嘴小女孩、[调皮]、[甜笑]；大笑/惊讶→吃惊、[笑哭]、[憨笑]、[惊讶]；生气/怼→鸟都不鸟你表情包、"
        "[发怒]、[炸毛]；委屈/感动→哭泣猫咪、[流泪]、[快哭了]；疑问→[疑问]、吃惊。"
        "3D emoji 优先用内嵌写法：把 [名称] 直接写进消息文本（如「太开心了[大笑]」「嗯？[疑问]」），"
        "随文字一起上屏、不占步骤；单独的 [发送emoji]/[对方emoji] 留给「只发表情不打字」的时刻。"
        "对话有来有回才像真人：她发表情你也要接（[对方emoji] / [对方表情]），别只让一方发"
    ),
    "max_time_marks": (
        "实时段的时间分隔条（`内容 | 18:22`）整份不超过 {value} 处，"
        "只钉在关键节点（换天、隔了很久）；历史会话块内首末条的时间标注不计数"
        "（那是微信列表必须的），不要每条消息都挂一个时间"
    ),
}


def _skill_text(s: dict) -> str:
    hint = _CANONICAL_HINTS.get(str(s.get("kind") or ""))
    if hint:
        try:
            val = int(float(s.get("value")))
        except (TypeError, ValueError):
            val = s.get("value")
        return hint.format(value=val)
    if str(s.get("kind") or "") == "max_annotations":
        # 旧规则：限制「注释」处数。现在 [打字不发] 正文本来就该是技巧说明、不限处数，
        # 这条规则只保留「[我方打字] 里不许写策略注释」的兜底校验，不再作为提示词条目。
        return ""
    return str(s.get("prompt_hint") or s.get("title") or "").strip()


def _preference_lines(pref) -> list:
    """把 feedback.json 里的自由文本偏好拆成一行一条（只取以 - 开头的条目）。"""
    out = []
    for line in str(pref or "").splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        s = s.lstrip("-").strip()
        if len(s) >= 2:
            out.append(s)
    return out


def skills_prompt_block(skills=None) -> str:
    """把规则库拼成提示词块。

    与旧版「一段自由文本偏好」的区别：规则条目是结构化的、可校验的，
    每条都可能在生成后被 validate_generated_steps 命中并触发定向重写。
    """
    items = skills if skills is not None else load_enabled_skills()
    rules = [s for s in items if (s.get("type") or "rule") == "rule"]
    styles = [s for s in items if (s.get("type") or "rule") != "rule"]
    # 兜底：feedback.json 里还有没入库/没启用的历史偏好时也一并注入，
    # 避免出现「用户写了评价、生成时却一条都没看到」的情况。
    known = {_skill_text(s) for s in items if _skill_text(s)}
    legacy = [t for t in _preference_lines(load_feedback().get("preferences", ""))
              if t not in known]
    if not rules and not styles and not legacy:
        return "（暂无生效规则）"
    lines = []
    if rules:
        lines.append("【必须遵守的硬性规则】（生成结果会被逐条校验，违反哪条就按哪条重写）")
        lines += [f"- {_skill_text(s)}" for s in rules if _skill_text(s)]
    if styles:
        if lines:
            lines.append("")
        lines.append("【创作风格偏好】")
        lines += [f"- {_skill_text(s)}" for s in styles if _skill_text(s)]
    if legacy:
        if lines:
            lines.append("")
        lines.append("【长期创作偏好（历史沉淀，尚未入库，同样要遵守）】")
        lines += [f"- {t}" for t in legacy]
    return "\n".join(lines)


def load_preferences_block() -> str:
    """兼容旧调用：返回「生效规则 + 风格偏好」提示词块。"""
    return skills_prompt_block()


def save_preferences_block(pref: str):
    data = load_feedback()
    data["preferences"] = (pref or "").strip()
    save_feedback(data)


# ------------------------------------------------------------
# 钉住的硬要求：distill_preferences 会整段重写 preferences，手写的关键要求会被
# 大模型「总结」掉、静默消失。下面这份是唯一真源——既写进蒸馏提示词要求原样保留，
# 又在蒸馏结果里兜底补回（缺失就补、重复就只留一条）。
# 2026-09-15 用户点名：每个图片槽都要写「配图注释」（拿剧本找照片时不用通读上下文）。
# ------------------------------------------------------------
_PINNED_PREFS = (
    "- ★配图注释（每个图片槽都要写，用户硬要求）：在每个图片/照片槽位上方紧跟一行以 # 开头的注释当「找图说明书」，"
    "四段式——# 【照片N·我发/她发｜用途】效果＝画面主体+细节+画面形式（对镜自拍/特写/竖屏/暖光） ｜ "
    "找图＝随手拍或网搜关键词 ｜ 呼应＝前后哪两句台词；⚠️ 注释行内禁用中文冒号「：」和英文冒号「:」——"
    "历史块解析会把「xx：yy」当成一条对白凭空上屏，分隔一律用「＝」「｜」；注释以 # 开头运行时会跳过，不影响成片",
    "- 配图注释也要覆盖「不用找」的项，且「效果＝」画面白描一条都不能省：朋友圈点图的「效果＝」必须写点开后的画面"
    "（穿搭/场景/姿势/光线）＋对应人物库哪个人第几条动态＋真实素材路径（如 /images/sets2/xxx.jpg）＋配文——"
    "人物与照片只能照人物库（peer_presets.json 的 posts）原文引、禁止虚构；"
    "历史块占位图写明该会话不打开、列表页只显示「[图片]」、不用准备素材；"
    "粉丝引流固定图写明直接用图库里哪一张＋封面实际画面（如红底大字报「男生脱单其实超简单」）",
    "- ★配图注释覆盖「每一次」点图：同一处连着写两条 [点开图片]（引用哪条点哪条 + 再点一张）时，"
    "【两条上方各写一行 # 注释】，不许只给第一条写——第二条没注释，配图清单里就是空白格，"
    "用户还是得回去翻上下文才知道点开的是谁的哪张",
)


def _ensure_pinned_prefs(pref: str) -> str:
    """保证钉住的硬要求在偏好块里存在且只出现一次。"""
    lines = [l for l in str(pref or "").splitlines() if l.strip()]
    for pin in _PINNED_PREFS:
        head = pin[:18]
        if not any(head in l for l in lines):
            lines.append(pin)
    return "\n".join(lines)


def _rule_preferences() -> str:
    """无大模型时，用规则从高分反馈里提炼偏好块。"""
    data = load_feedback()
    feedback = [f for f in data.get("feedback", []) if isinstance(f, dict)]
    if not feedback:
        return _ensure_pinned_prefs("")
    scored = [f for f in feedback if int(f.get("score", 0)) >= 4]
    if not scored:
        return _ensure_pinned_prefs("")
    lines = []
    seen_text = set()
    for f in scored:
        c = str(f.get("comment", "")).strip()
        if c and c not in seen_text:
            seen_text.add(c)
            lines.append(f"- 用户曾评价（{f.get('score')}星）：{c}")
    if not lines:
        return _ensure_pinned_prefs("")
    return _ensure_pinned_prefs("\n".join([
        "以下是从过去多次生成中，用户给出高分评价后沉淀的创作偏好，尽量遵守：",
        *lines,
    ]))


_STALE_PREF_PATTERNS = (
    re.compile(r"150\s*步"),                                    # 旧步数口径（现行 ≤200）
    re.compile(r"(开头|开局)[^，。；\n]{0,14}图"),                # v7：开场是表情包，图片不作开场动作
    re.compile(r"表情[^，。；\n]{0,12}(不超过|不要超过|别超过|少于|≤)\s*3"),  # 旧表情额度（现行 ≤10）
    re.compile(r"(要有|加上|加个|加入|来一?[条个段笔])[^，。；\n]{0,4}语音"),  # 语音禁用，只许「不使用语音」
)


def _sanitize_pref_lines(pref: str) -> str:
    """蒸馏结果防线：逐行丢掉与最新定标打架的旧口径行。"""
    out = []
    for line in str(pref or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if any(p.search(s) for p in _STALE_PREF_PATTERNS):
            continue
        out.append(s if s.startswith("-") else "- " + s)
    return "\n".join(out)


def distill_preferences(api_key: str, model: str = None, base_url: str = None) -> str:
    """把历史高分布 + 留言蒸馏成一段「创作偏好 / 技巧」文本，写回 feedback.json。

    有 Key 用大模型汇总；无 Key 用规则兜底。返回偏好块文本。
    """
    data = load_feedback()
    feedback = [f for f in data.get("feedback", []) if isinstance(f, dict)]
    # 只取高分级与含留言的，避免噪音
    useful = [f for f in feedback if int(f.get("score", 0)) >= 4 or str(f.get("comment", "")).strip()]
    if not useful:
        save_preferences_block("")
        return ""
    if not api_key:
        pref = _sanitize_pref_lines(_rule_preferences())
        save_preferences_block(pref)
        return pref
    try:
        lines = []
        for f in useful[-40:]:
            lines.append(
                f"主题：{str(f.get('brief',''))[:80]} | 评分：{f.get('score')} | 留言：{str(f.get('comment',''))[:120]}")
        user_text = "\n".join(lines)
        system = (
            "你是微信聊天剧本的『创作偏好总结器』。下面是用户对多份已（男追女聊天教学）剧本的评价记录。"
            "请总结成一段【可执行的创作偏好/技巧】清单（每行一条，用 - 开头），"
            "包括：题材方向、人物设定、聊天套路（共情/调动情绪/探知三观/拉高格局/邀约等）、"
            "节奏（停顿/插话/后台消息）、画面元素（表情/图片/链接卡）等维度。"
            "只输出清单，不要解释，不要评论。\n"
            "⚠️ 以下几条是用户点名、必须长期保留的硬要求，请【逐字原样】抄进你的输出清单，"
            "不许改写、不许精简、不许合并、不许省略：\n" + "\n".join(_PINNED_PREFS)
        )
        raw = st.call_deepseek(api_key, system, user_text, model or st.DEFAULT_MODEL, base_url or st.DEFAULT_BASE_URL)
        pref = str(raw).strip()
        # 去掉 markdown 围栏
        pref = re.sub(r"^```(?:text|markdown)?\s*", "", pref)
        pref = re.sub(r"\s*```$", "", pref)
        pref = _ensure_pinned_prefs(_sanitize_pref_lines(pref))
        save_preferences_block(pref)
        return pref
    except Exception:  # noqa: BLE001
        pref = _ensure_pinned_prefs(_sanitize_pref_lines(_rule_preferences()))
        save_preferences_block(pref)
        return pref


# ============================================================
# 完整性检查（防偷工减料）
# ============================================================

# 明确表示"此处省略 / 自行发挥"的占位符。
# 注意：不要用省略号（……、...、…）当占位——它们在正常口语里表示停顿/迟疑/省略语气
# （如"你真是...""不过……也行"），若误判会把本就完整的剧本反复打回重写（病态自我迭代）。
_PLACEHOLDER_RE = re.compile(
    r"(?:\[省略\]|【省略】|\(省略\)|（省略）|此处省略|以下省略|中间省略|"
    r"省略[了0-9一二三四五六七八九十]+字|省略号|省略内容|"
    r"内容自拟|自行发挥|自行补充|自行添加|待补充|待填充|填充内容|填内容|写内容|"
    r"任意发挥|自由发挥|随便写|随便填|TODO|待定|从略|此处从略)"
)

# 单个/连续 xxx / XXX / xxx，可能被用作占位
_PLACEHOLDER_XXX_RE = re.compile(r"(^|\s)((?:x{2,})|(?:X{2,})|(?:？{2,}))(\s|$|[。，])")


def strip_code_fences(text: str) -> str:
    """去掉 markdown 代码块围栏，避免整体被 ``` 包住。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:text|markdown)?\s*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    return t


def check_completeness(text: str) -> list:
    """检测剧本是否存在"偷工减料"占位/缩略，返回问题清单。

    只报明确的占位与过量省略；自然聊天里出现单个省略号不视为问题（避免误报）。
    """
    issues = []
    text = strip_code_fences(text or "")
    if not text.strip():
        return ["生成结果是空的，疑似大模型未产出内容或全部被省略。"]
    # 占位符（「别让他自由发挥」「不要自行发挥」这类自然否定句不算占位）
    for m in _PLACEHOLDER_RE.finditer(text):
        prev = text[max(0, m.start() - 4):m.start()]
        if re.search(r"(别|不要|不用|不必|禁止|避免|不能)", prev):
            continue
        ctx = text[max(0, m.start() - 12):m.end() + 12].replace("\n", " ")
        issues.append(f"检测到省略/占位：『{m.group(0)}』在「…{ctx}…」附近，请补全真实内容。")
    # 单个/连续 xxx / XXX / xxx 可能是占位；「？？？」例外——失守型字幕（可歪引擎，
    # 2026-09-17 定调）合法出现在 [打字不发] 行内，跳过该行以免把「？？？ 完了」当占位打回。
    for ln in text.splitlines():
        stripped = ln.strip()
        is_hold_line = stripped.startswith("[打字不发]")
        for m in _PLACEHOLDER_XXX_RE.finditer(ln):
            if is_hold_line and "？" in m.group(2):
                continue
            ctx = text[max(0, text.find(ln) + m.start() - 12):text.find(ln) + m.end() + 12].replace("\n", " ")
            issues.append(f"检测到占位符：『{m.group(0)}』，请改用具体文字。")
    # 行数过少 / 没有对话
    non_empty = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if len(non_empty) < 5:
        issues.append(f"剧本行数过少（仅 {len(non_empty)} 行），内容疑似被大幅省略。")
    if not re.search(r"[\[\【]\s*(打开聊天|打开会话|进入聊天)\s*[\]】]", text):
        issues.append("剧本里没有 [打开聊天]，构不成会话场景。")
    return issues


# ============================================================
# 生成结果结构化校验（动作级）
# ============================================================

# 这些动作必须有具体文案/内容
_MESSAGE_ACTIONS = {"我方打字", "对方发消息", "打字不发", "发朋友圈", "评论", "转发消息"}
# 这些动作必须有联系人
_CONTACT_ACTIONS = {"打开聊天", "对方后台发消息", "对方后台发表情"}


def _norm_action(name: str) -> str:
    return st.ACTION_ALIASES.get(name, name)


def _as_str_list(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()]


# 「心理活动 / 解说说」的典型词。这些词本应只作为创作说明，不该出现在消息正文里。
_ANNOTATION_HINTS = (
    "需求感", "冷读", "格局", "博弈", "注意力", "铺垫", "拉高", "共情她", "把话题权",
    "降低她的防备", "情绪到位", "主动权", "自我暴露", "不哄不追问", "需求", "框架",
)

# 「策略注释 / 心理活动」的识别线索：真实聊天话术是对着她说、会出现「你」；
# 而解说式注释常用第三人称或策略名词。用于把「最多 2 处注释」这条规则落到实处。
_STRATEGY_NOUNS = (
    "情绪", "节奏", "话题", "话术", "博弈", "冷读", "格局", "需求", "铺垫",
    "场景", "开场", "理由", "朋友圈", "主动权", "框架", "心态", "氛围",
)
_STRATEGY_IMPERATIVES = ("别问", "别提", "别急", "别把", "不要", "切忌")

# 强注释信号：出现就是「给观众看的解说词」，不可能是发出去的话术。
_STRONG_ANNOTATION = (
    "需求感", "冷读", "格局", "博弈", "主动权", "框架", "话术", "方法论",
    "三观", "自我暴露", "把话题权",
)

# 「我方心里失守」型字幕白名单（可歪引擎，2026-09-17 用户拍板两型并存）。
# 主线女主会话的 [打字不发] 允许写我方看到她消息瞬间的心理失守——
# 短促、无「你」、非话术，是张力来源，不应被判成聊天草稿。
_LOSE_COMPOSURE_HINTS = (
    "？？？", "???", "完了", "坏了", "好家伙", "上头", "这谁", "谁敢", "不敢答",
    "别多想", "别想歪", "血压", "心跳", "招架不住", "接不住", "顶不住", "绷不住",
    "心虚", "腿软", "愣住", "懵", "慌", "冒汗", "不敢接", "这个话题有毒", "危险发言",
)

# 「给观众看的技巧说明」的识别线索。[打字不发] 的正文按用户要求应该是「为什么这样聊有效」
# 的打法说明（如「以退为进」「故意否定 引起注意」），而不是聊天话术草稿。
_TACTIC_HINTS = (
    "试探", "暗示", "共情", "情绪", "主动权", "框架", "节奏", "铺垫", "话题", "安全感",
    "好奇", "误会", "激将", "以退为进", "反客为主", "否定", "肯定", "认同", "调侃", "施压",
    "压力", "后撤", "立住", "推高", "拉扯", "抛", "丢", "留白", "观察", "复制", "反转",
    "标准答案", "思路", "逻辑", "打法", "套路", "技巧", "尺度", "边界", "需求", "冷读",
    "格局", "博弈", "反差", "转移", "引导", "制造", "加深", "点破", "传递", "台阶",
    "退路", "冷处理", "让步", "女生", "对方", "她", "他", "夸", "探知", "扔", "第一步",
    "第二步", "第三步", "别问", "别急",
)

# 打法的「动词/结构」线索：技巧说明几乎都带这些字，而聊天话术很少带。
# 背景（用户实测）：旧版只认 _TACTIC_HINTS 的词表，像「故意慢半拍 让注意力停在我这」
# 「用一句承诺收尾 把约钉死」「已读不回别追 隔天用图重新开场」这些完全合格的打法说明
# 因为没踩中词表被判成「聊天话术草稿」，26 处里误判 6 处，生成循环为此反复重写。
_TACTIC_VERBS = (
    "让", "用", "把", "先", "再", "别", "留", "故意", "主动", "顺势", "适当", "适度",
    "判断", "决定", "退场", "钩子", "收尾", "开场", "稳住", "埋", "补", "压", "抬",
    "换", "拖", "收", "放", "停", "降温", "示弱", "含糊", "承诺", "钉", "点到", "慢半拍",
)


def _looks_like_tactic_note(content: str) -> bool:
    """判断 [打字不发] 的正文是不是「给观众看的技巧说明」而非聊天话术草稿。

    改成反向判断，避免旧版「没踩中词表就判成话术」的大面积误伤：
      - 命中打法词（词表 + 打法动词）→ 是技巧说明；
      - 命中「我方心里失守」白名单（可歪引擎：主线会话允许的另一种字幕型）→ 是；
      - 否则，只有明显是「对着对方说的话」才判成话术草稿：出现「你」，或整句是个问句/感叹句。
    """
    t = (content or "").strip()
    if not t:
        return False
    if any(w in t for w in _LOSE_COMPOSURE_HINTS):
        return True
    if any(w in t for w in _TACTIC_HINTS):
        return True
    if any(w in t for w in _TACTIC_VERBS):
        return True
    if "你" in t:
        return False
    if re.search(r"[?？!！]$", t):
        return False
    return True


def _looks_like_strategy_note(content: str) -> bool:
    """判断一条 [我方打字] 的正文是不是「策略注释/心理活动」而非真实话术。

    早先的写法是「出现 她/他/对方 就算注释」，结果把「问她今天被谁惹了」这类
    正常聊天话术也判成注释，生成完永远过不了校验。现在改成：
      - 命中强信号词（需求感/冷读/格局…）直接算注释；
      - 句子里同时出现「你」「我」= 明显在跟对方说话，不算注释；
      - 其余只有在「第三人称/祈使式」叠加「策略名词」时才判为注释。
    """
    t = (content or "").strip()
    if not t:
        return False
    if any(w in t for w in _STRONG_ANNOTATION):
        return True
    if "你" in t or "我" in t:
        return False
    if any(w in t for w in ("她", "他", "对方")) and any(w in t for w in _STRATEGY_NOUNS):
        return True
    if any(w in t for w in _STRATEGY_IMPERATIVES) and any(w in t for w in _STRATEGY_NOUNS):
        return True
    return False


def _count_history_and_realtime(text: str):
    """统计 (历史块内消息行数, 历史块外实时对白行数)。"""
    hist = 0
    real = 0
    in_hist = False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if re.match(r"^[\[\【]\s*历史会话\s*[\]\】]", s):
            in_hist = True
            continue
        if re.match(r"^[\[\【]\s*历史会话结束\s*[\]\】]", s):
            in_hist = False
            continue
        if in_hist:
            if re.match(r"^[\[\【]\s*会话\s*[\]\】]", s):
                continue
            hist += 1
        else:
            if re.match(r"^[\[\【]\s*(我方打字|打字不发|对方发消息|对方后台发消息)\s*[\]\】]", s):
                real += 1
    return hist, real


def _opened_contacts(text: str) -> set:
    """剧本里会被 [打开聊天] 打开的会话名集合（2026-09-16 新增）。

    打开聊天后聊天页渲染该会话的**全部**历史消息（dialogue.vue 里
    `v-for="(item,index) in msgInfo.msg"` 整条 msg 数组都渲染），所以：
      - 会被打开的会话：历史应该写成有来有回的一段对话（多条、「我：」回复、
        按真实间隔排的时间条），打开时才像「我们之前就聊了一些」；
      - 不会被打开的会话：仍按列表页预览口径压成 1~2 条（列表页只显示最后一条）。
    「像列表页预览」那些限制（max_history_two_sided / max_history_streak /
    时间条间隔）只对【不会打开】的会话生效，靠这个集合排除。
    """
    out = set()
    for ln in (text or "").splitlines():
        m = re.match(r"^\s*[\[\【]\s*(?:打开聊天|打开会话|进入聊天|进入会话)\s*[\]\】]\s*(.+?)\s*$",
                     ln.strip())
        if m:
            out.add(m.group(1).split("|")[0].strip())
    return out


def _history_sessions(text: str, skip_opened: bool = False) -> list:
    """解析 [历史会话] 块，返回 [(会话名, [(说话人, 内容), ...]), ...]。

    用于校验「历史会话要有来有回」：旧版把整块当纯文本，看不出是不是一个人刷屏。
    skip_opened=True 时只返回【不会被 [打开聊天] 打开】的会话（2026-09-16）：
    这些才受「像微信列表预览」的单向/条数/时间条限制。
    """
    sessions = []
    cur = None
    in_hist = False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^[\[\【]\s*历史会话\s*[\]\】]", s):
            in_hist = True
            continue
        if re.match(r"^[\[\【]\s*历史会话结束\s*[\]\】]", s):
            in_hist = False
            cur = None
            continue
        if not in_hist:
            continue
        m = re.match(r"^[\[\【]\s*会话\s*[\]\】]\s*(.+)$", s)
        if m:
            cur = (m.group(1).strip(), [])
            sessions.append(cur)
            continue
        m = re.match(r"^([^：:|]{1,16})[：:]\s*(.+)$", s)
        if m and cur is not None:
            cur[1].append((m.group(1).strip(), m.group(2).strip()))
    if skip_opened:
        opened = _opened_contacts(text)
        sessions = [s for s in sessions if s[0] not in opened]
    return sessions


def _max_history_streak(text: str):
    """历史会话里同一人最长连续发了几条，返回 (条数, 是谁)。

    只统计【不会被打开】的会话：会被打开的会话是打开后可见的一段真实对话，
    连发 3 条属于正常（微信里也常见），不该按列表页预览的口径卡。
    """
    best, who = 0, ""
    for _name, msgs in _history_sessions(text, skip_opened=True):
        run, prev = 0, None
        for speaker, _c in msgs:
            run = run + 1 if speaker == prev else 1
            prev = speaker
            if run > best:
                best, who = run, speaker
    return best, who


def _history_time_gaps(text: str) -> list:
    """统计历史会话内部相邻消息的分钟间隔，返回 [gap, ...]。

    用于检查时间戳是否「机械地每分钟一条」/「相邻时间条间隔不足 5 分钟」。
    2026-09-14 起同一会话内中间消息不带时间标注（只有首条/末条/间隔较久的带），
    所以 prev 要跨过无时间标注的消息，比较的是相邻两条「带时间标注」的消息。
    2026-09-16：只统计【不会被打开】的会话——被打开的会话是有来有回的一段对话，
    多条时间条是真实微信的样子（列表页看不到，打开后时间条才逐段出现）。
    """
    gaps = []
    for _name, msgs in _history_sessions(text, skip_opened=True):
        prev = None
        for _speaker, content in msgs:
            m = re.search(r"(\d{1,2}):(\d{2})\s*$", str(content or "").strip())
            cur = (int(m.group(1)) * 60 + int(m.group(2))) if m else None
            if prev is not None and cur is not None:
                gaps.append(cur - prev)
            if cur is not None:
                prev = cur
    return gaps


def _history_one_sided_sessions(text: str) -> list:
    """历史会话里「只有一方说话」的会话名列表。"""
    out = []
    for name, msgs in _history_sessions(text):
        if not msgs:
            continue
        speakers = {w for w, _ in msgs}
        mine = any(w in ("我", "我方") for w in speakers)
        others = any(w not in ("我", "我方") for w in speakers)
        if not (mine and others):
            out.append(name)
    return out


def _history_stats(text: str, skip_opened: bool = False):
    """历史会话统计，返回 (会话总数, 双方来回的会话数, 「我：」出现的总条数)。

    用户给的标准样本里，9 个会话只有 1 个是双方来回（其余只留对方最后一两句），
    所以「双方有来有回」只该在整块级别要求，不能要求每个会话都一问一答。
    skip_opened=True 时只统计【不会被打开】的会话（2026-09-16）：被打开的会话
    本来就该是一段完整对话，不占「列表页最多几个双向会话」的额度。
    """
    total = 0
    two_sided = 0
    mine_lines = 0
    for _name, msgs in _history_sessions(text, skip_opened=skip_opened):
        total += 1
        speakers = {w for w, _ in msgs}
        mine = any(w in ("我", "我方") for w in speakers)
        others = any(w not in ("我", "我方") for w in speakers)
        if mine and others:
            two_sided += 1
        mine_lines += sum(1 for w, _ in msgs if w in ("我", "我方"))
    return total, two_sided, mine_lines


def _count_interjections(steps: list) -> int:
    """统计带「插话」参数的动作数（打字不发/我方打字 的第三段）。"""
    n = 0
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        if _norm_action(s.get("action")) in ("打字不发", "我方打字"):
            p = s.get("params") or {}
            if str(p.get("插话") or "").strip():
                n += 1
    return n


def _count_typing_hold(steps: list) -> int:
    """统计 [打字不发] 动作的处数（内容停在输入框、不发送）。"""
    return sum(1 for s in (steps or [])
               if isinstance(s, dict) and _norm_action(s.get("action")) == "打字不发")


def _norm_text(s) -> str:
    """去掉空白与常见标点，用于判断两句聊天话术是不是「同一句」。"""
    return re.sub(r"[\s，。、！？!?~～…·,.;；:：\"'“”‘’（）()【】\[\]—\-_]+", "", str(s or ""))


def _typing_send_repeats(steps: list) -> list:
    """找出「[打字不发] 的内容又在随后的 [我方打字] 里原样发了一遍」的地方。

    参考剧本的写法：[打字不发] 放策略注释/不要的半句话 -> [删除文字] -1 清空 ->
    [我方打字] 写完整的真实话术，两者内容不同。若相同（或前者是后者的前缀），
    观众会看到同一句话在输入框里出现两次。
    返回 [(打字不发原文, 我方打字原文), ...]。
    """
    out = []
    acts = [s for s in (steps or []) if isinstance(s, dict)]
    for i, s in enumerate(acts):
        if _norm_action(s.get("action")) != "打字不发":
            continue
        held_raw = str((s.get("params") or {}).get("内容") or "").strip()
        held = _norm_text(held_raw)
        if len(held) < 2:
            continue
        for j in range(i + 1, min(i + 4, len(acts))):
            a = _norm_action(acts[j].get("action"))
            if a in ("删除文字", "等待", "对方正在输入"):
                continue
            if a == "我方打字":
                sent_raw = str((acts[j].get("params") or {}).get("内容") or "").strip()
                sent = _norm_text(sent_raw)
                if sent and (sent == held or (len(held) >= 6 and sent.startswith(held))):
                    out.append((held_raw, sent_raw))
            break
    return out


def _interjection_echoes(steps: list) -> list:
    """找出「插话说过的话，随后又用一条 [对方发消息] 重复了一遍」的地方。

    插话本身就是对方发出去的一条消息；再单独发一条同样的内容，观众会看到对方把
    同一句话说了两遍。返回 [插话原文, ...]。
    """
    out = []
    acts = [s for s in (steps or []) if isinstance(s, dict)]
    for i, s in enumerate(acts):
        if _norm_action(s.get("action")) not in ("打字不发", "我方打字"):
            continue
        raw = str((s.get("params") or {}).get("插话") or "").strip()
        if not raw:
            continue
        ij = [_norm_text(x) for x in re.split(r"[；;\n]+", raw) if _norm_text(x)]
        if not ij:
            continue
        for j in range(i + 1, min(i + 5, len(acts))):
            a = _norm_action(acts[j].get("action"))
            if a in ("删除文字", "等待", "对方正在输入"):
                continue
            if a == "对方发消息":
                got = _norm_text((acts[j].get("params") or {}).get("内容"))
                if got and got in ij:
                    out.append(raw)
            if a not in ("打字不发", "我方打字"):
                break
    return out


def _orphan_peer_replies(steps: list) -> list:
    """找出「对方在打字不发停住窗口里的回应被写成独立 [对方发消息] 行」的地方。

    规范第六节第 3 条：`[打字不发]` 停住窗口里对方冒过的气泡必须收进第 3 段插话，
    不许写成独立 [对方发消息] 行。这里检查两层：
      1. 窗口内（[打字不发] 与它的 [删除文字] 之间）出现的独立 [对方发消息]——
         会被渲染两次（插话机制 + 独立消息），必须改写进插话段；
      2. 窗口收口后（[删除文字] 之后、下一个我方动作之前）紧跟的 [对方发消息]，
         且该 [打字不发] 没有插话段——这就是「打出→停住→对方回话→删掉」的窗口戏
         被拆出来了，画面上对方突然凭空冒话，应收进第 3 段插话。
    返回 [(打字不发原文, 消息原文列表), ...]。
    """
    out = []
    acts = [s for s in (steps or []) if isinstance(s, dict)]
    for i, s in enumerate(acts):
        if _norm_action(s.get("action")) != "打字不发":
            continue
        raw = str((s.get("params") or {}).get("内容") or "").strip()
        has_inter = bool(str((s.get("params") or {}).get("插话") or "").strip())
        msgs = []
        closed = False
        for j in range(i + 1, len(acts)):
            a = _norm_action(acts[j].get("action"))
            if a in ("删除文字", "等待", "对方正在输入"):
                if a == "删除文字":
                    closed = True
                continue
            if a == "对方发消息":
                msgs.append(str((acts[j].get("params") or {}).get("内容") or "").strip())
                continue
            break
        if not msgs:
            continue
        # 窗口没收口（消息混在打字不发与删除文字之间）一律算；
        # 窗口收口后：没有插话段的算（窗口戏被拆出），已有插话段的属窗口外回应，不算。
        if not closed or not has_inter:
            out.append((raw, msgs))
    return out


def _consecutive_solo_holds(steps: list) -> list:
    """找出「连续两个无插话的 [打字不发]」的连排独角戏。

    用户口径：连排两条 [打字不发]（中间只有 [删除文字]/[等待]），且两条都没有第 3 段插话——
    观众看的就是「打一段→删→再打一段」的独角戏，节奏拖沓。只要其中一条带插话
    （窗口里有对方气泡），博弈感就在，不算。返回 [(前一条原文, 后一条原文), ...]。
    """
    out = []
    acts = [s for s in (steps or []) if isinstance(s, dict)]
    prev_hold = None  # (原文, 有无插话)
    for s in acts:
        a = _norm_action(s.get("action"))
        if a == "打字不发":
            raw = str((s.get("params") or {}).get("内容") or "").strip()
            has_inter = bool(str((s.get("params") or {}).get("插话") or "").strip())
            if prev_hold is not None and not prev_hold[1] and not has_inter:
                out.append((prev_hold[0], raw))
            prev_hold = (raw, has_inter)
        elif a in ("删除文字", "等待", "对方正在输入"):
            continue
        else:
            prev_hold = None
    return out


def _count_people(text: str) -> int:
    """统计「真正展开聊天的对象」数量（[打开聊天] 的目标）。

    旧版把 [会话] 里所有历史联系人都算进来，而「历史会话要铺满屏幕」与
    「出场人物不超过 3 人」本就矛盾：9 个历史会话会恒判超员，
    导致每次生成都被打回重写。这里只数真正打开聊天的人。
    """
    names = set()
    for n in re.findall(r"\[打开聊天\]\s*([^\n\r|]+)", text or ""):
        n = n.strip()
        if n and n not in ("我", "自己", "聊天主页", "主页", "返回主页"):
            names.add(n)
    return len(names)


def _has_opening_image(steps: list, text: str) -> bool:
    # v7 定标（2026-09-15 用户拍板）：开场第一动作=表情包贴纸，图片不作第一动作——
    # 「开场视觉钩子」= 表情包 或 图片 都算合规（一加人就表情包+图片连发两张=假，用户点名）。
    # 2026-09-16 更新（用户拍板「别公式化开局」）：开场改为「我方打字回历史信息」也算合规——
    # 此时视觉钩子由历史块末条美女图承担（列表页 + 打开聊天后上方都可见，不再是空对话）。
    for ln in (text or "").splitlines()[:25]:
        if "[图片]" in ln or re.search(r"\[(发送图片|对方发图片|发送表情)\]", ln):
            return True
    for s in (steps or [])[:6]:
        if isinstance(s, dict) and _norm_action(s.get("action")) in (
                "发送图片", "对方发图片", "发送表情"):
            return True
    hist = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text or "", re.S)
    if hist:
        for ln in reversed(hist.group(1).splitlines()):
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if re.search(r"\[(?:图片|动画表情|表情)\]|对方表情", s):
                return True
            break
    return False


# ============================================================
# 素材引用 / 节奏 的校验辅助
# ------------------------------------------------------------
# 用户实测反馈（一份真实剧本暴露的写法）：
#   1) 图片写成完整文件名——`[对方发图片] /images/avatar/好显身材的连衣裙__1_Missyaa_
#      来自小红书网页版_20260831_185446_546.jpg`；或写成图库里根本没有的描述（「洱海的日落」），
#      运行时破图、配图面板也找不到；
#   2) 表情写成「猫咪捂脸」「柴犬敲木鱼」这类图库里不存在的名字，运行时全回落成同一张默认表情；
#      并且同一个表情反复用（害羞猫咪 3 次）；
#   3) 每发一条消息就 `[等待] 0.2` 跟一个等待，50 处等待把节奏拖成节拍器；
#   4) 严格一问一答（交替率 0.81），没有一方连发。
# 下面这些函数把「引用怎么写」「节奏怎么走」变成可校验的口径。
# ============================================================

_ASSET_RAW_RE = re.compile(r"[/\\]|\.(?:jpe?g|png|gif|webp|bmp)\s*$|_20\d{6}[_-]\d{6}", re.I)
# 「微信」不列入（本项目的图本就是微信聊天截图，属合法描述）；只拦"来自/来源"式后缀。
_ASSET_SOURCE_RE = re.compile(r"来自小红书|来自微信|网页版|comfyui|wechat", re.I)
_EMOJI_ACTIONS = ("发送表情", "对方表情", "对方后台发表情")
_IMAGE_ACTIONS = ("发送图片", "对方发图片")

# 用腻素材黑名单（2026-09-14 用户终审点名：「男女相抱」钩子图反复出现没有创新，
# 「狗歪头」当默认垫图用滥）。出现在任何图片/表情引用里都打回，让钩子图轮换新面孔。
# 后续再有新素材被用腻，往这个元组里加名字即可。
_OVERUSED_ASSETS = ("男女相抱", "狗歪头")

# [打字不发] 停留标尺（2026-09-14 用户定标）：常规 0.5；合并长字幕/博弈大窗口 1.0~1.5。
# 写出标尺之外的数值（如 0.3 / 0.6 / 2.0）直接打回，避免旧口径漏改。
_TYPING_HOLD_SCALE = (0.3, 0.5, 1.0, 1.5)   # 0.3=短字幕+插话快节奏（2026-09-14 用户定标）


def _realtime_asset_refs(steps: list):
    """实时步骤里所有图片/表情引用，返回 [(动作名, 引用文本, 'emoji'|'image')]。

    只看实时动作（[编辑主页] 里的历史消息不在此列）：历史块里的图片只是列表预览文本，
    实时动作里的引用才是运行时要真渲染成图片的。
    """
    out = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in _EMOJI_ACTIONS:
            ref = str(p.get("表情") or p.get("图片") or "").strip()
            if ref:
                out.append((act, ref, "emoji"))
        elif act in _IMAGE_ACTIONS:
            ref = str(p.get("图片") or "").strip()
            if not ref:
                # `[图片] 好显身材的连衣裙` 这种写在消息正文里的写法，解析后描述留在「内容」里、
                # 图片为空（等配图面板补图）。这里把「像素材名」的短描述也纳入校验，
                # 否则「洱海的日落」这种图库里没有的描述会绕过校验，到配图面板才暴露。
                desc = str(p.get("内容") or "").strip()
                if re.fullmatch(r"[\u4e00-\u9fff]{2,14}", desc):
                    ref = desc
            if ref:
                out.append((act, ref, "image"))
    return out


def _asset_ref_issue(ref: str) -> str:
    """引用写成文件名/路径/来源后缀时返回说明，否则返回空串。"""
    if not ref:
        return ""
    if _ASSET_RAW_RE.search(ref):
        return "写成了文件名/路径（含扩展名或时间戳）"
    if _ASSET_SOURCE_RE.search(ref):
        return "带上了「来自小红书 / 网页版」这类来源后缀"
    return ""


def _asset_ref_resolvable(ref: str) -> bool:
    """引用能否解析到真实图片（短名 / /images/ 路径 / 外链）。"""
    ref = (ref or "").strip()
    if not ref:
        return True
    if ref.startswith("http://") or ref.startswith("https://"):
        return True
    try:
        import main                                     # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return True                                     # 取不到图库时不要误判
    if ref.startswith("/images/"):
        return bool(main._emoji_url_valid(ref))
    return bool(main._lookup_emoji_file(ref))


def _overused_asset_hit(ref: str) -> str:
    """引用命中用腻素材黑名单时返回素材名，否则返回空串。"""
    ref = (ref or "").strip()
    if not ref:
        return ""
    for name in _OVERUSED_ASSETS:
        if name in ref:
            return name
    return ""


def _link_cover_resolvable(title: str, ref: str) -> bool:
    """链接卡片封面引用能否解析到真实图（含空 ref 的按标题自动匹配）。

    解析规则与 main._resolve_link_image 完全同源；「不要图」类关键词合法返回空，
    不算失败。运行时解析不到 = 渲染空白封面方框（用户终审实测「粥铺暖光门头」事故）。
    """
    ref = (ref or "").strip()
    try:
        import main                                     # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return True                                     # 取不到解析器时不要误判
    if ref and ref in set(getattr(main, "_LINK_NO_IMAGE_KEYWORDS", ()) or ()):
        return True
    try:
        return bool(main._resolve_link_image(str(title or ""), ref))
    except Exception:                                   # noqa: BLE001
        return True


def _nearest_asset_name(ref: str, kind: str = "") -> str:
    """在可用素材清单里找与 `ref` 最接近的合法名字（给报错文案用）。

    为什么需要：历史里「猫咪捂脸」被编出来 10 次，而清单里其实是「害羞猫咪」。
    只说「请改成清单里的名字」，模型下一轮很可能再编一个近义词；
    直接把「最接近的是『害羞猫咪』」写进报错，它才会真的照抄。
    判据是「公共字 + 字面包含」——中文关键词短，字级重合度比编辑距离好用。
    """
    ref = (ref or "").strip()
    if not ref or kind not in ("emoji", "image", ""):
        return ""
    try:
        sticker, sexy, teach = _asset_whitelist()
    except Exception:                                       # noqa: BLE001
        return ""
    pool = sticker if kind == "emoji" else (list(sexy) + list(teach))
    if not pool:
        return ""
    best, best_score = "", 0.0
    ref_chars = set(ref)
    for name in pool:
        if name in ref or ref in name:
            score = 2.0 + len(set(name) & ref_chars) / max(len(name), 1)
        else:
            common = len(set(name) & ref_chars)
            if common == 0:
                continue
            score = common / max(len(set(name)), 1) + common / max(len(ref_chars), 1)
        if score > best_score:
            best, best_score = name, score
    return best if best_score >= 0.5 else ""


def _emoji_repeat_stats(steps: list):
    """返回 (不同表情数, 最高重复次数, 重复最多的表情名)。"""
    refs = [ref for _act, ref, kind in _realtime_asset_refs(steps) if kind == "emoji"]
    if not refs:
        return 0, 0, ""
    counter = {}
    for r in refs:
        counter[r] = counter.get(r, 0) + 1
    name = max(counter, key=lambda k: counter[k])
    return len(counter), counter[name], name


def _count_emoji_total(steps: list) -> int:
    """整份剧本发出的表情总数（贴纸表情包 + 3D emoji；`发送emoji 3,5,8` 算 3 个）。

    文本内嵌的 [微笑] 等标记也按个数计入：内嵌与单独一行是同一种「发表情」行为，
    不统计的话「表情是调味料、合计不超过 N 个」这条规则会被内嵌写法绕过。
    """
    total = 0
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        if act in ("发送表情", "对方表情", "对方后台发表情",
                   "发送emoji", "对方emoji"):
            ref = str((s.get("params") or {}).get("表情") or (s.get("params") or {}).get("图片") or "").strip()
            if not ref:
                continue
            parts = [x for x in re.split(r"[，,、\s]+", ref) if x]
            total += max(1, len(parts))
        elif act in ("我方打字", "打字不发", "对方发消息", "对方后台发消息"):
            # 文本内嵌 emoji：数 内容 + 插话 里的 [名称] 标记个数
            for key in ("内容", "text", "插话"):
                v = (s.get("params") or {}).get(key)
                if isinstance(v, str) and v:
                    total += len(re.findall(r"[\[【]([^\[\]】【]{1,8})[\]】]", v))
    return total


_EMOJI3D_VOCAB_CACHE = {"at": 0.0, "names": None}


def _emoji3d_vocab():
    """names.json 里全部 3D emoji 名称+别名的集合（小写）。

    给「表情多样性」统计用：只有命中真名的内嵌标记才算 3D emoji，
    避免把「[图片]」「[已读]」这类功能性方括号误算进表情。
    """
    import time
    now = time.time()
    if _EMOJI3D_VOCAB_CACHE["names"] is not None and now - _EMOJI3D_VOCAB_CACHE["at"] < 60:
        return _EMOJI3D_VOCAB_CACHE["names"]
    names = set()
    try:
        import main                                     # noqa: PLC0415
        for e in main._load_wxemoji3d():
            if e.get("name"):
                names.add(str(e["name"]).strip().lower())
            for a in (e.get("aliases") or []):
                if str(a).strip():
                    names.add(str(a).strip().lower())
    except Exception:                                   # noqa: BLE001
        names = set()
    _EMOJI3D_VOCAB_CACHE.update(at=now, names=names)
    return names


def _emoji_variety_stats(steps: list):
    """返回 (不同表情种数, 贴纸种数, 3D emoji 种数, 3D emoji 出现次数)。

    口径：单独动作（发送表情/发送emoji/对方表情/对方emoji）的引用 + 消息文本里的
    内嵌 [名称]（只认 names.json 真名）。模型只会用两三个表情、3D emoji 一个不用
    的堵点就靠这条统计暴露出来。
    """
    sticker_names = set()
    emoji3d_names = set()
    emoji3d_uses = 0
    vocab = _emoji3d_vocab()
    for _act, ref, _kind in _realtime_asset_refs(steps):
        for part in re.split(r"[，,、\s]+", (ref or "").strip().lower()):
            if not part:
                continue
            if part in vocab:
                emoji3d_names.add(part)
                emoji3d_uses += 1
            else:
                sticker_names.add(part)
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        if _norm_action(s.get("action")) not in ("我方打字", "打字不发",
                                                 "对方发消息", "对方后台发消息"):
            continue
        p = s.get("params") or {}
        for key in ("内容", "text", "插话"):
            v = p.get(key)
            if not isinstance(v, str) or not v:
                continue
            for m in re.findall(r"[\[【]([^\[\]】【]{1,8})[\]】]", v):
                n = m.strip().lower()
                if n in vocab:
                    emoji3d_names.add(n)
                    emoji3d_uses += 1
    return len(sticker_names | emoji3d_names), len(sticker_names), len(emoji3d_names), emoji3d_uses


def _count_time_marks(text: str) -> int:
    """统计**实时对白**里的时间分隔条处数（`内容 | 18:22`）。

    不计历史会话块：历史列表本来就靠时间戳撑真实感（参考剧本 10~19 处），
    把它算进「时间标注要少」的上限会让规则永远过不去。这条规则管的是实时对白，
    也就是用户说的「不要每条消息都挂一个时间点」。
    """
    n = 0
    in_hist = False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^[\[\【]\s*历史会话\s*[\]\】]", s):
            in_hist = True
            continue
        if re.match(r"^[\[\【]\s*历史会话结束\s*[\]\】]", s):
            in_hist = False
            continue
        if in_hist:
            continue
        if re.search(r"\|\s*(?:\d{1,2}:\d{2}|昨天\s*\d{1,2}:\d{2}|"
                     r"(?:星期|周)[一二三四五六日天]|\d+\s*(?:分钟|小时|天)前)\s*$", s):
            n += 1
    return n


def _wait_beat_ratio(steps: list):
    """返回 (我方消息数, 紧跟着 [等待] 的我方消息数)。"""
    seq = [s for s in (steps or []) if isinstance(s, dict)]
    mine = followed = 0
    for i, s in enumerate(seq):
        if _norm_action(s.get("action")) != "我方打字":
            continue
        mine += 1
        if i + 1 < len(seq) and _norm_action(seq[i + 1].get("action")) == "等待":
            followed += 1
    return mine, followed


def _dialogue_runs(steps: list):
    """返回 (对白条数, 最长连发, 交替率)。交替率越高越像「我一条、对方一条」的朗读。"""
    seq = []
    for s in steps or []:
        act = _norm_action(s.get("action"))
        if act in ("我方打字", "发送表情", "我方发链接", "我方发图片"):
            seq.append("me")
        elif act in ("对方发消息", "对方表情", "对方发图片", "对方后台发消息", "对方后台发表情"):
            seq.append("peer")
    if not seq:
        return 0, 0, 0.0
    max_run = run = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    alt = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    ratio = alt / (len(seq) - 1) if len(seq) > 1 else 0.0
    return len(seq), max_run, round(ratio, 3)


def _collect_messages(steps: list):
    """提取所有「会作为消息上屏」的内容，返回 [(动作名, 内容)]。"""
    out = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in ("我方打字", "打字不发", "对方发消息", "评论", "发朋友圈", "转发消息"):
            content = str(p.get("内容") or p.get("文案") or "").strip()
            if content:
                out.append((act, content))
    return out


def _rule_issues(steps: list, skills: list, text: str):
    """按规则库校验生成结果，返回 (问题清单, 被违反的规则 id 列表)。"""
    issues = []
    violated = []
    _seen_issue_msgs = set()
    action_set = {_norm_action(s.get("action")) for s in (steps or []) if isinstance(s, dict)}
    messages = _collect_messages(steps)
    sessions = len(re.findall(r"\[会话\]", text or ""))
    hist_lines, real_lines = _count_history_and_realtime(text)
    # 篇幅预算：min_realtime_lines 与 max_script_steps 一起收敛过，
    # 校验时也必须用同一套数字，否则「提示词说 110、校验器按 130 打回」。
    nums = rule_numbers(skills)

    def _need_int(value, default=0):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    for sk in skills or []:
        if not isinstance(sk, dict):
            continue
        if (sk.get("type") or "rule") != "rule":
            continue
        kind = sk.get("kind")
        val = sk.get("value")
        stitle = str(sk.get("title") or sk.get("prompt_hint") or "规则")
        hit_msgs = []
        if kind == "banned_action":
            for a in _as_str_list(val):
                if _norm_action(a) in action_set:
                    hit_msgs.append("出现了禁用动作 [%s]" % a)
        elif kind == "required_action":
            for a in _as_str_list(val):
                if _norm_action(a) not in action_set:
                    hit_msgs.append("缺少必需动作 [%s]" % a)
        elif kind == "min_sessions":
            need = _need_int(val)
            if sessions < need:
                hit_msgs.append("会话数只有 %d，少于要求的 %d" % (sessions, need))
        elif kind == "min_history_messages":
            need = _need_int(val)
            if hist_lines < need:
                hit_msgs.append("历史会话消息只有 %d 条，少于要求的 %d" % (hist_lines, need))
        elif kind == "min_realtime_lines":
            # 用「篇幅预算」收敛后的值：与 max_script_steps 一并看，
            # 避免出现「对白要 130 条、整份又不能超 200 步」这种永远过不去的组合。
            need = int(nums.get("min_realtime_lines") or _need_int(val))
            if real_lines < need:
                hit_msgs.append("实时对白只有 %d 条，少于要求的 %d" % (real_lines, need))
        elif kind == "max_message_chars":
            need = _need_int(val)
            for act, content in messages:
                # 只约束我方真正会发出去的话术；对方/历史消息长短不影响「我方言简意赅」的诉求。
                # [打字不发] 的正文是给观众看的技巧说明（天然比话术长），把它算进来会恒判不通过
                # ——旧版就是这样把 15 处技巧说明全打回重写的。
                if act != "我方打字":
                    continue
                if len(content) > need:
                    hit_msgs.append("【%s】内容过长（%d 字，上限 %d）：%s…" % (act, len(content), need, content[:18]))
                    break
        elif kind == "forbid_text":
            for w in _as_str_list(val):
                for act, content in messages:
                    if w in content:
                        hit_msgs.append("【%s】出现禁止词「%s」：%s…" % (act, w, content[:18]))
                        break
                if hit_msgs:
                    break
        elif kind == "forbid_annotation_as_message":
            # [打字不发] 现在按用户要求就是「给观众看的技巧说明」，不算违规；
            # 只有真的会发出去的 [我方打字] 里出现心理活动/解说才是硬伤。
            for act, content in messages:
                if act == "我方打字" and any(h in content for h in _ANNOTATION_HINTS):
                    hit_msgs.append("把心理活动/解说当成消息内容了：%s…" % content[:24])
                    break
        elif kind == "opening_image":
            if not _has_opening_image(steps, text):
                hit_msgs.append("开头没有表情包或图片（v7 定标：开场第一动作=表情包贴纸；"
                                "表情包+图片连发两张=假，只发一张）")
        elif kind == "max_time_marks":
            need = _need_int(val)
            if need > 0:
                _txt = re.sub(r"\[\s*历史会话\s*\].*?\[\s*历史会话结束\s*\]", "", text or "", flags=re.S)
                marks = len(re.findall(r"\|\s*\d{1,2}:\d{2}\s*$", _txt, re.M))
                if marks > need:
                    hit_msgs.append("实时段时间分隔条 %d 处，超过上限 %d：只钉在换天/隔了很久的关键节点"
                                    % (marks, need))
        elif kind == "max_people":
            need = _need_int(val)
            people = _count_people(text)
            if need and people > need:
                hit_msgs.append("出场人物 %d 人，超过上限 %d" % (people, need))
        elif kind == "max_annotations":
            # 用户明确：[打字不发] 的正文就是给观众看的技巧说明，不再限制处数；
            # 这条规则只用来兜住「[我方打字] 里写策略注释」这个硬伤（会真的发出去）。
            typed = [c for act, c in messages
                     if act == "我方打字" and _looks_like_strategy_note(c)]
            if typed:
                hit_msgs.append("把策略注释/心理活动当成消息发出去了 %d 处（例：%s）"
                                % (len(typed), "；".join(c[:16] for c in typed[:3])))
        elif kind == "history_two_sided":
            # 只要求「整块里至少有一个会话是双方来回」，不要求每个会话都一问一答：
            # 用户给的标准样本就是 9 个会话里只有 1 个是双方来回，其余只留对方最后一两句。
            need = 1 if isinstance(val, bool) or val is None else max(1, _need_int(val, 1))
            total, two_sided, mine_lines = _history_stats(text)
            if total and mine_lines == 0:
                hit_msgs.append("历史会话里完全没有「我：」的回复"
                                "（至少要有一个会话是「对方说 → 我回 → 对方再说」）")
            elif total and two_sided < need:
                hit_msgs.append("历史会话里只有 %d 个会话是双方来回，至少要有 %d 个"
                                "（其余会话可以只留对方最后一两句，不必每个都一问一答）"
                                % (two_sided, need))
        elif kind == "max_history_streak":
            need = _need_int(val, 3)
            streak, who = _max_history_streak(text)
            if streak > need:
                hit_msgs.append("历史会话里「%s」连续发了 %d 条，超过上限 %d"
                                "（历史要有来有回，不要一个人刷屏）" % (who, streak, need))
        elif kind == "min_interjections":
            # 口径统一：插话数按**本剧本实际的** [打字不发] 处数收敛（参考剧本约 1:3）。
            # 旧版规则库写死 10 处、书写规范块却劝「配太多会显得对方一直在抢话」，
            # 模型只能二选一 —— 现在两边都取同一个数。
            holds = _count_typing_hold(steps)
            need = _need_int(val, 2)
            if holds:
                need = min(need, max(2, int(round(holds / _TYPING_PER_INTERJECTION))))
            got = _count_interjections(steps)
            if got < need:
                hit_msgs.append("带「插话」的动作只有 %d 处，少于要求的 %d"
                                "（本剧本有 %d 处 [打字不发]，按约 1:3 配插话即可；"
                                "格式：[打字不发] 技巧说明 | 停留 | 对方插话，"
                                "插话只能是对方真发出来、回应我已发出消息的一句口语）"
                                % (got, need, holds))
        elif kind == "min_typing_hold":
            need = _need_int(val, 2)
            got = _count_typing_hold(steps)
            if got < need:
                hit_msgs.append("[打字不发] 只有 %d 处，少于要求的 %d"
                                "（写法：[打字不发] 技巧说明 | 停留；"
                                "正文写「为什么这样聊有效」，不是聊天话术）"
                                % (got, need))
        elif kind == "asset_ref_plain":
            for act, ref, _k in _realtime_asset_refs(steps):
                why = _asset_ref_issue(ref)
                if not why:
                    continue
                # 2026-09-15：预绑定放行——引用是 /images/ 路径且文件真实存在（配图清单
                # 直接显示「已配图」），这条规则的本意是拦 LLM 编造的假文件名，不拦真图。
                if ref.startswith("/images/") and _asset_ref_resolvable(ref):
                    continue
                hit_msgs.append("【%s】素材引用%s：%s…"
                                "（只写图库里的短名，如「好显身材的连衣裙」「害羞猫咪」；"
                                "不要写文件路径、扩展名、时间戳或来源后缀）"
                                % (act, why, ref[:26]))
                break
        elif kind == "asset_ref_exists":
            # 2026-09-14 用户定调：图片描述清单外也允许（跑视频前用户会按名字上传图片，
            # 配图面板也能手动补），只对「表情/贴纸」强制存在——表情没有配图面板兜底，
            # 名字编出来会全部回落成同一张默认表情，那才是真破图。
            for act, ref, kind in _realtime_asset_refs(steps):
                if kind != "emoji" or _asset_ref_resolvable(ref):
                    continue
                near = _nearest_asset_name(ref, kind)
                hit_msgs.append(
                    "【%s】引用的表情名「%s」在图片库里不存在"
                    "（运行时会回落成同一张默认表情）%s。"
                    "请从【可用素材】清单里逐字挑一个，不要自己描述画面。"
                    % (act, ref[:26],
                       ("；清单里最接近的是「%s」" % near) if near else ""))
                break
        elif kind == "max_same_emoji":
            need = _need_int(val, 2)
            _distinct, top, top_name = _emoji_repeat_stats(steps)
            if top > need:
                hit_msgs.append("同一个表情「%s」用了 %d 次，超过上限 %d："
                                "表情要换着来，不要整段反复发同一张"
                                % (top_name, top, need))
        elif kind == "min_distinct_emoji":
            need = _need_int(val, 6)
            distinct, n_stick, n_e3d, _uses = _emoji_variety_stats(steps)
            if distinct < need:
                hit_msgs.append(
                    "整份剧本只用了 %d 种不同的表情（贴纸 %d 种 + 3D emoji %d 种），少于要求的 %d 种："
                    "表情包按情绪换着发（害羞/无语/认怂/点赞/晚安各有现成素材），"
                    "3D emoji 优先内嵌在消息文本里（如「太开心了[大笑]」「嗯？[疑问]」）"
                    % (distinct, n_stick, n_e3d, need))
        elif kind == "max_wait_ratio":
            try:
                cap = float(val)
            except (TypeError, ValueError):
                cap = 0.6
            if cap <= 0:
                cap = 0.6
            mine, followed = _wait_beat_ratio(steps)
            if mine >= 8 and followed * 1.0 / mine > cap:
                hit_msgs.append("[等待] 被当成每句话之间的固定节拍：%d 条我方消息里 %d 条后面紧跟 [等待]"
                                "（%.0f%%，上限 %.0f%%）：等待只留在真正要停一下的地方，"
                                "节奏靠连发 / 打字不发 / 插话，而不是每句都跟一个 0.2 秒"
                                % (mine, followed, followed * 100.0 / mine, cap * 100))
        elif kind == "min_burst":
            need = _need_int(val, 2)
            total, max_run, ratio = _dialogue_runs(steps)
            if total >= 12 and max_run < need:
                hit_msgs.append("实时对白 %d 条却没有任何一方连发（最长连发 %d 条，至少要 %d 条）："
                                "不要严格一问一答，允许一方连着发 2~3 条" % (total, max_run, need))
            elif total >= 12 and ratio > 0.75:
                hit_msgs.append("实时对白交替率 %.2f 偏高（上限 0.75）：几乎每条都是「我一条、对方一条」，"
                                "像朗读脚本；要有一段一方连发 2~3 条。" % ratio)
        if hit_msgs:
            violated.append(str(sk.get("id") or ""))
            for m in hit_msgs[:3]:
                # 同一条问题可能被多条规则同时命中（如两条都写「话要短」），
                # 去重避免把重复的问题堆进重写提示词里。
                if m in _seen_issue_msgs:
                    continue
                _seen_issue_msgs.add(m)
                issues.append("%s（规则：%s）" % (m, stitle))

    # ---- 图片预算（2026-09-16 用户定调：开头钩子必须保留，其余图片能省则省）----
    # 无条件检查（不挂在规则库 kind 上，保证默认生效）。口径：
    #   · 只统计「需要用户上传」的实时图片引用（[发送图片]/[对方发图片] 的图片参数）；
    #   · 图库短名能解析到真图 = 零上传，不计入；
    #   · 开场钩子（前 6 步内）豁免 1 张——硬性要求 17 要求它必须存在；
    #   · [点开图片]（朋友圈真图）、历史块占位图不在此列，本来就不用找。
    cap_imgs = _need_int(nums.get("max_extra_images"), 5)
    if cap_imgs > 0:
        hook_exempted = False
        upload_refs = []
        for _i, _s in enumerate(steps or []):
            if not isinstance(_s, dict):
                continue
            _act = _norm_action(_s.get("action"))
            if _act not in _IMAGE_ACTIONS:
                continue
            _ref = str((_s.get("params") or {}).get("图片") or "").strip()
            if not _ref or _asset_ref_resolvable(_ref):
                continue
            if _i < 6 and not hook_exempted:
                hook_exempted = True          # 开场钩子（硬性要求 17）
                continue
            upload_refs.append((_act, _ref))
        if len(upload_refs) > cap_imgs:
            _e = "；".join("%s: %s" % (a, r[:18]) for a, r in upload_refs[:4])
            issues.append(
                "需要用户上传的图片有 %d 张，超过上限 %d（开场钩子已豁免 1 张，"
                "图库短名零上传不计入）：除开场钩子外只有剧情必需的图才发"
                "（图梗错位 / 证物道具 / 邀约画面），纯情绪反应用贴纸或内嵌 emoji，"
                "可发可不发的图一律不发。超出的例子：%s"
                % (len(upload_refs), cap_imgs, _e))
    return issues, violated


def validate_generated_steps(steps: list, skills=None, text: str = ""):
    """对归一后的步骤做结构化校验。

    返回 (问题清单, 被违反的规则 id 列表)：
      - 问题清单为空 = 通过；
      - 规则 id 列表用于把「哪条规则被命中」回写到规则库的命中次数，
        并让下一轮 critique 定向修复。
    """
    if not steps:
        return (["生成结果没有可执行步骤，请重新生成。"], [])
    issues = []
    has_chat = any(isinstance(s, dict) and _norm_action(s.get("action")) == "打开聊天" for s in steps)
    if not has_chat:
        issues.append("剧本缺少 [打开聊天]，无法构成一段可运行的聊天场景。")

    msg_count = 0
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in _MESSAGE_ACTIONS:
            msg_count += 1
            content = str(p.get("内容") or p.get("文案") or "").strip()
            if not content:
                issues.append(f"【{act}】消息内容为空，不能只写指令不写具体话术。")
            elif re.fullmatch(r"[.。，,、…·\-—_*~！!？?]+", content):
                # 「哦」「好」「嗯」这类单字是真实聊天里正常的短回复，不能算占位；
                # 只有整条都是标点/省略号才判定为没写内容。
                issues.append(f"【{act}】消息内容疑似占位（『{content}』），请写具体话术。")
        if act in _CONTACT_ACTIONS:
            if not str(p.get("联系人") or "").strip():
                issues.append(f"【{act}】缺少联系人，无法定位会话。")
        if act in ("等待", "对方正在输入"):
            sec = p.get("秒数", 1)
            try:
                if float(sec) <= 0:
                    issues.append(f"【{act}】时长必须大于 0（当前 {sec}）。")
            except (TypeError, ValueError):
                issues.append(f"【{act}】时长不是有效数字（{sec}）。")
        if act == "打字不发":
            hold = p.get("停留")
            hold = hold if not isinstance(hold, list) else (hold[0] if hold else None)
            if hold is not None:
                try:
                    _hold_f = float(hold)
                    if _hold_f < 0:
                        issues.append("【打字不发】停留秒数不能为负。")
                    elif not any(abs(_hold_f - s) < 1e-6 for s in _TYPING_HOLD_SCALE):
                        issues.append("【打字不发】停留 %.1f 不在停留标尺内：标尺 0.3/0.5/1.0/1.5"
                                      "（0.3=短字幕快节奏，常规带插话 0.5，长字幕/博弈窗口 1.0~1.5）。"
                                      % _hold_f)
                except (TypeError, ValueError):
                    pass
    if 0 < msg_count < 3:
        issues.append(f"对话消息过少（仅 {msg_count} 条），请按参考剧本补充完整聊天过程，不要省略。")

    # ---- 实时区消息 / 教学字幕不许重复 ----
    # 用户反馈：同一句话连发两遍、同一条字幕教两遍，是重排/改写时的低级事故，
    # 观众一眼穿帮。近邻窗口内同一说话人+同一内容只允许出现一次。
    _recent = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        p = s.get("params") or {}
        if act in ("我方打字", "对方发消息", "对方后台发消息"):
            content = str(p.get("内容") or p.get("文案") or "").strip()
            if content:
                for _pa, _pc in _recent:
                    if _pa == act and _pc == content:
                        issues.append("同一句话「%s」说了两遍：改写/重排时把段落重复了，"
                                      "删掉重复的那份。" % content[:20])
                        break
                _recent.append((act, content))
                if len(_recent) > 12:
                    _recent.pop(0)
        elif act == "打字不发":
            cap = str(p.get("内容") or p.get("文案") or "").strip()
            if cap:
                for _pa, _pc in _recent:
                    if _pa == "打字不发" and _pc == cap:
                        issues.append("教学字幕「%s」出现了两次：每条字幕只教一个新要点，"
                                      "不要重复教同一个动作。" % cap[:20])
                        break
                _recent.append(("打字不发", cap))
                if len(_recent) > 12:
                    _recent.pop(0)

    # ---- 历史会话「像微信列表预览」的硬性检查 ----
    # 用户给的标准样本：9 个会话只有 1 个带「我：」的回复，其余只留对方最后 1~2 条。
    # 旧提示词要求「每个会话都一问一答」，导致模型把历史块写成 10 个会话全部双方来回，
    # 看起来不像微信列表。这里按规则数值（没配规则时默认 2）兜底校验。
    # 2026-09-16：只对【不会被打开】的会话计数——被 [打开聊天] 打开的会话打开后
    # 可见全部历史消息，本来就该写成有来有回的一段对话，不占这个额度。
    hist_total, hist_two_sided, _hist_mine = _history_stats(text, skip_opened=True)
    if hist_total >= 3:
        cap = int(rule_numbers(skills or []).get("max_history_two_sided", 2) or 2)
        if hist_two_sided > cap:
            issues.append("历史会话里有 %d 个【不会被打开】的会话写了「我：」的回复，超过上限 %d"
                          "（要像微信列表预览：只留 1 个会话带我方回复，"
                          "其余只留对方最后 1~2 条，不要每个会话都一问一答；"
                          "会被 [打开聊天] 打开的会话不受此限）"
                          % (hist_two_sided, cap))

    # ---- 时间戳不能机械地「每分钟一条」/ 同会话时间条过密 ----
    # 用户反馈 1：历史会话里相邻两条消息永远差 1 分钟（21:47 / 21:48 / 21:49），一眼假。
    # 用户反馈 2（2026-09-14）：微信同会话内相邻两条消息间隔不足 5 分钟时不会显示第二个时间条；
    # 每条消息都带时间标注 = 每条都渲染一条时间条，3 分钟隔一条时间条真微信里不存在。
    # 正确写法：同会话内只有首条、末条（列表时间要用）和间隔较久（≥5 分钟）的消息带时间标注。
    gaps = _history_time_gaps(text)
    close = [g for g in gaps if g < 5]
    if close:
        issues.append("历史会话里有 %d 处相邻时间标注间隔不足 5 分钟（最小 %d 分钟）："
                      "微信里间隔不足 5 分钟不会显示第二个时间条。"
                      "同一会话内只给首条和末条消息写「| 时间」，中间消息一律不带时间标注；"
                      "首末都带时间时两者间隔至少 5 分钟。" % (len(close), min(close)))
    elif len(gaps) >= 3:
        ones = sum(1 for g in gaps if g == 1)
        if ones >= max(3, int(len(gaps) * 0.8)):
            issues.append("历史会话的时间戳几乎是机械的每分钟一条（%d 个相邻间隔里 %d 个正好差 1 分钟）："
                          "同一会话内只有首条、末条和间隔较久（≥5 分钟）的消息带时间标注，"
                          "其余消息不写「| 时间」，间隔要错落。" % (len(gaps), ones))

    # ---- 会被打开的会话：历史要写成一段有来有回的对话（2026-09-16 用户要求）----
    # 用户实测：打开聊天后上方只有 1~2 条历史，一眼假；「打开里面就该有信息，
    # 像我们之前就聊了一些」。素材可以从其他剧本里已收尾的会话搬（同人物库）。
    # 提示级：偏薄只提示，不拦通过（粉丝引流号按原口径，不要求铺长）。
    _opened_thin = []
    for _onm, _omsgs in _history_sessions(text):
        if _onm not in _opened_contacts(text) or "粉丝" in _onm:
            continue
        if len(_omsgs) < 6:
            _opened_thin.append("%s(%d条)" % (_onm, len(_omsgs)))
    if _opened_thin:
        print("[提示] 会被 [打开聊天] 打开的会话历史偏薄（<6 条）：%s\\n"
              "      打开后聊天页渲染该会话【全部】历史消息，应该是一段有来有回的对话——"
              "打开里面就有信息，像「我们之前就聊了一些」；"
              "素材可从其他剧本里已收尾的会话搬过来（同一人物库，改名/改时间即可）。"
              % "、".join(_opened_thin))

    # ---- 同一个人只能有一个会话 ----
    # 用户反馈：同一个人在微信里只会有一个会话条目，出现两个 [会话] 同名直接穿帮。
    _seen_conv = set()
    for _cname, _msgs in _history_sessions(text):
        if _cname in _seen_conv:
            issues.append("历史会话里「%s」出现了多个会话：同一个人在微信里只会有一个会话，"
                          "把相关消息合并进同一个会话（注意同一人连发不要超过上限）。" % _cname)
        _seen_conv.add(_cname)

    # ---- 篇幅上限：整份剧本的实时指令步数 ----
    # 用户反馈「别 300 多步，控制在 200 步左右」。打字不发要够密，但不能靠无限拉长来堆。
    step_cap = int(rule_numbers(skills or []).get("max_script_steps", 0) or 0)
    if step_cap and len(steps) > step_cap:
        issues.append("整份剧本 %d 步，超过上限 %d 步：把篇幅压到 %d 步左右——"
                      "砍掉重复的来回和多余的 [对方正在输入]/[等待] 空转，"
                      "保留必要的 [打字不发] 节奏，而不是把话术删成摘要。"
                      % (len(steps), step_cap, step_cap))

    # ---- 「打字不发 / 插话」写法合理性检查 ----
    # 参考剧本的写法：[打字不发] 放策略注释或不要的半句话 -> [删除文字] -1 清空 ->
    # [我方打字] 发不同的真实话术。生成时模型常把同一句话打两遍，或让对方回答
    # 还没发出去的内容，或把插话又单独重发一遍——这里逐条兜底。
    for held, sent in _typing_send_repeats(steps):
        issues.append("【打字不发】的内容又被原样发了一遍（『%s』→『%s』）："
                      "打字不发只放策略注释或不要的半句话，随后的 [我方打字] "
                      "必须写不同的话术。" % (held[:14], sent[:14]))
    for echo in _interjection_echoes(steps):
        issues.append("插话『%s』说完又用一条 [对方发消息] 重复了一遍："
                      "插话本身就是对方的消息，不要再用独立消息重发。" % echo[:18])

    # ---- 打字不发窗口里的对方回应必须收进第 3 段插话（规范六-3）----
    for held, msgs in _orphan_peer_replies(steps):
        issues.append(
            "「%s」停住窗口里对方的回应（%s）被写成了独立 [对方发消息]："
            "按规范必须收进 [打字不发] 第 3 段插话（「；」分隔），"
            "不许写成独立消息行，更不许整段漏掉。" % (held[:16], "、".join(m[:10] for m in msgs)))

    # ---- 连排独角戏：连续两个无插话的 [打字不发] ----
    for first, second in _consecutive_solo_holds(steps):
        issues.append(
            "「%s」和「%s」连排且都没有插话，像独角戏太拖沓："
            "把两条字幕并成一条（中间空格衔接），或在中间插入对方插话/一条真实消息再继续。" % (first[:14], second[:14]))

    # ---- [打字不发] 的正文应该是「给观众看的技巧说明」----
    # 用户明确：打字不发是给观众看的，要写「为什么这样聊」的技巧，不是聊天话术草稿，
    # 也不是对方的心理活动。这里逐条统计，写成话术的直接点名重写。
    held_contents = [str((s.get("params") or {}).get("内容") or "").strip()
                     for s in (steps or [])
                     if isinstance(s, dict) and _norm_action(s.get("action")) == "打字不发"]
    held_contents = [c for c in held_contents if c]
    if len(held_contents) >= 4:
        bad = [c for c in held_contents if not _looks_like_tactic_note(c)]
        if len(bad) > max(1, len(held_contents) * 0.2):
            issues.append("[打字不发] 有 %d/%d 处写成了聊天话术草稿而不是字幕"
                          "（例：%s）：[打字不发] 的正文只有两种合法写法——"
                          "① 给观众看的打法说明（如「以退为进」「把选择权丢给她」）；"
                          "② 主线会话的我方心里失守型（如「？？？」「完了 别多想」「这谁敢答应」）。"
                          "不是马上要发出去的话，也不是对方的心理活动。"
                          % (len(bad), len(held_contents),
                             "；".join(c[:12] for c in bad[:5])))

    # ---- 会话切换过渡与后台消息（2026-09-13 用户点破的两条结构铁律）----
    # ① 视频里切会话都是「聊天 → 返回主页列表 → 点开下一个」：[打开聊天] 时画面必须在列表页；
    #    聊天页直接跳聊天页、从朋友圈/主页直接进会话，画面都会和真实录屏对不上。
    # ② [打开聊天] 后对方"凭空先发"一条消息不合理：那是我在看别的会话时发来的，
    #    必须用 [对方后台发消息] 在切换前投递；打开会话后才真正新到的消息才用 [对方发消息]。
    _screen = "home"          # home=主页列表 / chat=聊天页 / other=朋友圈·主页等中间页
    _await_first = False      # 刚 [打开聊天]，还没看到第一条消息动作
    _ever_opened = False      # 是否打开过至少一个会话（后台消息位置检查用）
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        if act == "打开聊天":
            if _screen != "home":
                why = ("聊天页直接跳另一个聊天页" if _screen == "chat"
                       else "朋友圈/对方主页等页面直接进会话")
                issues.append("会话切换不允许" + why + "，必须先 [返回主页] 回列表再 [打开聊天]"
                              "（规则：会话过渡）")
            _screen = "chat"
            _await_first = True
            _ever_opened = True
            continue
        if act == "返回主页":
            _screen = "home"
            _await_first = False
            continue
        if act in ("打开对方主页", "进入对方朋友圈", "闪到对方朋友圈", "打开对方设置", "进入朋友圈"):
            _screen = "other"
            _await_first = False
            continue
        if act == "闪回聊天":
            _screen = "chat"
            _await_first = False
            continue
        if _await_first and act in ("对方发消息", "对方发图片", "对方发链接", "对方表情"):
            issues.append("[打开聊天] 后不允许对方立刻先发消息：对方在我看别的会话时就发来的，"
                          "应改用 [对方后台发消息]（联系人=目标会话）写在切换前的上一个会话块尾；"
                          "打开会话后才真正新到的消息才用 [对方发消息]（规则：后台消息）")
            _await_first = False
            continue
        if act in ("点开图片", "播放视频"):
            # 2026-09-15：在朋友圈里点开配图 / 播放朋友圈视频，画面仍在【朋友圈】
            # （不是聊天页）。所以随后要回会话，必须 [闪回聊天] 或 [返回主页]→[打开聊天]，
            # 否则会被下面的 [打开聊天] 检查按「朋友圈直接进会话」打回。
            _screen = "other"
            _await_first = False
            continue
        if act in ("我方打字", "打字不发", "删除文字", "发送表情", "发送图片", "我方发链接",
                   "对方发消息", "对方发图片", "对方发链接", "对方表情", "对方emoji", "发送emoji",
                   "对方语音", "发送语音", "转账", "对方转账", "查看图片",
                   "切换底部面板", "隐藏键盘", "对方正在输入"):
            _screen = "chat"
            _await_first = False
            continue
        # ③ 禁区：整份剧本还没打开过任何会话时，就用后台消息投递内容（2026-09-13 用户点破）。
        #    此时「我正看着别的会话」的前提从未成立，这种内容若是开场白/既有对话，
        #    必须写进 [历史会话] 块（含我方回复）。
        #    注意：已打开过会话之后，在主页/朋友圈等页面收后台消息是合法用法（参考剧本同款），不拦。
        if act in ("对方后台发消息", "对方后台发表情", "后台消息队列", "后台消息") and not _ever_opened:
            issues.append("[对方后台发消息] 出现在整份剧本第一次 [打开聊天] 之前："
                          "还没打开过任何会话，后台消息的语义（我正看着别的会话时对方发来的）不成立；"
                          "这种打开会话之前就已发生的对话（如开场白）必须写进 [历史会话] 块"
                          "（含我方回复），不要用后台消息投递开场白（规则：后台消息位置）")

    # ---- 人设隔离：主线会话里不许冒出「导师/引流」词汇（2026-09-13 写剧本实测教训）----
    # 用户明确：主角在女主面前只是个会聊天的普通人，教学/引流只放在粉丝会话、
    # [打字不发] 观众字幕和结尾字幕。删除「带学员」段落时如果只删铺垫不删结论，
    # 还会留下「不收费」这类悬空话头——那类因果问题无法机检，交给 critique 提示词，
    # 这里只机检最硬的「词汇暴露」。
    _GURU_WORDS = ("博主", "学员", "教学", "带课", "上课", "关注", "点赞", "秘籍", "扣6", "扣 6")
    # 「点赞」单独出现多半指「给她朋友圈点赞」（断联/复联打法的核心动作），不是引流；
    # 只有「点赞关注/点关注」这类引流组合、或同句还出现其他导师词时才算（2026-09-13 规则自查修正）。
    _FAN_BAIT_RE = re.compile(r"点赞关注|点赞\s*关注|点关注|求点赞|关注公众号|扣\s*6")
    _GURU_COMBO_WORDS = ("关注", "扣6", "扣 6", "秘籍", "博主", "学员", "教学", "带课", "上课")
    _cur_peer = ""
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        if act == "打开聊天":
            _cur_peer = str((s.get("params") or {}).get("联系人") or "")
            continue
        if (act == "我方打字" and _cur_peer
                and not any(k in _cur_peer for k in ("粉丝", "学员"))):
            c = str((s.get("params") or {}).get("内容") or "")
            hit = []
            for w in _GURU_WORDS:
                if w not in c:
                    continue
                if w == "点赞" and not (_FAN_BAIT_RE.search(c)
                                        or any(k in c for k in _GURU_COMBO_WORDS)):
                    continue  # 单独的「点赞」= 朋友圈点赞动作，不算引流
                hit.append(w)
            if hit:
                issues.append("主线会话「%s」的 [我方打字] 出现导师/引流词汇（%s，『%s…』）："
                              "主角在女主面前只是会聊天的普通人，教学/引流只放在粉丝会话、"
                              "[打字不发] 观众字幕和结尾字幕里（规则：人设隔离）"
                              % (_cur_peer, "、".join(hit), c[:14]))

    # ---- 实时段时间条必须晚于历史块最新时间、且按出现顺序递增 ----
    # 实测教训：后台消息带「| 21:04」，但它回应的对话 21:05 才发生——时间倒流，一眼假。
    # 规则：历史块里最新一条的时间是实时段的地板，实时段时间条只许往前走。
    _m_hist = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text or "", re.S)
    if _m_hist:
        _hist_latest = None
        for _hh, _mm in re.findall(r"(\d{1,2}):(\d{2})", _m_hist.group(1)):
            _t = int(_hh) * 60 + int(_mm)
            _hist_latest = _t if _hist_latest is None else max(_hist_latest, _t)
        if _hist_latest is not None:
            _prev_t = _hist_latest
            for _hh, _mm in re.findall(r"\|\s*(\d{1,2}):(\d{2})", (text or "")[_m_hist.end():]):
                _t = int(_hh) * 60 + int(_mm)
                if _t < _prev_t:
                    issues.append("实时段时间条 %02d:%02d 早于之前的时间（时间在倒流）："
                                  "整份剧本时间只往前走，后台消息的时间条必须晚于它回应的对话"
                                  "（规则：时间线单调）" % (int(_hh), int(_mm)))
                _prev_t = max(_prev_t, _t)

    # ---- 对方连发节奏：相邻两条对方消息之间必须隔 [等待] 0.2（2026-09-14 晚定标 0.3→0.2）----
    # 真人手感：她发完一条要停半拍再发下一条；我方打字自带 0.15s 内置停顿，不需要等待。
    _PEER_MSG_ACTIONS = ("对方发消息", "对方发图片", "对方发链接", "对方表情", "对方emoji")
    _prev_peer = False
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        if act in _PEER_MSG_ACTIONS:
            if _prev_peer:
                issues.append("对方相邻连发两条消息中间缺 [等待] 0.2："
                              "两条 [对方…] 消息之间插一条 [等待] 0.2（发完一条停半拍再发下一条）；"
                              "我方消息不用加（打字自带停顿）（规则：对方连发节奏）")
            _prev_peer = True
        elif act == "等待":
            _prev_peer = False
        else:
            _prev_peer = False

    # ---- 台词提「朋友圈」必须真的打开朋友圈（2026-09-15 定标；主笔经验第 3 条）----
    # 主笔经验："台词提「朋友圈」必须先有打开朋友圈动作——校验器只查「视频↔点开图片」错配，
    # 不查朋友圈；3 篇栽在这里"。这里补上硬卡。
    # 判定口径（2026-09-15 实测校准）：提了朋友圈、画面里却从不打开=打回。两种合法写法都放行：
    #   ① 动作在前（四连完 → [闪回聊天] → 台词引朋友圈细节，v5 首选）；
    #   ② 预告式（我方说「朋友圈借我参观下」/「我这就去翻翻」→ 紧接着的动作行就打开，镜头跟上）——
    #      所以允许提及之后 _MOMENTS_LOOKAHEAD 个动作内兑现。只有前后都不兑现才判失败。
    # 只看实时段（历史会话块里聊到朋友圈是人设背景，不算）。
    _MOMENTS_OPEN_ACTS = ("打开对方主页", "进入对方朋友圈", "闪到对方朋友圈", "进入朋友圈",
                          "点赞", "评论", "发朋友圈", "编辑朋友圈")
    _MOMENTS_LOOKAHEAD = 8
    _rt = re.sub(r"\[历史会话\].*?\[历史会话结束\]", "", text or "", flags=re.S)
    _mlist = []
    for _line in _rt.splitlines():
        _ls = _line.strip()
        if not _ls or _ls.startswith("#"):
            continue
        _m = re.match(r"\[([^\]|]+)\]", _ls)
        if not _m:
            continue
        _mlist.append((_m.group(1).strip(), _ls))
    for _i, (_a, _ls) in enumerate(_mlist):
        if _a not in ("我方打字", "打字不发", "对方发消息") or "朋友圈" not in _ls:
            continue
        if any(x[0] in _MOMENTS_OPEN_ACTS for x in _mlist[:_i]):
            continue                      # 前面已经打开过朋友圈 → 合法
        if any(x[0] in _MOMENTS_OPEN_ACTS for x in _mlist[_i + 1:_i + 1 + _MOMENTS_LOOKAHEAD]):
            continue                      # 预告式：紧接着就打开 → 合法
        issues.append("台词提到『朋友圈』（『%s』）但前后都没有打开朋友圈的动作：搭讪篇第一段必须"
                      "做四连 [打开对方主页] 名 → [进入对方朋友圈] → [点开图片] 序号=1,1 | 停留=0.3 "
                      "→ [等待] 0.3 → [闪回聊天]；提了却不打开=画面对不上"
                      "（规则：台词提朋友圈必兑现）" % _ls[:28])
        break                             # 一份剧本只报一次，避免刷屏

    # ---- 台词与查看动作匹配：说「视频」却去 [点开图片]（2026-09-13 实测教训）----
    # 只回看最近 2 条消息动作的文本，窗口收紧避免误伤「早先随口提过视频」的正常剧本。
    _recent_msg_texts = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        if act in ("我方打字", "打字不发", "对方发消息"):
            _recent_msg_texts.append(str((s.get("params") or {}).get("内容") or ""))
            _recent_msg_texts = _recent_msg_texts[-2:]
        elif act == "点开图片":
            for c in _recent_msg_texts:
                if "视频" in c:
                    issues.append("台词提到『视频』（『%s…』）随后却是 [点开图片]：说视频配 "
                                  "[播放视频]（序号=动态序号），说照片/图片才配 [点开图片]"
                                  "（规则：台词动作匹配）" % c[:16])
                    break

    # ---- 历史块图片 / 链接封面：只查用腻素材，不再拦截清单外描述（2026-09-14 用户定调）----
    # 用户工作流：跑视频前会按剧本里的图片描述手动上传图片，「图片库没有的就等我上传」——
    # 描述性命名是创造力，不能打回。所以这里只拦「用腻素材」；
    # 哪些图要上传由 _check_script_quality.py 的 [提示] 段列清单（不判定失败）。
    _m_hist_block = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text or "", re.S)
    if _m_hist_block:
        _hist_body = _m_hist_block.group(1)
        _seen_bad_hist_img = set()
        # 历史块 [图片]/[配图] 描述（`她：[图片] xxx | 22:32`、`我：[图片] xxx`）
        for _pic in re.findall(r"\[(?:图片|配图)\]\s*([^\|\n]+)", _hist_body):
            _pic = _pic.strip()
            if not _pic or _pic in _seen_bad_hist_img:
                continue
            _over = _overused_asset_hit(_pic)
            if _over:
                issues.append("历史会话里的图片「%s」是已经用腻的素材（用户点名批评过）："
                              "钩子图/垫图必须换新面孔，从【可用素材】清单里挑没用过的短名"
                              "（规则：用腻素材）。" % _pic[:20])
                _seen_bad_hist_img.add(_pic)
    # 实时段图片/表情引用命中用腻素材
    for _act, _ref, _kind in _realtime_asset_refs(steps):
        _over = _overused_asset_hit(_ref)
        if _over:
            issues.append("【%s】用了已经用腻的素材「%s」（用户点名批评过）："
                          "按情绪从【可用素材】清单里换一张没怎么用过的（规则：用腻素材）。"
                          % (_act, _ref[:20]))
            break

    # ---- 同一角色台词开头复读（按会话隔离）----
    # 用户终审实测：22:26「你回不回消息啊 非要我盯着你么」→ 22:53 又一句「你回不回消息啊 说你呢」，
    # 同一个开头用两次像复读机。同一说话人**在同一会话里**的消息共用 ≥7 字开头且内容不同时打回；
    # 跨会话重复同一口头禅是「人设记忆点」，不算复读（相亲剧本「放鸽子的是狗」两次分别发给不同人）。
    _prefix_seen = {}
    _prefix_reported = set()
    _prefix_peer = ""
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _norm_action(s.get("action"))
        if act == "打开聊天":
            _prefix_peer = str((s.get("params") or {}).get("联系人") or "")
            continue
        if act == "闪回聊天":
            _prefix_peer = str((s.get("params") or {}).get("回到")
                               or (s.get("params") or {}).get("联系人") or "")
            continue
        if act not in ("我方打字", "对方发消息", "对方后台发消息"):
            continue
        content = str((s.get("params") or {}).get("内容") or "").strip()
        if len(content) < 8:
            continue
        peer = _prefix_peer
        if act == "对方后台发消息":
            peer = str((s.get("params") or {}).get("联系人") or peer)
        key = (peer, content[:7])
        if key in _prefix_seen and _prefix_seen[key] != content:
            if key not in _prefix_reported:
                issues.append("会话「%s」里「%s…」这个开头被同一人用了两次（另一句：『%s…』）："
                              "换个说法，同一句台词不要复读两遍。"
                              % (peer or "?", key[1], _prefix_seen[key][:10]))
                _prefix_reported.add(key)
        elif key not in _prefix_seen:
            _prefix_seen[key] = content

    # ---- 规则库校验（评价沉淀出的硬性规则）----
    rule_issues, violated = _rule_issues(steps, skills or [], text)
    issues += rule_issues
    return (issues, violated)


# ============================================================
# 问题严重度：让「回退到最好一版」的比较不再只看条数
# ------------------------------------------------------------
# 旧版评分是 (问题条数, -文本长度)：1 个「没有 [打开聊天]」和 1 个「措辞不够口语」
# 完全同权，于是纠错轮把剧本砍半、却把致命问题留在里面时，反而会被判成「更好」。
# ============================================================

# 严重度分档的关键词。
#   fatal(3) = 剧本根本跑不起来，或被解析器静默丢了内容（不是"写得不够好"，是"缺东西"）
#   rule (2) = 违反了用户沉淀下来的硬规则（会被打回重写）
#   其余      = 风格建议（改了更好，不改也能用）
# 为什么必须分档：旧评分是「有几个问题」，于是 1 个致命问题和 1 个措辞问题同权，
# 模型宁可去改措辞也不去补 [打开聊天]，critique 轮次全浪费在无谓的地方。
_SEV_FATAL = (
    "没有 [打开聊天]", "缺少 [打开聊天]", "生成结果没有可执行步骤", "没有可执行",
    "省略/占位", "占位符", "疑似占位", "内容为空", "正文为空",
    "缺少联系人", "未知指令", "无法识别", "已跳过", "静默丢弃", "被丢弃",
    "解析不出", "格式无法识别",
)
_SEV_RULE = (
    "（规则：", "超过上限", "少于要求", "少于要求", "不允许", "禁用动作", "被禁止",
    "互斥", "缺少必需动作", "必需动作",
    "（审稿员）",            # 语义终审发现的问题与硬规则同权（会打回重写）
    "用腻的素材",            # 男女相抱/狗歪头等黑名单素材
    "在图片库里搜不到",      # 历史块图片清单外自造名
    "解析不到真实图片",      # 链接封面空白
    "不在停留标尺内",        # 打字不发停留 0.3 等旧口径
    "不要复读两遍",          # 同一角色台词开头复读
)


def issue_severity(issue: str) -> int:
    """给一条问题打严重度：3=致命（跑不起来/内容被丢）/ 2=硬规则（会被打回）/ 1=风格。"""
    t = str(issue or "")
    if any(k in t for k in _SEV_FATAL):
        return 3
    if any(k in t for k in _SEV_RULE):
        return 2
    return 1


def issues_score(issues) -> tuple:
    """把问题清单压成一个可比较的分数：越小越好。

    (致命×3 + 硬规则×2 + 风格×1, 问题条数)
    —— 第一条是主序（严重度加权），第二条只在完全同分时用来打破平局。
    调用方还会在后面追加 `-len(text)`，用于「同分时更完整的优先」。
    """
    sev = 0
    for x in issues or []:
        sev += issue_severity(x)
    return (sev, len(issues or []))


# ============================================================
# 规则数值 -> 写作规范块
# ------------------------------------------------------------
# 用户反馈的两个硬伤（历史会话写法、插话格式从没出现），根因是：
#   1) 旧提示词把历史会话要求成「每个会话都一问一答」，生成出来 10 个会话全部双方来回，
#      不像微信列表；用户给的标准样本是 9 个会话只有 1 个带「我：」的回复；
#   2) 插话写法藏在第 5 条要求的括号里，没有独立小节，也没有任何规则去校验。
# 这里把「历史会话怎么写 / 插话怎么写」做成独立规范块，数值直接取自规则库，
# 保证「提示词要求的」与「生成后校验的」永远是同一套数字。
# ============================================================

_RULE_NUM_DEFAULTS = {
    # ---- 篇幅预算（数值实测自 3 份参考剧本：实时对白 112~125 条 / 解析步数 189~194 步）----
    "max_script_steps": 200,      # 实时指令步数上限（0=不限制）
    "min_realtime_lines": 110,    # 实时对白条数下限
    "min_typing_hold": 15,        # 至少几处「打字不发」（参考剧本 44~50 处）
    "min_interjections": 8,       # 至少几处插话（与「打字不发」配比约 1:3）
    # ---- 历史会话 ----
    "max_history_streak": 2,      # 历史会话里同一人最多连续几条
    "max_history_two_sided": 2,   # 历史会话里最多几个会话带「我：」的回复
    # ---- 其它 ----
    "max_annotations": 2,         # 策略注释最多几处（只用于兜住 [我方打字] 里的解说）
    "max_same_emoji": 2,          # 同一个表情最多重复几次
    "max_emoji_total": 0,         # 整份表情总数上限（0=不限制；用户rule「表情不超过3个」用这个）
    "min_distinct_emoji": 6,      # 至少用几种不同的表情（贴纸+3D emoji 去重；0=不校验）
    "max_time_marks": 0,          # 时间分隔条处数上限（0=不限制）
    "max_wait_ratio": 0.6,        # 紧跟 [等待] 的我方消息占比上限
    "min_burst": 2,               # 至少有一方连发几条
    # ---- 图片预算（2026-09-16 用户定调：开头钩子必须保留，其余图片能省则省——
    #      图一多用户找不到也配不过来）----
    "max_extra_images": 5,        # 除开场钩子外、需要用户上传的实时图片上限（0=不限制）
}

# 参考剧本实测：实时对白 / 解析步数 ≈ 0.60~0.64，取 0.70 作上限比例，
# 保证「对白下限」与「步数上限」永远能同时满足。
_REALTIME_PER_STEP = 0.70
# 参考剧本实测：44~50 处「打字不发」配 15~18 处插话 ≈ 1:3。
_TYPING_PER_INTERJECTION = 3

# 这几个 kind 的值是小数，不能像其它规则那样取整。
_RULE_FLOAT_KINDS = {"max_wait_ratio"}


def _apply_budget(nums: dict):
    """把「篇幅」相关的几条规则收敛成一个自洽的预算（就地修改 nums）。

    为什么必须收敛：旧库里 `min_realtime_lines=130` 与 `max_script_steps=200` 是两条独立规则，
    而 130 条对白 + 每个 [打字不发] 配一条 [删除文字] 已经逼近 200 步
    （实测最好的一条正是 194/200），模型被夹在「对白不够」与「步数超」之间
    （19 条卡前者、7 条卡后者）。参考剧本的真实比例是 对白/步数 ≈ 0.6，
    所以按比例收敛后，两条规则永远能同时满足。

    插话同理：参考剧本 44~50 处「打字不发」只配 15~18 处插话（约 1:3）。
    """
    notes = []
    cap = int(nums.get("max_script_steps") or 0)
    floor = int(nums.get("min_realtime_lines") or 0)
    if cap > 0:
        allowed = max(20, int(cap * _REALTIME_PER_STEP))
        if floor > allowed:
            notes.append("实时对白下限 %d 条 ⟂ 步数上限 %d 步：已按参考比例收敛为 %d 条"
                         % (floor, cap, allowed))
            floor = allowed
    nums["min_realtime_lines"] = floor
    nums["realtime_allowed"] = floor

    hold = int(nums.get("min_typing_hold") or 0)
    ij_allowed = max(2, int(round(hold / _TYPING_PER_INTERJECTION))) if hold else 0
    ij = int(nums.get("min_interjections") or 0)
    if ij_allowed and ij > ij_allowed:
        notes.append("插话下限 %d 处 ⟂ 打字不发下限 %d 处（参考比例约 1:3）：已收敛为 %d 处"
                     % (ij, hold, ij_allowed))
        ij = ij_allowed
    nums["min_interjections"] = ij
    nums["interjection_allowed"] = ij_allowed
    nums["budget_notes"] = notes
    return nums


def rule_numbers(skills=None) -> dict:
    """从规则库读出这几项的数值；没配规则就用默认值，最后按预算收敛。"""
    out = dict(_RULE_NUM_DEFAULTS)
    out["history_two_sided"] = True
    out["budget_notes"] = []
    for s in skills or []:
        if not isinstance(s, dict) or (s.get("type") or "rule") != "rule":
            continue
        kind = s.get("kind")
        if kind in _RULE_NUM_DEFAULTS:
            try:
                num = float(s.get("value"))
            except (TypeError, ValueError):
                continue
            if num > 0:
                out[kind] = num if kind in _RULE_FLOAT_KINDS else int(num)
        elif kind == "history_two_sided":
            out["history_two_sided"] = bool(s.get("value"))
    return _apply_budget(out)


# ============================================================
# 可用素材白名单（图片 / 表情）
# ------------------------------------------------------------
# 用户实测反馈（一份真实剧本）：图片写成「洱海的日落」「试衣间试裙子的自拍」，
# 图库里根本没有对应图，配图面板找不到、运行时渲染成破图；表情写成「柴犬敲木鱼」
# 「猫咪捂脸」「傲娇」「抱拳」——这些只是图片库里的展示标签，文件名里没有这些字，
# 运行时全部回落成同一张默认表情。
# 根因：提示词从没告诉模型「图库里到底有什么」。这里在生成前把「文件名能命中」的
# 可用关键词现算出来写进提示词，并配套可校验规则（asset_ref_plain / asset_ref_exists），
# 做到「提示词只让写真实存在的素材 + 生成后被校验打回」。
# ============================================================

_ASSET_TS_RE = re.compile(r"_\d{8}[_-]\d{6}(?:_\d{3})?$")
# 只丢弃「名字本身」带这些字样的候选（不整文件丢弃，否则「好显身材的连衣裙__1_…来自小红书…」
# 这种带来源后缀的好图会被误杀）。
_ASSET_SKIP_HINTS = ("来自小红书", "微信", "wechat", "img_", "image_", "view1", "comfyui",
                     "cartoon", "qrcode", "url-", "welcome", "launchimage", "聊天记录",
                     "截图", "封面", "头像")
_ASSET_STICKER_HINTS = ("表情包", "猫咪", "喵星人", "柴犬", "狗", "牛", "仓鼠", "吃惊", "没眼看",
                        "毁灭吧", "歪头", "木鱼", "鸟都不鸟你", "赵本山", "抱拳", "捂脸", "泪",
                        "嘟嘴", "翻白眼", "害羞", "晚安", "溜了", "呆滞", "预定", "认可")
_ASSET_SEXY_HINTS = ("自拍", "美腿", "连衣裙", "性感", "御", "高跟鞋", "沙发", "健身",
                     "喝酒", "穿", "腿", "背影", "相抱")
_ASSET_TEACH_HINTS = ("教学", "教程", "素材", "技巧", "案例", "脱单")

_ASSET_CACHE = {"at": 0.0, "data": None}


def _emoji_tags_block():
    """3D emoji 全量标签清单（名称+别名），读 names.json 单一数据源。

    创作模式提示词必须给出完整标签表：只给「微笑/捂脸/大笑」几个示例时，
    模型会自创标签名（历史头号堵点=素材名编造），运行时解析不到就被打回。
    """
    try:
        import main                                     # noqa: PLC0415
        lib = [e for e in main._load_wxemoji3d() if e.get("name")]
    except Exception:                                   # noqa: BLE001
        return ""
    if not lib:
        return ""
    cells = []
    for e in lib:
        aliases = [str(a) for a in (e.get("aliases") or []) if str(a)]
        cells.append("%d %s%s" % (int(e["idx"]), e["name"],
                                  "（%s）" % "、".join(aliases) if aliases else ""))
    lines = []
    for i in range(0, len(cells), 5):
        lines.append("｜".join(cells[i:i + 5]))
    return ("【3D emoji 标签清单】（共 %d 个；内嵌 [标签]、[发送emoji]、[对方emoji] "
            "只能用下面的名称或括号里的别名，一字不差、不要自创）\n%s"
            % (len(lib), "\n".join(lines)))


def _asset_whitelist():
    """扫描图片库，返回 (表情包关键词, 女生图关键词, 教学图关键词)。

    只保留「写成剧本关键词后能被 main._lookup_emoji_file 命中」的名字，
    因此这些名字运行时一定显示成真图，不会破图、也不会回落成默认表情。
    结果缓存 60 秒，避免每次拼提示词都全量扫目录。
    """
    import time
    now = time.time()
    if _ASSET_CACHE["data"] is not None and now - _ASSET_CACHE["at"] < 60:
        return _ASSET_CACHE["data"]
    result = ([], [], [])
    try:
        import main                                     # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        _ASSET_CACHE.update(at=now, data=result)
        return result
    labels = {}
    try:
        with open(os.path.join(main.FRONTEND_DIR, "public", "images", "_gallery_meta.json"),
                  "r", encoding="utf-8") as fh:
            labels = json.load(fh) or {}
    except (OSError, ValueError):
        labels = {}
    stems = []                              # 所有图片文件名（去扩展名、小写），用于快速判断关键词能否命中
    cands = []
    for d in getattr(main, "_IMAGE_SEARCH_DIRS", []) or []:
        if not os.path.isdir(d):
            continue
        folder = os.path.basename(os.path.normpath(d))
        try:
            fns = sorted(os.listdir(d))
        except OSError:
            continue
        for fn in fns:
            if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
                continue
            stem = os.path.splitext(fn)[0]
            stems.append(stem.lower())
            raw = [_ASSET_TS_RE.sub("", stem.split("__")[0])]
            raw += [_ASSET_TS_RE.sub("", p) for p in stem.split("_")]
            rel = (folder + "/" + fn) if folder not in ("images", "") else fn
            lab = labels.get(rel)
            if lab:
                raw.append(str(lab))
            for c in raw:
                c = (c or "").strip()
                if not (2 <= len(c) <= 14) or c == "表情包":
                    continue
                if not re.fullmatch(r"[\u4e00-\u9fff]+", c):
                    continue
                if any(h in c.lower() for h in _ASSET_SKIP_HINTS):
                    continue
                if any(c == s or c in s or s in c for s in stems):
                    cands.append(c)
            # 标签拆词直接放行：展示名与文件名对不上的素材（sticker/ 表情包等）
            # 由 main._lookup_emoji_file 的标签解析兜底命中，不能再要求文件名互相包含。
            # 另外把「去掉空格的整标签」（如 喵星人01）也作为关键词放行——
            # 同系列多张图（喵星人 01~40）靠编号区分；此时裸系列名（喵星人）不进清单，
            # 强制模型带编号挑具体那张，避免永远命中第一张。
            if lab:
                base = str(lab)
                nos = base.replace(" ", "")
                toks = set()
                for c in base.split():
                    c = c.strip()
                    if not (2 <= len(c) <= 14) or c == "表情包":
                        continue
                    if not re.fullmatch(r"[\u4e00-\u9fff0-9]+", c):
                        continue
                    if not re.search(r"[\u4e00-\u9fff]", c):
                        continue          # 纯数字编号不算关键词
                    if any(h in c.lower() for h in _ASSET_SKIP_HINTS):
                        continue
                    toks.add(c)
                numbered = nos != base and re.search(r"\d", nos)
                if numbered:
                    toks = {t for t in toks
                            if not (nos.startswith(t) and t != nos)}
                    toks.add(nos)
                cands.extend(toks)
    names = set(cands)
    # 复核一遍：确认每个名字真的能被运行时解析到（与 main._lookup_emoji_file 完全一致）
    names = {n for n in names if main._lookup_emoji_file(n)}
    sticker, sexy, teach = [], [], []
    for n in sorted(names):
        if any(h in n for h in _ASSET_TEACH_HINTS):
            teach.append(n)
        elif any(h in n for h in _ASSET_STICKER_HINTS):
            sticker.append(n)
        elif any(h in n for h in _ASSET_SEXY_HINTS):
            sexy.append(n)
    result = (sticker, sexy, teach)
    _ASSET_CACHE.update(at=now, data=result)
    return result


_USAGE_CACHE = {"at": 0.0, "data": None}


def _gallery_usage():
    """读图片库用法说明 _gallery_usage.json：{图片相对路径 -> 一句用法}。

    给创作模式提示词用：只报名字模型容易用错场景（把「生闷气」发给开心场景），
    名字后面必须带上「什么时候发」的说明，模型才会挑对。
    """
    import time
    now = time.time()
    if _USAGE_CACHE["data"] is not None and now - _USAGE_CACHE["at"] < 60:
        return _USAGE_CACHE["data"]
    data = {}
    try:
        import main                                     # noqa: PLC0415
        p = os.path.join(main.FRONTEND_DIR, "public", "images", "_gallery_usage.json")
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except Exception:                                   # noqa: BLE001
        data = {}
    _USAGE_CACHE.update(at=now, data=data)
    return data


def _sticker_usage_pairs(sticker_names):
    """给表情包关键词配上用法说明，返回 [(关键词, 用法或 '')]。

    关键词 -> 图片路径的映射复用 _gallery_meta.json 标签（含无空格别名），
    与 main._lookup_emoji_file 的解析规则完全一致，保证「清单里写的」运行时必命中。
    """
    usage = _gallery_usage()
    if not usage:
        return [(n, "") for n in sticker_names]
    labels = {}
    try:
        import main                                     # noqa: PLC0415
        with open(os.path.join(main.FRONTEND_DIR, "public", "images", "_gallery_meta.json"),
                  "r", encoding="utf-8") as fh:
            labels = json.load(fh) or {}
    except Exception:                                   # noqa: BLE001
        labels = {}
    kw2rel = {}
    for rel, lab in labels.items():
        lab = str(lab or "").strip()
        if not lab:
            continue
        kw2rel.setdefault(lab.replace(" ", ""), rel)
        kw2rel.setdefault(lab, rel)
    pairs = []
    for n in sticker_names:
        rel = kw2rel.get(n) or kw2rel.get(n.replace(" ", ""))
        u = str(usage.get(rel, "") or "") if rel else ""
        if not u:
            # 模糊回退：文件名派生的短词（如「毁灭吧」）对到包含它的标签用法上
            for krel, lab in labels.items():
                lab = str(lab or "").strip()
                if lab and (n in lab or lab in n) and usage.get(krel):
                    u = str(usage[krel])
                    break
        pairs.append((n, u))
    return pairs


def _asset_block() -> str:
    """把可用素材白名单拼成提示词块；清单为空时退回一句通用要求。

    为什么要写成「编号 + 反面例子」：体检 41 条历史，**34 次**被判定
    「引用的素材在图片库里找不到」，被编出来的名字集中在「猫咪捂脸」(10 次)、
    「柴犬敲木鱼」(3 次)、「洱海的日落」这类**生动但不存在**的描述上 ——
    模型把「图片关键词」当成了「画面描述」。清单本身在提示词里，
    但写成一行长文本，模型注意力压不住；编号 + 明写「这些都算错」效果好得多。
    """
    sticker, sexy, teach = _asset_whitelist()
    if not (sticker or sexy or teach):
        return ("【可用素材】写图片/表情时只能引用图片库里真实存在的图：先在「📚 图片库」里"
                "确认有对应文件，再照它的文件名/关键词写，不要自创描述。")

    def _numbered(names):
        return " ".join("%d.%s" % (i, n) for i, n in enumerate(names, start=1))

    lines = [
        "【可用素材 —— 表情/贴纸必须逐字取自下面清单；图片描述可以自造，但要好弄】",
        "  ⚠️ ①表情包名必须**逐字**照抄，不要组合、不要加修饰词、不要换说法"
        "（「猫咪捂脸」「柴犬敲木鱼」这类听起来自然但库里没有的名字 → 破图）。",
        "  ⚠️ ②③的图片：描述可以自造（跑视频前用户会按名字去准备图），但必须满足下面三条"
        "——否则用户拿不到素材，剧本等于废了。",
    ]
    if sticker:
        pairs = _sticker_usage_pairs(sticker)
        lines.append("")
        lines.append("① 表情包 —— [发送表情] / [对方表情] 只能用这 %d 个，"
                     "括号里是它的画面和适用场景，按场景挑、不要混用：" % len(pairs))
        for i, (n, u) in enumerate(pairs, start=1):
            lines.append("   %d.%s%s" % (i, n, ("（%s）" % u) if u else ""))
    lines.append("")
    lines.append("② 图片描述三条要求（[图片]/[对方发图片]/[发送图片] 通用）：")
    lines.append("   (a) 清晰：主体 + 细节 + 画面形式（竖屏实拍/手机随手拍/表情包大图/网图），去空格 ≥10 字；")
    lines.append("   (b) 好弄：随手拍得到、相册翻得到、网搜关键词一搜就有；")
    lines.append("       禁止要加工的（拼成长图/加红框/多图合成/裁出单人照）与要造场景的（朋友圈截图/弹窗截图/转账截图/群聊截图）。")
    lines.append("   (c) ★梗图优先：奶龙、卡皮巴拉、柴犬、悲伤蛙、汤姆猫、doge、奥特曼、黑人问号、旺仔这类")
    lines.append("       知名沙雕梗图/表情包大图，搜「角色名 + 动作」就有 —— 这是制造笑点最强的武器。")
    if sexy:
        lines.append("")
        lines.append("   图库里现成的常用图（可直接逐字引用，也可自造上面那种梗图）：" + _numbered(sexy))
    if teach:
        lines.append("")
        lines.append("③ 粉丝/学员会话的引流图 —— 仍用这 %d 个：" % len(teach))
        lines.append("   " + _numbered(teach))
    return "\n".join(lines)


def writing_spec_block(skills=None) -> str:
    """生成「剧本书写规范」提示词块：历史会话格式 + 插话格式 + 特殊消息写法。

    历史会话的目标风格（来自用户给的标准样本）：
      - 像微信列表预览：绝大多数会话只留对方最后 1~2 条、不写「我：」；
      - 整块里只有 1 个（最多 max_history_two_sided 个）会话带「我：」的回复；
      - 按最后一条消息时间从新到旧排列，会话内部时间递增；
      - 每条都要有钩子（悬念/暧昧/八卦/具体细节），不要「在吗/吃了吗」这类废话；
      - 同一个人不要连发一大堆，时间标注错落。
    """
    nums = rule_numbers(skills)
    streak = nums["max_history_streak"]
    two_sided_max = nums["max_history_two_sided"]
    interjections = nums["min_interjections"]
    typing_holds = nums["min_typing_hold"]
    max_steps = nums["max_script_steps"]
    realtime_floor = nums["min_realtime_lines"]
    return f"""A. 一行一条指令，格式 `[动作名] 参数`；参数里的多段用「|」分隔（停留 / 插话 / 时间）。
   【篇幅预算】四个数字一起满足、不要只把某一条拉满：整份实时指令（历史块以外，含 [打字不发]/[删除文字]/[对方正在输入] 等所有指令行）≤ {max_steps} 步、实时对白 ≥ {realtime_floor} 条、[打字不发] ≥ {typing_holds} 处、插话 ≈ [打字不发] 的 1/3。节奏要密，但靠「同一句话拆成几次打字/删改」，不要靠多开来回、堆空转指令把剧本拉长。
B. 【历史会话块】只放「已经发生过」的消息，用来把聊天列表铺满。目标是「微信列表预览」的样子（注意说话人冒号）：
   ```
   [历史会话]
   [会话] susu
   susu：那我先走了 | 23:21
   susu：好不想啊
   我：哈哈，很快还会见
   susu：没完没了加班真的好累啊 | 19:21
   susu：[图片] 视频缩略图：女生的腿
   [会话] 粉丝 军
   粉丝 军：[对方发链接] 聊天案例解析（必看） | 课程封面图 | 恋爱技巧 | 19:19
   [会话] 宝宝
   宝宝：小狗项圈给你买一个 | 19:18
   宝宝：我觉得我们发展太快了 | 19:31
   宝宝：[图片] 风景照
   [会话] SUM
   SUM：我通过了你的朋友验证请求，现在我们可以开始聊天了 | 19:18
   [会话] 芝士栗子
   芝士栗子：鸡要八毛什么意思 | 19:17
   [会话] 不要放糖
   不要放糖：那胖胖的你不喜欢吗 | 19:16
   [会话] 一粥困八天（暧昧期）
   一粥困八天（暧昧期）：泰国果冻干嘛的 | 19:15
   [会话] 绿叶
   绿叶：这个还有味道的？ | 19:14
   [会话] 糯米冻
   糯米冻：你牵着那个妹妹是谁 | 19:10
   [历史会话结束]
   ```
   - 【绝大多数会话只有对方在说】上面 9 个会话里只有 susu 一个带「我：」的回复，其余 8 个只留对方最后 1~2 条、
     不写「我：」。整块里带「我：」的会话至少 1 个、最多 {two_sided_max} 个，而且我方回复要夹在对方消息中间
     （像真聊过），不要每个会话都写成「对方说 → 我回 → 对方再说」的一问一答，那不像微信列表。
   - 【顺序】会话按最后一条消息的时间从新到旧往下排（微信列表顺序）；同一个会话内部，时间从上到下递增。
   - 每个 [会话] 一般写 1~2 条，只有要真正展开的那 1~2 个会话才多写几条（最多 3~5 条）。
   - 历史会话里同一个人最多连续 {streak} 条，超过就必须换会话。
   - 【会话名】用生活化的昵称/备注，可以带关系标注，如「一粥困八天（暧昧期）」「luna-富婆」「粉丝 军」。
   - 【跨会话因果】历史块里任何人「提及/汇报某件事」的消息，时间必须晚于这件事实际发生的时间：
     例：女主 22:12 才发「不合适」，粉丝 22:02 就说「她发了句不合适」= 因果倒置，直接穿帮。
     需要徒弟/闺蜜提前讨论某事件时，把该事件的发生时间提前，或把提及时间往后放。
   - 【每条都要有钩子】消息要具体、有信息量、带悬念/暧昧/八卦，让人想点开，
     例如「你牵着那个妹妹是谁」「泰国果冻干嘛的」「小狗项圈给你买一个」「鸡要八毛什么意思」；
     禁止「在吗」「吃了吗」「哈哈」「晚安」这类没信息量的寒暄。
   - 【画面要杂】整块里安排 1~2 条图片消息（`[图片] 视频缩略图：女生的腿`、`[图片] 风景照`）、
     1 条链接卡片（`[对方发链接] 标题 | 封面图 | 来源 | 时间`）、1 条系统消息
     （如 `SUM：我通过了你的朋友验证请求，现在我们可以开始聊天了`），让列表看起来是真的。
   - 【历史块的图】历史 [图片] 与链接卡封面的描述**可以自由创作**（写具体画面描述，
     用户跑视频前会按名字上传对应图片；也可以直接用【可用素材】清单短名零上传直接跑），
     同样禁止文件路径/扩展名/时间戳/来源后缀。
   - 时间标注写在内容后面（`| 19:21`）。**同一会话内只有首条和末条消息带时间标注**
     （微信行为：间隔不足 5 分钟不会显示第二个时间条，所以中间消息一律不带「| 时间」；
     首末都带时间时两者间隔至少 5 分钟，一般差 5~30 分钟错落）。跨会话的时间自然递增。
   - 会话数按规则来（没有规则时 9~10 个；软件会自动把主页会话补齐到 10、并把 [打开聊天] 引用的
     主角移进前 8 行，超出 10 个的才截掉）。
C. 【打字不发 / 插话】—— 这是全片最真实的地方：我还在打字，对方就插进来。写法：
   - `[打字不发] 内容 | 停留`：内容停在输入框不发送，再用 `[删除文字] -1` 清空，
     最后用 `[我方打字]` 发真实话术。停留常规写 `| 0.5`（带插话的常规窗口就 0.5；
     合并长字幕、需要观众读完的博弈大窗口才 1.0~1.5）。插话是**可选的第三段**，
     只在要制造「我还在打字、对方就抢话」时才加：`[打字不发] 内容 | 停留 | 对方插话一句`。
   - 【插话是谁说的话 —— 最容易写错的一条】第 3 段是**她发来的消息**（画面上是她的气泡），
     她的话里「我」只能指她自己、「你」指我。**绝不能**把我方心理（「这是明着钓我」「吊着我」
     「明明在等我；还嘴硬」）、我方教学策略（「见好就收」「看你怎么圆」）、对她刚发的东西的点评
     （「就这光线 也敢发？」）写进插话——观众会在她的气泡里看到只有我才会想的话，前后矛盾；
     也**不要复述她上一条已经说过的话**（插话要有新信息）。校验器 3.12 会直接判问题。
   - 【承接铁律 —— 插话要"接得住"，我下一句要"答得上"（2026-09-14 用户第 3 次现场抓）】
     插话 = **我打字期间她发来的消息**，锚点只有两个：① 接我上一条**已经发出去**的消息
     （还停在输入框里的草稿她根本看不到，**不能拿草稿当她的锚点**）；② 她自己起的新话题。
     反例①（用户原话「莫名其妙的回答了一句」）：她上一句只是「疼死了都[大哭]」，
     → 我删掉草稿后发「这事怪我」——她没怪过我，我认什么责？
     反例②（同段）：插话写「关你什么事」，可上文我最后一条是「我这人最听话」，根本没人管过她。
     正例：她「都怪你 逗我笑」→ 我「这事怪我」→ 她「你认这么快干嘛」→ 我「昨天就该拦着你吃那碗冰」。
     **落笔后自查两句**：她为什么要在这时候说这句（前一句我说了什么能让她这么说）？
     我删掉草稿后发的这句，是不是在答她？
     校验器 3.13 直接判问题：「回应型孤立句」（关你什么事／管得着吗／要你管，上文却没人管过她）、
     「认责句空降」（这事怪我／都怪我／是我的问题，前文她没怪过我）、「答非所问」。
   - **不是每个 [打字不发] 都要配插话**：参考剧本里 44~50 处打字不发只配 15~18 处插话，
     也就是大约每 3 处打字不发配 1 处插话。整份剧本至少 {interjections} 处带插话；
     你打字不发写得越密，插话按 1/3 跟着加即可，但不要每个都配，那样显得对方一直在抢话。
     （规则库与校验器用的是同一个数，不会出现「一边要求 N 处、一边劝你少配」的矛盾。）
   - `[我方打字] 正在打的这句 | 对方抢白一句`：边打字边被插话，随后把这句话发出去。
   - 多条插话用「；」分隔：`[打字不发] 先调动好奇心 | 0.5 | 你这人什么意思？！；就你会说`
   - 停留只用标尺上的数：0.5 / 1.0 / 1.5，不要写 0.3、0.6、2.0 这类标尺外的数值。
   - 【打字不发写什么 —— 最重要的一条】字幕分两型（2026-09-17 定调，两型并存）：
     **A 打法型**：写给观众看的一句话技巧说明，点出「这一步在做什么、为什么这样聊有效」，
     如「以退为进」「故意否定 引起注意」「把选择权丢给她」——**粉丝/学员会话一律用这型**。
     **B 失守型**（可歪引擎）：主线女主会话允许写「我方看到她消息瞬间的心理失守」——
     短促、不解释、不点破，如「？？？」「完了 别多想」「大晚上的 这谁敢答应」「接不住」。
     这是张力来源：观众看到主角也顶不住，代入感立刻拉满。每条主线会话至少 1 处 B 型。
     写的是**打法或我方失守**，不是聊天话术草稿，也不是对方的心理活动：
     ✅ 正确：`[打字不发] 故意否定 引起注意 | 0.5`、`[打字不发] ？？？ 这问法有点上头 | 0.5`
     ❌ 错误：`[打字不发] 那我就陪你聊到天亮`（这是马上要发的话）
     ❌ 错误：`[打字不发] 她其实在等你先低头`（这是对方的心理活动，不是技巧也不是我方失守）
     **绝不能把紧接着要原样发出去的那句话写进 [打字不发]**——观众会看到同一句出现两次；
     随后的 `[我方打字]` 必须写与它不同的完整话术。
   - 【插话回应什么】插话是**对方**发的一条消息，必须是对方能真发出来的口语，
     三种合法来源：回应「我已经发出去的上一条消息」；对方自己起一个新话题；
     **预演「我正在打/正要发的这条若发出去，她此刻会怎么回」**（插话跟着输入框里
     正在打的字走，像她凑巧瞄到你在打字就抢话——随后 [我方打字] 的真实话术要和
     预演错开方向，她刚泼了冷水你就别把这句原样发出去）。
     严禁插话回应剧本里没发生过的剧情/设定；也不要把「幸灾乐祸」「她其实在等你」
     这类心理活动/态度词写成插话。
   - 插话说过的话，不要再单独用一条 `[对方发消息]` 重复一遍。
   - 整份剧本至少 {typing_holds} 处 `[打字不发]`、至少 {interjections} 处带插话；
     重点是「打字不发」要密集：展开的会话里连着打四五次、删掉再打都是正常的，
     参考剧本里 `[打字不发]` 的数量接近 `[我方打字]` 的一半以上。插话是「参数」，
     不是单独一行，不要写成 `[对方插话] 内容`。
   - 注意区分：`[对方正在输入] 1.0` + `[对方发消息] 内容` 是「我打完、对方再回」，
     没有重叠感；要制造「我还在打字对方就插进来」的紧凑节奏，必须用 C 的写法。
D. 【消息里的特殊内容】写在消息正文开头即可，系统会自动识别：
   - 图片：`[图片] 关键词`（如 `[我方打字] [图片] 好显身材的连衣裙`）——写具体画面描述即可
     （图库里没有的用户会按名字上传，配图面板也能手动补）；**禁止写文件路径、扩展名、
     `_20260831_185446` 这类时间戳，也不要带「来自小红书 / 网页版」来源后缀**。
   - 表情：`[表情] 关键词`（如 `[对方发消息] [表情] 害羞猫咪`）——同样只写【可用素材】里的短名；
     同一个表情整份最多用 2 次，换着用（清单外或编出来的名字会全部回落成同一张默认表情）。
   - 链接卡片：`[链接] 标题 | 图片 | 来源`（图片参数写具体画面描述即可，用户会按名字上传；
     也可写「随机」「封面」或留空按标题自动匹配；禁止文件路径/时间戳/来源后缀）
   - 时间分隔条：消息末尾加 `| 21:40`（历史会话里写在内容后面）。
E. [历史会话] 块只放历史消息；`[打开聊天]` 和实时对白必须写在历史块【外面】的独立指令行。
F. 【`[我方打字]` 与 `[打字不发]` 的分工】`[我方打字]` 一律是能直接发出去的真实聊天话术，
   禁止把方法论/步骤/心理活动写进去；给观众看的技巧说明一律写在 `[打字不发]` 的正文里。
G. 【节奏 —— 别用 `[等待]` 打节拍】参考剧本里 `[等待]` 只出现在真正要停一下的地方
   （自由使用的约 7~12 处）；**不要每发一条消息就 `[等待] 0.2`**，那会变成节拍器，也被校验器拦。
   例外：**对方相邻连发两条消息之间必须插 `[等待] 0.2`**（见硬性要求 16）——这类等待
   必须加、不算在节拍上限里。
   被 `[等待]` 紧跟着的我方消息不要超过六成。更真实的做法是**一方连发 2~3 条**
   （连着几条 `[我方打字]`，或连着几条 `[对方发消息]`），不要每条都严格「我一条 → 对方一条」；
   参考剧本的最长连发是 6~15 条、交替率只有 0.19~0.56，整份对白不要写成朗读稿。
H. 【新功能要用起来】下面的【能力卡】列了几个新动作的「何时用 + 片段示例」——
   整份剧本至少用上其中 1~2 个（切换底部面板 / 发送emoji / 朋友圈 / 手机状态栏），
   不要通篇只有 [我方打字] 和 [对方发消息]：真机聊天里人本来就会切面板、发表情、打错再删。
I. 【会话切换与后台消息 —— 画面连续性】
   - 视频里切会话永远是：聊天页 → [返回主页]（看到列表）→ [打开聊天] 下一个人。
     两次 [打开聊天] 之间必须有一条 [返回主页]；从朋友圈/对方主页回到聊天也要先 [返回主页]。
   - 对方在「我正看别的会话」时发来的消息，用后台投递，写在切换之前：
     [打字不发] 以退为进 | 0.5
     [删除文字] -1
     [对方后台发消息] 另一个她 | 在忙吗 | 22:53
     [返回主页]
     [打开聊天] 另一个她
   - 后台消息支持图片/链接/时间条：内容写 `[图片] 素材短名`、`[链接] 标题 | 封面`，行尾 `| 21:40`。
   - 后台投递只能出现在「正打开着某个会话」的段落里（[打开聊天] 之后、[返回主页] 之前）；
     脚本开头还没打开任何会话时严禁用后台消息投递开场白——开场前已发生的对话一律写进 [历史会话] 块。
   - [打开聊天] 之后对方才真正新发的消息才用 [对方发消息]；不允许打开后对方「补发」
     一条早就该躺在列表里的旧消息——那种都走 [对方后台发消息]。"""


# ============================================================
# 生成提示词
# ============================================================

def _format_action_table_compact(actions=None) -> str:
    """把「可进 AI 剧本的动作」格式化成提示词简表：动作名 + 参数名 + 何时用。

    旧版直接把 editor_server.ACTIONS（60 条，含编辑主页/应用场景这类数据驱动动作）
    整份塞进提示词，既长又杂，而且每个动作只有一句 desc、没有「什么时候该用」——
    新动作（发送emoji / 切换底部面板 / 点赞…）名字躺在表里，模型永远不会主动用。

    现在从 action_registry.script_actions() 取（32 条），并带上 when。
    `actions` 参数仅为兼容旧调用保留（调用方传的 editor ACTIONS 会漏掉
    「我方发链接/对方发链接」这些 editor=False 的动作，所以不再采用）。
    """
    table = ar.script_actions()
    lines = []
    for i, a in enumerate(table, start=1):
        name = a["action"]
        bits = [p.get("key") for p in (a.get("params") or [])
                if p.get("key") not in ("数据", "data")]
        when = a.get("when") or a.get("desc") or ""
        pstr = ("（" + "、".join(bits) + "）") if bits else ""
        lines.append("%2d. [%s]%s —— %s" % (i, name, pstr, when))
    return "\n".join(lines)


def capability_block() -> str:
    """能力卡：新功能「什么时候用 + 长什么样」。

    体检结论：`切换底部面板 / 面板切换序列 / 发送emoji / 点赞 / 手机状态栏 / 闪回聊天`
    这些动作在 script_generator 里出现 0 次 —— 只有一行动作表里的名字，
    没有「什么时机用」的说明、参考剧本里也从没演过，等于新功能根本没接入生成链路。
    一张能力卡 = 何时用 + 3~6 行片段示例。
    """
    cards = ar.capability_cards()
    if not cards:
        return ""
    lines = ["【能力卡 —— 新功能「什么时候用 + 长什么样」，想用就照片段写】"]
    for c in cards:
        lines.append("- [%s] %s" % (c["action"], c["when"]))
        for snip in (c.get("snippet") or [])[:3]:
            lines.append("    " + snip)
    return "\n".join(lines)


def build_generation_prompt(actions=None, people_block: str = "", preferences: str = "",
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
        cat_note = (f"\n- 本剧本的角色以「{category}」类别为主，从【人物库】挑该类别人物；"
                    f"若类别里有多人，优先挑本剧本还没用过的那几个，避免同一张脸反复出现。")
    nums = rule_numbers(skills)
    action_text = _format_action_table_compact(actions)
    people_block = people_block or "（人物库为空，请用常见中文名）"
    pref_block = preferences or "（暂无历史沉淀）"
    ref_block = reference_text or "（暂无参考剧本，但请依聊天教学套路创作）"
    spec_block = writing_spec_block(skills)
    asset_block = _asset_block()
    emoji_tags_block = _emoji_tags_block()
    cap_block = capability_block()
    budget_note = ""
    if nums.get("budget_notes"):
        budget_note = "\n【篇幅预算已自动收敛（你只要按下面的数字写即可）】" + "；".join(nums["budget_notes"]) + "\n"

    head = f"""你是「微信聊天视频仿真剧本」创作助手，专注【男生追女生 / 聊天教学】类剧本。用户给你一个创作主题和若干参考剧本，你要产出一整套【可直接运行】的聊天教学剧本。

【动作表】（只能使用下列动作；参数名就是 JSON 里 params 的键）
{action_text}"""

    hard = f"""【硬性要求 —— 必须全部遵守】
1. 输出只能是【输出格式】里那种 JSON 对象（history + steps 两个键）；不要任何解释文字、不要 markdown 围栏、不要写 [指令] 文本。steps 里每个 action 必须来自【动作表】，params 的键必须是该动作自己的参数名。
2. 主题：围绕用户给的创作主题，编排一段「男生追女生」的完整聊天教学：先 history 铺底（历史会话）→ 打开聊天 → 我方打字 → 对方插话/后台消息 → 逐步引导（共情/调动情绪/探知三观/拉高格局）→ 情绪到位后铺垫邀约或收尾。
3. 【历史会话像微信列表预览，不是一问一答】绝大多数会话只留对方最后 1~2 条消息、不写 who=me；整块里只有 1 个（最多 {nums['max_history_two_sided']} 个）会话出现 who=me，且夹在对方消息中间。会话按最后一条消息时间从新到旧排列、会话内部时间递增；同一人最多连续 {nums['max_history_streak']} 条；**同一个人只允许出现一个会话**。**同一会话内只有首条和末条消息带「| 时间」标注**（微信里间隔不足 5 分钟不显示第二个时间条，中间消息一律不带时间），首末都带时两者间隔至少 5 分钟。**跨会话因果不能倒置**：历史块里任何人「提及/汇报某件事」的消息，时间必须晚于这件事实际发生的时间（例：女主 22:12 才发分手消息，别人 22:02 就在讨论"她发了不合适"= 穿帮）。
4. 【打字不发 + 插话必须用够】整份剧本至少 {nums['min_typing_hold']} 处 `[打字不发]`、至少 {nums['min_interjections']} 处带「插话」。「打字不发」要密集（一个展开的会话里连打四五次很正常），**但插话不是每个 [打字不发] 都配**：参考剧本 44~50 处打字不发只配 15~18 处插话，约每 3 处配 1 处，配太多会显得对方一直在抢话。三条硬性约束：① `[打字不发]` 的正文（params.内容）是**写给观众看的字幕**，两型并存——粉丝/学员会话写**技巧说明**（「这一步在做什么、为什么这样聊有效」，如「以退为进」「故意否定 引起注意」）；主线女主会话在技巧说明之外**至少 1 处写「我方心里失守」型**（「？？？」「完了 别多想」「大晚上的 这谁敢答应」——短促、不解释，观众看到主角也顶不住才有代入感）；**不能是马上要发出去的聊天话术草稿，也不能是对方的心理活动**；其后的 `[我方打字]` 内容必须与它不同；② 插话（params.插话）必须与「此刻画面」因果连续，三种合法来源：回应我已经发出去的上一条消息、对方自己起的新话题、或**预演「我正打的这条若发出去，她此刻会怎么回」**（随后 [我方打字] 的真实话术要与预演错开方向，不能她刚泼冷水我又原样发出）；严禁回应剧本里没发生过的剧情/设定（无源之水）；③ 插话说过的话，不要再用一条 `[对方发消息]` 重复一遍；④ 插话必须是**对方的台词**（自查：在插话前面加「她说」要通顺），不能写成我方口吻，也不能和对方最近一条消息同义重复（她刚催过「你人呢」，插话别再来一句「你倒是说啊」）；⑤ 剧情因果要闭环：每个话头（如「不收费」「那隐藏业务呢」）都必须有对应铺垫，台词和铺垫要么一起在、要么一起删，不许出现「回应了一个没发生过的设定」的句子；⑥ 因果时序：字幕和插话都必须出现在「触发它们的画面信号」**之后**（她还没冷淡就不能打「先稳住」，她还没冲人就不能打「先接情绪」）——信号在前、点题在后，不许提前剧透还没发生的剧情；⑦ 同一角色不要复读：同一人的台词不得重复相同开头（如两次「你回不回消息啊」），质问/怀疑类的来回每轮都要有新信息，不要三轮问同一个意思（「你变了」→「你真放下了？」→「你变了好多」这种空转要避免）；⑧ 结尾 CTA/观众字幕（「点赞关注扣6」这类）的预演插话不要写成粉丝在回应 CTA——CTA 是对观众喊的，预演只能来自剧情内逻辑；⑨ 贴纸情绪要匹配当前对话调性（严肃认错/争吵段落不发害羞猫咪这类卖萌贴纸，缓和/暧昧时刻才发）。
5. 【绝不偷工减料】禁止出现：……、[省略]、【省略】、省略、此处省略、以下省略、内容自拟、自行发挥、待补充、xxx、等等、同上、余下类似 等任何占位/缩略。每一步都要写出真实、完整、具体的中文内容。
6. 【`[我方打字]` / `[打字不发]` 分工】`[我方打字]` 一律是自然、口语化的真实聊天话术，禁止把方法论/步骤/心理活动写进去；给观众看的字幕一律写在 `[打字不发]` 的 params.内容 里——粉丝/学员线写技巧说明，主线女主线技巧说明与「我方心里失守」型混用（每条主线至少 1 处失守型）。
7. 【保留节奏】`[打字不发]` 的 params.停留：常规单条（含带插话的窗口）一律写 0.5——用户实测多段插话停 1 秒太拖，0.5 最利落；只有两条字幕合并成一条的长字幕、或需要观众读完的博弈大窗口，才写到 1.0~1.5。写出的时长要保留，不要一律用默认值。
8. 【人物】只从【人物库】里挑人名，同一剧本里同一个对象不要换名字；历史会话（history）写 9~10 个联系人把列表铺满（软件会自动补齐到 10 个），但真正 `[打开聊天]` 展开对白的最多 3 个人（历史列表里出现过的名字不算出场人物）；主线联系人尽量排在历史块的前 8 个（软件也会自动把掉出前 8 的主角移回去）。
9. 【画面丰富 + 图片少而精】适当穿插 [发送表情]、[发送emoji]、[对方后台发消息]、[我方发链接]、[手机状态栏]，让画面真实有层次。**图片预算（2026-09-16 用户定调）：开场钩子（硬性要求 17）必须保留，除此之外全篇需要用户上传的图片不超过 {nums['max_extra_images']} 张**——只有剧情必需的图才发（图梗错位暴击、证物道具、邀约画面各最多一张），纯情绪反应用贴纸或内嵌 emoji，可发可不发的图一律不发；能引用【可用素材】清单里的短名就直接用（图库已有=零上传，不计入上限），校验器按同口径硬卡。**图片与链接封面的描述可以自由创作**（写具体的画面描述即可，如 `[图片] 烤糊的蛋糕`、`[链接] 温粥小馆 | 粥铺暖光门头`——用户跑视频前会按名字上传对应图片，配图面板也能手动补），但**禁止写文件路径、扩展名、时间戳或来源后缀**；**表情/贴纸则必须逐字用【可用素材】清单里的短名**（如 `害羞猫咪`、`溜了溜了`）——表情没有配图面板兜底，名字编出来会全部回落成同一张默认表情。同一个表情整份最多用 {nums['max_same_emoji']} 次；整份至少换着用 {nums['min_distinct_emoji']} 种**不同**的表情（贴纸+3D emoji 合计去重，按【可用素材】里的情绪配对挑：害羞→害羞猫咪、无语→翻白眼、认怂→溜了溜了、点赞→认可表情包、晚安→晚安表情包、撒娇→女生撒娇表情包），3D emoji 优先内嵌写法（如「太开心了[大笑]」「嗯？[疑问]」「改天嘛[脸红]」），不要通篇一个 emoji 都没有。3D 黄脸 emoji 优先用【内嵌写法】：把 [名称] 直接写进消息文本里（如 内容: "太开心了[大笑]"、"是嘛[捂脸]"），随文字一起上屏，不必为它单独输出一条步骤；单独的 [发送emoji]/[对方emoji] 留给「只发表情不打字」的时刻。内嵌名称必须是 names.json 里的名称或别名（微笑/捂脸/大笑/爱心/害羞/调皮…），不要写 emoji 字符、编号或图库里没有的词。**「男女相抱」「狗歪头」是用腻素材，任何位置（钩子图/垫图/贴纸）都禁止再用**。
10. 【新功能至少用 1~2 个】从【能力卡】里挑 1~2 个新动作真的用进剧本（切换底部面板 / 发送emoji / 朋友圈 / 手机状态栏），不要通篇只有打字和发消息。
11. 【篇幅预算】整份剧本的实时指令（steps 的条数）控制在 {nums['max_script_steps']} 条以内、实时对白不少于 {nums['min_realtime_lines']} 条，两条一起满足；不要靠多开来回、堆 [对方正在输入]/[等待] 把剧本拉到 300 步。{budget_note}
12. 结尾可以再来一条 [返回主页] + 一条 [等待] 收束，保持整段像一个完整教学短视频。
13.【会话切换与后台消息】① 两次 [打开聊天] 之间必须隔一条 [返回主页]（先回列表再进下一个会话），不允许聊天页直接跳聊天页；从对方朋友圈/对方主页回到**原聊天**用 `[闪回聊天] 回到=联系人`（扫黑转场，一条到位），**不需要**也不应该再插 [返回主页]；但闪回之后要切换到**别的**会话，仍然要先 [返回主页]。② 对方在我看别的会话时发来的消息一律用 [对方后台发消息]（params: 联系人/内容；内容可用 `[图片] 短名`、`[链接] 标题 | 封面` 前缀，行尾可带 `| HH:MM` 时间条），只能写在「当前正打开着某个会话」的段落里、且在 [返回主页] 之前；**不允许 [打开聊天] 之后用 [对方发消息] 补一条"其实早就到了"的旧消息**——打开会话后才真正新到的消息才用 [对方发消息]。③ **开场白必须进历史会话块**：任何「打开会话之前就已经发生的对话」（包括对方的开场白和我方的回复）一律写进 [历史会话] 块，严禁用 [对方后台发消息] 在还没打开任何会话时投递开场白——后台消息的语义是「我正看着别的会话时对方发来的」，一个会话都没打开时它没有语义，播放时还会造成主页预览刚冒未读、下一秒就点进去的跳变。
14.【人设隔离——绝不在主线暴露导师身份】主线撩妹会话（[打开聊天] 展开的女主会话）的 `[我方打字]`/`[对方发消息]` 里，禁止出现 博主、情感博主、学员、教学、带课、上课、关注、扣6、秘籍 这类「导师/引流」词汇，以及「点赞关注」这类引流组合——主角在女主面前只是个会聊天的普通人，她不知道也不需要知道你在做教学。注意：单纯的「点赞」指给她朋友圈点赞（断联/复联打法的核心动作），**不属于**引流词，可以正常出现。教学与引流内容只允许出现在三个地方：① 粉丝/学员命名的会话（如「粉丝-龙龙」）；② `[打字不发]` 的观众字幕；③ 结尾下课字幕。
15.【时间线单调 + 台词动作匹配】① 整份剧本时间只往前走：history 各会话从新到旧排、同一会话内递增；实时段的后台消息时间条（| HH:MM）必须晚于历史块里最新的时间，且按出现顺序递增，不许「21:04 回应 21:05 发的话」这种时间倒流。② 同一条线上的多个邀约日期要错开（今天/周六/周日各约各的），不要全约「明天」。③ 台词提到什么，查看动作就得是什么：说「照片/图」配 `[点开图片]`，说「视频」配 `[播放视频]`，说「语音」配语音条——不许说「单曲循环了那条视频」却去 [点开图片]。
16.【对方连发节奏】对方**相邻连发**的两条消息（[对方发消息]/[对方发图片]/[对方发链接]/[对方表情]/[对方emoji] 相邻、中间没有任何其他动作时）之间，必须插一条 `[等待] 0.2`——她发完一条、停半拍再发下一条，才是真人手感（2026-09-14 晚定标 0.3→0.2）。**我方消息不需要**：`[我方打字]` 自带 0.15s 内置停顿，连发多行直接写就行，加了等待反而拖沓。
17.【5 秒钩子 —— 每条视频开场必须有图片暴击】开场尽早出图撑 5 秒留存，两种形态按剧情选：
A 实时全屏：`[对方发图片] 图片=<素材短名> | 打开=是 | 停留=1.2`（上屏自动全屏放大），适合「照片是当下互动」——她钓你反应、发照下马威；注意 [打开聊天] 后对方不能立刻先发，先垫一拍（我方贴图/打字）她再甩照片，暴击仍要落在开场第 3 个动作左右。
B 历史块图片：钩子图写成历史会话末条（`她：[图片] 画面描述 | 22:32`），打开会话第一眼就是大图，适合「照片是过去的遗物」——前任旧合照、回忆杀；此时实时区**不要**再用全屏重复同一张图。遗物照片的时间必须早于分手/断联类消息（分手之后才发合照 = 情绪逻辑不通）；「男女相抱」已用腻禁用，钩子图必须换没拍过的新面孔（画面描述自由创作，用户会按名字上传；也可用【可用素材】清单短名零上传直接跑）。
垫场贴图不要每条视频都用同一张（尤其「狗歪头」已经用滥），按情绪轮换新面孔。
18.【开场点题——她先开口，我方第一句回应她】选题必须由**她先说出口**（「我是不是胖了」「睡不着 你管不管」），或由她发的图/状态把处境直接摆出来（热水袋+药盒=她疼着）；我方第一句必须**回应她的话或她的处境**，绝不许上来打分式评图当开场（反例：「照片我看了」「先说结论」+挑刺三连、「头像我已经鉴定过了」「挺好看的 我收了」——她一句没说，视频前 10 秒在对一张图打分，选题悬空）。评图只能作为**她那张图的证据回应**出现（她说"裤子说我胖了"→我看图回"裤子缩水了"），且落点必须在她本人/她的处境，不是给照片打分。进去就聊=直接进选题，不是"人呢"，也不是"图打几分"。校验器 3.14 对打分式开场直接判问题。"""

    return "\n\n".join([
        head,
        people_block + cat_note,
        "【必须遵守的规则 / 创作偏好】（由你过去的评价沉淀而来；其中硬性规则会在生成后被逐条校验，违反会被打回重写）\n" + pref_block,
        "【剧本书写规范 —— 这套软件只认这一种写法，必须严格遵守】\n" + spec_block,
        asset_block,
        emoji_tags_block,
        cap_block,
        "【参考剧本】（整篇只当风格与结构模板；片段示例告诉你某个动作怎么演。人物名一律换成【人物库】里的，不要照抄参考里的人名）\n" + ref_block,
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
    issue_lines = "\n".join(f"- {x}" for x in issues[:20])
    violation_block = ""
    if violations:
        v_lines = "\n".join(f"- {x}" for x in list(violations)[:10])
        violation_block = (
            "\n【你上一版违反的硬性规则 —— 必须逐条改掉，这是本次修改的重点】\n" + v_lines + "\n")

    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\n- 本剧本的角色以「{category}」类别为主，从【人物库】挑该类别人物；"
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
- 【打字不发 + 插话】按书写规范 C 补足：整份至少 {nums['min_typing_hold']} 处 `[打字不发]`、至少 {nums['min_interjections']} 处带插话。**重点改 `[打字不发]` 的正文**：必须是字幕——粉丝/学员线写技巧说明（「为什么这样聊有效」），主线女主线可写「我方心里失守」型（？？？/完了 别多想/这谁敢答应），
  不是聊天话术草稿、不是对方心理活动 —— 凡是像「那我陪你聊到天亮」「她其实在等你先低头」这类，全部改写。同时检查：`[打字不发]` 的内容有没有在随后的 `[我方打字]` 里原样又发一遍；插话有没有在回答没发出去的内容；插话有没有被下一条 `[对方发消息]` 重复。
- 【历史会话】要像微信列表预览：绝大多数会话只留对方最后 1~2 条、不写 who=me；整块里最多 {nums['max_history_two_sided']} 个会话带 who=me；同一个人只允许出现一个会话；同一会话内只有首条和末条消息带「| 时间」（间隔不足 5 分钟微信不显示第二个时间条），中间消息不带时间。
- 【篇幅】steps 条数控制在 {nums['max_script_steps']} 以内、实时对白不少于 {nums['min_realtime_lines']} 条；超长时优先砍重复的来回、多余的 [对方正在输入]/[等待]、同一句话的多次删改，不要为了压长度把话术删成摘要或省略。
- 【素材引用】**图片与链接封面**：写具体画面描述即可（用户会按名字上传图片，配图面板也能补），禁止文件路径/扩展名/时间戳/来源后缀；**表情/贴纸必须逐字用【可用素材】清单里的短名**（编出来的名字会回落成默认表情）；同一个表情最多 {nums['max_same_emoji']} 次；整份至少 {nums['min_distinct_emoji']} 种**不同**表情（贴纸+3D emoji 合计去重）——不够就把部分纯文字消息补上贴纸（如 害羞猫咪/翻白眼/溜了溜了/认可表情包）或内嵌 3D emoji（把 [大笑]/[害羞]/[疑问]/[捂脸] 直接写进消息文本），同一个名字不要反复用。「男女相抱」「狗歪头」是用腻素材，禁止再用。
- 【节奏】多余的 [等待] 删掉，只保留真正要停一下的地方；至少有一段「一方连发 2~3 条」，不要严格一问一答。
- 【会话切换/后台消息】两次 [打开聊天] 之间必须有 [返回主页]；[打开聊天] 后不许对方直接先发一条旧消息，
  应改为切换前的 [对方后台发消息]（写在 [返回主页] 之前；内容支持 [图片]/[链接] 前缀与时间条）。
  [对方后台发消息] 只许出现在「正打开着某个会话」的段落里；出现在脚本开头/历史块刚结束的位置时，
  要把那段对话（含我方回复）整体改写进 [历史会话] 块，不要用后台消息投递开场白。
- 【人设隔离/时间线/因果闭环】主线女主会话里不许出现 博主/学员/教学/关注/秘籍/「点赞关注」组合 等导师引流词汇（只留在粉丝会话与观众字幕；单独的「点赞」= 给她朋友圈点赞，不算）；实时段时间条必须晚于历史块最新时间且递增；若问题涉及剧情因果（话头没有铺垫、引用了不存在的设定），要把铺垫和结论一起补齐或一起删掉，不要只改一半；台词说照片/视频，随后的查看动作要跟着改匹配（[点开图片] / [播放视频]）。
- 【对方连发节奏】对方相邻连发的两条消息（[对方发消息]/[对方发图片]/[对方表情] 等紧挨着）之间要补一条 [等待] 0.2；我方消息之间不要加（打字自带停顿）。
- 输出仍是 JSON：只需要 patches + append_steps，不要输出整篇剧本。"""

    return "\n\n".join([
        "你是同一套「微信聊天视频仿真剧本」的纠错助手。下面这一版剧本存在问题，请**只做定向修补**。",
        "【上一步的问题】\n" + issue_lines + violation_block,
        "【动作表】\n" + action_text,
        people_block + cat_note,
        "【必须遵守的规则 / 创作偏好】\n" + pref_block,
        "【剧本书写规范】\n" + spec_block,
        asset_block,
        "【参考剧本】\n" + ref_block,
        script_format_mod.PATCH_SPEC,
        repair,
    ])


# ============================================================
# 自动审稿员（语义终审，2026-09-14 新增）
# ------------------------------------------------------------
# 机械校验兜不住"要动脑子"的语义错误（跨会话因果倒置、遗物照片发在分手后、
# 三轮质问同义空转、CTA 预演错位……用户终审 11 处问题里 7 处属于这类）。
# 审稿员在机械校验全部通过后跑一遍语义清单，发现问题以「（审稿员）」前缀
# 混入问题清单，驱动既有 critique 轮定向回炉——复用整条纠错链路，不另起炉灶。
# 任何调用失败/解析失败都放行（fail-open），不让终审故障卡死生成。
# ============================================================

REVIEWER_MAX_ISSUES = 8          # 单轮最多报几条，防刷屏
REVIEWER_MAX_ROUNDS = 2          # 一次生成里最多跑几轮审稿（防止改好又改坏空转）


def build_reviewer_system_prompt() -> str:
    return """你是「微信聊天视频仿真剧本」的终审审稿员。前面已有机械校验（格式/数量/时间条/素材白名单）把关，你只审机器查不了的**语义与剧情逻辑**。逐条对照下面清单审这份剧本：

1.【跨会话因果】历史块里任何人提及/讨论某件事的时间，必须晚于该事件实际发生的时间（例：女主 22:12 才发分手消息，别人 22:02 就在讨论"她发了不合适"= 倒置）。
2.【字幕/插话因果】字幕和插话必须出现在触发信号之后，严禁剧透还没发生的剧情；插话只能是三种合法来源（回应已发消息/新话题/预演正打的话），且预演后的真实话术要错开方向。
3.【CTA 预演】结尾「点赞关注」类 CTA 的预演插话不能像粉丝在回应 CTA。
4.【钩子】开场 5 秒内是否有图片暴击；钩子图的语义是否通（遗物照片不能发在分手消息之后）；是否复用观众看腻的老面孔。
5.【台词质量】同一人复读同一开头；相邻几轮质问/怀疑是同一个意思的空转（「你变了」→「你真放下了？」→「你变了好多」）；教学字幕重复教同一个要点。
6.【贴纸/表情时机】贴纸情绪与对话调性匹配（严肃认错段不发卖萌贴纸）。
7.【人设一致】导师/教学词汇只出现在粉丝会话、观众字幕、结尾字幕；主线会话里主角是普通人。
8.【剧情逻辑】关系状态、邀约、时间前后一致；话头有铺垫、铺垫有回收；没有"回应了没发生过的设定"。

输出要求：只输出一个 JSON 字符串数组，最多 %d 条，每条格式「问题位置（引用原文≤12字）+ 错在哪 + 怎么改」，如 ["历史块粉丝龙龙 22:02 的消息提及了女主 22:12 才发生的分手，因果倒置；把龙龙这条时间改到 22:15 之后"]。没有问题输出 []。不要输出数组以外的任何文字。""" % REVIEWER_MAX_ISSUES


def reviewer_parse_issues(raw: str) -> list:
    """解析审稿员输出为问题清单；任何解析失败返回 []（fail-open）。"""
    text = strip_code_fences(str(raw or "")).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x or "").strip()][:REVIEWER_MAX_ISSUES]
    except (ValueError, TypeError):
        pass
    # 容错：模型没按 JSON 输出时，按行提取「- / 1. 」开头的条目
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        m = re.match(r"^(?:[-*•]|\d+[.、)])\s*(.+)$", ln)
        if m and len(m.group(1)) >= 8:
            lines.append(m.group(1).strip())
    return lines[:REVIEWER_MAX_ISSUES] if lines else []


def build_reviewer_user_message(text: str) -> str:
    return "【待审剧本】\n" + (text or "").strip()


def build_outline_prompt(brief: str, category: str = "",
                         people_block: str = "", ref_titles=None) -> str:
    """两段式·第一段：只出「剧情大纲」不出剧本。

    为什么单拆一段：一段式生成里「编剧情」和「写 200 行逐行指令」挤在一次调用里，
    模型的注意力全被格式/规则占住，剧情永远写得平。先出一份 300~600 字的大纲
    给用户把关（人物、钩子、递进、转折、收尾、画面运用规划），确认后第二段
    才按大纲展开成逐行剧本 —— 剧情质量卡在用户这一关。
    """
    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\n- 人物从【人物库】里挑「{category}」类别的，人名直接用库里真名（第二段生成会照用）。")
    refs = f"（参考风格：{'、'.join(ref_titles)}）" if ref_titles else ""
    people = people_block or "（人物库为空，用常见中文名）"

    return f"""你是「微信聊天教学视频」的剧情策划。用户给你一个创作主题，你只负责设计剧情大纲，**不写任何聊天内容、不写任何 [指令]**。

{people}{cat_note}{refs}

【输出格式】纯文本 markdown，按下面五个小节写（总长 300~600 字，不要展开对白）：

## 一、人物与关系
主线对象（1 人）+ 副线点缀（1~2 人，只出现在历史会话列表），各一句话人设。

## 二、主线剧情
按顺序写 4~6 个剧情节点：开场钩子（为什么这条视频有人看）→ 递进 1~2 步（共情/调动情绪/探三观/拉格局，写清每步的策略意图）→ 转折或反转（全片最精彩的一下，具体写发生了什么）→ 收尾（邀约 / 引流话术方向）。

## 三、副线安排
副线人物在历史列表里留什么消息、有没有串线（后台消息插入主线）。

## 四、画面运用规划
列 4~8 个「画面时刻」，每条一行：`动作（朋友圈 / 对方主页 / 图片查看器 / 转账 / 后台消息 / 表情包插话 / 链接卡） + 出现在哪个节点 + 为什么这里值得切画面`。纯聊天打字不算画面时刻；同一类画面全片最多重复 2 次。

## 五、给观众的技巧点
列 3~6 条「[打字不发] 字幕」的技巧说明短句（每条 ≤14 字，如「以退为进」「故意否定 引起注意」），这是打在键盘上给观众看的教学卖点。

只输出大纲正文，不要解释、不要 markdown 围栏。"""


def _gen_user_message(brief: str, category: str, ref_titles: list, outline: str = "") -> str:
    """构造首次生成时的 user 消息；带「已确认大纲」时强制按大纲展开。"""
    desc = str(brief or "").strip()
    cat = f"（人物类别：{category}）" if category in CATEGORIES else ""
    refs = f"参考剧本：{ '、'.join(ref_titles) }" if ref_titles else "无参考剧本"
    body = f"创作主题：{desc}\n{cat}\n{refs}\n\n"
    outline = str(outline or "").strip()
    if outline:
        body += ("【剧情大纲 —— 用户已确认，必须严格遵循】\n"
                 "人物、剧情节点、转折、收尾不得偏离大纲；【画面运用规划】要逐条落实成真实步骤；"
                 "【技巧点】要全部用进 [打字不发] 的正文。\n"
                 "===== 剧情大纲 开始 =====\n" + outline + "\n===== 剧情大纲 结束 =====\n\n")
    body += "请按【输出格式】直接产出 JSON（history + steps），不要写 [指令] 文本、不要任何解释。"
    return body


def _critique_user_message(current_text: str) -> str:
    """构造纠错轮次的 user 消息：把上一版剧本**带行号**交给模型，便于它精确引用。"""
    body = (current_text or "").strip()
    if not body:
        return ("请针对上面的问题，按【输出格式】给出一组 patches（find/with）来修复，"
                "不要输出整篇剧本。")
    return ("《当前剧本》如下（左侧是行号，只用来帮你定位，不要写进 find/with）：\n\n"
            "===== 当前剧本 开始 =====\n" + script_format_mod.number_lines(body) +
            "\n===== 当前剧本 结束 =====\n\n"
            "请针对上面的问题，输出 patches（要改的那几行）与 append_steps（要补的内容）。"
            "不要重写整篇。")


# ============================================================
# 评价 -> 候选规则（「越写越好」飞轮的沉淀入口）
# ------------------------------------------------------------
# ⚠️ 这组函数曾随旧版被整体裁掉，导致 editor_server 的评价接口调用
# extract_skill_candidates / save_skill_candidates 时 AttributeError 被
# try/except 吞掉 —— 用户写了评价、规则库却永远收不到新规则（静默失效）。
# 现从 _bak2_script_generator.py 恢复，并把新增的数值类 kind 补进
# _normalize_candidate 的数值分支（否则会被误降级成 style）。
# ============================================================

_CANDIDATE_SYSTEM = """你是「微信聊天剧本创作规则抽取器」。
用户对刚生成的一版剧本打了分并写了留言。请把留言里的要求拆成若干条**可执行、可校验**的规则。
只输出 JSON，格式：{"skills":[{"type":"rule","title":"...","kind":"...","value":...,"prompt_hint":"..."}]}

kind 只能取以下之一（value 必须与 kind 匹配）：
- banned_action：禁用某个动作，value 写动作名，如 "转账"、"发送语音"
- required_action：必须包含某个动作，value 写动作名，如 "打字不发"
- min_sessions：最少会话数，value 写整数
- min_history_messages：历史会话消息最少条数，value 写整数
- min_realtime_lines：实时对白最少条数，value 写整数
- max_message_chars：单条消息最大字数，value 写整数
- forbid_text：消息正文禁止出现的词，value 写词，如 "语音"
- forbid_annotation_as_message：禁止把心理活动/解说当成消息发出，value 写 true
- opening_image：开头必须有表情包或图片做钩子，value 写 true
- max_people：出场人物上限，value 写整数
- max_annotations：仅用于兜底「`[我方打字]` 里写了策略注释」这个硬伤，value 写整数
  （注意：`[打字不发]` 的正文现在就是给观众看的技巧说明，不再限制处数，不要为它建规则）
- history_two_sided：历史会话整体要有双方对话（整块里至少 1 个会话是我和对方来回），value 写 true
  （用户说"历史会话只有她一个人在说""我一句都没回"就填这条；注意：用户并不要求每个会话都一问一答）
- max_history_streak：历史会话里同一个人最多连续发几条，value 写整数
- max_history_two_sided：历史会话里最多几个会话带「我：」的回复，value 写整数
  （用户说"每个会话都有我回的""不像微信列表预览"就填这条，一般填 2）
  （用户说"她一个人刷屏""连着发一大堆"就填 2 或 3）
- min_interjections：至少几处「插话」，value 写整数
  （用户说"插话没用起来""要多用插话""边打字边被打断"就填 10~15）
- min_typing_hold：整份剧本至少几处「打字不发」，value 写整数
  （用户说"打字不发太少""多来点打字不发"就填 10~15）
- max_script_steps：整份剧本的实时指令步数上限，value 写整数
  （用户说"太长了""别 300 多步""控制在 200 步左右"就填 200）
- asset_ref_plain：图片/表情引用只能写图库里的短名，禁止文件路径/扩展名/时间戳/来源后缀，value 写 true
  （用户说"剧本里怎么出现文件名了""配图写的是路径""图片名太长太丑"就填这条）
- asset_ref_exists：图片/表情引用必须能在图片库里找到真实文件，value 写 true
  （用户说"图显示不出来""破图""表情全变成同一张""表情包找不到"就填这条）
- max_same_emoji：同一个表情最多重复几次，value 写整数（一般 2）
  （用户说"表情老是重复""同一个表情发了好几次"就填这条）
- max_wait_ratio：被 [等待] 紧跟着的我方消息占比上限，value 写小数（一般 0.6）
  （用户说"节奏很机械""每条后面都跟一个等待""像节拍器"就填这条）
- min_burst：实时对白里至少有一方连发几条，value 写整数（一般 2 或 3）
  （用户说"太像一问一答了""没有连发""像朗读稿"就填这条）
- max_emoji_total：整份剧本发出的表情（贴纸+3D emoji）总数上限，value 写整数
  （用户说"表情太多了""别一直发表情"就填这条）
- max_time_marks：时间分隔条（`内容 | 18:22`）处数上限，value 写整数
  （用户说"不要每条消息都挂时间"就填这条）

要求：
- 一条留言尽量拆成 1~6 条独立规则；留言里有具体数值就填进 value。
- title 用简短中文；prompt_hint 写成给大模型的命令句，如「会话数不少于 9 个」。
- 只是主观感受（如「不够精彩」）时，type 用 "style"，不带 kind/value。
- 不要输出解释、不要 markdown 围栏。"""


def _rule_skill_candidates(text: str) -> list:
    """无大模型时的兜底抽取：覆盖最常见的几类明确要求。"""
    out = []

    def add(kind, value, title, hint):
        out.append({"type": "rule", "title": title, "kind": kind, "value": value, "prompt_hint": hint})

    if re.search(r"(不涉及|不要|没有|别).{0,4}转账", text):
        add("banned_action", "转账", "禁用转账", "不要出现转账相关动作")
    if re.search(r"(不涉及|不要|没有|不使用).{0,4}语音", text) or "语音功能" in text:
        add("banned_action", "发送语音", "禁用语音消息", "不要使用语音消息")
    m = re.search(r"会话.{0,6}?(\d+)\s*(?:个|条)", text)
    if m:
        add("min_sessions", int(m.group(1)), "会话数下限", "会话数不少于 %s 个" % m.group(1))
    m = re.search(r"历史会话.{0,8}?(\d+)\s*条", text)
    if m:
        add("min_history_messages", int(m.group(1)), "历史消息下限", "历史会话消息不少于 %s 条" % m.group(1))
    if re.search(r"(太长|话.{0,2}长|短一点|简短|短小)", text):
        add("max_message_chars", 15, "单条消息字数上限", "我方每条消息不超过 15 个字")
    if re.search(r"开头.{0,6}图片", text):
        add("opening_image", True, "开头要有图片", "剧本开头必须插入一张图片")
    if re.search(r"(两个女生|三人|3\s*人|三个人)", text):
        add("max_people", 3, "出场人物上限", "出场人物不超过 3 人")
    if "打字不发" in text:
        add("required_action", "打字不发", "必须使用打字不发", "必须使用 [打字不发] 制造博弈节奏")
    if re.search(r"(心理活动|解说|注释).{0,12}(不要|别|不当成|别当成|禁止)", text) or \
       re.search(r"(不要|别|禁止).{0,12}(心理活动|解说|注释)", text):
        add("forbid_annotation_as_message", True, "禁止心理活动外发",
            "不要把心理活动/解说当成消息正文，正文必须是真实聊天话术")
    if re.search(r"(心理活动|解说|注释|博弈).{0,14}(一两句|少|太多|多)", text) or \
       re.search(r"(一两句|少一点|别太多).{0,14}(心理活动|解说|注释)", text):
        add("max_annotations", 2, "别把心理活动当消息发",
            "心理活动/解说只允许写在 [打字不发] 的技巧说明里，"
            "绝不能写进 [我方打字] 当成消息发出去")
    if re.search(r"(诱惑|擦边|吸引)", text):
        out.append({"type": "style", "title": "内容要有诱惑性",
                    "prompt_hint": "会话内容要有诱惑性、适度擦边，可参考用户提供的案例尺度"})
    if "铺满" in text:
        add("min_history_messages", 20, "历史会话铺满",
            "历史会话消息不少于 20 条，把过往聊天记录铺满屏幕")
    # 插话：能读出次数就变成可校验规则，读不出也至少要求 5 处
    if "插话" in text:
        m = (re.search(r"插话.{0,10}?(\d+)\s*(?:次|处|条)", text)
             or re.search(r"(\d+)\s*(?:次|处|条).{0,10}?插话", text)
             or re.search(r"至少.{0,6}?(\d+).{0,8}?插话", text))
        if m:
            add("min_interjections", int(m.group(1)), "插话次数下限",
                "至少 %s 处用「插话」写法：`[打字不发] 技巧说明 | 停留 | 对方插话一句`，"
                "插话只能是对方真发出来、回应我已发出消息的一句口语" % m.group(1))
        else:
            add("min_interjections", 5, "至少 5 处插话",
                "至少 5 处用「插话」写法：`[打字不发] 技巧说明 | 0.5 | 对方插话一句`")
    # 篇幅上限：用户嫌太长 / 报出步数时变成可校验规则
    ms = re.findall(r"(\d+)\s*多?\s*步", text)
    if ms:
        # 「别 300 多步，控制在 200 步左右」：取较小的那个，通常才是要控制到的目标值
        val = min(int(x) for x in ms)
        add("max_script_steps", val, "实时指令步数上限",
            "整份剧本的实时指令控制在 %d 步以内" % val)
    elif re.search(r"(太长|过长|篇幅|拉长|别.{0,4}那么长)", text):
        add("max_script_steps", 200, "实时指令步数上限",
            "整份剧本的实时指令控制在 200 步以内")
    # 历史会话时间戳别机械地每分钟一条（内置校验，这里只留风格提示）
    if re.search(r"(时间戳|时间标注|时间)", text) and \
       re.search(r"(一分钟|1\s*分钟|机械|整齐|一样|每分)", text):
        out.append({"type": "style", "title": "历史会话时间标注要克制",
                    "prompt_hint": "同一会话内只有首条和末条消息带「| 时间」标注"
                                   "（微信里间隔不足 5 分钟不会显示第二个时间条），"
                                   "中间消息不带时间；首末间隔至少 5 分钟且错落"})
    # 打字不发写什么（用户说「打字不发是给观众看的/要写技巧/别写心理活动」时命中）
    if "打字不发" in text and re.search(r"(技巧|观众|为什么|心理|草稿|话术)", text):
        out.append({"type": "style", "title": "[打字不发] 写技巧说明",
                    "prompt_hint": "[打字不发] 的正文是给观众看的一句话技巧说明"
                                   "（「为什么这样聊有效」，如「以退为进」「故意否定 引起注意」），"
                                   "不是聊天话术草稿，也不是对方的心理活动"})
    # 打字不发：读得出次数就变成可校验的数量下限
    if "打字不发" in text:
        m = (re.search(r"打字不发.{0,12}?(\d+)\s*(?:次|处|条)", text)
             or re.search(r"(\d+)\s*(?:次|处|条).{0,12}?打字不发", text))
        if m:
            add("min_typing_hold", int(m.group(1)), "打字不发次数下限",
                "整份剧本至少 %s 处 [打字不发]：正文写「给观众看的技巧说明」，"
                "不是聊天话术草稿" % m.group(1))
        elif re.search(r"(少|不够|多(用|来|加)|增加|加强)", text):
            add("min_typing_hold", 5, "至少 5 处打字不发",
                "整份剧本至少 5 处 [打字不发]：正文写「给观众看的技巧说明」")
    # 历史会话整体要有双方对话（用户吐槽「只有她一个人在说」时最容易命中）
    if (re.search(r"历史.{0,24}(双方|有来有回|来回|互相|对话|我(也|要)?回|"
                  r"一个人|单方面|刷屏)", text)
            or re.search(r"(单方面|一个人|只有她|只有他|刷屏).{0,24}历史", text)):
        add("history_two_sided", True, "历史会话整体要有双方对话",
            "整个历史会话块至少要有 1 个会话是「对方说 → 我回 → 对方再说」，"
            "其余会话可以只留对方最后一两句")
    if re.search(r"(刷屏|连发|连着发|连续发)", text):
        add("max_history_streak", 2, "历史会话同一人最多连续 2 条",
            "历史会话里同一个人最多连续发 2 条，超过必须由另一方接话或换会话")
    # 历史会话别每个都写我的回复（用户要「像微信列表预览」时命中）
    if (re.search(r"(每个会话|逐个会话).{0,8}(都|全).{0,6}(我|回)", text)
            or re.search(r"(一问一答|列表预览|只留对方|像微信列表)", text)):
        add("max_history_two_sided", 2, "历史会话最多 2 个带我的回复",
            "历史会话里最多 2 个会话带「我：」的回复，其余只留对方最后 1~2 条，像微信列表预览")
    # 历史会话内容要有钩子（用户嫌「没信息量/废话」时命中）
    if re.search(r"(没信息量|没意思|废话|太水|干巴巴|钩子|悬念|想点开)", text):
        out.append({"type": "style", "title": "历史会话每条都要有钩子",
                    "prompt_hint": "历史会话每条消息都要具体、有信息量、带悬念/暧昧/八卦，"
                                   "禁止「在吗」「吃了吗」「哈哈」「晚安」这类废话"})
    return out


def extract_skill_candidates(comment, brief="", category="", api_key="",
                             model=None, base_url=None) -> list:
    """把一条评价留言拆成候选规则（不直接入库，交前端确认后保存）。"""
    text = str(comment or "").strip()
    if not text:
        return []
    fallback = _rule_skill_candidates(text)
    if not api_key or str(api_key).upper().startswith("REPLACE"):
        return [_normalize_candidate(c) for c in fallback]
    try:
        user = ("创作主题：%s\n人物类别：%s\n用户评价：%s"
                % (brief or "（未填）", category or "不限", text))
        raw = st.call_deepseek(api_key, _CANDIDATE_SYSTEM, user,
                               model or st.DEFAULT_MODEL, base_url or st.DEFAULT_BASE_URL,
                               timeout=120, max_tokens=2000, json_mode=True)
        data = json.loads(strip_code_fences(raw or "") or "{}")
        items = data.get("skills") if isinstance(data, dict) else None
        out = []
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind") or "").strip()
            if kind and kind not in store.RULE_KINDS:
                kind = ""
            title = str(it.get("title") or "").strip()[:40]
            hint = str(it.get("prompt_hint") or title or "").strip()[:200]
            if not title and not hint:
                continue
            out.append(_normalize_candidate({
                "type": "rule" if kind else "style",
                "title": title or hint[:20],
                "kind": kind or None,
                "value": it.get("value"),
                "prompt_hint": hint,
            }))
        return [_normalize_candidate(c) for c in (out or fallback)]
    except Exception:  # noqa: BLE001
        return [_normalize_candidate(c) for c in fallback]


def save_skill_candidates(candidates, source_feedback=None, enabled=True, source_note=""):
    """把用户确认过的候选规则写入规则库，返回入库后的条目列表。"""
    saved = []
    for c in candidates or []:
        if not isinstance(c, dict):
            continue
        c = _normalize_candidate(c)
        kind = c.get("kind") or None
        if kind and kind not in store.RULE_KINDS:
            kind = None
        saved.append(store.add_skill(
            title=str(c.get("title") or c.get("prompt_hint") or "").strip(),
            kind=kind,
            value=c.get("value"),
            skill_type=str(c.get("type") or ("rule" if kind else "style")),
            prompt_hint=str(c.get("prompt_hint") or "").strip(),
            enabled=enabled,
            source_feedback=source_feedback,
            source_note=source_note,
        ))
    return saved


# ============================================================
# 分阶段装配生成（P2，2026-09-17）
# ------------------------------------------------------------
# 旧链路（一次性生成整篇 200 步 JSON）的三大病根：剧情平、跨会话矛盾、
# patch「改好一处弄坏两处」。新链路把「编剧情」和「写对白」拆开：
#   阶段1  Beat Sheet：模型只出【会话轮换表】JSON（历史块 + 会话清单 +
#          每会话的桥段/节拍 + 后台消息清单）——本地可校验、可打回重出；
#   阶段2  骨架装配：纯代码——历史块渲染、[返回主页] 配对、后台消息
#          插入位置、时间条分配，全部本地算，模型不再管簿记；
#   阶段3  逐会话填充：每次调用只写一个会话块（25~70 步），携带前块
#          尾部上下文 + 金样桥段示范；块级失败只重写该块；
#   阶段4  全文校验 + 既有 critique patch + 审稿员（原样复用）。
# 旧链路保留：payload.pipeline="legacy" 可强制走回一次性生成。
# ============================================================

BRIDGE_LIBRARY = (
    ("可歪递进开场", "她抛语义双关（帮/来/陪我，宾语空着）→≥3拍递进→我方只追问不点破→落点极日常"),
    ("整蛊冷读开场", "她一句离谱炸弹→我方不接盘，冷读拆解→顺着她的剧本反问→揭底后轻打一下"),
    ("转账废物测试化解", "坦然收下并重新定义→废物测试→把行为升华成仪式感→反手给她奖励"),
    ("分手挽回·以退为进", "不哄反退→占据高地（怪以前爱太满）→把「谁变了」反打回去→她先慌"),
    ("学员实战陪聊", "学员不会开口→逐句遥控→打回无联系回复→教「话题要有两人联系」→画面感收网"),
    ("睡前故事互动钩子", "她睡不着→用故事接住→停在包袱前切走留悬念→回来揭晓→她主动要求再讲"),
    ("深夜暧昧递进邀约", "先暧昧拉扯→她笑骂→突然转真诚→顺势给邀约理由→立刻落实时间地点"),
    ("粉丝线公开课引流", "粉丝带截图求助→一句病因→发公开课卡→「先看这两篇」→CTA"),
    ("收拾索取型", "她狮子大开口→不撕破脸，用错位回复消解节奏→她急了我方更稳"),
    ("表白后化解推进", "共情降防备→故意曲解→举例打消顾虑→「时间给我们答案」→推进见面"),
    ("跳过中间商直邀", "绕过传话人直接聊目标→贴脸开大试探→自曝身份→画面感描述→收网"),
)

BEATSHEET_SPEC = """【Beat Sheet 输出格式 —— 只输出一个 JSON 对象，不要解释、不要 markdown 围栏】
{
  "title": "剧本标题",
  "history": [
    {"contact": "生活化昵称", "messages": [{"who": "peer", "text": "最后一条钩子消息 | 20:12"}]}
  ],
  "sessions": [
    {"person": "人物库名字", "kind": "main", "bridge": "桥段名（从桥段库选）", "start_time": "21:05",
     "beats": ["节拍1：她抛双关，宾语空着", "节拍2：我方只追问，失守字幕1处", "节拍3：落点极日常"],
     "tail": "本会话结束时的状态（一句话）"}
  ],
  "background": [
    {"from": "人物库名字", "during": "填写其消息送达时正打开的会话人物名", "text": "消息内容", "time": "21:45"}
  ],
  "cta": true
}
- history：9~10 个会话垫满列表；**展开会话（sessions 里出现的人物）的历史必须 6~8 条、有来有回**，
  最后一条是钩子单句（别想歪式留白），因为打开聊天后会渲染该会话全部历史消息；
  未展开的路人会话只写 1 条对方钩子消息，**且必须是「一句半截话、留想象空间」的暧昧钩子**
  （用户定标：列表页要有故事感）——「半夜睡不着」「一个人在家 有点冷」「刚洗完澡 头发还湿着」
  「我那里不舒服」「加班到腿软」；★点到为止、不给结果、**不要把话说完**、更不许加「别想歪 是XX」式解释
  （「半夜睡不着 你来陪我聊会儿」只取前半句）；
  整块最多 1 个会话带 who="me"；时间从新到旧排；
  主线人物排在最前面；可穿插 1 条 [图片] 短名 或 [链接] 标题 | 封面 ——
  ★它是**某条已有会话的最后一条消息**（我方发的，写成 `我：[链接] 标题 | 封面` 或 `我：[图片] 短名`），
  **不要为图片/链接单独开一个会话**：history 每一项的"人"必须是真人名，
  实测模型会建成 `[会话] [链接] xx` 这种怪会话，机械门直接报「格式无法识别」丢掉整段。
  ★合规红线：擦边只做钩子不做内容，露骨描写、性行为细节一律禁止。
- sessions：2~4 个会话按轮换顺序；kind 只有 "main"（女主线）与 "fan"（粉丝/学员线）；
  main 会话 beats 必须含「可歪/冷读/反差」类开场节拍、「极日常落点」、以及 1 个中后段升级节拍
  （她试探→我方反将／模糊叙述吊住／反推拉／终局反转，至少其一——对应「全程引擎」，防止退化成纯关心）；
  fan 会话用「粉丝线公开课引流」桥段、
  beats 必含 CTA（想要聊天秘籍的兄弟 点赞关注扣 6 我安排）；
  bridge 只能从桥段库选：「可歪递进开场」「整蛊冷读开场」「转账废物测试化解」「分手挽回·以退为进」
  「学员实战陪聊」「睡前故事互动钩子」「深夜暧昧递进邀约」「粉丝线公开课引流」「收拾索取型」
  「表白后化解推进」「跳过中间商直邀」。
- start_time：每个会话开场的时间（HH:MM），整条时间线必须递增且晚于 history 最新时间；
  background 的 time 晚于 during 会话的 start_time、早于下一个会话的 start_time。
- background：1~4 条；from 必须是本剧本其他会话的人物；during 必须是某个会话的 person；
  粉丝 CTA 前后才各允许 1 条主线钩子后台消息用来引回主线。
- cta：true 时最后一个 fan 会话必须以 CTA + 「下课 遇到不会聊的女生就来找我吧」收尾。"""


def build_beatsheet_prompt(brief: str, category: str = "", people_block: str = "",
                           ref_summaries: str = "", skills=None) -> str:
    """P2·阶段1：只出会话轮换表（Beat Sheet），不出剧本。"""
    cat_note = ""
    if category in CATEGORIES:
        cat_note = (f"\n- 人物一律从【人物库】挑「{category}」类别的真名，主线对象优先挑没用过的。")
    nums = rule_numbers(skills)
    return f"""你是「微信聊天教学视频」的剧情策划。根据创作主题设计一份【会话轮换表】（Beat Sheet），只做结构设计，**不写任何聊天对白正文**（beats/tail 里只写结构性描述，一句话即可）。

{people_block}{cat_note}

【主题】{brief}

【金样结构摘要 —— 结构就学它们】
{ref_summaries or "（无）"}

【桥段库 —— 每个会话必须绑定一个桥段】
""" + "\n".join(f"- {name}：{desc}" for name, desc in BRIDGE_LIBRARY) + f"""

{BEATSHEET_SPEC}

【硬性要求】
1. 历史块 {nums.get('min_history_sessions', 9)}~10 个会话；展开的 main 会话 1~2 个、fan 会话 1 个；全部 person 来自人物库且互不重复（历史块人物除外）。
   展开会话（sessions 里的人物）在 history 里必须有 6~8 条有来有回的历史消息（最后一条=钩子）；路人会话 1 条即可。
2. 每个会话的 beats 3~6 条；beats 是导演视角的节拍描述（如「她抛双关：想请你帮个忙」），不是台词。
3. 桥段分配要服务主题；两个 main 会话不能用同一个桥段。
4. fan 会话放最后一个，前面穿插主线后台钩子把它自然引出（例：主线聊到一半粉丝求助截图到达）。
"""


def repair_beatsheet(sheet):
    """Beat Sheet 的确定性修补（格式类问题由代码补，不让模型重抽）。

    ★2026-09-18 实测：模型常漏填 `background[].time`，校验器判「后台消息缺 time（HH:MM）」，
    白烧两次调用（约 77 秒）才抽到一版完整的。时间是**可以推出来的**：
    取该条 `during` 会话的 start_time + 5 分钟，并按下一个会话的 start_time 收敛。
    """
    if not isinstance(sheet, dict):
        return sheet
    sessions = [s for s in (sheet.get("sessions") or []) if isinstance(s, dict)]
    starts = [str(s.get("start_time") or "").strip() for s in sessions]

    def _hhmm(x):
        try:
            h, m = str(x).strip().split(":")
            return int(h) * 60 + int(m)
        except Exception:  # noqa: BLE001
            return None

    def _fmt(v):
        v = int(v) % (24 * 60)
        return "%02d:%02d" % (v // 60, v % 60)

    bg = sheet.get("background")
    if not isinstance(bg, list):
        return sheet
    filled = 0
    for item in bg:
        if not isinstance(item, dict) or _hhmm(item.get("time")) is not None:
            continue
        during = str(item.get("during") or "").strip()
        base = None
        for i, s in enumerate(sessions):
            if str(s.get("person") or "").strip() == during:
                v = _hhmm(starts[i])
                if v is not None:
                    base = v + 5
                    # 收敛：不能晚于下一个会话的开场
                    if i + 1 < len(sessions):
                        nxt = _hhmm(starts[i + 1])
                        if nxt is not None and base >= nxt:
                            base = max(v, nxt - 1)
                break
        if base is None:
            vs = [v for v in (_hhmm(x) for x in starts) if v is not None]
            base = (max(vs) + 5) if vs else 21 * 60 + 45
        item["time"] = _fmt(base)
        filled += 1
    if filled:
        sheet["_bg_time_filled"] = filled
    return sheet


def validate_beatsheet(sheet, people_names=None, skills=None) -> list:
    """P2·阶段1 本地校验：结构合法性 + 时间线粗校验。返回问题清单（空=通过）。"""
    issues = []
    if not isinstance(sheet, dict):
        return ["Beat Sheet 不是 JSON 对象"]
    history = sheet.get("history") or []
    if not isinstance(history, list) or len(history) < 8:
        issues.append(f"历史块会话数 {len(history)} < 8（要求 9~10 个垫满列表）")
    sessions = sheet.get("sessions") or []
    if not isinstance(sessions, list) or not (1 <= len(sessions) <= 4):
        issues.append(f"展开会话数 {len(sessions)} 不在 2~4 范围")
    names = [str(s.get("person") or "").strip() for s in sessions if isinstance(s, dict)]
    if len(names) != len(set(names)):
        issues.append("展开会话人物重复")
    mains = [s for s in sessions if isinstance(s, dict) and s.get("kind") == "main"]
    fans = [s for s in sessions if isinstance(s, dict) and s.get("kind") == "fan"]
    if not mains:
        issues.append("缺少 main 主线会话")
    if not fans:
        issues.append("缺少 fan 粉丝/学员会话（CTA 载体）")
    bridges = [str(s.get("bridge") or "").strip() for s in sessions if isinstance(s, dict)]
    valid_bridges = {n for n, _ in BRIDGE_LIBRARY}
    for b in bridges:
        if b and b not in valid_bridges:
            issues.append(f"桥段「{b}」不在桥段库里")
    main_bridges = [str(s.get("bridge") or "") for s in mains]
    if len(main_bridges) != len(set(main_bridges)):
        issues.append("两个 main 会话用了同一个桥段")
    for i, s in enumerate(sessions):
        if not isinstance(s, dict):
            continue
        beats = s.get("beats") or []
        if not isinstance(beats, list) or not (3 <= len(beats) <= 6):
            issues.append(f"会话「{s.get('person')}」beats 数 {len(beats)} 不在 3~6")
    # 时间线粗校验：history 最新时间 < 会话 start_time 递增 < background 归属
    def _hhmm(x):
        try:
            h, m = str(x).strip().split(":")
            return int(h) * 60 + int(m)
        except Exception:  # noqa: BLE001
            return None
    hist_times = []
    session_persons = {str(s.get("person") or "").strip() for s in sessions if isinstance(s, dict)}
    sess_msg_count = {}
    for sess in history:
        if not isinstance(sess, dict):
            continue
        contact = str(sess.get("contact") or "").strip()
        msgs = sess.get("messages") or []
        if contact in session_persons:
            sess_msg_count[contact] = len(msgs)
        for m in msgs:
            if isinstance(m, dict):
                t = str(m.get("text") or "")
                import re as _re
                mm = _re.search(r"\|\s*(\d{1,2}:\d{2})\s*$", t)
                if mm:
                    v = _hhmm(mm.group(1))
                    if v is not None:
                        hist_times.append(v)
    start_vals = []
    for s in sessions:
        if isinstance(s, dict):
            v = _hhmm(s.get("start_time") or "")
            if v is None:
                issues.append(f"会话「{s.get('person')}」缺 start_time 或格式不是 HH:MM")
            else:
                start_vals.append(v)
    if hist_times and start_vals and max(hist_times) >= min(start_vals):
        issues.append("会话 start_time 必须晚于历史块里所有时间")
    # 展开会话的历史必须 ≥6 条（打开聊天会渲染该会话全部历史；机械门硬卡 ≥6）
    # ★2026-09-18 修：这里原来写 3~6 条，与机械门「<6 判提示/不通过」口径不一致 ——
    # 校验放行 4~5 条，最后会在门禁那里挂掉，白跑一整轮。
    for p in session_persons:
        if sess_msg_count.get(p, 0) < 6:
            issues.append(f"展开会话「{p}」在历史块里只有 {sess_msg_count.get(p, 0)} 条消息，"
                          "必须 6~8 条有来有回（打开后会渲染全部历史）")
    for a, b in zip(start_vals, start_vals[1:]):
        if a >= b:
            issues.append("会话 start_time 没有递增")
            break
    bg = sheet.get("background") or []
    persons = set(names)
    for item in bg if isinstance(bg, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("from") or "").strip() not in persons | {str(h.get("contact") or "").strip() for h in history if isinstance(h, dict)}:
            issues.append(f"后台消息 from「{item.get('from')}」不是本剧本人物")
        if str(item.get("during") or "").strip() not in persons:
            issues.append(f"后台消息 during「{item.get('during')}」不是展开会话人物")
        v = _hhmm(item.get("time") or "")
        if v is None:
            issues.append("后台消息缺 time（HH:MM）")
    return issues


def assemble_skeleton(sheet) -> dict:
    """P2·阶段2：纯代码装配骨架。

    返回 {"history_text":…, "blocks":[{person, kind, bridge, beats, start_time,
            "prefix_lines":[…], "suffix_lines":[…], "bg_lines":[…]}],
          "ending_lines":[…], "text":…}
    text = 历史块 + 每块 prefix（占位注释，最终被块内容替换）+ 结尾，仅供 debug。
    """
    import script_format as sf_mod
    history_text = "\n".join(sf_mod.render_history(sheet.get("history") or []))
    sessions = [s for s in (sheet.get("sessions") or []) if isinstance(s, dict)]
    bg = [b for b in (sheet.get("background") or []) if isinstance(b, dict)]

    def _bg_lines(person):
        lines = []
        for item in bg:
            if str(item.get("during") or "").strip() == person:
                lines.append("[对方后台发消息] %s | %s | %s" % (
                    str(item.get("from") or "").strip(),
                    str(item.get("text") or "").strip(),
                    str(item.get("time") or "").strip()))
        return _annotate_bg_lines(lines)

    blocks = []
    for i, s in enumerate(sessions):
        person = str(s.get("person") or "").strip()
        prefix = [] if i == 0 else []   # 返回主页统一由上一块的 suffix 负责，避免重复
        prefix.append(f"[打开聊天] {person}")
        blocks.append({
            "person": person,
            "kind": str(s.get("kind") or "main").strip(),
            "bridge": str(s.get("bridge") or "").strip(),
            "beats": [str(b) for b in (s.get("beats") or [])],
            "tail": str(s.get("tail") or "").strip(),
            "start_time": str(s.get("start_time") or "").strip(),
            "prefix_lines": prefix,
            "bg_lines": _bg_lines(person),
            "suffix_lines": (["[返回主页] 0.3"] if i < len(sessions) - 1 else []),
        })
    ending = ["[等待] 1.0"]
    return {"history_text": history_text, "blocks": blocks,
            "ending_lines": ending,
            "text": history_text + "\n" + "\n".join(
                ln for b in blocks for ln in (b["prefix_lines"] + ["<会话块填充位·%s>" % b["person"]] + b["bg_lines"] + b["suffix_lines"]))
            + "\n" + "\n".join(ending)}


def _find_bridge_snippet(bridge: str) -> str:
    """从参考库找与桥段对应的 snippet 示范（找不到返回空串）。

    匹配规则：桥段名前 6 字出现在 snippet 标题里即视为同一桥段
    （snippet 标题常带括号补充说明，如「深夜暧昧递进→真诚一击邀约（情绪过山车收网）」）。
    """
    try:
        key = (bridge or "").replace("·", "")[:6]
        if not key:
            return ""
        for r in store.list_references():
            if (r.get("kind") or "") != "snippet":
                continue
            title = str(r.get("title") or "").replace("·", "")
            if key in title:
                return str(r.get("text") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _block_rules_text(skills=None, block_start_time: str = "块首时间") -> str:
    """P2·阶段3 块级生成用的精简规则（不搬全量 18k 系统提示）。"""
    nums = rule_numbers(skills)
    return f"""【本块对白规则】
1. 你写的 steps 里禁止出现 [打开聊天]/[返回主页]/[对方后台发消息]/[历史会话]——切换与簿记由系统负责。
2. [打字不发] 至少 {max(4, nums['min_typing_hold'] // 2)} 处，紧跟 [删除文字] -1；字幕两型：打法型（「以退为进」）+ 主线会话至少 1 处失守型（「？？？」「完了 别多想」「这谁敢答应」）；fan 会话一律打法型。字幕绝不是聊天话术草稿，也绝不是对方心理活动；随后 [我方打字] 必须与字幕不同。
3. 插话（打字不发第 3 段 / 我方打字第 2 段）必须是对方台词（加「她说」要通顺），只回应已发出的上一条；插话过的话不要再写 [对方发消息] 重复。
4. 对方相邻连发两条消息之间必须插 [等待] 0.2；我方连发不加等待。全块不要写成严格一问一答，要有一方连发 2~3 条。
4b. [打字不发] 停留只用标尺值：0.3 / 0.5 / 1.0 / 1.5（常规带插话 0.5；长字幕/博弈窗口 1.0~1.5），禁止 0.8 这类标尺外数值；每条字幕内容都不许重复。
5. 本块首条对方的实时消息（[对方发消息]/[对方发图片]）内容末尾加「 | {block_start_time}」时间条（把上面给的块首时间原样抄进去）；本块其余消息一律不带时间条。
6. 表情/贴纸逐字用【可用素材】短名，同一表情全块 ≤2 次；3D emoji 用内嵌写法（太开心了[大笑]）。图片少而精：全块至多 1 张、写具体画面描述。
7. 主线（main）会话禁止出现 博主/学员/教学/关注/秘籍/点赞关注 等引流词；fan 会话允许。
8. 台词口语化、说人话；禁止 省略/待补充/xxx 等占位；禁止把方法论写进台词。
9. 全程引擎（main 会话必守，0916 定调）：可歪/冷读开场只是入场券，本块中后段**不许退化成纯关心/伺候/查户口式询问**——至少 1 次「她试探→我方反将」（不接盘不解释，把问题打回去，如「没别的女生半夜敢烦我 你是独一份的麻烦」）或「模糊叙述吊住」（上来坐坐/就我一个人，留白让观众想歪）；收尾前安排 1 个反推拉或反转点（进一步后撤：站楼下不上楼／终局反转：回头看整局是她安排的），落点仍极日常。fan 会话不适用此条。"""


def build_block_prompt(block: dict, tail_context: str = "", people_block: str = "",
                       actions=None, skills=None) -> str:
    """P2·阶段3：单个会话块的生成 prompt。只输出 {"steps":[…]}。"""
    kind_note = ("这是主线女主会话：写可歪/智斗/暧昧拉扯，落点极日常，至少 1 处失守型字幕。"
                 "中后段守「全程引擎」——她试探我方反将、模糊叙述吊住、反推拉/终局反转，不许退化成纯关心伺候。"
                 if block.get("kind") == "main" else
                 "这是粉丝/学员会话：教学感，含公开课/发图帮助，字幕一律打法型，beats 里有 CTA 就按 CTA 写。")
    demo = _find_bridge_snippet(block.get("bridge") or "")
    demo_block = ""
    if demo:
        demo_block = ("\n【桥段示范 —— 本块按这个示范的写法和密度来】\n" + demo + "\n")
    beats = "\n".join(f"  {i+1}. {b}" for i, b in enumerate(block.get("beats") or []))
    nums = rule_numbers(skills)
    return f"""你是「微信聊天教学视频」的剧本写手。系统已经把结构骨架搭好，你只负责写【一个会话块】的对白步骤。

【人物库】
{people_block or "（用常见中文名）"}

【本块信息】
- 人物：{block.get('person')}（{block.get('kind')}）
- 桥段：{block.get('bridge')}
- 块首时间：{block.get('start_time')}
- 节拍（按顺序全部演出，不许跳）：
{beats}
- 结束状态：{block.get('tail') or '自然收束'}
{kind_note}
【前文尾部（上一块最后几步，衔接要自然，不许复读）】
{tail_context or "（这是第一块，直接开场）"}
{demo_block}
【动作表】（只能用这些 action；禁止 打开聊天/返回主页/对方后台发消息/历史会话）
{_format_action_table_compact(actions)}

【可用素材】
{_asset_block()}

{_block_rules_text(skills, block.get("start_time") or "块首时间")}

【篇幅】本块 steps 控制在 25~70 条、实时对白 ≥ {nums['min_realtime_lines'] // 2} 条。

【输出格式 —— 只输出一个 JSON 对象】
{{"steps": [ {{"action": "我方打字", "params": {{"内容": "…"}}}}, … ]}}
不要写 history、不要写解释、不要 markdown 围栏。"""


# ------------------------------------------------------------
# P2.5 三层分工（2026-09-18）
#   戏层：AI 只写「谁说了什么」（build_dialogue_prompt）
#   壳层：纯代码卡 [打字不发] 位（weave_shells / render_shell_items）
#   字层：AI 只填字幕（build_subtitle_prompt）
#
# 动机：旧版把一个块的 12 件事（beats/两边台词/字幕两型/插话/等待/停留标尺/
#   时间条/素材短名/人设隔离/全程引擎/篇幅/JSON）塞进同一个提示词，模型的
#   注意力被格式规则吃掉 —— 实测表现为：字幕位置全错（79% 跟在她消息后）、
#   插话写成我方口吻、替她编台词。改成分层后：格式由代码保证（永不出错），
#   模型每次只做一件事。
# ------------------------------------------------------------

_ME_ACTION_SET = ("我方打字", "发送表情", "发送图片", "我方发链接", "发送emoji")
_PEER_ACTION_SET = ("对方发消息", "对方表情", "对方发图片", "对方emoji", "对方发链接", "对方转账")
_DIALOGUE_ACTIONS = ("我方打字", "发送表情", "发送图片", "发送emoji",
                     "对方发消息", "对方表情", "对方发图片", "对方emoji")


def _step_act(step) -> str:
    return _norm_action((step or {}).get("action")) if isinstance(step, dict) else ""


def _pick_even(seq, k):
    """从 seq 里等间隔取 k 个（首尾都取到，避免壳全挤在开头）。"""
    seq = list(seq)
    if k <= 0 or not seq:
        return []
    if k >= len(seq):
        return seq
    if k == 1:
        return [seq[0]]
    return [seq[int(i * (len(seq) - 1) / (k - 1))] for i in range(k)]


_DIALOGUE_CRAFT_RULES = """━━━ 让这段聊天好看（每块都要有，不是可选项）━━━
A. **图梗·错位暴击（最强笑点，每块 ≥1 处）**：先立预期 → 再砸一张完全对不上的沙雕图。
   结构四步：① 台词先立预期（不能凭空发图，如她说「喜欢高高瘦瘦的」）② 我方顺杆接（「正好认识一个特别符合的」）
   ③ 图错位（要美 → 路边三根又细又高的电线杆并排 竖屏实拍；要性感 → 奶龙穿JK校服裙）④ 她笑骂/拆台收尾
   （「你拿电线杆糊弄我」）。★第③步必须用 `发送图片` 动作真的把图发出去（图片描述自造，
   写法见写戏铁律 11）——只写台词不发图 = 她在回应一张不存在的图。梗图每块 1 张，别连发。
B. **土味金句（≥1 处）**：押韵对仗式的情话/比喻。金样：「撒网是姐姐的本事 入网是我的荣幸」
   「没抓住姐姐的心 就别说姐姐花心」。★要短，单条 ≤20 字，别写成诗朗诵。
C. **反差自嘲（全篇 ≥1 处，但全篇只许用一次）**：前面撩得飞起、突然装腼腆，等她拆台。
   示范任选一句、也可以换说法：「我平时不这样的 平常很腼腆」「换个人我早不接这话了」「我这人平时挺闷的」。
   ★实测踩坑：块0 与块1 都写「我平时不这样的 平常很腼腆」——观众一眼看出是同一个模板，第二个块必须换一句。
D. **网络热梗点缀（2~4 处，贴语境不硬塞）**：栓Q／纯爱战士／画大饼／破防／拿捏／上头／已老实／那咋了／显眼包／搭子。
E. **挑逗拉扯 ≥2 处**：正话反说（她发自拍问好看吗 →「我觉得不好看 毕竟衣服哪有人好看」）、
   抬杠式撩、曲解装傻。★落点必须锚在**她发的东西**上（照片→她本人/照片本身），
   严禁把结论落到我身上（「显得我不够帅」= 照片里根本没有我，逻辑断裂，校验器直接判问题）。
F. **她也要反撩 ≥2 次**（「怕了吗」「光吃饭看电影吗[脸红]」），不许只有我方输出、她只接招。
G. 全部梗共用一条禁忌：梗不能盖过教学主线，同一梗词全块 ≤2 次。"""


# 「本账号规则库」里的**格式类**条目关键词：这些由壳层/字层负责，戏层一个都不许写，
# 塞给它只会制造矛盾、并让推理模型逐条纠结（实测把单次调用从 45s 拖到 10min+ 卡死）。
_RULE_FMT_TOKENS = (
    "打字不发", "删除文字", "[等待]", "等待]", "停留", "步数", "时间条", "时间分隔",
    "时间节点", "插话", "表情总量", "同名表情", "不同表情", "实时对白", "实时指令",
    "会话数", "交替率", "等待占比", "[我方打字]", "[对方发消息]", "[发送",
    "[对方", "[点开图片]", "[打开", "[返回主页]", "[闪回", "[进入", "[历史会话]",
)


def content_only_rules(text: str) -> str:
    """把规则库文本过滤成「只留内容类要求」——喂给戏层的版本。

    为什么必须过滤（2026-09-18 实测）：整块 5.7k 字里绝大多数是**格式规定**
    （`[打字不发]`/`[等待]`/停留标尺/步数上限/插话写法），而戏层被明确要求
    「一个格式标记都不许写」。把这些一起塞进去有两个后果：
    ①模型要逐条判断「这条到底要不要执行」——deepseek-flash 是**推理模型**，
      推理阶段因此被拉爆，单次调用从 45 秒涨到 10 分钟以上（实测卡死）；
    ②提示词里出现自相矛盾的指令，模型会挑「更容易」的那条执行。
    """
    if not text or not text.strip():
        return ""
    kept, dropped = [], 0
    for ln in str(text).splitlines():
        s = ln.strip()
        if not s:
            kept.append(ln)
            continue
        if s.startswith("【"):          # 小节标题保留
            kept.append(ln)
            continue
        if any(t in s for t in _RULE_FMT_TOKENS):
            dropped += 1
            continue
        kept.append(ln)
    out = "\n".join(kept).strip()
    # 全被滤光时退化成原文，宁可多给也不能让戏层空手
    return out or str(text).strip()


def build_dialogue_prompt(block, tail_context: str = "", people_block: str = "",
                          skills=None, preferences: str = "",
                          history_context: str = "") -> str:
    """P2.5·戏层提示词：只写对话，一切格式与字幕由系统另外处理。

    与旧 build_block_prompt 的区别：这里**没有**字幕/停留/时间条这些格式负担 ——
    模型只回答一个问题：「这段聊天好不好看」。

    ★2026-09-18 修：把「本账号长期规则库（preferences）」和「让聊天好看」的创作规则
    接进来。此前戏层是**唯一写内容**的一层，却只拿到了素材清单和数值阈值，
    39 条积累的创作经验（图梗、嵌 emoji 挑法、插话视角铁律、交替率…）一条都没进 ——
    这是「AI 写得还是很差」的机器层原因。规则库里的**格式类**条目由系统负责，
    这里用一句框定语让模型只落实其中的**内容要求**。
    """
    kind = str((block or {}).get("kind") or "main")
    beats = "\n".join("  %d. %s" % (i + 1, b) for i, b in enumerate(block.get("beats") or []))
    nums = rule_numbers(skills)
    _floor = int(nums.get("min_realtime_lines", 110) or 110)
    # 篇幅要给壳层的 [删除文字]/[等待] 留出步数余量：实测每块 55 条对白 + 补等待后总步数越 200。
    lo = max(30, int(_floor / 3.4))
    hi = max(lo + 6, int(_floor / 2.6))
    if kind == "main":
        craft_rules = _DIALOGUE_CRAFT_RULES
    else:
        craft_rules = """━━━ 让这段聊天好看 ━━━
A. **给具体的东西**：不要只讲道理 —— 发一张能说明问题的图 / 一条链接，或直接把自己当年的翻车
   原话说给她听，让她「哦 原来是这样」。
B. **土味金句（≥1 处）**：押韵对仗式的一句话，如「撒网是姐姐的本事 入网是我的荣幸」；单条 ≤20 字。
C. **网络热梗点缀（1~2 处，贴语境）**：破防／拿捏／上头／已老实／那咋了／显眼包。
D. 她要是只「嗯嗯哦哦」，说明你没给干货 —— 她必须有自己的具体困境、追问和下一步打算。"""
    _rules_block = ""
    if preferences and preferences.strip():
        _content_rules = content_only_rules(preferences)
        _rules_block = f"""
【本账号长期规则库（用户一条条攒下来的，只挑**内容相关**的给你；格式类已由系统过滤掉）】
{_content_rules}
"""
    _hist_block = ""
    if history_context and history_context.strip():
        _hist_block = f"""
【列表页现状（本会话打开前，观众已经看到这些）】
{history_context}
★打开本会话的人会看到属于「{block.get('person')}」的那几条历史消息，**已经说过的话不许再发一遍**
（实测翻车：历史块写「家里停电了 一个人在 好黑」，实时第一句又是「家里停电了 就我一个人 好黑」= 复读）；
你的开场要**接着历史往下走**，或者干脆换个角度起。
★★**开局钩子（本块前几条必须有，用户定标：开局引流靠这个拉停留）**：她本块前几句里要出现
一个**擦边暗示**——「刚洗完澡 头发还湿着」「一个人在家有点怕」「你猜我现在穿什么」「你觉得我这种身材好追吗」，
或发一张性感氛围图（吊带裙/健身马甲线/微湿头发，性感靠氛围穿搭，不露点）。
★合规红线不变：只做钩子不做内容，露骨描写、性行为细节一律禁止。
"""
    if kind == "main":
        engine = """4. **全程引擎（本块必守）**：中后段**不许退化成纯关心/伺候/查户口**——至少 1 次
   「她试探 → 我方反将」（不解释、不接盘，把话打回去，例：「没别的女生半夜敢烦我 你是独一份的麻烦」）；
   收尾前安排 1 个反推拉或反转点（进一步后撤：站楼下不上楼／终局反转：回头看整局是她安排的），
   落点仍然极日常（帮个忙、换个灯泡、一起吃个饭）。
5. 她要有还手：至少 2 轮她**真的**拒绝、反问或不买账（不是嘴上说说就答应）。"""
    else:
        engine = """4. 这是粉丝/学员会话：她是来请教或要资料的粉丝，聊得轻松、给具体帮助（发张图/发条链接/
   讲两句实操），结尾自然收口到「想要聊天秘籍的兄弟 点赞关注扣6我安排」。
5. 粉丝要有具体困境与反应：别当传声筒——说自己的失败案例、追问怎么落地、给出下一步打算。"""
    if kind == "main":
        # ★2026-09-18 修：此前只把「图梗」写在创作规则 A 里，但提示词抬头写着
        # 「图片的短名必须逐字照抄素材清单」——模型据此认定「清单里的图都是女生自拍、
        # 当不了图梗」，于是**只写了图梗台词、一次 [发送图片] 都不发**（v6 实测：
        # 「你拿只水豚糊弄我？」「上香得三根」都在回应一张不存在的图）。
        # 这里把「图片描述可自造 + 参数名 + 只发 1 张 + 别带 打开=是」写成硬性条目。
        pic_rule = """11. **本块必须发 1 张图（图梗·错位暴击，全块唯一）**：先由她说出一个期待
   （「我喜欢高高瘦瘦的」）→ 我方顺杆接（「正好认识一个特别符合的」）→ **真的发图** →
   她笑骂拆台收尾。发图写法：`{"action": "发送图片", "params": {"图片": "路边三根又细又高的电线杆并排 竖屏实拍"}}`。
   ★`图片` 参数写**自造的画面描述**（主体＋细节＋画面形式，去空格 ≥10 字），
   **不要从素材清单里挑、不要写文件路径或扩展名**——用户跑视频前会按这个描述去准备图；
   ★描述必须是「随手拍得到 / 网搜关键词一搜就有」的**沙雕梗图**（奶龙、卡皮巴拉、柴犬、悲伤蛙、
   汤姆猫、doge、黑人问号、旺仔这类「角色名＋动作」，搜一下就有），**禁止**要加工的
   （拼图/合成/裁人/加字/红框）和要造场景的（朋友圈截图/转账截图/聊天记录截图）；
   ★本块**只发这 1 张**，且**不许带 `打开=是`**（我方发图自己有预期，全屏暴击交给 [对方发图片]）；
   纯情绪反应一律用贴纸或内嵌 emoji，不要另发图片。
12. ★**没真发的图不许提**：写「你拿只水豚糊弄我？」「你这图太离谱」这类台词之前，
   必须**已经有一条 `发送图片`** —— 否则她在回应一张不存在的图，观众看不懂、校验器判问题。"""
    else:
        pic_rule = """11. 需要时最多发 1 张说明性图：`{"action": "发送图片", "params": {"图片": "…画面描述…"}}`，
   描述自造、去空格 ≥10 字、随手拍得到或网搜就有；不要带 `打开=是`，不要多发；
   纯情绪反应用贴纸或内嵌 emoji。"""
    return f"""你是「微信聊天记录」的编剧。格式、字幕、打字不发、等待、时间条这些**系统会另外处理**，
你这一轮只做一件事：**把这段聊天写得像真的、写得好玩、写得让人想看下去**。

【本块信息】
- 人物：{block.get('person')}（{kind}）
- 桥段：{block.get('bridge')}
- 本块开场时间：{block.get('start_time')}
- 节拍（按顺序全部演出来，不许跳）：
{beats or "  （无，按桥段自然走）"}
- 结束状态：{block.get('tail') or '自然收束'}

【前文尾部（上一块最后几句，衔接要自然，不许复读）】
{tail_context or "（这是第一块，直接开场）"}
{_hist_block}
【人物库】
{people_block or "（用常见中文名）"}

【可用素材（★表情/贴纸的短名必须逐字照抄这里；图片描述可以自造，见素材清单②）】
{_asset_block()}
{_rules_block}
━━━ 这一轮只写「谁说了什么」━━━
- 一行一条：我方说的话 / 她发来的消息。顺序就是真实发生的顺序。
- ★**本块第一条必须是我方发的消息**（画面是「我点开她的会话、我先开口」）：她的第一句话
  放在第二条起。本块**第一条她的**消息末尾带时间条 ` | {block.get('start_time')}`（原样照抄），
  其余消息一律不写时间。
- ★**绝对不许出现**：`[打字不发]`、`[删除文字]`、`[等待]`、技巧点评、字幕、内心独白、
  括号注释（如「（笑）」「（停顿）」）以及任何格式标记 —— 这一轮它们一个字都不许出现。
- ★可用动作**只有这 8 个**：我方打字 / 发送表情 / 发送图片 / 发送emoji / 对方发消息 /
  对方表情 / 对方发图片 / 对方emoji。**禁止**出现 打开聊天 / 返回主页 / 对方后台发消息 / 历史会话。

━━━ 写戏铁律 ━━━
1. 说人话：单条 ≤20 字（**硬卡，超了会被打回**），口语、带情绪、可以有语气词；
   不要书面语、不要解释句、不要排比。长内容拆成连发，不要写成一大句。
2. **不许一问一答（交替率硬指标）**：全块「同一方连发」的相邻对数必须 ≥ 对白总数的 1/4
   —— 说白了**平均每 4 条对白就要出现 1 次连发**；任何一段连续 6 条以上的一问一答都算违规
   （最典型的翻车：中段从她回应到邀约，我一条她一条写十几条全在交替，读起来像朗读剧本）。
   连发时**每条必须是独立的新信息**，不许把一句话拆成几条凑数；
   她多数时候一条一条来，整块最多 2 次连发、每次不超过 2 条（她每多一条连发，系统都要
   另外补一次停顿，连发太多整篇会被撑爆）。
3. 她要有主动性：本块至少 1 次她**主动起话头或把话往前推**（例：「那你想我洗多久?」
   「行啊，谁不来谁是小狗」「我其实不太想跟我闺蜜吃饭」），不能全程等我喂。
{engine}
6. 细节锚在她的具体信息上（她刚说过的话、她的处境、她发的东西）；不要空泛关心，不要复读她的原话。
7. **表情是硬指标**：全块至少用 2 次贴纸表情（`发送表情` / `对方表情`，短名逐字照抄素材清单）
   ＋ 3~5 处内嵌 3D emoji（直接写进消息文本，如「太开心了[大笑]」）；整篇要凑够 6 种不同表情，别只用一种。
   ★内嵌 emoji **只能从这个清单里逐字挑**（写别的名字前端会原样显示成「[XX]」脏文字）：
   {inline_emoji_whitelist()}
8. **禁止占位符**：不许写「……」「。。。」「（沉默）」「（笑）」当消息内容；每条都要是真的一句话。
9. **不许提画面里没有的东西**：台词里禁止出现朋友圈动态、照片、视频、转账、通话记录
   —— 除非这一轮你真的发了图/表情（这两类系统会渲染）。
10. **她要有还手**：不要她一句就被说服，至少 2 轮真的反问、拒绝或不买账。
{pic_rule}

{craft_rules}

【篇幅】本块**必须**控制在 {lo}~{hi} 条对白（我方消息 + 她的消息合计，不含任何格式行）：
写超了会被校验器打回重写，**宁少勿多**——每条对白都要有信息量，不要凑数。

【输出格式 —— 只输出一个 JSON 对象，不要解释、不要 markdown 围栏】
{{"steps": [{{"action": "我方打字", "params": {{"内容": "…"}}}}, {{"action": "对方发消息", "params": {{"内容": "…"}}}}]}}
"""


def _interjection_text(step):
    """把「她」的一个 step 转成插话段写法（规范第三节路由表）。转不了返回 None。"""
    act = _step_act(step)
    p = (step or {}).get("params") or {}
    if act == "对方发消息":
        c = str(p.get("内容") or "").strip()
        if not c or re.search(r"\|\s*\d{1,2}:\d{2}\s*$", c):
            return None          # 带时间条的那条不收编（时间条会丢）
        return c.replace("|", "｜")
    if act == "对方表情":
        v = str(p.get("表情") or "").strip()
        return ("[对方表情] " + v) if v else None
    if act == "对方发图片":
        v = str(p.get("图片") or "").strip()
        return ("[对方图片] " + v) if v else None
    if act == "对方emoji":
        v = str(p.get("表情") or "").strip()
        return ("[对方emoji] " + v) if v else None
    return None


def _bg_line_from_step(person, step, time_str):
    """把「她的某条消息」转成 [对方后台发消息] 写法（规则：后台消息）。

    用途：戏层偶尔让会话块以**她**的消息开场，而 `[打开聊天]` 后第一条必须是我方的
    （对方那条语义上是「我在看别的会话时她发来的」）。壳层把它挪到上一个会话块尾，
    格式与 `assemble_skeleton._bg_lines` 完全一致：`[对方后台发消息] 谁 | 内容 | 时间`。
    """
    act = _step_act(step)
    p = (step or {}).get("params") or {}
    t = str(time_str or "").strip()
    if act == "对方发消息":
        c = re.sub(r"\s*\|\s*\d{1,2}:\d{2}\s*$", "", str(p.get("内容") or "").strip())
        if not c:
            return None
        return "[对方后台发消息] %s | %s | %s" % (person, c.replace("|", "｜"), t)
    if act == "对方表情":
        v = str(p.get("表情") or "").strip()
        return ("[对方后台发消息] %s | [表情] %s | %s" % (person, v, t)) if v else None
    if act == "对方发图片":
        v = str(p.get("图片") or "").strip()
        return ("[对方后台发消息] %s | [图片] %s | %s" % (person, v, t)) if v else None
    if act == "对方emoji":
        v = str(p.get("表情") or "").strip()
        return ("[对方后台发消息] %s | %s | %s" % (person, v, t)) if v else None
    return None


def _line_time_of(line):
    """取行尾 `| HH:MM` 的分钟数；没有返回 None。"""
    m = re.search(r"\|\s*(\d{1,2}):(\d{2})\s*$", str(line or ""))
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _line_set_time(line, minutes):
    """把行尾 `| HH:MM` 改写成给定分钟数。"""
    v = int(minutes) % (24 * 60)
    return re.sub(r"\|\s*\d{1,2}:\d{2}\s*$", "| %02d:%02d" % (v // 60, v % 60), str(line))


def _annotate_bg_lines(lines):
    """后台消息里若带 `[图片]`，在其上方补一行 # 配图注释（门禁的图片槽覆盖检查包含这一类）。"""
    out = []
    for ln in lines or []:
        if "[图片]" in str(ln) and not (out and str(out[-1]).startswith("#")):
            desc = re.search(r"\[图片\]\s*([^|｜]+)", str(ln))
            d = (desc.group(1).strip().replace("|", "｜") if desc else "")
            out.append("# 【后台图·她发｜配图】效果＝%s ｜ 找图＝按描述搜图或随手拍 ｜ 呼应＝%s"
                       % (d or "（按后台消息语境补一张实拍图）", str(ln)[:40].replace("|", "｜")))
        out.append(ln)
    return out


def place_hoisted_bg(prev_block, prev_lines, lead_bg):
    """把「块首她的消息」（3a-2 产物）按**时间顺序**插进上一个块的后台消息组。

    ★2026-09-18 实测：直接追加在 `bg_lines` 后面会撞「时间线单调」——上一个块可能本来就有
    Beat Sheet 给的后台消息（如 21:30），而 hoist 过来的那条带的是下一块的开场时间（21:38），
    追加在后就变成「21:38 → 21:30」的倒流，机械门判问题。这里合并后按时间排序，
    并以「本块正文里最后出现的时间」为下界兜底，保证只往前走。
    """
    base = max([v for v in (_line_time_of(x) for x in (prev_lines or [])) if v is not None] or [0])
    fixed = []
    for ln in lead_bg or []:
        v = _line_time_of(ln)
        if v is None:
            fixed.append(ln)
            continue
        if v <= base:
            v = base + 2
        base = max(base, v)
        fixed.append(_line_set_time(ln, v))
    merged = list((prev_block or {}).get("bg_lines") or []) + fixed
    (prev_block or {})["bg_lines"] = _annotate_bg_lines(sorted(
        merged, key=lambda x: (_line_time_of(x) if _line_time_of(x) is not None else 10 ** 6)))


def _step_plain_text(step):
    """把一步对话还原成「一句人话」，供配图注释引用（去掉动作前缀与时间条）。"""
    a = _step_act(step)
    p = (step or {}).get("params") or {}
    if a in ("我方打字", "对方发消息"):
        c = re.sub(r"\s*\|\s*\d{1,2}:\d{2}\s*$", "", str(p.get("内容") or "").strip())
        return c.replace("|", "｜")[:24]
    if a in ("发送表情", "对方表情", "发送emoji", "对方emoji"):
        v = str(p.get("表情") or "").strip()
        return ("[%s]" % v) if v else ""
    if a in ("发送图片", "对方发图片"):
        v = str(p.get("图片") or "").strip()
        return ("[图：%s]" % v) if v else ""
    return ""


def _nearest_plain(steps, i, action_set, forward=False):
    """从 i 出发（不含 i）向前/向后找最近一条属于 action_set 的对话，返回人话。"""
    rng = range(i + 1, len(steps)) if forward else range(i - 1, -1, -1)
    for j in rng:
        if _step_act(steps[j]) in action_set:
            return _step_plain_text(steps[j])
    return ""


def _image_annotation(steps, i, seq=1):
    """给「实时段图片槽」生成一行 `#` 配图注释（用户硬要求，纯代码生成、不过模型）。

    为什么要代码生成：配图注释是 `#` 开头的**散文行**，而戏层只输出 JSON 步骤，
    根本没有地方表达它（规则库里「配图注释」那条对戏层是死规则）。
    注释行以 `#` 开头 —— 运行时 parse_script_text 整行跳过，**不占步数**。

    格式对齐用户口径：`# 【照片N·谁发｜用途】效果＝… ｜ 找图＝… ｜ 呼应＝…`
    （分隔符用全角 `｜`，避免被「时间线单调」检查当成 `| HH:MM`）。
    """
    act = _step_act(steps[i])
    if act not in ("发送图片", "对方发图片"):
        return None
    desc = str(((steps[i] or {}).get("params") or {}).get("图片") or "").strip()
    if not desc:
        return None
    desc = desc.replace("|", "｜")
    who = "我发" if act == "发送图片" else "她发"
    mine = _nearest_plain(steps, i, _ME_ACTION_SET)
    hers = _nearest_plain(steps, i, _PEER_ACTION_SET, forward=True)
    parts = [
        "# 【照片%d·%s｜配图】效果＝%s" % (seq, who, desc),
        "找图＝按上面的描述搜图或随手拍；图库能解析到就直接用",
    ]
    chain = [x for x in (("我「%s」" % mine) if mine else "", ("她「%s」" % hers) if hers else "") if x]
    if chain:
        parts.append("呼应＝" + " → ".join(chain))
    return " ｜ ".join(parts)


def weave_shells(dialogue_steps, block=None, n_main=None, n_holds=None):
    """P2.5·壳层：纯代码给对话卡上 [打字不发] 壳（确定性，不经过模型）。

    规则（对齐金样实测：52% 字幕紧跟「我方已发消息」）：
      · 字幕挂在我方「出招段」之后（回指式）；她紧随的**整段连发**收进第 3 段插话
        （规范：删除后不许有独立 [对方×] 行，反应必须收进插话）；
      · 一部分主壳后面「连打第二条字幕」（副壳，不带插话，金样 24% 的用法）；
      · **[等待] 0.2 补在「她连发段内部每两条之间」**（机械门硬卡「对方连发节奏」）；
      · 每块总壳数 = n_holds（全篇 ≥15 ÷ 块数），带插话的主壳另有上限（≈全篇 6 条）；
      · 停留由代码定：主壳 0.5 / 副壳 0.3。

    返回 (items, shells)：
      items  = [("line", 文本) | ("shell", idx), …]
      shells = [{字幕, 停留, 插话, 我的, 她, kind}, …]
    """
    import script_format as sf_mod
    steps = [s for s in (dialogue_steps or []) if isinstance(s, dict)]
    n = len(steps)
    if n < 6:
        return [("line", sf_mod.render_step(s)) for s in steps], []

    lines = [sf_mod.render_step(s) for s in steps]

    # 1) 我方「出招段」的结尾位置
    me_ends = []
    for i, s in enumerate(steps):
        if _step_act(s) not in _ME_ACTION_SET:
            continue
        nxt = _step_act(steps[i + 1]) if i + 1 < n else ""
        if nxt not in _ME_ACTION_SET:
            me_ends.append(i)

    # 2) 主壳候选：出招段后面紧跟一整段「她的话」，且全部可转插话
    cands = []
    for i in me_ends:
        texts, j = [], i + 1
        while j < n and _step_act(steps[j]) in _PEER_ACTION_SET:
            t = _interjection_text(steps[j])
            if t is None:
                texts = None
                break
            texts.append(t)
            j += 1
        if texts:
            cands.append((i, texts))
    if not cands:
        return [("line", x) for x in lines], []

    # 目标：全篇打字不发 ≥15（机械门硬下限）、插话 ≈6 条（金样 3:1）
    # → 调用方按块数分配：每块总壳数 n_holds、其中带插话的主壳 n_main
    if n_main is None:
        n_main = 2
    if n_holds is None:
        n_holds = 5
    main_ids = _pick_even([i for i, _ in cands], max(1, min(int(n_main), len(cands))))
    main_set = set(main_ids)
    main_map = {i: t for i, t in cands if i in main_set}

    # 3) 收编决策：主壳把紧随的整段「她的话」收进插话（这些行不再单独成行）
    skip = set()
    for i in main_map:
        j = i + 1
        while j < n and _step_act(steps[j]) in _PEER_ACTION_SET:
            skip.add(j)
            j += 1

    # 4) 副壳（连打第二条，不带插话）：**不许两条副壳堆在同一个主壳后面** ——
    #    校验器 `_consecutive_solo_holds` 判「连排两个无插话的 [打字不发]，像独角戏太拖沓」。
    #    ★2026-09-18 修：改为优先放「我方连发段内部」的位置 —— steps[i] 与 steps[i+1] 都是我方的
    #    真实消息，副壳夹在中间：既不与别的壳连排，也不违反「[删除文字] 后不许她即时回应」。
    rest = max(0, int(n_holds) - len(main_ids))
    sub_indep = set()
    # ① 出招位（我发完她没接）：最自然，删掉不会留下她的行
    free_ends = [i for i in me_ends
                 if i not in main_set
                 and (i + 1 >= n or _step_act(steps[i + 1]) not in _PEER_ACTION_SET)]
    take = _pick_even(free_ends, min(rest, len(free_ends)))
    sub_indep.update(take)
    rest -= len(take)
    # ② 我方连发段内部（主力来源）：前后都是我方的真实消息
    if rest > 0:
        burst_inside = [i for i in range(n - 1)
                        if _step_act(steps[i]) in _ME_ACTION_SET
                        and _step_act(steps[i + 1]) in _ME_ACTION_SET
                        and i not in main_set]
        take = _pick_even(burst_inside, min(rest, len(burst_inside)))
        sub_indep.update(take)
        rest -= len(take)
    # ③ 还有余量才挂在主壳后面，且**每个主壳最多 1 条**（挂 2 条就是「连排独角戏」）
    sub_plan = {}
    k = 0
    while rest > 0 and main_ids and k < 8:
        mid = main_ids[k % len(main_ids)]
        if sub_plan.get(mid, 0) < 1:
            sub_plan[mid] = sub_plan.get(mid, 0) + 1
            rest -= 1
        k += 1

    # 5) [等待] 0.2：她连发段内部每两条之间必须有（段首那条前面不加——那是我方消息之后）
    wait_at = set()
    for i in range(1, n):
        if i in skip or _step_act(steps[i]) not in _PEER_ACTION_SET:
            continue
        if (i - 1) in skip:
            continue
        if _step_act(steps[i - 1]) in _PEER_ACTION_SET:
            wait_at.add(i)

    # 6) 出序列（★图片槽上方插一行 # 配图注释：用户硬要求，纯代码生成、不占步数）
    items, shells = [], []
    _pic_n = 0
    for i in range(n):
        if i in skip:
            continue
        if i in wait_at:
            items.append(("line", "[等待] 0.2"))
        _ann = _image_annotation(steps, i, _pic_n + 1)
        if _ann:
            _pic_n += 1
            items.append(("line", _ann))
        items.append(("line", lines[i]))
        if i in main_map:
            shells.append({"字幕": "", "停留": 0.5, "插话": main_map[i],
                           "我的": lines[i], "她": "；".join(main_map[i]), "kind": "main"})
            items.append(("shell", len(shells) - 1))
            for _ in range(sub_plan.get(i, 0)):
                shells.append({"字幕": "", "停留": 0.3, "插话": [],
                               "我的": lines[i], "她": "；".join(main_map[i]), "kind": "sub"})
                items.append(("shell", len(shells) - 1))
        elif i in sub_indep:
            shells.append({"字幕": "", "停留": 0.3, "插话": [],
                           "我的": lines[i], "她": "", "kind": "sub"})
            items.append(("shell", len(shells) - 1))
    return items, shells


def build_subtitle_prompt(shells, block=None, skills=None) -> str:
    """P2.5·字层提示词：只给每个壳写一句 2~10 字的字幕（回指式，讲我上一条在干什么）。

    这一层输入极小、任务极窄 —— 模型没有机会去动对话、也不可能把两边角色写混。
    """
    kind = str((block or {}).get("kind") or "main")
    rows = []
    for i, sh in enumerate(shells or [], 1):
        mine = str(sh.get("我的") or "").replace("[我方打字]", "").replace("[发送表情]", "").strip()
        hers = str(sh.get("她") or "").strip() or "（她还没回）"
        role = "她刚被我这句话带着走" if str(sh.get("kind")) == "main" else "连打的第二条（补充说明上一条）"
        rows.append("%d. 我刚发出去的：%s\n   她的即时反应：%s\n   这一格的性质：%s"
                    % (i, mine[:46], hers[:70], role))
    type_note = ("本块是**主线女主会话**：允许最多 1 处失守型（「？？？」「完了 别多想」「这谁敢答应」），"
                 "其余一律打法型/状态型。" if kind == "main" else
                 "本块是**粉丝/学员线**：一律打法型，禁止失守型。")
    return f"""你在给一段微信聊天视频写「键盘字幕」。字幕是主角一边聊一边敲在输入框里、
**永远不会发出去、打完就删**的解说 —— 观众就爱看这个。

【本块】人物 {block.get('person')}（{kind}）｜桥段 {block.get('bridge')}

【每一格给你三行信息】
{chr(10).join(rows)}

━━━ 写法 ━━━
- 每条 **2~10 字**（硬上限 14 字），短句标签体：「动作短语 + 空格 + 三五字补充」。
- 字幕讲的是**我刚发出去那句在干什么**（回指式讲解），不是我要发的下一句话，也不是她的心理活动。
- 三种可用型（按这个主次）：
  ①**打法型（主干）**：`以退为进`｜`拆穿不点破`｜`把选择权丢给她`｜`看似调侃实则测试接受度`｜`继续留钩子`；
  ②**状态型（次主干）**：`好奇了`｜`被架住了 不知道怎么收场`｜`上头了`｜`有戏`；
  ③**失守型（调料）**：`？？？`｜`完了 别多想`｜`这谁敢答应`。
- {type_note}
- **禁止**：写话术草稿（「那你明天有空吗」）、写她的心理活动（「她在想我」）、复述她说过的字、
  写「她接话了/她开口了」这类画面自己会演的承接描述。
- 每条内容都不许重复（相邻两条不能教同一个动作）。

【输出格式 —— 只输出一个 JSON 对象】
{{"subs": ["第一条字幕", "第二条字幕", "……"]}}
数组长度必须正好 {len(shells or [])}，顺序与上面编号一一对应。
"""


def apply_subtitles(shells, subs) -> list:
    """把字层返回的字幕回填进壳；返回超长/缺失的问题清单（供重试提示）。"""
    issues = []
    data = subs if isinstance(subs, list) else []
    for i, sh in enumerate(shells or []):
        raw = str(data[i]).strip() if i < len(data) else ""
        raw = raw.replace("|", "｜").replace("；", "，").strip()
        if not raw:
            issues.append("第 %d 条字幕缺失" % (i + 1))
            raw = "稳住节奏" if str(sh.get("kind")) == "main" else "顺手补一句"
        if len(raw) > 14:
            issues.append("第 %d 条字幕 %d 字，超过 14 字硬上限（「%s」）" % (i + 1, len(raw), raw[:20]))
        sh["字幕"] = raw
    return issues


def render_shell_items(items, shells) -> list:
    """壳层产物 -> 剧本行（[打字不发] … + [删除文字] -1）。"""
    import script_format as sf_mod
    out = []
    for kind, val in items:
        if kind == "line":
            out.append(val)
            continue
        sh = (shells or [])[val] if isinstance(val, int) and val < len(shells or []) else {}
        parts = [str(sh.get("字幕") or "").strip(), sf_mod._fmt_num(sh.get("停留") or 0.5)]
        if sh.get("插话"):
            parts.append("；".join(sh["插话"]))
        out.append("[打字不发] " + " | ".join(parts))
        out.append("[删除文字] -1")
    return out


_PLACEHOLDER_ONLY_RE = re.compile(r"^[\s.。，,、…⋯~～\-—_·！!？?；;：:“”\"'（）()\[\]【】]*$")


# ── 内嵌 3D emoji 白名单 + 确定性命中（2026-09-18）─────────────────────
# 实测：模型爱写微信**原生**表情名（[偷笑] [强] [破涕为笑]），但前端只认
# wxemoji3d_map.js 里有的 3D 名，库里没有的会原样显示成「[偷笑]」脏文字。
# 这是纯格式问题 —— 按三层分工由**代码**修：壳层前把非法名换成本库最近的真名，
# 没有对应就整段剔除（宁可少一个表情，也不让气泡里出现方括号字样）。
_INLINE_EMOJI_CACHE = None
# emoji 动作参数里的**运行时特殊值**，不是表情名，清洗时必须原样保留
# （规则原文：「`[对方emoji] 微笑`=3D黄脸（名称/编号/随机）」）
_EMOJI_PARAM_KEEP = ("随机", "任意", "随便", "无")
_INLINE_ACT_PREFIX = ("对方", "我", "发送", "打开", "删除", "打字", "等待", "返回", "进入", "点开",
                      "滑", "历史", "会话", "后台", "正在输入", "重发", "撤回", "语音", "转账", "静音",
                      "图片", "配图", "视频", "链接", "表情", "文件", "动画表情")
# 常见「微信原生名 → 3D 库真名」对照（库内真名清单见 _load_inline_emoji_names）
_INLINE_EMOJI_FIX = {
    "偷笑": "窃笑", "强": "赞", "弱": "差评", "破涕为笑": "哭笑不得",
    "白眼": "翻白眼", "发呆": "望天", "思考": "疑问", "鼓掌": "啪啪",
    "擦汗": "汗颜", "衰": "裂开", "骷髅头": "骷髅", "月亮": "晚安月",
    "太阳": "出太阳", "抱拳": "合十", "勾引": "示爱", "饥饿": "可怜",
    "傲慢": "傲娇", "折磨": "崩溃", "无聊": "犯懒", "晕死": "晕",
    "吐": "吐舌", "敲打": "捏", "愉快": "咧嘴笑", "激动": "兴奋",
    "憨笑": "憨笑", "抓头发": "抓狂", "哭": "大哭", "笑": "开心",
    "生气": "生气", "害羞": "脸红", "吓": "吃惊", "赞赞": "赞",
    "比心": "示爱", "加油": "加油拳", "打call": "666", "捂眼睛": "遮眼",
    "哭笑不得": "哭笑不得", "快哭": "快哭了", "流泪满面": "泪如雨下",
    "呵欠": "犯困", "抠鼻屎": "挖鼻", "鼻屎": "挖鼻", "撇嘴脸": "撇嘴",
    "鄙视脸": "鄙视", "傲慢脸": "傲娇", "害怕脸": "害怕", "尴尬脸": "尴尬",
    "汗死": "流汗", "无语脸": "无语", "懵逼": "困惑", "裂开脸": "裂开",
    "卧槽": "裂开", "狗头保命": "狗头保命", "滑稽": "窃笑",
}


def _load_inline_emoji_names():
    """读 wxemoji3d_map.js 的键（与机械门 _check_script_quality.py **同源同正则**）。"""
    global _INLINE_EMOJI_CACHE
    if _INLINE_EMOJI_CACHE is not None:
        return _INLINE_EMOJI_CACHE
    names = set()
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "vue-WeChat", "src", "assets", "wxemoji3d_map.js")
        with open(p, encoding="utf-8") as fh:
            jt = fh.read()
        names = set(re.findall(r'"([^"]{1,10})"\s*:', jt)) | set(re.findall(r"'([^']{1,10})'\s*:", jt))
    except Exception:
        names = set()
    _INLINE_EMOJI_CACHE = names
    return names


def sanitize_inline_emoji(text):
    """消息文本里的内嵌 `[XX]`：库内真名原样留，非法名换最近真名，无对应则剔除。"""
    s = str(text or "")
    if "[" not in s or "]" not in s:
        return s
    names = _load_inline_emoji_names()
    if not names:
        return s

    def _sub(m):
        nm = m.group(1)
        if nm in names:
            return m.group(0)
        if nm.startswith(_INLINE_ACT_PREFIX):
            return m.group(0)          # 动作标记，交给机械门报错，不要在这里吞掉
        fixed = _INLINE_EMOJI_FIX.get(nm)
        if fixed and fixed in names:
            return "[" + fixed + "]"
        return ""                       # 无名可换 → 剔除，绝不留下方括号文字

    return re.sub(r"\[([^\[\]]{1,6})\]", _sub, s)


def inline_emoji_whitelist(n: int = 48) -> str:
    """给戏层提示词用的常用内嵌表情真名清单（挑短、常用的，减少模型瞎编）。"""
    names = _load_inline_emoji_names()
    prefer = ["大笑", "捂脸", "笑哭", "呲牙", "偷笑", "得意", "坏笑", "害羞", "无语", "白眼惊",
              "偷看", "尴尬", "冷汗", "流汗", "流泪", "撇嘴", "叹气", "吃瓜", "机智", "调皮",
              "旺柴", "狗头", "猪头", "爱心", "心碎", "玫瑰", "礼物", "点赞", "大拇指", "合十",
              "拳头", "胜利", "抱头", "挥手", "拜拜", "晚安", "困", "裂开", "崩溃", "鼓掌",
              "加油拳", "666", "OK", "让我看看", "捂嘴", "红脸", "惊讶", "无奈"]
    out = []
    for nm in prefer:
        if nm in names:
            out.append("[%s]" % nm)
    for nm in sorted(names):
        if len(out) >= n:
            break
        if re.fullmatch(r"[\u4e00-\u9fff]{2,3}", nm) and ("[%s]" % nm) not in out:
            out.append("[%s]" % nm)
    return " ".join(out[:n])


def sanitize_emoji_name(name):
    """`发送emoji`/`对方emoji` 的「表情」参数：非法 CN 名换真名，换不到返回空串。

    ★只动「纯中文 1~6 字且不在库内」的值 —— 运行时的特殊写法（「随机」）和编号
    必须原样保留（实测回归：早期版本把「随机」当非法名剔掉，整个 emoji 步骤就没了）。
    """
    nm = str(name or "").strip()
    if not nm or nm in _EMOJI_PARAM_KEEP:
        return nm
    if not re.fullmatch(r"[\u4e00-\u9fff]{1,6}", nm):
        return nm
    names = _load_inline_emoji_names()
    if not names or nm in names:
        return nm
    fixed = _INLINE_EMOJI_FIX.get(nm)
    if fixed and fixed in names:
        return fixed
    return ""


def _clean_dialogue_steps(steps) -> list:
    """戏层输出清洗：只留 8 个对话动作、内容非空且不是占位符。

    实测踩过：模型会写 `[对方发消息] ……` / `[我方打字] ……` 当「沉默」的占位
    （机械门按「消息内容疑似占位」打回），所以在入口直接丢掉。
    同时把内嵌表情名（消息文本）与 emoji 动作参数（表情）里的非法名确定性修正。
    """
    if not isinstance(steps, list):
        return []
    out = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        act = _step_act(s)
        if act not in _DIALOGUE_ACTIONS:
            continue
        p = s.get("params") or {}
        if act in ("发送表情", "对方表情"):
            # ★2026-09-18 修 bug（两层，第二层是 v7 实测补的）：
            # ①原来它掉进下面的 else 分支、取「内容」必然为空 → 带参数的贴纸表情被整条误删，
            #   模型照硬指标写了贴纸也上不了屏（v6 实测：全篇零贴纸）。
            # ②但只「放行」还不够 —— 戏层有时把短名写在「内容」键上（v7 块1 两处都是「内容」），
            #   而 `render_step()` 只认「表情」键 → 渲染成裸 `[发送表情]` 空行
            #   （v6 里那几行空 `[发送表情]` 就是这么来的，已用渲染探针实测确认）。
            #   所以这里**把「内容」归一成「表情」**，让短名一律落到渲染器认的键上。
            # 短名对不对由机械门按素材清单查；★不能丢给 sanitize_emoji_name()——
            # 它只认 3D emoji 名，会把「害羞猫咪」当非法名清成空串。
            nm = str(p.get("表情") or "").strip()
            _alt = str(p.get("内容") or "").strip()
            if not nm and _alt:
                nm = _alt
                s = dict(s)
                p = dict(p)
                p["表情"] = _alt
                s["params"] = p
            ok = bool(nm)
        elif act in ("发送emoji", "对方emoji"):
            nm = sanitize_emoji_name(p.get("表情"))
            ok = bool(nm)
            if ok and nm != str(p.get("表情") or "").strip():
                s = dict(s)
                p = dict(p)
                p["表情"] = nm
                s["params"] = p
        elif act in ("发送图片", "对方发图片"):
            ok = bool(str(p.get("图片") or "").strip())
        else:
            c = sanitize_inline_emoji(str(p.get("内容") or "").strip())
            ok = bool(c) and not _PLACEHOLDER_ONLY_RE.match(c)
            if ok and c != str(p.get("内容") or "").strip():
                s = dict(s)
                p = dict(p)
                p["内容"] = c
                s["params"] = p
        if ok:
            out.append(s)
    return out


def _generate_block_onepot(block, tail_context, people_block, actions, skills,
                           call_llm, _dbg, bi, fails) -> str:
    """旧版「一锅端」块级生成 —— 仅作 P2.5 三层链路的降级回退路径保留。

    ★2026-09-18 修：重试时把上一版的问题追加进提示词（旧版重抽用同一个 sys_p，
    等于原地抽卡、白浪费一次调用）。
    """
    import script_format as sf_mod
    sys_p = build_block_prompt(block, tail_context, people_block, actions, skills)
    for t in range(BLOCK_MAX_TRIES):
        raw, err = call_llm(sys_p, "请输出本会话块的 steps JSON。")
        _dbg(f"staged_block{bi}_try{t}.txt", raw or "")
        problems = []
        if err:
            problems.append("调用失败：%s" % err)
        else:
            data = sf_mod.extract_json(sf_mod._strip_fences(raw or ""))
            steps = data.get("steps") if isinstance(data, dict) else data
            if not isinstance(steps, list) or len(steps) < 12:
                problems.append("steps 太少或不是数组（至少 25 条）")
            else:
                rendered = "\n".join(x for x in (sf_mod.render_step(s) for s in steps) if x)
                if len(rendered.splitlines()) >= 12:
                    return rendered
                problems.append("渲染后行数不足 12 行")
        fails.append("块%d(%s)：%s" % (bi, block.get("person"), "；".join(problems)))
        if problems and t < BLOCK_MAX_TRIES - 1:
            sys_p = (build_block_prompt(block, tail_context, people_block, actions, skills)
                     + "\n\n【你上一版的问题 —— 必须全部修掉】\n"
                     + "\n".join("- %s" % x for x in problems))
    return ""


BEATSHEET_MAX_TRIES = 3       # Beat Sheet 最多重出几次
BLOCK_MAX_TRIES = 2           # 单块最多重写几次
DEFAULT_START_TIME = "HH:MM"  # 块 prompt 里的占位说明用


def generate_staged_script(brief: str, category: str, people_block: str,
                           call_llm, actions=None, skills=None,
                           preferences: str = "", reference_text: str = "",
                           debug_dir: str = "", max_polish_rounds: int = 3):
    """P2 主流程：Beat Sheet → 骨架 → 逐块填充 → 拼装全文。

    call_llm(system_prompt, user_prompt) -> (raw_text, err)
    返回 (text, info)；info = {"beatsheet_issues":…, "block_fails":…, "sheet":…}。
    抛出的异常由调用方决定是否降级 legacy。
    """
    import script_format as sf_mod

    def _dbg(name, content):
        if debug_dir:
            try:
                with open(os.path.join(debug_dir, name), "w", encoding="utf-8") as fh:
                    fh.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2))
            except OSError:
                pass

    # 金样摘要（给 Beat Sheet 当结构范本，只取标题+摘要，不搬全文）
    ref_summaries = reference_text if len(reference_text) < 4000 else ""
    if not ref_summaries:
        try:
            refs = [r for r in store.list_references()
                    if (r.get("kind") or "full") == "full" and "直男许诺" in str(r.get("title"))]
            ref_summaries = "\n".join(
                f"- {r.get('title')}：{r.get('summary')}" for r in refs[:4])
        except Exception:  # noqa: BLE001
            ref_summaries = ""

    # ---- 阶段 1：Beat Sheet ----
    sheet = None
    sheet_issues = []
    bs_sys = build_beatsheet_prompt(brief, category, people_block, ref_summaries, skills)
    for i in range(BEATSHEET_MAX_TRIES):
        raw, err = call_llm(bs_sys, f"创作主题：{brief}\n请输出 Beat Sheet JSON。")
        if err:
            raise RuntimeError(f"Beat Sheet 调用失败：{err}")
        data = sf_mod.extract_json(sf_mod._strip_fences(raw or ""))
        # ★2026-09-18：先做确定性修补（模型漏填 background.time 这类格式问题由代码补），
        # 否则会白烧一次调用（实测 2 次、约 77 秒）才抽到完整版。
        data = repair_beatsheet(data)
        sheet_issues = validate_beatsheet(data, skills=skills)
        _dbg(f"staged_beatsheet_try{i}.json", raw or "")
        if not sheet_issues:
            sheet = data
            break
        bs_sys = (build_beatsheet_prompt(brief, category, people_block, ref_summaries, skills)
                  + "\n\n【你上一版的问题 —— 必须全部修掉】\n"
                  + "\n".join(f"- {x}" for x in sheet_issues))
    if sheet is None:
        raise RuntimeError("Beat Sheet 校验不通过：" + "；".join(sheet_issues))
    _dbg("staged_beatsheet_final.json", json.dumps(sheet, ensure_ascii=False, indent=2))

    # ---- 阶段 2：骨架 ----
    skeleton = assemble_skeleton(sheet)
    _dbg("staged_skeleton.txt", skeleton["text"])

    # ---- 阶段 3：逐块填充（P2.5 三层：戏层 AI 写对话 → 壳层代码卡位 → 字层 AI 只填字幕）----
    block_lines = []      # 每块渲染出的行
    block_fails = []      # 致命失败（最终抛错用）
    layer_fails = []      # 三层链路的降级/重试记录（info 回报用）
    # 壳数按块数分配：全篇目标「打字不发 ≥15、插话 5~8」→ 3 块约 5 壳/块（2 带插话 + 3 副壳）
    _nb = max(1, len(skeleton["blocks"]))
    _n_main_pb = max(2, int(round(6.0 / _nb)))          # 带插话的主壳（全篇 ≈6 条）
    _n_holds_pb = max(4, int(round(16.0 / _nb)))        # 打字不发总数（全篇 ≥15）
    tail_context = ""
    for bi, block in enumerate(skeleton["blocks"]):
        rendered = ""
        dialogue_steps = []

        # 3a 戏层：只写「谁说了什么」（禁止一切格式负担）
        # ★2026-09-18：把规则库（preferences）和历史块现状一起喂进去 —— 此前戏层只拿到
        # 素材清单和数值阈值，用户积累的 39 条创作经验一条都没进，是内容差的机器层原因。
        _hist_ctx = skeleton["history_text"] if bi == 0 else ""
        dlg_sys = build_dialogue_prompt(block, tail_context, people_block, skills,
                                        preferences=preferences, history_context=_hist_ctx)
        for t in range(BLOCK_MAX_TRIES):
            raw, err = call_llm(dlg_sys, "请输出本会话块的对话 JSON。")
            _dbg(f"staged_dlg{bi}_try{t}.txt", raw or "")
            problems = []
            if err:
                problems.append("调用失败：%s" % err)
            else:
                data = sf_mod.extract_json(sf_mod._strip_fences(raw or ""))
                steps = _clean_dialogue_steps(data.get("steps") if isinstance(data, dict) else data)
                if len(steps) >= 12:
                    dialogue_steps = steps
                    break
                problems.append("对话条数不足（清洗后仅 %d 条，至少 12 条）" % len(steps))
            layer_fails.append("块%d 戏层：%s" % (bi, "；".join(problems)))
            dlg_sys = (build_dialogue_prompt(block, tail_context, people_block, skills,
                                             preferences=preferences, history_context=_hist_ctx)
                       + "\n\n【你上一版的问题 —— 必须全部修掉】\n"
                       + "\n".join("- %s" % x for x in problems))

        # 3a-2 [打开聊天] 后不许对方先发（规则：后台消息）。纯卡位，不改内容：
        #   · 非首块 → 把她在块首的连发挪成**上一个会话块尾**的 [对方后台发消息]；
        #   · 首块（没有上一块可挂）→ 挪到我方第一句之后，保证「我方先开口」。
        lead_bg = []
        if dialogue_steps and _step_act(dialogue_steps[0]) in _PEER_ACTION_SET:
            if bi == 0:
                lead = []
                while dialogue_steps and _step_act(dialogue_steps[0]) in _PEER_ACTION_SET:
                    lead.append(dialogue_steps.pop(0))
                if dialogue_steps and _step_act(dialogue_steps[0]) in _ME_ACTION_SET:
                    dialogue_steps[1:1] = lead
                else:
                    dialogue_steps = lead + dialogue_steps
                layer_fails.append("块0 戏层以对方开场：已把她的开场挪到我方第一句之后")
            else:
                while dialogue_steps and _step_act(dialogue_steps[0]) in _PEER_ACTION_SET:
                    _ln = _bg_line_from_step(block.get("person"), dialogue_steps.pop(0),
                                             block.get("start_time"))
                    if _ln:
                        lead_bg.append(_ln)
                layer_fails.append("块%d 戏层以对方开场：已挪成上一块尾的 [对方后台发消息]（%d 条）"
                                   % (bi, len(lead_bg)))

        # 3b 壳层（纯代码卡位）+ 3c 字层（只填字幕）
        if dialogue_steps:
            items, shells = weave_shells(dialogue_steps, block, _n_main_pb, _n_holds_pb)
            if shells:
                sub_sys = build_subtitle_prompt(shells, block, skills)
                for t in range(2):
                    raw, err = call_llm(sub_sys, "请输出字幕 JSON。")
                    _dbg(f"staged_sub{bi}_try{t}.txt", raw or "")
                    if err:
                        layer_fails.append("块%d 字层调用失败：%s" % (bi, err))
                        break
                    data = sf_mod.extract_json(sf_mod._strip_fences(raw or ""))
                    subs = (data.get("subs") if isinstance(data, dict) else data) or []
                    issues = apply_subtitles(shells, subs)
                    if not issues:
                        break
                    layer_fails.append("块%d 字层：%s" % (bi, "；".join(issues)))
                    sub_sys = (build_subtitle_prompt(shells, block, skills)
                               + "\n\n【你上一版的问题 —— 必须全部修掉】\n"
                               + "\n".join("- %s" % x for x in issues))
            rendered = "\n".join(render_shell_items(items, shells))

        # 3z 降级：三层链路拿不出可用文本 → 回退旧的一锅端块级生成
        if len(rendered.splitlines()) < 12:
            layer_fails.append("块%d(%s) 三层链路不可用，回退旧块级生成" % (bi, block.get("person")))
            rendered = _generate_block_onepot(block, tail_context, people_block, actions,
                                              skills, call_llm, _dbg, bi, block_fails)
        if len(rendered.splitlines()) < 12:
            raise RuntimeError("会话块「%s」生成失败：" % block["person"]
                               + "；".join(layer_fails[-2:] or block_fails[-2:]))
        # 3a-2 的产物：按时间插进**上一个会话块**的后台消息组（时间必须单调，否则门禁判「时间倒流」）
        if lead_bg and block_lines:
            place_hoisted_bg(skeleton["blocks"][bi - 1], block_lines[-1], lead_bg)
        block_lines.append(rendered.splitlines())
        tail_context = "\n".join(rendered.splitlines()[-6:])

    # ---- 阶段 4：拼装全文（历史块 + 块(prefix 内容 bg suffix) + 结尾）----
    out = [skeleton["history_text"]]
    for bi, block in enumerate(skeleton["blocks"]):
        out.extend(block["prefix_lines"])
        out.extend(block_lines[bi])
        out.extend(block["bg_lines"])
        out.extend(block["suffix_lines"])
    out.extend(skeleton["ending_lines"])
    text = "\n".join(out).strip()
    _dbg("staged_assembled.txt", text)
    return text, {"beatsheet_issues": sheet_issues, "block_fails": block_fails,
                  "layer_fails": layer_fails, "sheet": sheet}

