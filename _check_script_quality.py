# -*- coding: utf-8 -*-
"""剧本质量门：按「创作模式」同一套规则离线校验 [指令] 剧本。

用法：
    py _check_script_quality.py 剧本库/xxx.txt 剧本库/yyy.txt ...

校验内容（与创作模式生成后的校验完全同一套）：
  1) 复刻 editor_server._parse_script_to_steps 的完整离线管线：
     split_history_block -> translate_offline -> merge_typing_waits ->
     normalize_step_people -> cap_home_and_align_contacts ->
     ensure_all_contacts_in_home -> convert_image/link_marker_steps
  2) script_generator.validate_generated_steps（结构 + 规则库 36 条硬规则）
  3) 素材引用逐个验证能否解析到真图（与 main._lookup_emoji_file 一致）
  4) 关键指标：解析步数 / 实时对白 / 打字不发 / 插话 / 会话数 / 表情总数
  5) 因果检查：[删除文字] 后、下一个我方动作前，禁止对方即时回应
     （反应只能收进 [打字不发] 第 3 段多段插话；对方后台消息不受限）
  6) 配图注释覆盖：**每个**图片槽上方是否有一行 # 注释（谁发/效果/找图/呼应），
     逐条判定、不把连续多张并成一组（连写两条 [点开图片] 时第二条也要有自己的注释）。
     只出提示不拦截——注释是创作习惯，写详写略没有硬阈值。
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import script_generator as G
import script_translator as T


_NEW2OLD = {
    "[我方发消息]": "[我方打字]", "[观众字幕]": "[打字不发]", "[清空输入框]": "[删除文字]",
    "[我方发图片]": "[发送图片]", "[我方发表情]": "[发送表情]", "[我方发emoji]": "[发送emoji]",
    "[我方发语音]": "[发送语音]", "[对方发表情]": "[对方表情]", "[对方发emoji]": "[对方emoji]",
    "[对方发语音]": "[对方语音]",
    # ★[对方发图片] 不归一：parse_script_text 的 TEXT_COMMAND_MAP 只认「对方发图片」
    #   （main.py TEXT_COMMAND_MAP "对方发图片": "图片"）；「对方图片」只是插话路由的标记名，
    #   归一成它会导致独立指令行被当未知指令整条丢弃（2026-09-19 实测，相亲稿同坑）。
}


def _norm_new_action_names(t: str) -> str:
    """2026-09-18 改名兼容：新写法归一为内部标准名后再过全部检查。"""
    for _k, _v in _NEW2OLD.items():
        t = t.replace(_k, _v)
    return t


def _merge_split_interjections(t: str):
    """[她插话] 拆行式写法 -> 合并回行内第 3 段（仅门禁文本级检查用）。

    2026-09-19 新写法：`[她插话] 她的话` 独立成行、紧跟在 [打字不发]/[我方打字] 之后，
    与旧行内 `| 第3段` 渲染等价。本函数把它并回宿主行，让 3.12 插话主体 /
    3.13 承接断链 / 复述检查等「按第 3 段解析」的既有检查原样生效。
    - [打字不发] 宿主：用 ` | ` 追加（第 3 段语义，不动「停留」段）；
    - [我方打字] 宿主：用 `；` 追加（该动作行内第 2 段整段=插话）；
    - 中间隔了其他动作行则视为挂靠失败，[她插话] 原样保留，交位置检查判失败。
    返回 (合并后文本, 挂靠失败的 [她插话] 行号列表)。
    """
    out = []
    pending_host = None          # out 中可接插话的宿主行下标
    _host_re = re.compile(r"^\[(打字不发|我方打字)\]")
    orphan = []
    for raw in t.splitlines():
        s = raw.strip()
        if _host_re.match(s):
            out.append(raw)
            pending_host = len(out) - 1
            continue
        if s.startswith("[她插话]"):
            body = s[len("[她插话]"):].strip()
            if pending_host is not None and body:
                host_act = _host_re.match(out[pending_host].strip()).group(1)
                joiner = " | " if host_act == "打字不发" else "；"
                out[pending_host] = out[pending_host].rstrip() + joiner + body
                continue
            orphan.append(len(out) + 1)   # 近似行号（合并前原文行号在调用侧另行统计）
            out.append(raw)
            pending_host = None
            continue
        if s and not s.startswith("#"):
            pending_host = None           # 中间隔了实质行 -> 宿主失效（与解析器口径一致）
        out.append(raw)
    return "\n".join(out), orphan


def check_file(path: str) -> bool:
    text = open(path, encoding="utf-8").read()
    text = _norm_new_action_names(text)
    print("=" * 72)
    print("◆", os.path.basename(path))
    ok = True
    # 参考样本（外部作品原文，只作风格输入，不是产出稿）不进门禁
    if "参考" in os.path.basename(path):
        print("  （参考样本，跳过门禁）")
        return True

    # ---- 0. [她插话] 拆行式（2026-09-19 新写法）----
    # 先按原文行号查挂靠位置（挂靠不上=解析器会丢弃她的这条消息），再把拆行并回
    # 行内第 3 段，让 3.12 插话主体 / 3.13 承接断链 / 复述检查等按「第 3 段」解析的
    # 既有检查对拆行写法原样生效。
    _orig_lines = [l.strip() for l in text.splitlines()]
    _her_orphan = []
    for _hi, _hl in enumerate(_orig_lines):
        if not _hl.startswith("[她插话]"):
            continue
        _pj = _hi - 1
        while _pj >= 0 and (_orig_lines[_pj] == "" or _orig_lines[_pj].startswith("#")):
            _pj -= 1
        if _pj < 0 or not _orig_lines[_pj].startswith(
                ("[观众字幕]", "[打字不发]", "[我方发消息]", "[我方打字]")):
            _her_orphan.append(_hi + 1)
    if _her_orphan:
        ok = False
        print("[问题] %d 处 [她插话] 没有紧跟在 [观众字幕]/[我方发消息] 之后"
              "（挂靠不上=她的这条消息会被丢弃）：" % len(_her_orphan))
        for _n in _her_orphan:
            print("  - 第%d行 %s" % (_n, _orig_lines[_n - 1][:50]))
        print("      正确写法：[她插话] 只能紧跟 [观众字幕]/[我方发消息] 行（中间可空行/# 注释）；"
              "多条用「；」分隔或连写多行")
    text, _ = _merge_split_interjections(text)

    # ---- 1. 复刻编辑器离线管线 ----
    all_names = T._collect_text_person_names(text)
    global_map = T.build_name_replacement_map(all_names)
    history_steps, cleaned, hist_warn, repl_map = T.split_history_block(text, pre_mapping=global_map)
    full_map = {**global_map, **repl_map}
    steps, warns = T.translate_offline(cleaned)
    steps = T.merge_typing_waits(steps, cleaned)
    if history_steps:
        steps = [s for s in history_steps + steps]
    T.normalize_step_people(steps, pre_mapping=full_map)
    T.cap_home_and_align_contacts(steps, warns)
    T.ensure_all_contacts_in_home(steps)
    T.convert_image_marker_steps(steps)
    T.convert_link_marker_steps(steps)

    warns = list(hist_warn) + list(warns)
    if warns:
        print(f"[警告] {len(warns)} 条：")
        for w in warns:
            print("  -", w)
            ok = False

    # ---- 1.5 因果检查：删除文字后不许对方即时回应 ----
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    causal = []
    for i, l in enumerate(raw_lines):
        if not l.startswith("[删除文字]"):
            continue
        for j in range(i + 1, min(i + 6, len(raw_lines))):
            nxt = raw_lines[j]
            if nxt.startswith("[对方") and not nxt.startswith("[对方后台"):
                causal.append(
                    "第%d行 [删除文字] 后紧跟「%s」——她不能回应没发出去的字；"
                    "对方反应应收进 [打字不发] 第 3 段多段插话（用「；」分隔）" % (j + 1, nxt)
                )
                break
            if nxt.startswith(("[我方打字]", "[打字不发]", "[打开聊天]", "[返回主页]")):
                break
    if causal:
        ok = False
        print("[因果] %d 处删除后对方即时回应：" % len(causal))
        for c in causal:
            print("  -", c)
    else:
        print("[因果] 删除文字后无对方即时回应（反应都在插话里）")

    # ---- 1.6 配图注释覆盖检查（2026-09-15 用户硬要求，只提示不拦截）----
    # 用户拿剧本去找照片时，希望每个图片槽上方就有一行「谁发·要什么效果·去哪找·呼应哪句」
    # 的 # 注释，而不是通读上下文才敢动手。注释是创作习惯、写详写略没有硬阈值，
    # 所以这里只出提示、不影响通过；运行时 parse_script_text 会整行跳过 # 行。
    _SLOT_RES = (
        re.compile(r"^\[(发送图片|对方发图片|点开图片|播放视频)\]"),
        re.compile(r"^\[对方后台发消息\].*\[(图片|配图)\]"),
        re.compile(r"^[^\[\s#][^:：]*[:：]\s*\[(图片|配图)\]"),   # 历史块 `某人：[图片] 描述`
    )

    def _is_slot(ln):
        return any(r.match(ln) for r in _SLOT_RES)

    missing = []
    for i, ln in enumerate(raw_lines):
        if not _is_slot(ln):
            continue
        # 逐条严格判定：每个槽位自己上方都要有一行 # 注释。
        # 早前把「连续多张（[点开图片] 序号=1,1 / 2,1）」当一组、只查第一条，
        # 结果第二条在配图清单里是个空白格——用户看不出点开的是谁的哪张，
        # 还是得回去通读上下文（2026-09-15 用户点名要改）。
        prev = raw_lines[i - 1] if i > 0 else ""
        if not prev.startswith("#"):
            missing.append((i + 1, ln))
    if missing:
        print("[提示] %d 处图片槽位上方没有配图注释（# 行）——"
              "写好「效果＝… ｜ 找图＝… ｜ 呼应＝…」，拿剧本找图时不用再通读上下文（不影响通过）；"
              "连着写两条 [点开图片] 时两条都要各写一行：" % len(missing))
        for lineno, ln in missing[:10]:
            print("  - 第%d行 %s" % (lineno, ln[:46]))

    # ---- 2. 创作模式同一套规则校验 ----
    skills = G.load_enabled_skills()
    issues, violated = G.validate_generated_steps(steps, skills, text)
    if issues:
        ok = False
        print(f"[问题] {len(issues)} 条：")
        for x in issues:
            print("  -", x)
    else:
        print("[规则] validate_generated_steps 全部通过（含规则库 %d 条）" % len(skills))

    # ---- 3. 素材引用逐个验证 ----
    bad = []
    soft_img = []
    for act, ref, kind in G._realtime_asset_refs(steps):
        if not G._asset_ref_resolvable(ref):
            near = G._nearest_asset_name(ref, kind)
            if kind == "image":
                # 2026-09-14 用户定调：图片描述允许清单外自造，跑视频前按名字上传即可，
                # 不再判失败（表情/贴纸没有配图面板兜底，仍然硬卡）。
                soft_img.append((act, ref))
            else:
                bad.append((act, ref, near))
    if bad:
        ok = False
        print("[素材] %d 个表情引用解析不到真图：" % len(bad))
        for act, ref, near in bad:
            print("  - [%s] %s%s" % (act, ref, ("  → 最接近：%s" % near) if near else ""))
    elif not soft_img:
        print("[素材] 实时段全部图片/表情引用都能解析到真图")
    if soft_img:
        print("[提示] 实时段 %d 张图片是自造描述（跑视频前按名字上传即可，不影响通过）：" % len(soft_img))
        for act, ref in soft_img:
            print("  - [%s] %s" % (act, ref))

    # ---- 3.5 待上传图片清单（只提示，不判定失败）----
    # 2026-09-14 用户定调：图片/封面描述允许清单外自造（跑视频前用户按名字上传图片，
    # 配图面板也能手动补）。这里把「当前图库里还缺哪些图」列成清单，方便照单上传。
    need_upload = []
    _hm = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text, re.S)
    # 历史块的图/链接封面不列入清单：列表页每行只显示该会话最后一条的文本，
    # 图片只显示「[图片]」、链接只显示「[链接]」——用户看不到图，不用准备素材。
    # （2026-09-14 用户实测「只有最后一句能看到」后改）
    if _hm:
        _hb_cnt = (len(re.findall(r"\[对方发图片\]", _hm.group(1)))
                   + len(re.findall(r"\[(?:图片|配图)\]", _hm.group(1)))
                   + len(re.findall(r"\[(?:我方发链接|对方发链接|发链接)\]", _hm.group(1))))
        if _hb_cnt:
            print("[提示] 历史块有 %d 处图片/链接标记——列表页只显示「[图片]」「[链接]」字样，"
                  "看不到内容，无需准备素材。" % _hb_cnt)
    for act, ref, kind in G._realtime_asset_refs(steps):
        if kind == "image" and not G._asset_ref_resolvable(ref):
            need_upload.append((act, ref))
    for s in steps:
        if isinstance(s, dict) and G._norm_action(s.get("action")) in ("我方发链接", "对方发链接"):
            p = s.get("params") or {}
            lt = str(p.get("标题") or "").strip()
            li = str(p.get("图片") or p.get("封面") or "").strip()
            if li and not G._link_cover_resolvable(lt, li):
                need_upload.append((G._norm_action(s.get("action")) + "封面", "%s（%s）" % (li, lt)))
    if need_upload:
        print("[提示] 以下 %d 处图片/封面图库里还没有，跑视频前按名字上传即可（不影响通过）："
              % len(need_upload))
        for a, r in need_upload:
            print("  - [%s] %s" % (a, r))
    else:
        print("[提示] 图片/封面全部命中现有图库，无需上传")

    # ---- 3.4b 我方发图不打开（2026-09-14 用户规则）----
    # 我方 [发送图片] 时自己已有预期，再写 打开=是 全屏打开很奇怪；
    # 要全屏暴击就让 [对方发图片] 来做。
    bad_self_open = [ln.strip() for ln in text.splitlines()
                     if ln.strip().startswith("[发送图片]") and "打开=是" in ln]
    if bad_self_open:
        ok = False
        print("[问题] 我方 [发送图片] 带 打开=是 共 %d 处 —— 发图时已有预期，打开很奇怪；"              % len(bad_self_open) + "去掉 打开=是（全屏暴击交给 [对方发图片]）：")
        for ln in bad_self_open:
            print("  - " + ln)
    meme_self_img = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("[发送图片]"):
            continue
        ref = s[len("[发送图片]"):].split("|")[0].replace("图片=", "").strip()
        if (re.search(r"表情包|梗图|沙雕|被摸头|被揉|卖萌|可爱|rua", ref)
                or (re.search(r"猫|狗|柴犬", ref) and re.search(r"享受|摸|揉|憨|瘫", ref))):
            meme_self_img.append(s)
    if meme_self_img:
        print("[提示] %d 处我方 [发送图片] 疑似纯表情包性质 —— 素材清单里有贴纸可代替，优先 [发送表情]；[发送图片] 留给剧情必需的具体画面：" % len(meme_self_img))
        for ln in meme_self_img:
            print("  - " + ln)


    # ---- 3.5c 素材易得度（2026-09-14 用户反馈：图片不要那么难找）----
    # 用户口径：图要么随手拍/相册翻就有，要么网上搜关键词一搜一大把；
    # 「要加工制作」（拼成/拼接/合成/裁出/红框）或「要造场景截图」
    # （朋友圈截图/弹窗截图/转账截图）的都拿不到——粉丝会话（引流图）例外。
    _CRAFT_RE = re.compile(r"拼成|拼接|拼图|合成|裁出|裁成|抠图|红框|红笔|加标注|九宫格拼")
    _SCENE_RE = re.compile(r"朋友圈[^，。\|]{0,4}截图|弹窗|转账[^，。\|]{0,4}截图|群聊[^，。\|]{0,4}截图"
                              r"|订单[^，。\|]{0,4}截图|短信[^，。\|]{0,4}截图|通话记录|打招呼[^，。\|]{0,4}截图|推销话术")
    _FANS_RE = re.compile(r"脱单教程|教程封面|案例解析|引流封面")
    _all_pics = [r for _a, r, _k in G._realtime_asset_refs(steps) if _k == "image"]
    _hm2 = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text, re.S)
    if _hm2:
        _all_pics += [x.strip() for x in re.findall(r"\[(?:图片|配图)\]\s*([^\|\n]+)", _hm2.group(1))]
        _all_pics += [x.strip() for x in re.findall(r"\[对方发图片\]\s*图片=([^\|\n]+)", _hm2.group(1))]
    _craft_pics, _scene_pics = [], []
    for _r in _all_pics:
        if not _r or _FANS_RE.search(_r):
            continue
        if _CRAFT_RE.search(_r):
            _craft_pics.append(_r)
        elif _SCENE_RE.search(_r):
            _scene_pics.append(_r)
    if _craft_pics:
        ok = False
        print("[问题] %d 张图要「加工制作」（拼成/裁出/红框/合成），用户没法快速拿到 —— 换成随手拍或网搜一搜就有的："
              % len(_craft_pics))
        for _r in _craft_pics:
            print("  - " + _r)
        print("      可换方向：一杯奶茶/外卖盒/猫/窗外晚霞/衣架上的裙子/自拍/美甲/票根。")
    if _scene_pics:
        ok = False
        print("[问题] %d 张图要「造场景截图」（朋友圈/弹窗/转账截图），用户手上没有 —— 换成实拍物："
              % len(_scene_pics))
        for _r in _scene_pics:
            print("  - " + _r)
        print("      单张手机自截的聊天界面可以（两秒能截），但别要求拼图或造不存在的记录。")

    # ---- 3.11 台词逻辑锚点（2026-09-14 用户反馈「这段打字莫名其妙」）----
    # 反例：她发自拍（照片主体=她），我方挑刺的结论却落在「我不够帅」上——照片里根本没有我，
    # 逻辑断裂 = 低级错误。挑刺/反说的落点必须与她发的东西同主体（照片→她/照片本身）。
    _MISANCHOR = re.compile(r"显得我不够帅|显得我不好看|显得我没(?:那么)?帅|把我拍得")
    _mis = [(i + 1, l.strip()) for i, l in enumerate(text.splitlines())
            if l.strip().startswith("[我方打字]") and _MISANCHOR.search(l)]
    if _mis:
        ok = False
        print("[问题] %d 处台词逻辑错位（挑刺/反说的落点没锚在对方发的东西上）：" % len(_mis))
        for _n, _l in _mis:
            print("  - 第%d行 %s" % (_n, _l))
        print("      反例：她发自拍 →「显得我不够帅」（照片里没有我，逻辑断了）")
        print("      正例：她发自拍 →「人比照片好看」「拍得你太好看 影响我睡觉」（落点回到她/照片本身）")

    # ---- 3.4c 内嵌表情名合法性（2026-09-14 发现）----
    # 消息文本里内嵌的 [名字] 只认 wxemoji3d_map.js 里的键（前端精确查表）；
    # 库里没有的名字 → 前端原样显示成「[大笑]」这种文字，气泡里很脏。
    _map_js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vue-WeChat", "src", "assets", "wxemoji3d_map.js")
    _emoji_names = set()
    if os.path.exists(_map_js):
        _jt = io.open(_map_js, encoding="utf-8").read()
        _emoji_names = set(re.findall(r'"([^"]{1,10})"\s*:', _jt)) | set(re.findall(r"'([^']{1,10})'\s*:", _jt))
    if _emoji_names:
        _ACT_PREFIX = ("对方", "我", "发送", "打开", "删除", "打字", "等待", "返回", "进入", "点开",
                       "滑", "历史", "会话", "后台", "正在输入", "重发", "撤回", "语音", "转账", "静音",
                       "图片", "配图", "视频", "链接", "表情", "文件", "动画表情")   # 历史块标记语法，不是内嵌表情
        _bad_inline = []
        for _ln in text.splitlines():
            _s = _ln.strip()
            if not _s:
                continue
            for _m in re.finditer(r"\[([^\[\]]{1,6})\]", _s):
                _nm = _m.group(1)
                if _s.startswith("[" + _nm + "]"):
                    continue
                if _nm.startswith(_ACT_PREFIX):
                    continue
                if _nm in _emoji_names:
                    continue
                _bad_inline.append((_nm, _s[:46]))
        if _bad_inline:
            ok = False
            print("[问题] %d 处内嵌表情名不在表情库里（前端会原样显示成「[XX]」文字）—— 改用库内真名：" % len(_bad_inline))
            for _nm, _ctx in _bad_inline[:8]:
                print("  - [%s]  ← %s" % (_nm, _ctx))
            print("      查名：py -c \"import script_generator as G; print(G._asset_block())\" 或 vue-WeChat/src/assets/wxemoji3d_map.js")
    # ---- 3.5b 图片描述清晰度（2026-09-14 用户反馈：要清晰到能直接去找素材）----
    # 标准：描述=主体+细节+画面形式（实拍/竖屏/特写…），拿到描述就能搜图/拍图。
    # 实时段自造图 <10 字 = 硬卡；历史块预览图 <8 字 = 提示。
    def _desc_plain(r):
        return len(re.sub(r"\s", "", r))
    def _is_shot(r):
        return bool(re.search(r"截图|长图", r))
    # 截图/长图类必须写清「谁的截图 + 截图上什么内容 + 形式」，门槛 ≥16 字
    # （2026-09-14 用户反馈：「聊天记录截图拼成的一张长图」不知道用什么图）；
    # 其余实时图 ≥10 字；历史块预览图 ≥8 字。
    short_rt = [(a, r) for a, r in need_upload
                if ("封面" not in a) and (a != "历史图片")
                and ((_is_shot(r) and _desc_plain(r) < 16)
                     or ((not _is_shot(r)) and _desc_plain(r) < 10))]
    short_hb = [(a, r) for a, r in need_upload
                if a == "历史图片" and _desc_plain(r) < 8]
    if short_rt:
        ok = False
        print("[问题] %d 张实时图描述不合格（用户没法照着找素材）—— 按「主体+细节+画面形式」补长：" % len(short_rt))
        for a, r in short_rt:
            print("  - [%s] %s" % (a, r))
        print("      普通图示例：「夜跑路上」→「夜晚城市江边跑步道 路灯下一双运动鞋特写 竖屏实拍」")
        print("      截图类示例：「聊天记录截图拼成的一张长图」→「微信聊天记录截图拼成的竖屏长图 男方连发多句土味话术 女方只回短句 红框圈住其中一句 手机截图」")
        print("      （截图/长图类须 ≥16 字：谁的截图 + 截图上什么内容 + 形式）")
    if short_hb:
        print("[提示] %d 张历史块预览图描述偏短（<8字），建议补细节（不卡通过）：" % len(short_hb))
        for a, r in short_hb:
            print("  - [%s] %s" % (a, r))

    # ---- 3.6 字幕长度提示（2026-09-28 更新口径：四目的，拆解/读她为主）----
    # 技巧拆解/读她/情绪 6~16 字、上限 20；钩子/CTA/下课允许到 40 字。
    long_caps = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("[打字不发]"):
            continue
        body = s[len("[打字不发]"):].split("|")[0].strip()
        if len(body) > 20:
            long_caps.append(body)
    if long_caps:
        print("[提示] %d 条字幕超过 20 字（口径：技巧拆解/读她/情绪 6~16 字、上限 20；"
              "钩子/CTA/下课允许到 40 字——非 CTA 的长句建议砍到「动作+目的」）：" % len(long_caps))
        for b in long_caps:
            print("  - [%d字] %s" % (len(b), b))

    # ---- 3.6b 模板字幕残留（2026-09-18 B4：字层旧兜底「塞模板」病灶的门禁回扫）----
    # 旧版字层失败时会把「顺手补一句」这类解说腔模板直接塞上屏 —— 观众一眼假。
    # 生成器侧已改为「重试→弃壳、永不塞模板」（script_generator._SUB_BLACKLIST），
    # 这里对最终成品兜底：历史稿/手写稿/二修稿里残留的模板字幕一律报问题。
    # 与 script_generator._SUB_BLACKLIST 保持同源（子串匹配，防「顺手补一句新的」变体漏网）。
    _SUB_TPL_BAN = ("稳住节奏", "顺手补一句", "继续推进", "先这样", "补一句", "推进节奏")
    _tpl_hits = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("[打字不发]"):
            continue
        body = s[len("[打字不发]"):].split("|")[0].strip()
        hit = next((t for t in _SUB_TPL_BAN if t in body), "")
        if hit:
            _tpl_hits.append(body)
    if _tpl_hits:
        ok = False
        print("[问题] %d 条字幕是旧兜底模板腔（字层生成失败时曾直接塞模板上屏，观众一眼假；"
              "现口径=重试后仍失败就弃壳，宁缺勿假）—— 换成真字幕或删掉整对壳：" % len(_tpl_hits))
        for b in _tpl_hits:
            print("  - %s" % b)

    # ---- 3.7 台词复读扫描（2026-09-14：LLM 审判通读查不出"散布式复读"，计数问题必须代码化）----
    # a) 完全重复的台词（同文出现在实时对白里 >=2 次，或后台消息文本与实时对白撞车）
    from collections import Counter
    live_texts = []
    bg_texts = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("[我方打字]") or s.startswith("[对方发消息]"):
            live_texts.append(s.split("]", 1)[1].split("|")[0].strip())
        elif s.startswith("[打字不发]"):
            # 字幕正文与插话段一并计入口癖统计（不计入同文复读判定）
            seg = s.split("]", 1)[1].split("|")
            if len(seg) >= 3 and seg[2].strip():
                live_texts.append(seg[2].strip())
        elif s.startswith("[对方后台发消息]"):
            parts = [x.strip() for x in s.split("|")]
            if len(parts) >= 2:
                bg_texts.append(parts[1])
    dup = [(t2, c) for t2, c in Counter(live_texts).items() if c >= 2 and t2]
    bg_hit = [b for b in bg_texts if b in set(live_texts)]
    if dup or bg_hit:
        print("[提示] 台词复读扫描发现（复读/双投是观众一眼能看出的硬伤，建议逐条改写）：")
        for t2, c in sorted(dup, key=lambda x: -x[1]):
            print("  - 同文实时台词 x%d：%s" % (c, t2))
        for b in bg_hit:
            print("  - 后台消息与实时对白同文双投：%s" % b)

    # b) 高频句式（3 字滑窗在对白全文出现 >=4 次 → 疑似口癖/句式复读）
    blob = "".join(live_texts)
    blob = "".join(ch for ch in blob if ch not in "，。！？；：、 	|")
    grams = Counter(blob[i:i+3] for i in range(len(blob) - 2))
    hot = [(g, c) for g, c in grams.items() if c >= 4 and not all(ch in "的了是不我你他她它啊呢吧吗哦嗯" for ch in g)]
    if hot:
        print("[提示] 高频 3 字片段（>=4 次，人工确认是否口癖复读）：")
        for g, c in sorted(hot, key=lambda x: -x[1])[:8]:
            print("  - %s x%d" % (g, c))

    # ---- 3.8 历史块检查（2026-09-14 用户实测：列表页每行只显示该会话【最后一条】消息）----
    # 渲染事实（vue-WeChat/src/components/wechat/msg-item.vue）：
    #   列表页只渲染 item.msg[item.msg.length-1].text，也就是每个会话的【最后一条】；
    #   图片消息显示「[图片]」、表情显示「[表情]」；前面几条在列表页完全看不到。
    # 因此：a) 会话写多条 → 提示（前面白写，唯一作用是未读角标数字）
    #       b) 只有「最后一条」是图/表情的会话，才在列表页留下「[图片]」这种行
    #       c) 每会话的钩子/擦边/信息必须压在这一条里自带，不能靠上一句铺垫
    # ★2026-09-16 更正：以上只对【不会被 [打开聊天] 打开】的会话成立。被打开的会话
    #   打开后聊天页渲染**全部**历史消息（dialogue.vue 遍历整条 msg 数组），所以这类
    #   会话的历史就该写成有来有回的一段对话（用户要求：打开里面就有信息，
    #   像「我们之前就聊了一些」），不受「压成 1 条」的限制。
    _open_contacts = G._opened_contacts(text)
    _hb_lasts_txt = ""
    _hfun = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text, re.S)
    if _hfun:
        _hb = _hfun.group(1)
        conns = []
        cur = None
        for _ln in _hb.splitlines():
            _s = _ln.strip()
            _m2 = re.match(r"^\[会话\]\s*(.+)$", _s)
            if _m2:
                cur = (_m2.group(1).strip(), [])
                conns.append(cur)
            elif cur is not None and _s:
                cur[1].append(_s)
        _VIS = re.compile(r"\[对方发图片\]|\[(?:图片|动画表情|表情)\]|对方表情|\[发送表情\]")
        _lasts = [c[1][-1] for c in conns if c[1]]
        _hb_lasts_txt = chr(10).join(_lasts)
        _multi = [c for c in conns
                  if len(c[1]) > 1 and "粉丝" not in c[0] and c[0] not in _open_contacts]
        if _multi:
            print("[提示] 历史块有 %d 个会话写了多条消息——这些会话【不会被打开】，"
                  "列表页只看得到最后一条，前面 %d 条看不见（唯一作用是未读角标数字）：%s"
                  "      ★想让擦边展开成一来一回，要放进「打开聊天」的会话（打开后全部可见，可多条）；"
                  "未打开的会话请压成 1 条。"
                  % (len(_multi), sum(len(c[1]) - 1 for c in _multi),
                     "、".join(c[0] for c in _multi[:4])))
        # 会被打开的会话：历史够不够「像聊过一段」（用户 2026-09-16 口径，提示级不拦截）
        _thin = [c[0] for c in conns
                 if c[0] in _open_contacts and "粉丝" not in c[0] and len(c[1]) < 6]
        if _thin:
            print("[提示] 会被 [打开聊天] 打开的会话历史偏薄（<6 条）：%s"
                  "      ★打开后聊天页渲染该会话全部历史 —— 应该写成有来有回的一段对话，"
                  "打开里面就有信息；素材可从其他剧本已收尾的会话搬（同一人物库）。"
                  % "、".join(_thin))
        if not [x for x in _lasts if _VIS.search(x)]:
            print("[提示] 历史块没有哪个会话的【最后一条】是图片/表情——列表页是一列纯文字行"
                  "（不算错；1~2 个会话把图放最后，列表行会出现「[图片]」更像真微信）")
        _HOOK = re.compile(r"[？?]|你|别想歪|猜|睡不着|一个人|抱抱|洗|撩|醉|冷|湿|腿|吊带|睡衣|怎么办|咋办|要不要|该不该|值得")
        _guys = [c for c in conns if c[1] and "粉丝" not in c[0]]
        _dull = [c[0] for c in _guys
                 if not _HOOK.search(c[1][-1]) and not _VIS.search(c[1][-1])]
        if _guys and len(_dull) == len(_guys):
            print("[提示] %d 个路人会话的最后一条既没问句也没钩子（列表页只看得到这一句）：%s"
                  % (len(_dull), "、".join(_dull[:5])))
        # 未打开会话的擦边话要「直接说给『我』听」——含第二人称「你」+ 邀约/暗示，才有点击欲；
        # 自言自语式的吐槽（「今天好累」「他都不理我」）不算擦边钩子。（2026-09-14 用户定标）
        # 未打开的会话只有最后一条可见：擦边要「说半句、留想象空间」——
        # 把话说完（后面接「你来…」式邀约）反而没味道。（2026-09-14 用户二次纠正：
        # 「半夜睡不着 你来陪我聊会儿」→ 取「半夜睡不着」就刚好）
        _SEXY_OVER = re.compile(r"你来(?:陪|接|不|嘛|吧)|来陪我|来接我|什么时候来|穿给你|想给你看|等我")
        _over = [c[0] for c in _guys if _SEXY_OVER.search(c[1][-1])]
        if _over:
            print("[提示] 历史块有 %d 个未打开会话的擦边话「说太满」（带明确邀约 / 把话说完了）：%s"
                  % (len(_over), "、".join(_over[:4])))
            print("      未打开的会话只有最后一条可见 —— 留半句、留想象空间，别在后面接「你来…」：")
            print("      「半夜睡不着 你来陪我聊会儿」→「半夜睡不着」；「一个人在家 有点冷 你来不来」→「一个人在家 有点冷」。")
    # ---- 3.9 梗密度提示（2026-09-14 用户反馈：总体不够有趣，没玩到很多梗）----
    _meme_words = ["栓Q", "纯爱战士", "海王", "舔狗", "画大饼", "画饼", "破防", "拿捏",
                   "上头", "发疯", "卑微", "已老实", "那咋了", "显眼包", "搭子", "内耗",
                   "松弛感", "偷感", "尊嘟", "退退退", "泰裤辣", "纯路人"]
    _meme_hits = sum(text.count(w) for w in _meme_words)
    # 图梗（错位暴击）：用户定标 2026-09-14 —— 先立预期再砸一张对不上的沙雕图，是最强笑点位
    _meme_pic_words = ["奶龙", "卡皮巴拉", "悲伤蛙", "汤姆猫", "奥特曼", "黑人问号", "旺仔",
                       "猫猫虫", "葫芦娃", "电线杆", "doge", "Doge", "沙雕", "梗图", "表情包大图"]
    _meme_pic_hits = sum(text.count(w) for w in _meme_pic_words)
    # 只算「发给女主的图」——粉丝会话的引流图（教程/封面/案例解析）不算图梗
    _mine_pics = [r for _a, r, _k in G._realtime_asset_refs(steps)
                  if _k == "image" and _a == "发送图片"
                  and not re.search(r"教程|封面|案例解析|引流|解析", r)]
    if _meme_pic_hits == 0 and not _mine_pics:
        print("[提示] 全篇没有一处图梗（错位暴击）—— 用户定标：图梗是最强笑点位，每篇建议 ≥1 处："
              + "她说喜欢高高瘦瘦的 → 「正好认识一个特别符合的」→ [发送图片] 图片=路边三根又细又高的电线杆并排 竖屏实拍 → 她笑骂收尾。")
    if _meme_hits < 2:
        print("[提示] 网络热梗只检出 %d 处（建议 2~4 处贴语境点缀）；金句梗/反差梗无法机检，" % _meme_hits
              + "按生成器「梗密度」规则逐条自查：土味金句 ≥1、反差自嘲 ≥1、总梗数 ≥4")

    # ---- 3.9c 全程引擎检查（2026-09-18：中后段不许退化成纯关心/伺候/查户口）----
    # 用户定调：可歪开场只是入场，中后段必须维持「智斗 + 暧昧」——至少 1 次
    # 「她试探 → 我方反将」，收尾前留 1 个反推拉/反转点，落点仍然极日常。
    # 语义没法机检，这里只量「退化信号」：实时段后半程我方消息几乎全是关心/伺候、零反击推拉。
    # ★内容类指标一律只做 [提示]、不判失败（门禁是下限不是验收，禁止逼模型删戏凑绿）。
    _FIGHT = re.compile(r"凭什么|那你呢|你说呢|谁更|你倒是|我可不|你猜|你确定|要不你|你敢|"
                        r"糊弄|蹬鼻子上脸|想得美|占我便宜|还收费|反过来|你自己说|给我个理由|"
                        r"你先说|轮不到|排第|前面还有|你数|数到")
    _SERVE = re.compile(r"多喝热水|早点睡|注意身体|别熬夜|好好休息|吃饭了吗|吃了吗|"
                        r"注意安全|照顾好自己|别累着|多穿点|记得吃药|我帮你|我陪你|"
                        r"要不要我|我过来|给你带|我来吧|听你的|都依你|别难过|别生气|"
                        r"你先睡|保重|小心点|慢慢来")
    _my_msgs = []
    for _s in steps:
        if isinstance(_s, dict) and G._norm_action(_s.get("action")) == "我方打字":
            _c = str((_s.get("params") or {}).get("内容") or "").strip()
            if _c:
                _my_msgs.append(_c)
    if _my_msgs:
        _half = _my_msgs[len(_my_msgs) // 2:]
        _serve_hits = [_m for _m in _half if _SERVE.search(_m)]
        if len(_serve_hits) >= 3 and not any(_FIGHT.search(_m) for _m in _half):
            print("[提示] 全程引擎疑似断线：实时段后半程 %d 条我方消息几乎全是关心/伺候、零反击或推拉——"
                  % len(_serve_hits)
                  + "用户定调：中后段不许退化成纯关心/查户口，至少 1 次「她试探 → 我方反将」，"
                  + "收尾前留 1 个反推拉（站楼下不上楼）或反转点（回头看整局是她安排的）。")
        if not any(_FIGHT.search(_m) for _m in _my_msgs):
            print("[提示] 全篇没检出「反将/推拉」类我方台词（凭什么/那你呢/你倒是/排第几…）——"
                  + "全程引擎靠这个撑张力与暧昧；若选题本身就是纯安慰型可忽略。")

    # ---- 3.9d 近似复读（提示级，2026-09-18 补）----
    # 门禁已有「同一句话说了两遍」的[问题]级检查，但那是**精确字符比对** ——
    # 抓不到「我平时不这样的 平常挺腼腆的[捂脸]」与「我平时不这样的 平常挺腼腆」这种
    # 改个尾字/多带一个 emoji 的复读（v6 实测漏网，而门禁自己也说复读是「观众一眼能看出的硬伤」）。
    # 这里按「去内嵌 emoji + 去标点空格 + 去语气尾字」归一后比对，只做提示、不动既有判定。
    _dup_key = {}
    for _s in steps:
        if not isinstance(_s, dict):
            continue
        if G._norm_action(_s.get("action")) not in ("我方打字", "对方发消息"):
            continue
        _raw = str((_s.get("params") or {}).get("内容") or "").strip()
        if not _raw:
            continue
        _k = re.sub(r"\[[^\[\]]{1,6}\]", "", _raw)
        _k = re.sub(r"[\s，。！？、,.!?~～…]+", "", _k)
        _k = _k.rstrip("的了吧啊呀嘛呢哦嗯哈")
        if len(_k) >= 8:
            _dup_key.setdefault(_k, []).append(_raw)
    _near = {k: list(dict.fromkeys(v)) for k, v in _dup_key.items() if len(v) > 1}
    if _near:
        print("[提示] 近似复读 %d 组（去掉内嵌 emoji / 语气尾字后是同一句，观众看起来就是复读）：" % len(_near))
        for _k, _v in list(_near.items())[:4]:
            print("  - " + _k[:18] + "：" + " ／ ".join(_v)[:70])

    # ---- 3.10 三层分工检查（2026-09-14 用户定标：引流 / 趣味 / 历史块 各司其职）----
    # 用户原话：开局女生性感图 或 擦边暗示话题 = 引流；后续聊天的智斗 = 有趣；要区分开。
    # 历史会话里「没被打开」的会话可以用擦边话术（如「姨妈来了 我那里湿透了」这类半截话）。
    # 全部为提示级（不同选题适配度不同），不判失败。
    _SEXY_PIC = re.compile(r"吊带|睡衣|浴巾|浴缸|浴室|刚洗完澡|刚冲完凉|湿发|微湿|马甲线|健身|瑜伽|丝袜|短裙|露肩|深V|锁骨|对镜自拍|口红印|长腿|细腰")
    _SEXY_TALK = re.compile(r"一个人在家|怕黑|好追吗|身材|穿什么|穿得少|穿那么少|湿了|湿透|睡不着|抱一下|抱抱|亲我|腿.{0,2}软|心跳|撩我|想你了|睡衣|床上|洗澡|短裙|裙子|吊带|锁骨|长腿|低胸|过膝袜|黑丝|不舒服|腿软|就剩我")
    _hb_m = re.search(r"\[历史会话\](.*?)\[历史会话结束\]", text, re.S)
    _rt_text = text[_hb_m.end():] if _hb_m else text
    _rt_acts = [ln.strip() for ln in _rt_text.splitlines() if ln.strip().startswith("[")][:14]
    # 历史块只取每会话【最后一条】（列表页唯一可见的内容）
    _open_txt = ((_hb_lasts_txt if _hb_m else "") + chr(10) + chr(10).join(_rt_acts))
    _open_pics = re.findall(r"图片=([^|" + chr(10) + r"]+)", _open_txt)
    _head_pic = [r for r in _open_pics if _SEXY_PIC.search(r)]
    _head_talk = [ln for ln in _open_txt.splitlines() if _SEXY_TALK.search(ln)]
    if not _head_pic and not _head_talk:
        print("[提示] 开局（前 14 个动作）没有「性感氛围图」或「擦边暗示话题」——用户定标：开局引流靠这个拉停留。"
              "可加：她发一张刚洗完澡的对镜自拍/吊带裙（性感到位不露点），或第一句擦边暗示「刚洗完澡」「一个人在家有点怕」「你猜我现在穿什么」。")
    if _hb_m:
        _hb_seg = _hb_lasts_txt   # 只算每会话最后一条（列表页唯一可见）
        if not _SEXY_TALK.search(_hb_lasts_txt) and not _SEXY_PIC.search(_hb_lasts_txt):
            print("[提示] 历史块没有擦边/暧昧钩子（未打开的会话可用）——用户定标：让列表页有故事感。"
                  "★写法：**一句半截话、留想象空间**（不要铺垫+反转，也不要加「别想歪」式解释，更不要把话说完）："
                  "「半夜睡不着」「一个人在家 有点冷」「刚洗完澡 头发还湿着」「我那里不舒服」「加班到腿软」；"
                  "**被打开（打开=是）的会话没这个限制，擦边可以写多条、展开成一来一回**。"
                  "红线仍成立：只做钩子不做内容，露骨描写禁止。")
    # ---- 3.12 插话主体（2026-09-14 用户实测：插话槽被写成了「我方心理」）----
    # `[打字不发] 字幕 | 停留 | 插话` 的第 3 段是【她发来的消息】（参考原文 18 处插话
    # 全是她的口吻：「说呗；你都拿到我联系方式了，还有什么不好说的」）。
    # 用户抓到的反例：`… | 大半夜发这个；这是明着钓我`——「发这个」的施事是她自己发的图，
    # 她不可能说自己发图来「钓我」，整句前后矛盾；`…；可爱`／`…；见好就收`／`…；看你怎么圆`
    # 同属我方评价或教学策略。判据：
    #   a) 插话里出现我方教学/策略词   → 判问题
    #   b) 插话是我方视角（她说不出）  → 判问题
    #   c) 插话在点评她自己刚发的东西  → 判问题
    #   d) 插话复述她上一条已说过的话  → 提示（要有新信息）
    _TT_STRATEGY = re.compile(
        r"见好就收|看你怎么圆|给个?台阶|留个口子|稳住|不解释|别秒回|收线|铺垫|反差|挑刺|揽责|"
        r"金句|图梗|战术|打法|教学|话术|钩子|留白|复盘|暴击|擦边|引流|反将|正话反说|先抑后扬|"
        r"接住|得接|控场|点题|收网|收官")
    _TT_MYVOICE = re.compile(r"明着.{0,3}(?:我|钓|撩|套路)|吊着我|明明在等我|这是钓我|看你怎么")
    _TT_MYWORD = re.compile(r"可爱|心疼|挺好看|真好看|贤惠|体贴")
    _TT_NOTE = re.compile(r"这是|先|别|得|要|该|等于|比|接住|记住|优先|直接|再收|差不多|尽量")
    _TT_TONE = re.compile(r"[？?！!]|吧|呗|啊|呀|嘛|哈|啦|哦|哟|嗯|了|的|呢|着|谁|哪|不")
    _tt_lines = [(i + 1, l.strip()) for i, l in enumerate(text.splitlines())
                 if l.strip().startswith("[打字不发]")]
    _tt_bad = []
    for _n, _l in _tt_lines:
        _seg = _l[len("[打字不发]"):].split("|")
        if len(_seg) < 3 or not _seg[2].strip():
            continue
        for _part in [x.strip() for x in re.split(r"；", _seg[2]) if x.strip()]:
            _plain = re.sub(r"\[[^\[\]]{1,8}\]", "", _part)   # 去掉 [对方表情] 等行首标记
            _why = None
            if _TT_STRATEGY.search(_plain):
                _why = "出现我方教学/策略词（观众会看到她的气泡里出现我的打法说明）"
            elif _TT_MYVOICE.search(_plain):
                _why = "是我方视角，她说不出这句"
            elif _TT_MYWORD.search(_plain) and not re.search(r"你", _plain):
                _why = "是我方对她的评价（她的气泡里不会出现我夸她的话）"
            elif (re.search(r"照片|自拍|这张图|这图|光线|角度|拍得|发图|发照片|发这个|发这种", _plain)
                  and not re.search(r"[你我]", _plain)):
                _why = "在点评她自己刚发的东西（点评她的自拍是我的活儿）"
            elif (len(_plain) >= 5 and not re.search(r"[你我]", _plain)
                  and not _TT_TONE.search(_plain) and _TT_NOTE.search(_plain)):
                _why = "像我的备注不像她的话（全无人称、也没有语气词/问句）"
            if _why:
                _tt_bad.append((_n, _part, _why))
    if _tt_bad:
        ok = False
        print("[问题] %d 处 [打字不发] 第 3 段「插话」写成了我方的话（插话=【她】发来的消息）："
              % len(_tt_bad))
        for _n, _part, _why in _tt_bad:
            print("  - 第%d行 插话「%s」→ %s" % (_n, _part, _why))
        print("      反例：`… | 大半夜发这个；这是明着钓我`（她自己发的图，不会说自己发图来钓我）")
        print("             `…；可爱`／`…；见好就收`／`…；看你怎么圆`（我方评价/策略）")
        print("      正例：`… | 就等你一句话呢`／`… | 睡了 不跟你说了`／`… | 说呗；你都拿到我联系方式了，还有什么不好说的`")
    # d) 插话复述她上一条 → 提示（插话必须有新信息）
    _tt_dup = []
    _raw = [l.strip() for l in text.splitlines() if l.strip()]
    for _i, _l in enumerate(_raw):
        if not _l.startswith("[打字不发]"):
            continue
        _seg = _l[len("[打字不发]"):].split("|")
        if len(_seg) < 3:
            continue
        _prev = " ".join(_raw[_j] for _j in range(max(0, _i - 6), _i)
                         if _raw[_j].startswith(("[对方发消息]", "[对方发图片]", "[对方表情]")))
        if not _prev:
            continue
        for _part in [x.strip() for x in re.split(r"；", _seg[2]) if len(x.strip()) >= 5]:
            # 最长公共子串：命中的片段要占插话本身的 60% 以上才算「复述」
            # （避免把合理呼应误判，如「越描越黑 我还是先认账吧」对上「先挑刺还是先认账」）
            _best = 0
            for _s in range(len(_part)):
                for _e in range(len(_part), _s + _best, -1):
                    if _part[_s:_e] in _prev:
                        _best = max(_best, _e - _s)
                        break
            if _best >= 5 and _best >= 0.6 * len(_part):
                _tt_dup.append((_i + 1, _part))
    if _tt_dup:
        print("[提示] %d 处插话几乎复述了她刚说过的话（插话要有新信息，不能只是重复）："
              % len(_tt_dup))
        for _n, _part in _tt_dup:
            print("  - 第%d行 插话「%s」" % (_n, _part))

    # ---- 3.14 开场评图模板（2026-09-14 用户第 4 次实测：「女生说自己胖了开头没说，每篇开头都在评价对方照片」）----
    # 病灶：把「评价她的照片」当成万能开场（照片我看了/先说结论/三个问题/刚那条裙子我看了/头像鉴定），
    # 选题本身她一句没说，视频前 10 秒在对一张图打分。正确写法：她先开口点题（把选题说出口，
    # 或用图/状态把处境摆出来），我方第一句回应她的话或她的处境；评图只能当她的图的「证据回应」，
    # 且落点必须在她本人，不许是打分式（好看/角度不行/配不上）。
    _OPEN_CRUTCH = (
        re.compile(r"照片我看了|先说结论|头像我已经鉴定|^三个问题$"),
        re.compile(r"刚那条.{0,8}我看了|刚那张.{0,8}我看了"),
    )
    _op_all = []
    _op_i = 0
    for _ln in text.splitlines():
        _s = _ln.strip()
        if _s.startswith("[打开聊天]") or _s.startswith("[返回主页]"):
            _op_i = 0
        elif _s.startswith("[我方打字]"):
            _op_i += 1
            if _op_i <= 6:
                _op_all.append(_s[len("[我方打字]"):].strip())
    for _txt in _op_all:
        for _rx in _OPEN_CRUTCH:
            if _rx.search(_txt):
                ok = False
                print("[问题] 3.14 开场评图模板：我方开场打分式评图「%s」——她还没把选题说出口。开场必须她先点题、我方第一句回应她的话（或她的处境），评图只能当证据回应" % _txt)
                break


    # ---- 3.13 承接断链（2026-09-14 用户第 3 次实测：「关你什么事」→「这事怪我」接不上）----
    # 病灶：[打字不发] 的插话槽 = 「我打字期间她发来的消息」，它和【我删掉草稿之后发的那句】
    # 必须形成一问一答。两个典型断链：
    #   ① 回应型孤立句：她说「关你什么事／管得着吗／要你管」，但上文我根本没管过她 → 她这句无源；
    #   ② 认责句空降：她说的是「疼死了都」，我下一句却「这事怪我」——她没怪过我，我认什么责。
    # 规律：插话必须接得住我上一条【已发送】的消息（打字没发的不算）；我下一句必须是她插话的答。
    _LK_ISO = re.compile(r"关你(?:什么|屁)?事|管得着吗|要你管|你管我|少管闲事|不关你的事")
    _LK_ANS = re.compile(r"不关|不管|就管|想管|管的|听语气|讲道理|心情|规矩|说清楚|凭什么|别管|你管")
    _LK_CARE = re.compile(r"管|关心|问|劝|操心|担心|照顾|唠叨|提醒|别熬夜|早点|多穿|少喝")
    _LK_ATTR = re.compile(r"怪|怨|赖|还不是你|你害|都因为你")
    _LK_SELF = ("这事怪我", "这怪我", "那怪我", "都怪我", "我的错", "我的问题", "是我的问题",
                "是我不好", "我不好", "是我的错")
    _LK_CHAIN = re.compile(r"推远|搞乱|着急|没分寸|对不住|对不起|不该|惹|证明我|没顾|忽略|太急")
    _lk_raw = [l.strip() for l in text.splitlines() if l.strip()]
    _lk_ev = []
    for _i, _l in enumerate(_lk_raw):
        if _l.startswith(("[对方发消息]", "[对方发图片]", "[对方表情]", "[对方语音]", "[对方撤回]")):
            _lk_ev.append(("her", _i, _l))
        elif _l.startswith(("[我方打字]", "[发送图片]", "[我方表情]", "[我方语音]")):
            _lk_ev.append(("me", _i, _l))
        elif _l.startswith("[打字不发]"):
            _sg = _l[len("[打字不发]"):].split("|")
            if len(_sg) >= 3 and _sg[2].strip():
                _lk_ev.append(("ij", _i, _sg[2].strip()))
    _lk_bad = []
    for _k, (_kd, _ix, _s) in enumerate(_lk_ev):
        if _kd == "ij":
            _parts = [x.strip() for x in re.split(r"；", _s) if x.strip()]
            _iso = [p for p in _parts if _LK_ISO.search(p)]
            _nxt = ""
            for _j in range(_k + 1, len(_lk_ev)):
                if _lk_ev[_j][0] == "me":
                    _nxt = _lk_ev[_j][2]
                    break
            if _iso:
                _prev = ""
                for _j in range(_k - 1, -1, -1):
                    if _lk_ev[_j][0] == "me":
                        _prev = _lk_ev[_j][2]
                        break
                if not _LK_CARE.search(_prev):
                    _lk_bad.append((_ix + 1, _iso[0],
                                    "回应型孤立句——上文我最后一条是「%s」，没有任何我管过她的内容，她为什么说这句？"
                                    % re.sub(r"^\[[^\]]+\]\s*", "", _prev)[:16]))
                _nb = re.sub(r"^\[[^\]]+\]\s*", "", _nxt)
                if _nxt and not _LK_ANS.search(_nb):
                    _lk_bad.append((_lk_ev[_k + 1][1] + 1 if _nxt == _lk_ev[_k + 1][2] else _ix + 1,
                                    _nb[:20], "答非所问——她插话「%s」，我下一句「%s」接不住" % (_iso[0][:12], _nb[:14])))
        elif _kd == "me":
            _b = re.sub(r"^\[[^\]]+\]\s*", "", _s)
            if re.match(r"^(?:我说了|我说过|刚说了|我都说了)\s*", _b):
                continue
            if _b in _LK_SELF:
                _pre = _lk_ev[max(0, _k - 4):_k]
                _ptxt = " ".join(x[2] for x in _pre)
                _mtxt = " ".join(x[2] for x in _pre if x[0] == "me")
                _hers = " / ".join(re.sub(r"^\[[^\]]+\]\s*", "", x[2])[:14]
                                   for x in _pre if x[0] in ("her", "ij"))
                if not _LK_ATTR.search(_ptxt) and len(set(_LK_CHAIN.findall(_mtxt))) < 2:
                    _lk_bad.append((_ix + 1, _b,
                                    "认责句空降——前文她没怪过我（最近她的话：%s），这句「%s」没有归因"
                                    % (_hers[:60] or "无", _b[:12])))
    if _lk_bad:
        ok = False
        print("[问题] %d 处相邻话语接不上（承接断链）：" % len(_lk_bad))
        for _n, _txt, _why in _lk_bad:
            print("  - 第%d行 「%s」→ %s" % (_n, _txt, _why))
        print("      反例①：他上一句只是「疼死了都」→ 我删掉草稿后发「这事怪我」（她没怪我，我认什么责）")
        print("      反例②：插话「关你什么事」——上文我最后一条是「我这人最听话」，没有我管过她的内容")
        print("      正例①：她「都怪你」→ 我「这事怪我」→ 她「怪你什么」→ 我「昨天就该拦着你吃那碗冰」")
        print("      正例②：她「你管我」→ 我「管你是因为你是我搭子」（我上文确实管了她穿衣喝冰）")
        print("      ★写法：插话必须是我【已发送】那条消息的自然反应；删掉草稿后发的那句，必须直接答她插话。")

    # ---- 3.14 多参数动作的「|」分隔（2026-09-16 十五连2 实测）----
    # 反例：`[点开图片] 序号=1,1 停留=0.3`（漏了 `|`）——解析器按 `|` 分段，
    # 整段被当成「序号 = "1,1 停留=0.3"」：停留值被吞、序号变脏，画面按默认值走。
    # 判据：该动作参数 ≥2 个、行内没有 `|`、却出现了「=值 空白 键=」的形状。
    try:
        import action_registry as _reg                      # noqa: PLC0415
        _pdef = _reg.param_defaults() or {}
    except Exception:                                       # noqa: BLE001
        _pdef = {}
    _bad_sep = []
    for _n, _ln in enumerate(text.splitlines(), start=1):
        _s = _ln.strip()
        _m = re.match(r"^\[([^\[\]]+)\]\s*(\S.*)$", _s)
        if not _m:
            continue
        _cmd, _arg = _m.group(1).strip(), _m.group(2).strip()
        if len((_pdef.get(_cmd) or {})) < 2 or "|" in _arg:
            continue
        if re.search(r"=\S*\s+\S*=", _arg):
            _bad_sep.append((_n, _s))
    if _bad_sep:
        ok = False
        print("[问题] %d 处多参数动作漏写「|」分隔（后面的参数会被整段吞进前一个参数）：" % len(_bad_sep))
        for _n, _s in _bad_sep[:6]:
            print("  - 第%d行 %s" % (_n, _s[:64]))
        print("      正确写法：多个参数之间用 `|` 分隔 —— `[点开图片] 序号=1,1 | 停留=0.3`、"
              "`[我方发链接] 标题=xxx | 图片=yyy`；缺 `|` 时后一个参数会并进前一个，画面/标题就脏了。")

    # ---- 3.15 点图前置动作（2026-09-16 十五连2 实测：13/14 篇漏了，点开的是「我的朋友圈」）----
    # `[点开图片]` 的口径是「点开对方朋友圈动态里的配图（没进对方朋友圈时才用我的朋友圈）」，
    # 所以前面必须有进朋友圈的动作，否则画面点开的是错的人、台词「你朋友圈那张」当场对不上。
    _all_lines = [x.strip() for x in text.splitlines()]
    _bad_pic_ctx = []
    for _n, _s in enumerate(_all_lines, start=1):
        if not _s.startswith("[点开图片]"):
            continue
        _prev = _all_lines[max(0, _n - 11):_n - 1]
        if not any(x.startswith(("[打开对方主页]", "[进入对方朋友圈]", "[打开我的朋友圈]",
                                "[打开朋友圈]"))
                   for x in _prev):
            _bad_pic_ctx.append((_n, _s))
    if _bad_pic_ctx:
        ok = False
        print("[问题] %d 处 [点开图片] 前面没有「进朋友圈」的前置动作（会点开成我的朋友圈，画面/台词对不上）："
              % len(_bad_pic_ctx))
        for _n, _s in _bad_pic_ctx[:6]:
            print("  - 第%d行 %s" % (_n, _s[:64]))
        print("      正确四连：`[打开对方主页] 名` → `[进入对方朋友圈]` → `[点开图片] 序号=1,1 | 停留=0.3` → `[闪回聊天] 回到=名 | 闪黑=否`")

    # ---- 4. 关键指标 ----
    hist, real = G._count_history_and_realtime(text)
    holds = G._count_typing_hold(steps)
    ij = G._count_interjections(steps)
    sessions = text.count("[会话]")
    distinct, top, top_name = G._emoji_repeat_stats(steps)
    total_emoji = G._count_emoji_total(steps)
    n_steps = len(steps)
    total, max_run, ratio = G._dialogue_runs(steps)
    # 阈值一律从规则库实读，避免默认值改了而这里还印着旧数字（表情总额默认 0=不限，
    # 印成「≤10」会把合规的剧本显示成越线）。
    _rn = G.rule_numbers()
    _emj_cap = int(_rn.get("max_emoji_total") or 0)
    _same_cap = int(_rn.get("max_same_emoji") or 0)
    _ij_min = int(_rn.get("min_interjections") or 0)
    _hold_min = int(_rn.get("min_typing_hold") or 0)
    print("[指标] 步数 %d（≤%d） | 实时对白 %d（≥%d） | 打字不发 %d（≥%d） | 插话 %d（≥%d）"
          % (n_steps, int(_rn.get("max_script_steps") or 0), real,
             int(_rn.get("min_realtime_lines") or 0), holds, _hold_min, ij, _ij_min))
    print("[指标] 历史消息 %d | 会话 %d（≥9） | 表情总数 %d（%s） | 同名表情最高重复 %d（%s）"
          % (hist, sessions, total_emoji,
             ("≤%d" % _emj_cap) if _emj_cap else "不限",
             top, ("≤%d" % _same_cap) if _same_cap else "不限"))
    print("[指标] 实时对白 %d 条 | 最长连发 %d | 交替率 %.2f（≤0.75）" % (total, max_run, ratio))
    return ok


def main():
    files = sys.argv[1:]
    if not files:
        print(__doc__)
        return
    all_ok = True
    for f in files:
        if not os.path.isfile(f):
            print("文件不存在：", f)
            all_ok = False
            continue
        if not check_file(f):
            all_ok = False
    print("=" * 72)
    print("结论：", "全部通过 ✅" if all_ok else "存在问题，需要修 ❌")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
