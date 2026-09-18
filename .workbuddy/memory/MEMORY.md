# F:\weixin-auto 长期备忘（工作版；版本史/长版全文见 MEMORY_full_archive.md 与每日日志）

## 排障铁律
- Edit 会静默丢编辑：改完必 grep 确认落盘。探针绝不改页面状态。
- editor_server.py 改完须重启；前端 html/js 每请求读盘（让用户 Ctrl+Shift+R）。
- Windows isabs('/x/y')=True：web 路径先判 web；改解析/动作必跑机械门。
- ★项目装 U 盘、盘符随电脑变：落盘禁存绝对路径（longimg_api._rel/_abs）；脚本用 %~dp0 或 __file__。
- ★机械门必须用系统 Python312（托管 3.13 缺 playwright → 解析器加载失败 → steps 全空 → 全篇误报、步数显示 1）。阈值从 G.rule_numbers() 实读。真管线=main.py --workflow。

## 出片入口
- ★★创作模式 v2（0917 staged 上线；**0918 三层分工实装**）：Beat Sheet→骨架→**逐块填充=戏层 AI 写对话 → 壳层代码卡位 → 字层 AI 只填字幕**→机械门→终审；任一层失败回退一锅端。戏层必须拿到**过滤后的**规则库（`content_only_rules()`，整块灌会让推理模型卡 10 分钟）。create.db=SQLite 数据层；完整作业书=项目 skill「创作模式全流程」（.workbuddy\skills\）；软件/AI 手写/二修三条路都过同一套门禁。全程引擎 0918 起有机械**提示**项（门禁 3.9c：中后段退化检测）。
- 3 入口：工作流/脚本/并发(concurrent.html)。片头三选一；改片头用 POST /api/tasks/<id> {options:{intro_path}}，别手改 tasks.json。
- ★并行批量灌入/清空：`_probe_tmp/_conc_import_batch.py`（--dir / --clear 先备份 / --speed --intro --wallpaper / --dry-run）。链路=POST /api/tasks → /parse {offline:true}（与 doImport 同源）。清空不必停服务（接口数==文件数时逐条 DELETE）。

## 剧本规则（权威=创作模式_打字不发博弈字幕规范.md）
- ★★★开局引擎（0916 二次定调）：**重点是话题的诱惑性——让观众想歪，且必须合规**。①她抛**语义双关**（帮/来/陪/教我，**宾语始终空着**＝张力来源）②**≥3 拍递进**（状态→求助→条件→地点）③我方**不敢点破**只追问、零漂亮话（积极接招=油腻）④落点**极日常**（帮上班/拍照片），越平越好笑 ⑤合规＝零露骨词/零身体描写，暧昧全在观众脑内；**禁"别想歪 是XX"式解释**。`[打字不发]` 写**我方心里失守**（？？？/完了），不写技巧点评。反面＝我方点评她刚发的图（10/15 篇中招）。详见 _工作文件/_可歪引擎_暧昧牵引.md。
- ★开场别公式化、别一上来发表情包；朋友圈四连开场用 [等待] 0.3 垫拍。
- ★会被 [打开聊天] 打开的会话历史 ≥6 条；未打开的路人会话 1 条即可（列表页只渲染末条）；素材可跨剧本借已收尾会话。
- ★需上传实时图 ≤5（图库解析不到才计入、短名不计、前 6 步豁免 1 张）。
- ★画面外动作禁令：台词禁声称画面里不会发生的事（换头像/改备注/设背景/换昵称）——走真实动作步或改成纯口头成立的说法。
- ★全程引擎（0916 三次定调）：可歪开场只是入场，**中后段不许退化成纯关心/伺候**（用户批「一直询问=无聊」）。每篇维持智斗+暧昧：她试探→我方反将、模糊叙述继续吊（上来坐坐/就我一个人）、我方反推拉（站楼下不上楼）、终局反转（从头到尾是她安排的）；落地仍极日常。
- 停留 0.3/0.5/1.0/1.5；她说话前 [等待] 0.2。★机械门硬指标：步数≤200、实时对白≥110、打字不发≥15、插话≥5、会话≥9、表情≥6种/同名≤2、**交替率≤0.75**（需双方各 2~3 条连发段）、**[等待] 占比≤60%**（口径=我方消息后紧跟 [等待]；节奏靠连发而非每句跟 0.2）、主页会话 ≤10（写 11 个报「已截断」不通过）；插话=她的口吻≈打字不发的 1/3；CTA=「想要聊天秘籍的兄弟 点赞关注扣6我安排」。
- 点图四连必真点图（打开对方主页→进朋友圈→[点开图片] 序号=1,1 停留=0.3→闪回聊天）。
- ★`[删除文字] -1` 后对方**不能立刻回应**（她不能回应没发出去的字）：要反应就写进 [打字不发] 第 3 段插话，或先补一句真发出去的 [我方打字]。
- 机械门 3.14=多参数必须 `|`；3.15=点图前必须有进朋友圈；短名错一字=整图空白。

