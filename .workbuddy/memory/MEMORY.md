# F:\weixin-auto 长期备忘（精简工作版）
> 版本史/长版全文见 `MEMORY_full_archive.md`（含 2026-09-21 精简前完整快照）；逐日细节见 `YYYY-MM-DD.md` 日志。

## 一、写稿三路线（用户定调）
- **参考改编（默认）**：不从零写。拿主题最近的参考稿做底稿，保留骨架与 ~85% 对话，只改 4~6 处（开场可歪钩子／补反将／教学点对题／字幕瘦身），成稿附《修改对照说明》。底稿池=`剧本库\*.txt`（30 篇，已统一新指令名+拆行插话）；作业书=skill「创作模式全流程」路线 C。
- **桥段库**：真实精彩男女对话片段丢 `剧本库\_桥段库\`（体例见该目录 `片段收集体例.md`）→ 打标签入库 → 写稿按拍子检索 → **对话原句照搬**，只改人名／话题锚点／承接句。我的角色=剪辑师不是编剧。
- **创作模式 v2**：Beat Sheet→骨架→逐块填充（戏层 AI 写对话→壳层代码卡位→字层 AI 只填字幕）→机械门→终审；戏层只吃 `content_only_rules()` 过滤后的规则库。

## 二、剧本硬规则（权威=`创作模式_打字不发博弈字幕规范.md`；索引=`剧本库\剧本创作规则总览.md`）
- **指令名**（新名优先，旧名永久兼容）：[我方打字]→**[我方发消息]**｜[打字不发]→**[观众字幕]**｜[删除文字]→**[清空输入框]**｜[发送X]→**[我方发X]**｜[对方X]→**[对方发X]**。归一=ACTION_ALIASES（main.py/script_translator.py）；展示映射=script_generator `_ACTION_DISPLAY_RENAME`；**参考稿全文进提示词前经 `_norm_ref_text` 归一新名（勿删）**。
- **拆行插话**：`[观众字幕] 字幕 | 0.5` 的**下一行**写 `[她插话] 她的真消息`（只能紧跟 [观众字幕]/[我方发消息] 行，写别处=丢消息+门禁 fail）。
- **字幕性质**：回指讲解「刚发出去的那句」（金样 52%），不是预告旁白。四类用法：打法型 ~6 成／战况解读 ~2-3 成／情绪失守 ~5%（调料）／引流下课 10%。字幕 2~10 字，硬上限 14。
- **开局引擎**：话题诱惑性优先——她抛语义双关（宾语空着）→≥3 拍递进→我方只追问不点破→落点极日常；禁「别想歪 是XX」式解释；合规=零露骨词/零身体描写。
- **全程引擎**：中后段不许退化成纯关心；维持她试探→我方反将、模糊叙述吊、推拉、终局反转。
- **机械门硬指标**：步数≤200、实时对白≥110、打字不发≥15、插话≥5、会话≥9、表情≥6 种且同名≤2、**交替率≤0.75**、**[等待]占比≤60%**、主页会话≤10；CTA=「想要聊天秘籍的兄弟 点赞关注扣6我安排」。
- 其他硬点：≥6 条历史的会话才配 [打开聊天]；需上传实时图≤5；`[清空输入框] -1` 后对方不能立刻回应；点图四连必真点图；**台词提朋友圈必须真打开朋友圈**；画面外动作（换头像/改备注/设背景）禁令；多参数必须用 `|`；短名错一字=整图空白。
- 质检：`python _check_script_quality.py <文件…>`（可批量；批量模式只在最后打一条总结论，逐文件要看 `[问题]` 行）。`[提示]` 可不改，`[问题]` 必修。

## 三、编辑器 / 渲染
- 真渲染器=`main.py --editmode --headless --liveport 8001`（改 enhance 须重启）；ffmpeg 用 imageio_ffmpeg。
- 聊天背景层画在 `.dialogue::before`（画回 `.dialogue-section` 会随键盘上移）。
- 自动出图预览 autoRef→`/api/resolve-refs`；朋友圈预览=`editor/moments_preview.js`。
- 3 入口：工作流／脚本／并发（concurrent.html）；片头三选一，改片头用 `POST /api/tasks/<id> {options:{intro_path}}`，别手改 tasks.json；批量灌入=`_probe_tmp/_conc_import_batch.py`。

## 四、素材与归档
- 片头壁纸 `public/images/introwall/`；聊天背景 `public/images/bg`（别混）。头像在 `/images/avatar/`，选角见 `长图模式\头像选角表.md`（男生固定「男_竹林幽经.jpg」，女生跑 `随机女头.py`）。
- 定稿 → `剧本库\成品\<批次>_<日期>_<主题>\`（N 篇 txt + 00_总任务书.md + 配图清单.md + README.md），只复制不移动，过程材料留 `_inprogress\`。
- **来源标记（用户导入 / AI生成）**：每篇剧本首行 `# 来源：… · 出处：…`（`#` 行解析器整行跳过，加了不影响跑片）。工具 `_tag_script_source.py`（系统 Py312）：`--scan`／`--apply`／`--strip`（回滚）／`--report`（出 `剧本库\_来源台账.md`+`.json`）／`--set 路径 值 [出处]`（写 `_来源覆盖.json`，最高优先）。**改判定逻辑后必须复跑 `--scan` 确认与加标记前逐行一致**——标记会稀释 6-gram 并挤掉首行 `# 选题：`，判定一律走 `read_body()`（先 strip_tag）。台账基线：135 篇＝用户导入 9（手搓 7 篇 + 2 份参考件副本）｜AI生成 126。
- **编辑器来源字段叫 `origin`/`origin_note`，别和既有的 `source` 混**（`source` 是解析方式 llm/offline）。导入弹窗有「剧本来源」下拉（自动识别/用户导入/AI生成），任务卡有 👤/🤖 chip，标题栏计 `· 👤n 🤖n`。

