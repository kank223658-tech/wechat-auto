# G:\weixin-auto 项目长期备忘（精简版；全文在 MEMORY_full_archive.md，过程见每日日志）

## 排障铁律
- 探针绝不改页面状态；对照图必须同倍率，优先数值探针。
- ⚠️ Edit 工具会静默丢编辑：连续编辑后必须 grep 确认落盘；补丁用 Write 写文件再跑。
- 改 public/images 后先 curl 验证字节数（dev server 可能把覆盖写入/旧 SVG 缓存成 0 字节→URL mask/背景整元素隐身，图标一律内联 data-URL）。
- 录制期间别往 vue-WeChat 写文件（重编译→刷新→死帧）；录后 ffmpeg freezedetect 扫死帧；视频异常用稳定帧全分辨率对比。
- 改解析/动作后必跑 `_check_fullcover_parse.py`（65/65）。
- 复用工具（项目根）：`_check_scrollfx/_cmp_frames/_check_hardcut/_check_ghost2/_state_scan/_probe_num/_vg_track4/_vg_final/_check_blank/_probe_mic`、`_snd/_scan_backspace.py`。

## 真实渲染器
- 真渲染器=`py main.py --editmode --headless --liveport 8001`（改 enhance 后须重启）；`/shot.jpeg` 缓存帧（先 tap 再取）；`/api/tap|type|pick|edit|scroll|back|scene`；真帧 600×1300。验证实例=8002+`--scene scene.json`（发现 Tab≈362,1210、我≈487,1210、通讯录≈225,1210；通讯录路由 '#/contact'；朋友圈格≈200,190）。
- 重启渲染器：`taskkill /PID <pid> /T /F` 杀整树，杀完 netstat 验证只剩 0/1 个 LISTEN。
- 瞬间上屏必须登记 no-blend 硬切窗（span pad 3.0/2.5+DOM 计数轮询）；WX_DEBUG_BLEND=1 排查。

## 键盘/聊天 UI
- 键盘=整张贴图 `kb_body.png`(513px 高)+chat_exact.css 热区；数字页 kb_body_num.png。改键面文字必须 JS。
- 作用域：body.wx-chat / body.wx-on-moments（moments_extra.js 每 250ms 同步），两处 CSS 块同步维护。
- 候选条：单字行 cap=8；禁随机 emoji；Rime emoji 按 Unicode 区段过滤。组合态空格=「选定」右键=「确认」，1 帧硬切；发送键=合成 Enter（main.py 统一处理：chat-txt→气泡，momentCommentInput/commentInput→__wxSubmitComment）。
- 组合覆盖层（绿下划线拼音）：keyboard.js `isComposeTarget`= .chat-txt ∪ #momentCommentInput（评论框同享）。
- 朋友圈评论条（2026-09-12 照搬聊天框）：#commentBar 86px 黑条 bottom:513px + .cb-way 61px #2c2c2c 输入框 + 😊🖼 SVG（left 482/543）；无条内发送钮。
- my-rime process() 按键会话式：pyBuffer 清空点必须 refreshFromEngine('')。词库 `_ime_words()`=雾凇∪jieba∪custom_words.txt。

## 朋友圈顶部图标（2026-09-12）
- 返回箭头=`#moments > #wx-header::before`、相机=`::after`，均 opacity 1 常显；header sticky top=58。`.icon-return-arrow` div 在渲染器会话不出像素，只留热区。
- ⚠️ 相机 ::after 被 wx_icons.css 后注入强写 `background:currentColor!important+mask(...)!important`——moments_exact 里必须 background 全 !important + `mask:none!important` 抵消，SVG 用 `background-size:100% 100%`（viewBox 紧贴 artwork），实测 30×24。

## 三面板/图片库/emoji
- `window.__wxPanels` 唯一入口；230ms；稳态输入栏顶 y：1171/702/629/793。图片库 `/api/gallery/move` 自动改引用。
- 3D emoji 108 个：数据源 names.json；EMOJI3D_ORDER 手工静态数组；网格不插空槽、遮罩宽动态量取；惯性滑动 `__wxEmojiPanel.scrollTo`；抠图链 `_emoji_cut2/`。
- 隐私：wxid/地区常驻高斯模糊；peer 主页图标用参考图裁切 png。默认界面=场景编辑器（scene.json→__wxDefaultScene）；上游演示人物已全清；script_translator.EXTRA_IMAGES 只列真实存在文件。

## 创作模式/录屏
- 动作表唯一来源 action_registry.py（改 `_build_registry.py` 后重跑）。DeepSeek 实测可用=deepseek-flash/deepseek-v4-pro。联系人唯一来源=people.json+scene.json。配图打开动画控件冒烟 `_smoke_openopts.py`。
- 卡帧根因=冷加载撞录制，新动作资源必须挂预热链；持久 profile `.cache/chrome-profile`（WX_CACHE_PROFILE=0 关）。

## Git / 环境
- git 前加 `-c http.proxy= -c https.proxy=`；禁 `git add -A`；改前端记得 `git add vue-WeChat`；提交前 grep "sk-"。
- ⚠️ G 盘 FAT32：分支名禁斜杠；推送 `git push origin xxx:feat/xxx`。
- playwright 只在系统 py；ffmpeg 用 imageio_ffmpeg；dev server/渲染器沙箱外启动；跑录制前 `py -m py_compile main.py`。
- 参考视频换算：592宽 ×1.9916=1179tex、×1.0135=600画布；1179 参考图 ×0.509=600。截图预览是缩放过的，点按坐标必须按原图换算。
- 朋友圈下滑导航（2026-09-12）：header 背景=`rgba(27,27,27, var(--nav-a))` 与标题同步淡入（真机=封面滚出后黑条+标题约 170ms 纯 alpha 淡入，无分割线；图标白常显）；窗口 (y-380)/100（封面底 598 扫过导航底 124）。⚠️ /api/scroll 的 mouse.wheel 在朋友圈不滚（点按正常）；无头验证滚动态可直接设 #moments 的 --nav-a。
- 录制坑（2026-09-12）：成品视频是 VFR（只收录有视觉变化的帧，静止段无帧）→「视频过短/停在最后动作」先查场景内容是否够高（如朋友圈动态太少无物可滚），别怀疑采集链路。剧本参数格式=`[指令] 参数`（参数在括号外）。帧缓冲排查工具 _rec_mon.py（监控线程打印 _FRAMES）。
- 对方朋友圈导航（2026-09-12）：`.wpm-nav` sticky top0 h124（状态栏58+导航66）整块 `rgba(27,27,27,var(--pnav-a))` 淡入 + 昵称标题 + 常显箭头（与我朋友圈同款机制）；--pnav-a 窗口 (y-313)/100（封面537→导航底124）。场景 peer.posts 为空时内容不足一屏无物可滚——录对方朋友圈滚动前先确认动态够多。peer_pages.js ensureProfile 的 back 常量遮蔽外层 back() 函数（点击返回箭头会 TypeError），main.py 直调 __wxPeer.back() 不受影响。
