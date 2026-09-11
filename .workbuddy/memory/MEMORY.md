# G:\weixin-auto 项目长期备忘

## 排障铁律
- 调试探针绝不能改页面状态：`renderPosts`、`scrollIntoView`、screencast 录制期间的
  `page.screenshot()` 都会污染运行与录屏（曾致「下滑后淡入淡出+闪回原处」+「关图幽灵」，
  2026-09-11 根治，详见当日日志）。「探针永不复现、真跑总复现」= 观察者效应强信号。
- 判定视频异常要用**稳定帧全分辨率对比**（残差 <0.3% = 逐像素一致），轨迹里程计在
  pswp 开/关图压暗+缩放时会误读成几十到上百 px 的假滚动跳变。
- ⚠️ **Chrome 对 display:none 子树内的元素把 transform 解析为 none**（computed 值，
  连内联 !important 都无效）。给隐藏元素做 CSS 过渡动画必须：先显示 root →
  `void el.offsetWidth` 强制回流 → 再加动画类，否则首帧即终态、动画被整个跳过
  （2026-09-11 面板瞬现 bug 根因）。录制的成品视频是 1080×2340（画布×1.8），
  像素探针坐标记得换算。

## 视频排障工具（项目根目录，可复用）
- `_check_scrollfx.py <video>`：滚动轨迹/事件簇/倒退检测（270×585 灰度 + 纵向位移搜索）。
- `_cmp_frames.py <video> t1 t2 ...`：按时间抽全分辨率帧两两对比（最优 dy + 残差 + 分带差异）。
- `_check_hardcut.py`：Tab 硬切验证；`_check_ghost2.py`：关图幽灵配对量化。
- `_state_scan.py <video>`：每 0.1s 状态时间线（绿/蓝/键盘亮度/顶部亮度）——判断"某时刻什么在屏上"首选。
- `_probe_num.py`：绿/蓝像素 bbox + 指定行亮度剖面 + 键盘纹理行（std>30）数值定位。
- `_probe_regions.py` / `_probe_likecmt.py` / `_probe_end.py`：分区域 ASCII / 全帧故事板 / 配色行剖面。
- 坑：全帧 ASCII 易截断误读，优先用 _state_scan + _probe_num 数值判定；
  探针脚本别 os.remove 旧 png（沙箱守卫超时），用唯一文件名。

## 环境要点
- 模型看不了图片：一切视觉验证靠 PIL+numpy 像素采样 / ASCII 灰度 / 分带差异。
- playwright 只在系统 Python（`py` / Python314）；托管 3.13 没有且 venv 建不出（pip 502）。
- ffmpeg 用 imageio_ffmpeg 自带二进制；无独立 ffmpeg。
- 前端 dev server：托管 node 22.22.2-2 + `NODE_OPTIONS=--openssl-legacy-provider`，端口 8080，
  对不存在静态路径返回 200+index.html 回退（判文件存在必须看 content-type）。
- Bash 里 `nohup &` 会被回收，长驻服务用 run_in_background。
- ⚠️ Edit 工具会静默丢编辑（报成功但没写入，EBUSY 竞态）：对同一文件连续编辑后必须
  grep 关键标记确认落盘；Python ast 语法检查发现不了「def 行被吞进上一函数体」这类问题，
  要用运行时冒烟（起服务实测）兜底。2026-09-11 图片库分类改造时连续踩了 5 次。

## 图片库分类体系（2026-09-11 落地）
- 分类：avatar头像 / sticker表情包 / emoji / bg背景 / asset配图素材 / icon系统图标 / 🎬视频。
- 上传带 category 落对应子目录；`/api/gallery/move` 搬移文件并自动更新
  scene.json/workflow.json/people.json/peer_presets.json/reference_workflow.json/enhance/config.js 引用。
- 三个界面（shared_picker.js / scene.html 图片库 / concurrent.html）都有分类筛选+按分类上传+移动分类。