## 编辑器 / 渲染器
- 真渲染器=main.py --editmode --headless --liveport 8001（改 enhance 须重启）；ffmpeg 用 imageio_ffmpeg。
- ★聊天背景层画在 .dialogue::before，禁画回 .dialogue-section（固定定位会退化→背景随键盘上移）。
- ★自动出图预览：autoRef→/api/resolve-refs；[点开图片] 生成 previewOnly 槽；防递归=_fillAutoPreviews 一帧到位+redraw 上锁（三页）。朋友圈预览=editor/moments_preview.js（boot 必须 win.__wxPeer.apply(presets[person])；注入 enhance/human_actions.js 才有点图查看器）。

- 长图模式 v3.11 细节已移 archive（EXPORT_CSS 背景层禁用/镜头句数定标/状态栏节点）；渲染=系统 Python314。

## 归档 / 素材
- 定稿 → 剧本库\成品\<批次>_<日期>_<主题>\：N 篇 txt + 00_总任务书.md + 配图清单.md + README.md；过程材料留 _inprogress\；只复制不移动（_probe_tmp/_archive_batch_0916.py）。图梗描述「削到骨架」。
- ★video2script：`video2script\`=对标博主视频→剧本草稿管线（随 U 盘走）。新电脑=装 Python→双击 1-安装依赖.bat→视频放 input_videos\→拖上 2-视频转脚本.bat。OCR=RapidOCR；输出 draft.txt+report.md（确认代替手打）。自测=拖 v2s_smoke.mp4。首次跑真视频先 --probe 校准页面签名。坑：OpenCV 中文路径要 imencode/tofile；mp4v 禁 cap.set seek（漂移出鬼影帧）只能顺序解码。
- 片头壁纸=public/images/introwall/（/api/intro-wallpapers）；聊天背景=public/images/bg（/api/chat-bgs）——别混。
- 头像：内置 151 张在 /images/avatar/（约 40 张杂图别用）。选角=长图模式\头像选角表.md：男生固定「男_竹林幽经.jpg」；女生跑 随机女头.py（34 张池，避开最近 5 张）。

## Git / 环境
- git 代理 127.0.0.1:7899；禁 git add -A；改前端 add vue-WeChat；提交前查 "sk-"。
- PowerShell stdout 常被吞→写文件读；bash 工具链可能全坏→全程 PowerShell；★跑 py 中文输出乱码须 `[Console]::OutputEncoding=UTF8` + `$env:PYTHONIOENCODING="utf-8"`。
- ★AI 起的 editor_server 会被回收；常驻请用户双击 启动.bat。curl localhost 必加 --noproxy '*'。
- ★tasks.json 会被「空内存表」覆盖：动它前先停 8000 服务；恢复源=_probe_tmp/tasks_api.json。

## 剧本转录：历史会话判定铁律（2026-09-17 用户定调）
- 每次 [打开聊天] 那一刻屏上已有的消息=历史会话：首开会话写进 [历史会话块]（我方消息用「我：」，支持 [图片]/[链接]/内嵌3Demoji 如 我：[OK]），非首开会话则写成前一块尾部的 [对方后台发消息]；带打字/到达动画的才是实时步。
- 列表页预览+未读 badge 数是判定「后台到达」的最硬证据；打开后 0.3s/2s 双帧对比区分历史 vs 实时。
- ★cap.set 帧号 seek 有漂移（±1s+，14 号实测三帧互相矛盾），钉时间线必须顺序解码（cap.read 循环）。
- 聊天内点图用 [等待] 垫看图节拍；聊天外动画表情/贴纸对方后台到达用 [对方后台发消息] … | [图片] 短名 | 时间。
