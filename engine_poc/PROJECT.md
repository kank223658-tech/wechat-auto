# Rime 引擎接入项目（独立，不动现有成品）

## 目标
把真·Rime 引擎（雾凇拼音）通过 WASM 接入本项目，替换现有手写候选引擎，让候选/联想与真 Rime 一致。
本目录是**独立小项目**，与 `main.py` 现有录制管线隔离；验证通过后才考虑接入。

## 架构（已从 my_rime 源码确认）
```
主线程  LambdaWorker('./worker.js')  (@libreservice/my-worker)
          │  worker.register('process')/('setIME')/('deploy')/('selectCandidateOnCurrentPage')
          ▼
Worker  worker.js  (@libreservice/my-rime dist)
          │  expose({ process, setIME, deploy, setOption, setPageSize, changePage, resetUserDirectory, fsOperate })
          │  loadWasm('rime.js') 加载 @libreservice/my-rime 的 rime.js + rime.wasm + rime.data
          │  Module.ccall('init'/'set_ime'/'deploy'/'process'/'select_candidate_on_current_page', ...)
          ▼
librime (WASM)  ←  雾凇 schema 写入 /usr/share/rime-data/ 后 deploy() 编译
```

## 关键 API（源自 `src/workerAPI.ts` / `src/worker.ts`）
- `process(input: string)` → `RIME_RESULT`（候选 + committed），JSON。
- `selectCandidateOnCurrentPage(index)` → 选中的上屏文字。
- `setIME(schemaId)` / `deploy()` / `setPageSize(n)` / `setOption(opt, val)`。
- 用 `@libreservice/my-worker` 的 `LambdaWorker` 注册这些方法；`asyncFS(worker)` 访问虚拟 FS。

## 雾凇方案如何喂
- 雾凇 = `@libreservice/micro-plum` 可部署，或用 rime-ice 的 schema + dict.yaml。
- 把 `.dict.yaml` + `.schema.yaml` 写入 worker 的 `/usr/share/rime-data/`，`setIME('rime_ice')` 后 `deploy()`，
  librime 现场编译成 `.bin` 表（首次慢，后续可缓存预编译 ./build 下的 .bin）。

## 计划（分步）
1. [x] 立项：`engine_poc/my_rime`（源码，含 wasm/api.cpp、src/worker.ts、workerAPI.ts）。
2. [x] 依赖：`engine_poc/runner` 已装 `@libreservice/my-worker` + `@libreservice/my-rime`。
3. [x] **核心 PoC（已跑通）**：`runner/poc_run.py` 起本地服务 + 无头 Chromium 加载 `worker.js`，
       `process('nihao')` 返回真实候选 `你好 / 🙂️ / 妳好 / 逆號 / 你 / 🫵🏻 / 擬 / 尼`（含 Rime 的 emoji 预测）。
       —— 证明 Rime WASM 引擎在本机、本 headless 环境能跑。
       **注意**：`process(input)` 是持久会话，连续喂不同拼音会累加（`process('women')` → `ni hao wo men`）。
       接入时按"新组合前清空/新建会话"或"依赖引擎累积后提交"处理。
4. [x] **喂雾凇已跑通（核心里程碑）**：`poc_wusong.py` 用 micro-plum `Recipe+GitHubDownloader('iDvel/rime-ice',['rime_ice'])` 拉 29 个文件写入 `/rime/`，
       写 `default.custom.yaml` 设 `schema_list:[rime_ice]`，`deploy()` 编译（27.8s），`setIME('rime_ice')`。
       **出纯简体候选**：`process('nihao') → 你好 / 🙂️ / 拟好 / 你 / 🫵🏻 / 尼 / 泥 / 逆 / 拟 / 腻`（无繁体）。
       **已知问题**：a) `process` 是持久会话，连续喂不同拼音会累加（'women' → 'ni hao wo men'），接入需按会话管理；
       b) 依赖方案 melt_eng(英文)/radical_pinyin(拆字) 未随雾凇部署（报错，但纯中文拼音输入正常）；
       c) lua 文件 404（WASM 构建不支持 lua，非关键）；d) 部署约 28s，录屏前需预热/缓存。
5. [x] **接入录屏已跑通**：`main.py` 注入 `_rime_bootstrap_js()`（手动雾凇部署，仅依赖 my-worker，动态 import，无 import map/micro-plum/esbuild），
       `_inject_rime_engine()` 在 `inject_overlays` 里注入并 `wait_for_function` 等 `__rimeEngine.ready`（超时回退离线词库）。
       `enhance/keyboard.js` 加 `refreshFromEngine()`：引擎就绪时用 `__rimeEngine.process(拼音)` 换真实候选（拼音变则丢弃过期），
       提交仍走 `commitByPhrase` 保证文字一致。实测录屏日志 `[引擎] 雾凇引擎就绪`，候选条显示真引擎的空输入预测（吗/呢/吧/啊/了/的/呀/哦/😊）。
       **注**：引擎部署约 +68s/次录屏（用户已接受）；引擎文件在 `vue-WeChat/public/engine/`。
6. [ ] 更精细：候选与上屏对齐打磨、雾凇部署提速（预热/缓存）、按需简化候选展示。

## 注意
- 许可：`@libreservice/my-rime` AGPL-3.0-or-later。
- 性能：WASM + 词库启动较慢（已知，用户接受）；每键 `process` 需要异步，候选条要接回调。