## 五、环境与排障铁律
- 系统 Python **3.12.10**（`%LOCALAPPDATA%\Programs\Python\Python312\`）；托管 3.13 缺 playwright → 机械门会全篇误报，**别用**。主程序依赖 7 个：playwright／imageio-ffmpeg／pypinyin／pillow／jieba／numpy／scipy。playwright 内核需 `chromium_headless_shell-1243`（`playwright install chromium` 不会装，缺了报 Executable doesn't exist），国内走 npmmirror。
- **跑真管线前清代理**：`Remove-Item Env:HTTP_PROXY` + `$env:NO_PROXY="localhost,127.0.0.1"`（否则永久卡在「等待前端就绪」）；加 `python -u` 才看得到输出。
- **改完必 grep 确认落盘**（Edit 会静默丢编辑）；editor_server.py 改完重启；前端 html/js 每请求读盘，让用户 Ctrl+Shift+R。
- **新建/改写 .bat 必须 CRLF**（否则双击闪退）；老 bat=GBK 无 chcp，新 bat=UTF-8 无 BOM + `chcp 65001`，别混。
- 工具链：bash 工具链坏 → 全程 PowerShell；PowerShell stdout 常被吞 → 写文件再 Read；Python 中文输出需 `[Console]::OutputEncoding=UTF8` + `PYTHONIOENCODING=utf-8`。
- Git：`git add -u` + 显式列新增路径，**禁 `git add -A/.`**；提交前跑 `_工作文件/_git_precheck.py`（查 sk-/大文件），提交脚本 `_工作文件/_git_commit_0918.py`。素材图不入库。**注：这两个脚本内 `REPO` 写死 `F:\weixin-auto`，而仓库现在实际在 `E:\weixin-auto`（F 盘已不存在）→ 直接跑会失败，要么改盘符，要么按同规则手动走 `git add -u` + 显式列新增。**
- **推送习惯：`main` 与 `feat/emoji-panel-press-anim` 两个远程分支始终指向同一提交**，推完记得两边都推并 `git branch -f main HEAD`。`_backup_*` 备份目录是入库的（与 `_工作文件/_归档_临时文件/_probe_tmp/_inprogress_*` 不同，后四者 gitignore）。
- tasks.json 会被「空内存表」覆盖：动手前先停 8000 服务；恢复源 `_probe_tmp/tasks_api.json`。**且它是运行时热写文件——服务在跑时 `git add` 会抓到 32KB 截断版甚至 0 字节版并提交进去（JSON 解析直接失败）。稳妥做法：`hash-object -w` 存一份校验过的快照（>500KB 且 `json.loads` 通过、任务数=15），再 `git update-index --cacheinfo 100644,<sha>,tasks.json` 写入索引后提交，绕开工作区竞争。**
- 判 Python 可用性必须 `python --version` 实测（WindowsApps 的 python.exe 是 0 字节占位符）。

## 六、U 盘其它软件（非本项目）
- 换机一键入口 `E:\_一键装齐依赖.bat`；人读版 `E:\U盘软件环境说明.md`；作业书=skill「usb-software-env-setup」。
- 端口：weixin-auto 编辑器 8000/8001、AudioDeDupTool 8787、qqgen 8777、DouK WebUI 5556（API 5555）、洗图工作台 8765。
- 坑：DouK `webui_main.py` 菜单号是 **8**（不是 9）；`Volume\settings.json` 是 utf-8-sig；**禁 `pip --upgrade pip`**，一次只跑一个 pip。

## 七、剧本转录（历史会话判定）
- `[打开聊天]` 那一刻屏上已有的消息=历史：首开会话写进 `[历史会话块]`（我方用「我：」），非首开写成前一块尾部的 `[对方后台发消息]`；带打字/到达动画的才是实时步。
- 列表页预览+未读角标是「后台到达」的最硬证据；0.3s/2s 双帧对比区分历史 vs 实时。
- `cap.set` 帧号 seek 有漂移，钉时间线必须顺序解码。
- video2script：`video2script\`（视频→剧本草稿，RapidOCR；OpenCV 中文路径要 imencode/tofile；mp4v 只能顺序解码）。
