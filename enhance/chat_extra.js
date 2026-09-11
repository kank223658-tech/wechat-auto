/* ============================================================
   聊天增强（main.py 注入）
   ------------------------------------------------------------
   在聊天页补充更接近真人的气泡动作：
   图片消息 / 语音消息 / 撤回 / 转发 / @成员 / 系统提示
   ============================================================ */
(() => {
    if (window.__wxChatExt) return;

    /* ============================================================
       新气泡上屏滚底统一入口（window 级，供 chat_extra.js 与 main.py
       的 ENHANCE_JS 共用）：
         - 消息区未铺满（不可滚动，scrollHeight <= clientHeight）：
           直接 scrollTop = 0，瞬间出现、无动画（保持现状）；
         - 已铺满且本就在底部：直接贴底，无动画；
         - 已铺满且未到底：easeOutCubic 约 150ms 平滑滚到底——
           整列消息极快上移，新气泡从输入栏上沿滑出（接近真机微信）；
           rAF + cancelAnimationFrame 防抖，连续多条消息合并为一次滚动。
       ============================================================ */
    window.__wxSmoothScrollBottom = (sec) => {
        if (!sec) return;
        const max = sec.scrollHeight - sec.clientHeight;
        if (max <= 0) { sec.scrollTop = 0; return; }        // 未满：无动画
        const start = sec.scrollTop;
        if (start >= max) { sec.scrollTop = max; return; }  // 已在底部：直接贴底
        if (sec.__wxScrollRAF) cancelAnimationFrame(sec.__wxScrollRAF);
        const D = 150;                                      // 极快上移时长 ms（观感可调常量）
        let t0 = null;
        const step = (t) => {
            if (!t0) t0 = t;
            const p = Math.min(1, (t - t0) / D);
            const e = 1 - Math.pow(1 - p, 3);               // easeOutCubic
            sec.scrollTop = start + (max - start) * e;
            sec.__wxScrollRAF = p < 1 ? requestAnimationFrame(step) : null;
        };
        sec.__wxScrollRAF = requestAnimationFrame(step);
    };

    /* 气泡与系统提示样式 */
    const css = document.createElement('style');
    css.textContent = `
      .row .text.msg-image, .row.self .text.msg-image {
        padding: 0 !important; background: transparent !important;   /* padding 归零，让 JS 内联宽高即图片实际显示尺寸 */
        max-width: none !important;   /* 覆盖外层 .text 的 max-width:62%，避免图片被压小 */
        flex: none !important;        /* 防止在 .row flex 布局中被压缩 */
      }
      /* 图片气泡去掉气泡尖角（否则右侧残留绿色小三角，同表情气泡处理） */
      .row.self .text.msg-image:before,
      .row .text.msg-image:before { display: none !important; }
      .row .text.msg-image img {
        width: 100% !important; height: 100% !important;  /* 跟随 JS 内联的容器宽高，覆盖 180px 基线 */
        object-fit: contain !important;  /* 等比例完整显示，不裁切、不变形 */
        border-radius: 6px; display: block;
      }
      .row.self .text.msg-voice { background: #2bb262; }
      .row .text.msg-voice {
        display: flex; align-items: center; gap: 8px;
        min-width: 96px;
      }
      .voice-wave { display: flex; align-items: center; gap: 2px; height: 20px; }
      .voice-wave i { width: 3px; border-radius: 2px; background: #555; }
      .row.self .voice-wave i { background: #1e7f47; }
      .voice-dur { font-size: 12px; color: #666; white-space: nowrap; }
      .msg-system {
        clear: both; text-align: center; font-size: 12px;
        color: #b2b2b2; margin: 12px 0 2px;
      }
      /* ---- 微信转账卡片气泡（1:1 对齐参考图：橙底 #df8d37 + 白色圆圈转账图标贴图 + 大金额 + 标题 + 左下「转账」角标；收发双方同一样式） ----
         注意：带 body.wx-chat + .text.text 双类提高特异度，否则会被
         chat_exact.css 的 body.wx-chat .dialogue-section .row.self .text 绿底规则压掉 */
      .row .text.msg-transfer, .row.self .text.msg-transfer,
      body.wx-chat .dialogue-section .row .text.text.msg-transfer,
      body.wx-chat .dialogue-section .row.self .text.text.msg-transfer {
        background: #df8d37 !important; color: #fff !important;
        padding: 13px 16px 12px 14px; min-width: 356px; max-width: 72%;
        border-radius: 12px; box-shadow: none !important;
        position: relative;
        display: flex !important; flex-direction: column !important;
        align-items: flex-start !important;
      }
      /* 主区：左侧圆圈图标贴图 + 右侧 金额/标题 */
      .msg-transfer .tf-main {
        display: flex; align-items: center; gap: 12px;
      }
      /* 左侧转账图标：参考图原样抠出的白色圆圈 + 双向箭头透明 PNG */
      .msg-transfer .tf-icon {
        flex: 0 0 62px; width: 62px; height: 62px; display: block;
      }
      .msg-transfer .tf-icon img, .msg-transfer .tf-icon svg { width: 62px; height: 62px; display: block; }
      .msg-transfer .tf-body { flex: 1; min-width: 0; }
      .msg-transfer .tf-amount {
        display: flex; align-items: baseline;
        color: #fff; font-size: 23px; font-weight: 600;
        line-height: 1.15;
      }
      .msg-transfer .tf-amount .rmb { font-size: 23px; font-weight: 600; }
      .msg-transfer .tf-title {
        color: rgba(255, 255, 255, .96); font-size: 17px; font-weight: 400;
        line-height: 1.35; margin-top: 5px;
      }
      /* 左下角「转账」角标：纵向 flex 的第二行，天然排在图标下方 */
      .msg-transfer .tf-badge {
        display: block;
        margin-top: 14px;
        font-size: 15px; color: rgba(255, 255, 255, .78);
        letter-spacing: .5px; line-height: 1.2;
      }
      /* 我方/对方转账卡片气泡尖角（同款橙色，双方样式一致） */
      .row.self .text.msg-transfer:before {
        border-left-color: #df8d37 !important;
      }
      .row .text.msg-transfer:before {
        border-right-color: #df8d37 !important;
      }

      /* ============================================================
         一、消息气泡发送入场动画（与真实微信一致：从底部升起+回弹）
         所有新上屏的气泡（我/对方、文字/图片/语音/转账/转发/表情）
         统一带 pop-in：气泡先位于稍低位置微缩淡入，再升起并轻微回弹
         落定。回弹原点靠近发送方向（我方右下 / 对方左下）。
         ============================================================ */
      /* ---- 与真机一致的聊天行：flex 布局，头像与气泡垂直居中、大小贴合 ---- */
      /* 让消息区独立滚动（不依赖 sub-page 容器，避免直接滚 sub-page 触发子页返回主页） */
      .dialogue-section {
        height: calc(100% - 50px - 54px) !important;
        overflow-y: auto !important;
        -webkit-overflow-scrolling: touch;
      }
      /* 键盘弹出时：消息区高度扣除键盘高，滚动到底后最后一条消息正好落在输入栏上方，不被遮 */
      body.wxkb-open .dialogue-section {
        height: calc(100% - 50px - 54px - 340px - var(--kb-cand-h, 0px)) !important;
      }
      .dialogue-section .row {
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        margin: 9px 0 !important;
        overflow: visible !important;
      }
      .dialogue-section .row:not(.self) { justify-content: flex-start; }
      .dialogue-section .row.self { justify-content: flex-end; }
      /* 真机微信：转账卡/图片/表情包这类高内容，头像与内容顶部对齐（不垂直居中）；
         文字等普通消息行保持居中不变。行高由最高元素决定，此改动不影响行距与滚动。 */
      .dialogue-section .row:has(.text.msg-transfer),
      .dialogue-section .row:has(.text.msg-image),
      .dialogue-section .row:has(.text.msg-emoji) { align-items: flex-start !important; }
      .dialogue-section .row .header {
        width: 40px !important; height: 40px !important;
        border-radius: 4px !important;
        flex: 0 0 auto !important;
        object-fit: cover !important;
        margin: 0 !important;
        float: none !important;
        display: block !important;
        background: #2c2c2e;
      }
      .dialogue-section .row:not(.self) .header { order: 0; margin-right: 10px !important; }
      .dialogue-section .row:not(.self) .text { order: 1; margin: 0 !important; }
      .dialogue-section .row.self .text { order: 0; margin: 0 10px 0 0 !important; }
      .dialogue-section .row.self .header { order: 1; margin: 0 !important; }
      .dialogue-section .row .text {
        font-size: 17px !important; line-height: 1.42 !important;
        padding: 9px 13px !important; border-radius: 5px !important;
        max-width: 62% !important; box-shadow: none !important;
        margin: 0 !important;
      }

      /* 真机微信：气泡从底部升起 + 轻微回弹落定（不是从角落缩小淡入）。
         起点略低于最终位置并微缩，ease 尾段过冲(y>1)产生回弹手感；
         我方气泡回弹方向朝发送键(右)，对方朝左侧。 */
      /* 真机微信 iOS：消息入场是轻微缩放+淡入（约 0.15s ease-out，无大位移、无回弹过冲） */
      @keyframes wxMsgPop {
        0%   { transform: scale(.94); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
      }
      .dialogue-section .row.pop-in { animation: wxMsgPop .15s ease-out both; }
      .dialogue-section .row.self.pop-in { transform-origin: 95% 100%; }
      .dialogue-section .row.pop-in:not(.self) { transform-origin: 5% 100%; }

      /* ============================================================
         二、图片「发送中」过渡：先半透明缩略图 + 居中大号旋转进度圈，
         约 0.65s 后定格为完整图片（模拟真机发图先传后出）。
         ============================================================ */
      .row .text.msg-image.msg-sending { position: relative; }
      .row .text.msg-image.msg-sending img { opacity: .55; }
      .row .text.msg-image.msg-sending .sending-ring {
        position: absolute;
        left: 50%; top: 50%;              /* 相对 msg-image 中心 */
        width: 28px; height: 28px;        /* 更大 */
        margin: -14px 0 0 -14px;          /* 负 margin 微调至真正居中（无 transform，避免被动画覆盖） */
        box-sizing: border-box;
        display: flex; align-items: center; justify-content: center;
      }
      .row .text.msg-image.msg-sending .sending-ring .ring-inner {
        width: 28px; height: 28px;        /* 旋转层 */
        box-sizing: border-box;
        border: 3px solid rgba(255, 255, 255, .95);
        border-top-color: transparent;
        border-radius: 50%;
        animation: ringSpin .8s linear infinite;
      }
      @keyframes ringSpin { to { transform: rotate(360deg); } }

      /* ============================================================
         三、底部弹出面板（转账确认 / 表情包选择），仿微信 iOS 底部 ActionSheet
         ============================================================ */
      .wx-pop-mask {
        position: fixed; inset: 0; z-index: 999981;
        background: rgba(0, 0, 0, .38);
        opacity: 0; visibility: hidden;
        transition: opacity .22s ease, visibility .22s ease;
      }
      .wx-pop-mask.open { opacity: 1; visibility: visible; }
      .wx-pop-mask .wx-sheet {
        position: absolute; left: 0; right: 0; bottom: 0;
        background: #fff;
        border-radius: 14px 14px 0 0;
        padding: 20px 18px calc(22px + env(safe-area-inset-bottom));
        transform: translateY(100%);
        transition: transform .26s cubic-bezier(.2, .8, .3, 1);
        box-shadow: 0 -6px 24px rgba(0, 0, 0, .12);
      }
      .wx-pop-mask.open .wx-sheet { transform: translateY(0); }
      /* 深色模式下跟随聊天背景（微信深色：金融/表情面板为深色） */
      .dialogue-section { position: relative; }
      .wx-pop-mask .wx-sheet { color: #111; }
      .wx-pop-mask .wx-sheet .sheet-title {
        text-align: center; font-size: 17px; font-weight: 500;
        font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
      }

      /* ---- 转账确认卡片 ---- */
      .wx-sheet .tf-confirm { text-align: center; }
      .wx-sheet .tf-confirm .cf-header {
        color: #576b95; font-size: 14px; line-height: 1.4; margin-top: 4px;
      }
      .wx-sheet .tf-confirm .cf-amount {
        display: flex; align-items: baseline; justify-content: center; gap: 4px;
        color: #07c160; font-size: 46px; font-weight: 700; margin: 12px 0 6px; line-height: 1.05;
      }
      .wx-sheet .tf-confirm .cf-amount .rmb { font-size: 26px; font-weight: 600; }
      .wx-sheet .tf-confirm .cf-note {
        color: #9a9a9a; font-size: 13px; line-height: 1.4;
      }
      .wx-sheet .tf-confirm .cf-note:empty { display: none; }
      .wx-sheet .tf-btns { display: flex; gap: 12px; margin-top: 22px; }
      .wx-sheet .tf-btns .btn {
        flex: 1; height: 46px; border-radius: 8px; font-size: 16px;
        display: flex; align-items: center; justify-content: center; cursor: pointer;
      }
      .wx-sheet .tf-btns .btn-cancel { background: #f2f2f2; color: #111; }
      .wx-sheet .tf-btns .btn-ok { background: #07c160; color: #fff; }

      /* ---- 表情包面板（真实微信）：替换键盘的独立面板，顶部分类tab + 4×3网格 ----
         真实微信点键盘笑脸后：键盘收起 → 表情面板从底部替换键盘位置滑入。
         面板深色底，顶部分类tab居中，下方“添加的单个表情”小标题 + 4列×3行网格。 */
      .wx-emoji-panel {
        position: fixed; left: 0; right: 0; bottom: 0; z-index: 99990;
        background: #1c1c1e;
        border-radius: 12px 12px 0 0;
        box-shadow: 0 -4px 20px rgba(0, 0, 0, .3);
        padding: 10px 24px 66px;
        transform: translateY(100%);
        /* 面板滑入提速：末段不再拖沓。
           旧 .22s + easeOutQuad(.25,.46,.45,.94) 是强 ease-out，末段强烈减速——
           「先冲到 85% 再慢吞吞爬到顶」，正是底部瞬时穿透 + 拖沓的根源。
           改用 0.13s + easeOutQuint(.23,1,.32,1)：整个上行收敛到约 3 帧@30fps，
           末尾干脆落定（帧分布 61%/28%/10%/1%，不再有 1% 帧）。 */
        transition: transform .13s cubic-bezier(.23, 1, .32, 1);
        will-change: transform;
      }
      .wx-emoji-panel.open { transform: translateY(0); }
      /* 注：已移除表情面板「消息区压暗遮罩」(wx-emoji-mask)——真实微信打开表情面板不压暗消息区。
         输入栏仍随面板上移贴顶、消息区同步收缩让位，联动均保留。 */
      /* 表情面板打开态：输入栏【不收起、仅上移】到面板顶（真机行为）。
         --emoji-h 为 JS 实测的面板高度；面板比键盘(513px)高，故输入栏还要再上移一截。
         与 wxkb-open 相同的联动：输入栏顶边=面板顶，消息区同步收缩让出空间。
         ★ 选择器用 body.wx-chat.wx-emoji-open（0,3,1）而非 body.wx-emoji-open（0,2,1）：
           基础站姿规则 body.wx-chat .dialogue-footer/.dialogue-section 也是 (0,2,1)，
           两者同特异性时由「注入顺序」决定胜负——build_page 里本规则晚、赢(479px 正常)，
           但 main.py 真实流程里 chat_exact.css 晚、赢，导致表情面板打开时消息区不收缩
           (100% 1019px 不动)、文字被面板盖住。加 .wx-chat 抬高一档，无论顺序都必胜。 */
      body.wx-chat.wx-emoji-open .dialogue-footer {
        transform: translateY(calc(-1 * var(--emoji-h, 583px))) !important;
        height: calc(var(--chat-bar-base) + var(--chat-grow, 0px)) !important;
      }
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person {
        height: calc(var(--chat-bar-base) + var(--chat-grow, 0px)) !important;
      }
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .icon-dialogue-voice,
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .icon-dialogue-jianpan,
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .expression,
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .more {
        top: calc(22px + var(--chat-grow, 0px)) !important;
      }
      /* 消息区高度：消息区底边 = 输入栏顶边（真机：面板打开时消息区压缩、最后一条贴输入栏，不穿透面板）。
         旧式为 552 - (面板高-键盘513)，会把消息区底伸到输入栏/面板里，文字「透出来」。
         改为百分百相对 .dialogue 容器：容器高 - 顶部偏移(71) - 输入栏高(bar-base+grow) - 面板高(emoji-h)，
         即消息区底正好落在输入栏顶，最新消息滚动到底即贴输入栏。 */
      body.wx-chat.wx-emoji-open .dialogue-section {
        height: calc(100% - 71px - var(--chat-grow, 0px) - var(--emoji-h, 583px) - var(--chat-bar-base, 86px)) !important;
      }
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .chat-way { top: 12px !important; }
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .chat-say { top: 12px !important; }
      /* 表情面板打开时，输入栏右侧「笑脸键」换成「键盘键」（再点一下回到键盘；对齐参考视频）。
         用的就是你提供的键盘图标原图 kb_circle.png（已不再自己画，手绘 kb_circle.svg 已删除）。 */
      body.wx-chat.wx-emoji-open .component-dialogue-bar-person .expression {
        background: url('/images/chatbar/kb_circle.png') center / contain no-repeat !important;
      }
      /* 顶部分类 tab：搜索 / 笑脸 / 爱心(选中) / 手势。参考视频为【左对齐、均匀分布】：
         1080 参考下图标中心在 x≈82/225/367/510（全在屏幕中心 540 左侧），换算 600 逻辑宽：
         首格中心 ≈46px、格距 ≈79px、图标 ≈36px。故用 flex-start + 左内边距；居中会把整排挪到中间。 */
      .wx-emoji-panel .ep-tabs {
        display: flex; align-items: center; justify-content: flex-start; gap: 33px;
        padding: 0 0 8px 0;   /* 左内边距交给面板 24px；此处只留底部间隔 */
      }
      .wx-emoji-panel .ep-tab {
        width: 46px; height: 46px; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        opacity: .78; flex: none;
      }
      .wx-emoji-panel .ep-tab img { width: 36px; height: 36px; object-fit: contain; display: block; }
      .wx-emoji-panel .ep-tab.active { background: #2e2e30; opacity: 1; }
      /* 面板顶部居中短横把手（拖动指示；参考视频分类行下方一条，宽≈85px@1080→≈47px@600） */
      .wx-emoji-panel .ep-handle {
        width: 48px; height: 6px; border-radius: 3px;
        background: #3a3a3c; margin: 33px auto 21px;
      }
      /* “添加的单个表情”小标题：参考视频字高≈24px@600、左缘≈24px（对齐面板内边距） */
      .wx-emoji-panel .ep-head {
        font-size: 24px; line-height: 1; color: #8e8e93; text-align: left; margin: 0 0 25px;
      }
      /* 4列×3行 网格（对齐参考视频：单元格≈100px 方、列距≈50px、行距≈22px、左右留白≈24px） */
      .wx-emoji-panel .ep-grid {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 22px 50px;
      }
      .wx-emoji-panel .ep-cell {
        aspect-ratio: 1 / 1; border-radius: 8px; overflow: hidden;
        display: flex; align-items: center; justify-content: center;
        position: relative; cursor: pointer;
      }
      .wx-emoji-panel .ep-cell img {
        width: 100%; height: 100%; object-fit: contain; display: block;
      }
      /* 第一格：虚线圆角方框 + 加号（收藏/添加） */
      .wx-emoji-panel .ep-cell.ep-add {
        border: 1.6px dashed rgba(255, 255, 255, .45);
        border-radius: 10px; background: transparent;
      }
      .wx-emoji-panel .ep-cell.ep-add span {
        font-size: 30px; line-height: 1; color: rgba(255, 255, 255, .55); font-weight: 300;
      }
      /* 选中状态：不显示高亮框（去掉绿色选中框/浅底，保持干净） */
      .wx-emoji-panel .ep-cell.ep-picked { }
      /* ---- 底部弹出面板：深色模式统一（微信深色：金融/表情面板跟随深色） ---- */
      .wx-pop-mask .wx-sheet { background: #1c1c1e !important; color: #fff !important; }
      .wx-pop-mask .wx-sheet .sheet-title { color: #fff !important; }
      .wx-sheet .tf-confirm .cf-header { color: #8e8e93 !important; }
      .wx-sheet .tf-confirm .cf-amount { color: #07c160 !important; }
      .wx-sheet .tf-confirm .cf-note { color: #5a5a5e !important; }
      .wx-sheet .tf-btns .btn-cancel { background: #2e2e30 !important; color: #fff !important; }
      .wx-sheet .tf-btns .btn-ok { background: #07c160 !important; color: #fff !important; }

      /* ---- 修正：我方图片气泡去掉绿底、转账卡片统一为橙色（贴合参考图片3）---- */
      .dialogue-section .row .text.msg-image,
      .dialogue-section .row.self .text.msg-image {
        background: transparent !important; padding: 4px !important; box-shadow: none !important;
      }
      .dialogue-section .row .text.msg-transfer,
      .dialogue-section .row.self .text.msg-transfer,
      body.wx-chat .dialogue-section .row .text.text.msg-transfer,
      body.wx-chat .dialogue-section .row.self .text.text.msg-transfer {
        background: #df8d37 !important; color: #fff !important;
      }

      /* ============================================================
         四、表情贴纸气泡：无白底、图片直接上屏（仿微信表情包）
         ============================================================ */
      .row .text.msg-emoji,
      .row.self .text.msg-emoji {
        background: transparent !important; padding: 0 !important; box-shadow: none !important;
      }
      .row.self .text.msg-emoji:before,
      .row .text.msg-emoji:before { display: none !important; }
      .row .text.msg-emoji img { width: 128px; height: 128px; object-fit: contain; display: block; }
    `;
    document.head.appendChild(css);

    const scrollBottom = () => {
        const sec = document.querySelector('.dialogue-section');
        /* 统一走平滑滚底：未铺满瞬间显示、已铺满极快上移滑出（含防抖合并）。
           去掉 window.scrollTo：body 本为 overflow:hidden，滚页面无意义且可能引发跳动。 */
        window.__wxSmoothScrollBottom(sec);
    };
    const meAvatar = () =>
        (window.__wxConfig && window.__wxConfig.get().me.avatar) || '/images/header/header01.png';
    const peerAvatar = () =>
        (window.__wxConfig && window.__wxConfig.get().me.peerAvatar) || '/images/header/yehua.jpg';

    /* 图片气泡显示尺寸：统一按「面积恒定」等比缩放（约等于方图 196×196），
       横图(宽>高)自然更宽、竖图(高>宽)更窄、方图约正方形；比例不变、不裁切。
       加保护性宽高上限，防止超长图过高而撑大行高、影响下方聊天间距。
       同步读缓存得自然宽高；若图片未加载（new Image 首拿时 naturalWidth=0），
       则预加载并在 onload 后通过 onReady(size) 回填。 */
    function imageDisplaySize(url, onReady) {
        const AREA = 38400;        // 目标显示面积 ≈ 方图 196×196
        const MAX_W = 320;         // 保护性宽度上限（常规比例不触达）
        const MAX_H = 380;         // 保护性高度上限（防超长图过高压大行高）
        const fit = (w, h) => {
            if (!w || !h) return { w: 196, h: 196 };
            const scale = Math.sqrt(AREA / (w * h));   // 面积恒定，按原图比例缩放
            let W = Math.round(w * scale), H = Math.round(h * scale);
            if (W > MAX_W || H > MAX_H) {              // 保护性钳制极端长宽比
                const s2 = Math.min(MAX_W / w, MAX_H / h);
                W = Math.round(w * s2); H = Math.round(h * s2);
            }
            return { w: W, h: H };
        };
        const probe = new Image();
        probe.src = url;
        let w = probe.naturalWidth, h = probe.naturalHeight;
        if (w && h) return fit(w, h);                     // 缓存命中，同步可得
        if (onReady) {
            probe.onload = () => onReady(fit(probe.naturalWidth, probe.naturalHeight));
        }
        return fit(w, h);                                // 暂用占位，等 onload 回填
    }

    /* 给单个图片气泡容器按「面积恒定」规则内联显示尺寸。
       历史会话/场景消息由 Vue 渲染成 `<p class="text msg-image"><img></p>`，
       不带内联宽高，会被 chat_exact.css 的 max-width:none 撑到原始尺寸（巨大）。
       这里统一按 imageDisplaySize 规则计算显示尺寸写回容器，与运行时
       selfImage/peerImage 上屏的图片保持一致。图片未加载完时等 onload 回填。 */
    function fitImageBubble(p) {
        if (!p || p.getAttribute('data-fit') === '1') return;
        const img = p.querySelector('img');
        if (!img) return;
        const url = img.currentSrc || img.src;
        if (!url) return;
        if (img.naturalWidth && img.naturalHeight) {
            const s = imageDisplaySize(url);
            p.style.width = s.w + 'px';
            p.style.height = s.h + 'px';
            p.setAttribute('data-fit', '1');
            return;
        }
        if (img.complete) { p.setAttribute('data-fit', '1'); return; }  // 已加载但拿不到尺寸：放弃
        const done = () => {
            if (img.naturalWidth && img.naturalHeight) {
                const s = imageDisplaySize(url);
                p.style.width = s.w + 'px';
                p.style.height = s.h + 'px';
                p.setAttribute('data-fit', '1');
            }
        };
        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', () => p.setAttribute('data-fit', '1'), { once: true });
    }

    /* 遍历当前聊天区所有图片气泡统一缩放（含 Vue 渲染的历史消息）。 */
    function fitAllImageBubbles() {
        document.querySelectorAll('.dialogue-section .row .text.msg-image')
            .forEach(fitImageBubble);
    }

    /* 追加一条气泡；isSelf=true 时用我的头像与右侧绿色气泡。
       统一带 pop-in 入场动画（从气泡靠近发送按钮的一角缩放弹出）。
       imgBox：图片气泡专用，{url,size} —— 生成 `<p class="text msg-image">`
       并内联固定宽高，使行高从一上屏即稳定，头像不再随图片加载完成后下移。 */
    /* 时间分隔条占位：在气泡行前插入一条微信灰色时间分隔条（标注了时刻才显示）。
       复用 config.js 的 parseTimeSpec 换算显示文本；插入顺序在 .row 之前。 */
    function insertMsgTime(time) {
        if (!time) return null;
        let text = String(time);
        try {
            const spec = window.__wxConfig && window.__wxConfig.parseTimeSpec
                ? window.__wxConfig.parseTimeSpec(time) : null;
            if (spec) text = spec.text;
        } catch (e) { /* 解析失败就按标注原样显示 */ }
        const sec = document.querySelector('.dialogue-section');
        if (!sec) return null;
        const div = document.createElement('div');
        div.className = 'msg-time';
        div.textContent = text;
        return div;
    }

    function appendRow(isSelf, innerHtml, imgBox, time) {
        const sec = document.querySelector('.dialogue-section');
        if (!sec) return null;
        if (time) {
            const t = insertMsgTime(time);
            if (t) sec.appendChild(t);
        }
        const row = document.createElement('div');
        row.className = 'row clearfix pop-in' + (isSelf ? ' self' : '');
        if (imgBox) {
            const s = imgBox.size || { w: 180, h: 300 };
            const cls = 'text msg-image' + (imgBox.addClass ? ' ' + imgBox.addClass : '');
            const inner = '<p class="' + cls + '" style="width:' + s.w + 'px;height:' + s.h +
                'px;flex:none;">' + imgBox.innerHtml + '</p>';
            row.innerHTML = isSelf
                ? '<img src="' + meAvatar() + '" class="header" data-me-avatar>' + inner
                : '<img src="' + peerAvatar() + '" class="header">' + inner;
        } else {
            row.innerHTML = isSelf
                ? '<img src="' + meAvatar() + '" class="header" data-me-avatar>' + innerHtml
                : '<img src="' + peerAvatar() + '" class="header">' + innerHtml;
        }
        sec.appendChild(row);
        scrollBottom();
        return row;
    }

    /* 我方图片气泡上屏：先「发送中」占位（半透明缩略图 + 旋转进度圈），
       0.65s 后定格为完整图片。作为闭包函数供 __wxChatExt.selfImage 调用，
       避免 apply(null) 场景下 this 为 null。
       进入前先按真实宽高算出显示尺寸，让行高一上屏即固定，头像不下移；
       图片若未加载，onReady 里再回填实际比例。 */
    function pushImageBubbleImage(url, time) {
        const row = appendRow(true, '', {
            size: imageDisplaySize(url, (real) => {
                const p = row && row.querySelector('.text.msg-image');
                if (p) { p.style.width = real.w + 'px'; p.style.height = real.h + 'px'; }
            }),
            addClass: 'msg-sending',
            innerHtml: '<img src="' + url + '" style="width:100%;height:100%;object-fit:contain;">' +
                '<span class="sending-ring"><span class="ring-inner"></span></span>',
        }, time);
        if (!row) return false;
        setTimeout(() => {
            const el = row.querySelector('.msg-sending');
            if (el) el.classList.remove('msg-sending');
        }, 650);
        return true;
    }

    /* 语音波形条（时长越长条数越多） */
    function voiceHtml(secs, dark) {
        const n = Math.max(4, Math.min(14, Math.round(secs * 2.2)));
        let bars = '';
        for (let i = 0; i < n; i++) {
            const h = 6 + Math.round(Math.abs(Math.sin(i * 1.7)) * 10) + 2;
            bars += '<i style="height:' + h + 'px"></i>';
        }
        return '<p class="text msg-voice"><span class="voice-wave">' + bars +
            '</span><span class="voice-dur">' + secs + '"</span></p>';
    }

    /* 转账卡片内层 HTML（供 dialogue.vue 的 store 渲染 v-html 使用）。
       ★ 返回的是 <p class="text msg-transfer"> 的【内层】，不含外层 p——
         v-html 会替换元素内部内容。结构与 DOM 版 transferCard 完全一致；
         金额字号规则一致（>6 位缩小）；文字经 HTML 转义防注入。 */
    function _escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function transferCardInner(t) {
        const o = t || {};
        const amt = String(o.amount == null || o.amount === '' ? '1.00' : o.amount);
        const title = String(o.title == null ? '' : o.title);
        const amtFs = amt.length > 6 ? '17px' : '23px';
        return '<span class="tf-main">' +
            '<img class="tf-icon" src="/images/transfer/tf_icon.png" alt="">' +
            '<span class="tf-body">' +
                '<span class="tf-amount"><span class="rmb">¥</span>' +
                '<span class="amt" style="font-size:' + amtFs + '">' + _escHtml(amt) + '</span></span>' +
                '<span class="tf-title">' + _escHtml(title) + '</span>' +
            '</span>' +
            '</span>' +
            '<span class="tf-badge">转账</span>';
    }

    /* 转账卡片：1:1 复刻参考图（橙底 + 白色圆圈转账图标贴图，收发双方同一样式）。
       卡片文字每次可定制：
       · amount —— 第一行 ¥ 后的金额大字；
       · note   —— 第二行文字（「转账说明」），不传则用默认标题；
       · title  —— 可选第 5 参，显式覆盖第二行文字（优先级高于 note）。
       isSelf 只决定气泡在左还是右，以及默认文案（我方「你发起了一笔转账」/ 对方「对方发来一笔转账」）。 */
    function transferCard(isSelf, recipient, amount, note, title) {
        const amt = String(amount == null || amount === '' ? '1.00' : amount);
        const nt = String(note == null ? '' : note).trim();
        const tt = String(title == null ? '' : title).trim();
        const subtitle = tt || nt || (isSelf ? '你发起了一笔转账' : '对方发来一笔转账');
        const html = '<p class="text msg-transfer">' +
            '<span class="tf-main">' +
                '<img class="tf-icon" src="/images/transfer/tf_icon.png" alt="">' +
                '<span class="tf-body">' +
                    '<span class="tf-amount"><span class="rmb">¥</span><span class="amt"></span></span>' +
                    '<span class="tf-title"></span>' +
                '</span>' +
            '</span>' +
            '<span class="tf-badge">转账</span>' +
            '</p>';
        const row = appendRow(isSelf, html);
        if (!row) return false;
        const t = row.querySelector('.tf-title');
        if (t) t.textContent = subtitle;
        const a = row.querySelector('.tf-amount .amt');
        if (a) {
            a.textContent = amt;
            a.style.fontSize = String(amt).length > 6 ? '17px' : '23px';
        }
        return true;
    }

    /* ------------------------------------------------------------
       链接卡片气泡（微信公众号文章 / 分享链接）
       ------------------------------------------------------------
       布局对齐参考图（微信链接样式.jpg）：
         · 卡片统一深灰底 #2c2c2c（无论己方/对方，都不发绿，1:1 复刻参考图）；
         · 标题在左上（可自动换行，字多时撑高卡片）；
         · 方形缩略图在右侧、垂直居中（宽高等比，等宽等高的方图）；
         · 来源名（如「心灵知行」）在左下，前带一个小盒子图标，可脚本替换。
       标题/来源用 textContent 回填，杜绝脚本内容注入 HTML。
       ---- */
    function linkCard(isSelf, title, img, source, time) {
        const t = String(title == null ? '' : title).trim();
        const s = String(source == null || source === '' ? '心灵知行' : source);
        const icon = '<svg class="lk-ico" viewBox="0 0 24 24" width="22" height="22" fill="none"' +
            ' stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4"/><path d="M12 11v10"/></svg>';
        const imgHtml = img
            ? '<span class="lk-img"><img src="' + img + '" alt=""></span>'
            : '<span class="lk-img lk-img-empty"></span>';
        const html = '<p class="text msg-link">' +
            '<span class="lk-inner">' +
                '<span class="lk-title"></span>' +
                '<span class="lk-source">' + icon + '<span class="lk-name"></span></span>' +
            '</span>' +
            imgHtml +
            '</p>';
        const row = appendRow(isSelf, html, null, time);
        if (!row) return null;
        const titleEl = row.querySelector('.lk-title');
        if (titleEl) titleEl.textContent = t;
        const nameEl = row.querySelector('.lk-name');
        if (nameEl) nameEl.textContent = s;
        return row;
    }

    /* ============================================================
       底部弹出面板（ActionSheet）通用构建器
       bodyHtml：面板内容（转账确认 / 表情网格），btnsHtml：底部按钮（可为空）
       ---- */
    function buildSheet(title, bodyHtml, btnsHtml) {
        const mask = document.createElement('div');
        mask.className = 'wx-pop-mask';
        mask.innerHTML =
            '<div class="wx-sheet">' +
            (title ? '<div class="sheet-title">' + title + '</div>' : '') +
            bodyHtml +
            (btnsHtml ? btnsHtml : '') +
            '</div>';
        document.body.appendChild(mask);
        // 下一帧加 .open，保证滑出动画每次都从头播放
        requestAnimationFrame(() => { requestAnimationFrame(() => mask.classList.add('open')); });
        return mask;
    }
    function closeSheet(mask) {
        if (!mask) return;
        mask.classList.remove('open');
        setTimeout(() => { if (mask.parentNode) mask.parentNode.removeChild(mask); }, 260);
    }

    /* 转账确认弹窗：标题 + 转账给 + 金额 + 备注 + [取消][转账]。
       自动放映「弹出 → 停留展示金额 → 点'转账' → 收起 → onOk()上屏」。 */
    function confirmTransferSheet(who, amt, nt, onOk) {
        const body =
            '<div class="tf-confirm">' +
            '<div class="cf-header">转账给<b></b></div>' +
            '<div class="cf-amount"><span class="rmb">¥</span><span class="amt"></span></div>' +
            '<div class="cf-note"></div>' +
            '</div>';
        const btns =
            '<div class="tf-btns">' +
            '<div class="btn btn-cancel">取消</div>' +
            '<div class="btn btn-ok">转账</div>' +
            '</div>';
        const mask = buildSheet('确认转账', body, btns);
        const hb = mask.querySelector('.cf-header b');
        if (hb) hb.textContent = who;
        const a = mask.querySelector('.cf-amount .amt');
        if (a) a.textContent = amt;
        const n = mask.querySelector('.cf-note');
        if (n) n.textContent = nt;
        // 停留展示金额 0.85s → 「转账」按钮按下（高亮）→ 收起 → 上屏
        setTimeout(() => {
            const ok = mask.querySelector('.btn-ok');
            if (ok) ok.style.background = '#05a552';
            setTimeout(() => {
                closeSheet(mask);
                setTimeout(onOk, 120);
            }, 180);
        }, 850);
    }

    /* 表情面板：真实微信表情包面板（替换键盘，可点选 → 收起 → 上屏）。
       顶部分类tab + “添加的单个表情”标题 + 4×3网格（第一格为虚线收藏格）。
       params.url：要自动选中并上屏的表情图（脚本驱动）。缺省时不自动选中，
       由用户点选任意一格（键盘打开开关场景），点哪张上屏哪张并收起。
       时序（脚本）：收起键盘 → 面板滑入(0.3s) → 停 0.7s → 高亮选中格 → 0.2s → 收起 → 上屏。

       ★ 表情包库：网格「添加的单个表情」改用 main.py 离线解析时注入的
       __wxConfig.getEmojiLib()（我方发表情的表情图，去重后约 3 张），
       并把这些图【随机放进格子位置】（用户要求：随机几个位置放我的表情包）。
       未注入时回退到默认表情图列表。 */
    const _EMOJI_DEFAULTS = [
        '/images/avatar/赵本山表情包_20260903_193137_046.jpg',
        '/images/avatar/鸟都不鸟你表情包_20260904_171833_132.jpg',
        '/images/avatar/毁灭吧_我麻了_表情包_20260905_175020_589.jpg',
        '/images/avatar/好的表情包_20260905_175144_812.jpg',
        '/images/avatar/认可表情包_20260905_175240_649.jpg',
        '/images/avatar/哭泣猫咪_20260905_175009_399.jpg',
        '/images/avatar/狗歪头_20260905_204230_437.jpg',
        '/images/avatar/吃惊_20260905_204410_412.jpg',
        '/images/avatar/牛泪_20260905_204521_851.jpg',
        '/images/avatar/害羞猫咪_20260905_205157_951.jpg',
        '/images/avatar/女生好困了_20260905_205054_216.png',
    ];
    function _emojiDecorList() {
        /* 优先用「我方表情包库」（main.py 注入）；没有则回退到默认表情图。 */
        const lib = (window.__wxConfig && window.__wxConfig.getEmojiLib)
            ? window.__wxConfig.getEmojiLib() : [];
        return (lib && lib.length) ? lib.slice() : _EMOJI_DEFAULTS.slice();
    }
    function _shuffle(arr) {
        const a = arr.slice();
        for (let i = a.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            const t = a[i]; a[i] = a[j]; a[j] = t;
        }
        return a;
    }
    /* 消息区贴底跟随：在 durMs 内逐帧把 scrollTop 钉到「内容底 − 可视高」。
       —— 键盘/面板弹起时消息区高度收缩，内容铺满则最新消息贴着输入栏上移（文字上推）；
          收起时高度恢复，内容贴底下落。内容不铺满（scrollHeight<=clientHeight）时锚顶不动
          （真机：消息少时停留在顶部，不随键盘移）。 */
    function _pinSectionBottom(durMs) {
        const sec = document.querySelector('.dialogue-section');
        if (!sec) return;
        const t0 = performance.now();
        const step = (t) => {
            const max = sec.scrollHeight - sec.clientHeight;
            if (max > 0) sec.scrollTop = max;
            if (performance.now() - t0 < (durMs || 280)) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }
    function emojiSheet(opts, onPick) {
        const url = (opts && opts.url) || '';
        const autoPick = !!(opts && opts.url);   // 有 url 即脚本自动选中；无 url 则可点选
        const SLOTS = 11;                        // 网格 1..11 放表情（0 为虚线收藏格）
        /* 表情填充：我的表情包库去重后，每张【随机放进一个格子】（用户要求：随机几个位置
           放我的表情包）；剩余格子用默认表情图补满（去重），让面板保持饱满且不重复。 */
        let pool = _emojiDecorList();
        if (autoPick && url && pool.indexOf(url) < 0) pool = [url].concat(pool);
        const mine = [];
        for (const u of pool) if (mine.indexOf(u) < 0) mine.push(u);
        const positions = _shuffle(Array.from({ length: SLOTS }, (_, i) => i));
        const cellSrc = new Array(SLOTS).fill('');
        const used = new Set();
        let posIdx = 0;
        // 1) 我的表情包先放（随机格子）
        for (const u of mine.slice(0, SLOTS)) {
            cellSrc[positions[posIdx++]] = u;
            used.add(u);
        }
        // 2) 剩余格子用默认表情图补满（跳过已用，避免重复）
        const defOrder = _shuffle(_EMOJI_DEFAULTS.slice());
        let dIdx = 0;
        for (let i = 0; i < SLOTS; i++) {
            if (cellSrc[i]) continue;
            let src = defOrder[dIdx % defOrder.length];
            let guard = 0;
            while (used.has(src) && guard < defOrder.length) {
                dIdx++; src = defOrder[dIdx % defOrder.length]; guard++;
            }
            cellSrc[i] = src;
            used.add(src);
            dIdx++;
        }
        // 目标 url：保证在当前面板里能找到对应格（便于自动高亮）
        let pickIdx = -1;
        if (autoPick) {
            pickIdx = cellSrc.indexOf(url);
            if (pickIdx < 0) { pickIdx = positions[0]; cellSrc[pickIdx] = url; }
        }
        // 网格 12 格：index 0 = 虚线收藏格，1..11 放表情图。
        let cells = '<div class="ep-cell ep-add" data-idx="0"><span>+</span></div>';
        for (let i = 0; i < SLOTS; i++) {
            cells += '<div class="ep-cell" data-idx="' + (i + 1) + '"><img src="' + cellSrc[i] + '"></div>';
        }
        const body =
            '<div class="ep-tabs">' +
            '<div class="ep-tab"><img src="/images/emoji_panel/tab_search.png"></div>' +
            '<div class="ep-tab"><img src="/images/emoji_panel/tab_smile.png"></div>' +
            '<div class="ep-tab active"><img src="/images/emoji_panel/tab_heart.png"></div>' +
            '<div class="ep-tab"><img src="/images/emoji_panel/tab_gesture.png"></div>' +
            '</div>' +
            '<div class="ep-handle"></div>' +
            '<div class="ep-head">添加的单个表情</div>' +
            '<div class="ep-grid">' + cells + '</div>';

        const panel = document.createElement('div');
        panel.className = 'wx-emoji-panel';
        panel.innerHTML = body;
        document.body.appendChild(panel);

        // 实测面板高度：输入栏上移到面板顶（真机：输入栏不收起、仅上移）。
        // offsetHeight 不受 translateY 影响，故在滑入前即可测得。
        const panelH = panel.offsetHeight || 583;
        document.body.style.setProperty('--emoji-h', panelH + 'px');
        // 收起键盘，但跳过消息区高度动画（表情面板接管消息区高度），
        // 避免「键盘收起先把消息区弹回、面板再压缩」的两段跳动。
        try {
            if (window.__wxKeyboard && window.__wxKeyboard.hide) window.__wxKeyboard.hide({ keepSection: true });
        } catch (e) { /* 忽略 */ }
        document.body.classList.add('wx-emoji-open');
        // 同帧起步：先强制 reflow 提交 translateY(100%) 起始态，再立刻加 open，
        // 让面板滑入与键盘下滑同一帧开始，交叉才均匀（双 rAF 会让面板晚 ~一帧）。
        void panel.offsetHeight;
        panel.classList.add('open');
        // 消息区随面板上移的「文字上推」：内容铺满时逐帧贴底，最新消息贴着输入栏上移；
        // 内容未铺满时锚顶不动（真机行为）。面板收起时同样用到 _pinSectionBottom 让文字下落。
        _pinSectionBottom(280);

        const close = (cb) => {
            document.body.classList.remove('wx-emoji-open');
            panel.classList.remove('open');
            // 面板收起，消息区高度恢复：内容贴底跟随下落（文字「落下」）。内容不铺满则锚顶。
            _pinSectionBottom(300);
            setTimeout(() => { if (panel.parentNode) panel.parentNode.removeChild(panel); }, 360);
            if (cb) setTimeout(cb, 160);
        };

        if (autoPick) {
            const pick = panel.querySelector('.ep-cell[data-idx="' + (pickIdx + 1) + '"]');
            setTimeout(() => {
                if (pick) pick.classList.add('ep-picked');
                setTimeout(() => {
                    // 真实微信：点选表情包 → 表情立即上屏，随后面板才收起。
                    // 先 onPick(url) 上屏，再 close() 收起面板（不再等收起完成才上屏）。
                    if (onPick) onPick(url);
                    close();
                }, 200);
            }, 700);
        } else {
            // 可点选：点任一非收藏格 → 上屏该图并收起
            panel.querySelectorAll('.ep-cell:not(.ep-add)').forEach((c) => {
                c.addEventListener('click', () => {
                    const src = c.querySelector('img') && c.querySelector('img').src;
                    // 真实微信：点选即上屏，随后收回面板
                    if (onPick) onPick(src);
                    close();
                });
            });
        }
    }
    /* 消息写入 store（Vue 渲染）的通用入口。
       ★ 为什么不直接 appendRow：appendRow 直插 DOM 的气泡不进 store，
         离开聊天页再回来时 Vue 按 store 重画消息区，气泡就会「消失」。
       fields：消息字段，结构与后台消息（main.py _bgMsgEntry）和 dialogue.vue
       的渲染分支一致：image / emoji / voice / link{title,image,source} /
       transfer{amount,title} / system / text。text 字段同时供主页会话预览
       显示（如 '[图片]'/'[转账]'/'[表情]'）。
       time：时间标注（如 "18:22"），换算成 date + timeText + forceTime，
       由 dialogue.vue 的 showTime 在该消息前强制显示时间分隔条。
       onFresh(freshRow)：渲染完成后回调，参数是「刚上屏」的行元素（可能为
       null），供发送中动画 / 图片尺寸回填等后处理。
       沿用 pushMsgToStore 的「新行移到消息区末尾」修正：Vue 渲染的新行会插到
       最后一条 Vue 行之后、却落在既有直插气泡之前，这里把刚上屏的行
       appendChild 到最末，保证时序与真实发送一致。
       返回 entry（真值）；store 不可用返回 null（调用方退回 appendRow 兜底）。 */
    function pushStoreEntry(isSelf, fields, time, onFresh) {
        try {
            const app = document.getElementById('app');
            const vm = app && app.__vue__;
            if (!vm || !vm.$store || !vm.$route) return null;
            const state = vm.$store.state;
            const list = (state.msgList && state.msgList.baseMsg) || [];
            const mid = vm.$route.query && vm.$route.query.mid;
            const cur = list.find((it) => String(it.mid) === String(mid));
            if (!cur || !Array.isArray(cur.msg)) return null;
            /* 记录推送前已有的气泡行，渲染后据此定位「刚上屏」的那一行 */
            const sec = document.querySelector('.dialogue-section');
            const before = new Set(sec ? Array.from(sec.querySelectorAll('.row')) : []);
            const cfg = (window.__wxConfig && window.__wxConfig.get()) || null;
            const entry = Object.assign({
                name: isSelf ? (cfg && cfg.me && cfg.me.name) || 'd'
                             : (cur.user && cur.user[0] && cur.user[0].nickname) || '对方',
                headerUrl: isSelf ? meAvatar() : peerAvatar(),
                date: Date.now(),
            }, fields);
            if (time) {
                const parsed = (window.__wxConfig && window.__wxConfig.parseTimeSpec)
                    ? window.__wxConfig.parseTimeSpec(time) : null;
                if (parsed) { entry.date = parsed.ts; entry.timeText = parsed.text; }
                else entry.timeText = time;
                entry.forceTime = true;
            }
            cur.msg.push(entry);
            if (vm.$forceUpdate) vm.$forceUpdate();
            if (vm.$nextTick) vm.$nextTick(() => {
                const s = document.querySelector('.dialogue-section');
                let fresh = null;
                if (s) {
                    const rows = Array.from(s.querySelectorAll('.row'));
                    for (let i = rows.length - 1; i >= 0; i--) {
                        if (!before.has(rows[i])) { fresh = rows[i]; break; }
                    }
                    if (fresh) s.appendChild(fresh);   // 无直插气泡时为原地 no-op
                }
                if (onFresh) { try { onFresh(fresh); } catch (e) { /* 后处理失败不影响上屏 */ } }
                scrollBottom();
            });
            return entry;
        } catch (e) { return null; }
    }

    /* 表情消息入 store（薄封装，保持旧调用点兼容） */
    function pushEmojiToStore(isSelf, url, time) {
        return !!pushStoreEntry(isSelf, { text: '[表情]', emoji: url }, time);
    }

    /* 键盘「笑脸」键 / 输入栏右侧笑脸：打开可点选的表情面板（停在原地，点哪张发哪张）。 */
    window.__wxEmojiPanel = {
        open: function () {
            // 点选一张表情包：点选即上屏、随后收起面板（真实微信点表情包即发送）
            emojiSheet({}, function (src) {
                if (!src) return;
                if (!pushEmojiToStore(true, src)) {
                    appendRow(true, '<p class="text msg-emoji"><img src="' + src + '"></p>');
                }
            });
        },
        close: function () {
            document.body.classList.remove('wx-emoji-open');
            const p = document.querySelector('.wx-emoji-panel');
            if (p) { p.classList.remove('open'); setTimeout(() => p.remove(), 320); }
        },
        visible: function () {
            const p = document.querySelector('.wx-emoji-panel');
            return !!p && p.classList.contains('open');
        },
    };
    /* 输入栏右侧「笑脸」键：点一下收起键盘、表情面板滑入；再点一下收起面板、键盘滑回。
       （对齐参考视频：面板打开时该键回到键盘。用事件委托，兼容 Vue 重建 DOM。）
       图标切换是即时的（CSS .wx-emoji-open 直接把背景换成键盘图），无变暗/缩放动画。 */
    document.addEventListener('pointerdown', (ev) => {
        const ex = ev.target && ev.target.closest && ev.target.closest('.component-dialogue-bar-person .expression');
        if (!ex || !window.__wxEmojiPanel) return;
        if (window.__wxEmojiPanel.visible()) {
            window.__wxEmojiPanel.close();
            try { if (window.__wxKeyboard && window.__wxKeyboard.show) window.__wxKeyboard.show(); } catch (e) { /* 忽略 */ }
        } else {
            window.__wxEmojiPanel.open();
        }
    });

    /* ============================================================
       输入框可换行自动增高
       ------------------------------------------------------------
       .chat-txt 已改为 <textarea>（dialogue.vue）。当文字换行到多行时，
       盒子随内容长高；输入工具栏/消息区随之联动（--chat-grow 驱动
       chat_exact.css），发送清空后自动回落。键盘展开（wxkb-open）与
       表情面板打开（wx-emoji-open）两种展开态都生效。
       ============================================================ */
    const _GROW_BASE = 61;        // 必须与 --chat-box-base 一致
    const _GROW_LN_H = 38;        // 必须与 --chat-ln-h 一致
    const _GROW_MAX_LINES = 6;    // 达到该行数前输入框持续长高（真实微信“一直上移”），超出才转内部滚动
    const _growDoc = () => document.documentElement;

    const _chatGrowInput = () => {
        const ta = document.querySelector('.dialogue .chat-txt');
        return (ta && ta.tagName === 'TEXTAREA') ? ta : null;
    };
    /* 输入栏「展开态」判定：键盘展开(wxkb-open) 或 表情面板打开(wx-emoji-open)。
       两种展开态下输入栏都随 --chat-grow 增高（wx-emoji-open 与 wxkb-open 的 CSS 均引用
       --chat-grow），故 --chat-grow 都须保留/重算。否则键盘→表情面板切换时 wxkb-open
       被移除、grow 被误清 0，多行输入框坍缩截断。 */
    const _chatBarExpanded = () =>
        document.body.classList.contains('wx-chat') &&
        (document.body.classList.contains('wxkb-open') ||
         document.body.classList.contains('wx-emoji-open'));

    const _resetChatGrow = () => _growDoc().style.setProperty('--chat-grow', '0px');

    /* 消息区滚到底：仅当内容溢出可视区(历史铺满)才滚，贴住输入栏；
       未溢出时保持顶部锚定，键盘弹出只压缩底部空区，不把消息/头部往上顶。 */
    const _scrollChatSection = () => {
        const sec = document.querySelector('.dialogue-section');
        if (!sec || !(sec.scrollHeight > sec.clientHeight)) return;
        sec.scrollTop = sec.scrollHeight;
        requestAnimationFrame(() => { sec.scrollTop = sec.scrollHeight; });
    };

    /* 根据文字是否为空，给 .chat-way 加/去 has-text（驱动麦克风渐隐、输入框变全宽） */
    const _syncChatMic = (ta) => {
        const way = ta ? ta.closest('.chat-way') : null;
        if (!way) return;
        if ((ta.value || '').trim()) way.classList.add('has-text');
        else way.classList.remove('has-text');
    };

    /* 按内容高度重算 --chat-grow：切到 auto 量内容 → 算行数 → 交回 CSS calc 接管。 */
    const _recalcChatGrow = () => {
        if (!_chatBarExpanded()) { _resetChatGrow(); return; }
        const ta = _chatGrowInput();
        if (!ta) { _resetChatGrow(); return; }
        ta.style.setProperty('height', 'auto', 'important');   // 释放固定高再量内容
        const needed = ta.scrollHeight || 0;
        /* 封顶高度 = 单行基线 + (最大行数-1)*行高 */
        const maxH = _GROW_BASE + (_GROW_MAX_LINES - 1) * _GROW_LN_H;
        const h = Math.min(needed, maxH);
        const grow = Math.max(0, Math.round(h - _GROW_BASE));
        _growDoc().style.setProperty('--chat-grow', grow + 'px');
        /* 超过封顶行数 → 内部滚动，否则交给盒子高度（隐藏内部滚动条） */
        ta.style.setProperty('overflow-y', needed > maxH ? 'auto' : 'hidden', 'important');
        ta.style.removeProperty('height');                     // 让 CSS calc 决定最终高度
        _syncChatMic(ta);                                      // 同步麦克风渐隐/全宽
        _scrollChatSection();                                  // 消息区随上移
    };

    let _growHooked = false;
    const _hookChatGrow = () => {
        if (_growHooked) return;
        _growHooked = true;
        document.addEventListener('input', (e) => {
            const t = e.target;
            if (t && t.classList && t.classList.contains('chat-txt')) _recalcChatGrow();
        }, true);
        document.addEventListener('focusin', (e) => {
            const t = e.target;
            if (t && t.classList && t.classList.contains('chat-txt')) _recalcChatGrow();
        }, true);
        document.addEventListener('keydown', (e) => {
            if ((e.key === 'Enter' || e.keyCode === 13) && e.target &&
                e.target.classList && e.target.classList.contains('chat-txt')) {
                /* 发送由其它脚本先清空输入框；延后重算以捕获“发送后收起” */
                setTimeout(_recalcChatGrow, 0);
            }
        }, true);
        /* 键盘/表情面板开、关（wxkb-open / wx-emoji-open）时重置或触发，避免切换时 grow 被清空 */
        if (window.MutationObserver) {
            const obs = new MutationObserver(_recalcChatGrow);
            obs.observe(document.body, { attributes: true, attributeFilter: ['class'] });
        }
    };

    /* ============================================================
       聊天页专属结构注入（dialogue.vue mounted 时调用 __wxChatPage.mount）
       ------------------------------------------------------------
       补充参考图规格里需要、Vue 组件不渲染的元素：
         1. 导航栏未读胶囊 .nav-unread（"12"）
         2. 右侧三点悬浮胶囊 .chat-right-pill
         3. 输入框内麦克风 .chat-mic
         4. 消息区顶部被裁切的贴纸 .chat-clip-top
         5. 状态栏左侧图标随键盘切换（定位 / 静音）
       ============================================================ */
    window.__wxChatPage = {
        _hooked: false,

        mount() {
            /* 0. 聊天页是固定 600×1300 画布，本不该滚动。
                聚焦输入框时 dialogue.vue 的 focusIpt() 会写 document.body.scrollTop = scrollHeight，
                overflow:hidden 并不能阻止程序化滚动，导致整个 #app 被顶上约 210px(上顶/错乱)，
                这是“弹出把消息/页面顶上顶、收起错乱”的元凶。这里加滚动护栏：把 html/body 滚动钳回 0。
                (只复位滚动位置，不动布局/overflow/contain，风险低。) */
            if (!window.__wxScrollGuard) {
                window.__wxScrollGuard = setInterval(() => {
                    if (!document.body.classList.contains('wx-chat')) return;
                    if (document.documentElement.scrollTop) document.documentElement.scrollTop = 0;
                    if (document.body.scrollTop) document.body.scrollTop = 0;
                    if (window.pageYOffset || window.scrollY) window.scrollTo(0, 0);
                }, 50);
            }
            /* 0. 输入框可换行自动增高（仅首次挂载 hook，之后由 input/focus/keydown/class 触发） */
            _hookChatGrow();
            _recalcChatGrow();
            /* 1. 未读胶囊（固定显示 99，不随会话未读数变化） */
            if (!document.querySelector('.dialogue .nav-unread')) {
                const hd = document.querySelector('.dialogue #wx-header');
                if (hd) {
                    const pill = document.createElement('span');
                    pill.className = 'nav-unread';
                    pill.textContent = '99';
                    hd.appendChild(pill);
                }
            }
            /* 2. 右上角三点悬浮胶囊 */
            if (!document.getElementById('chat-right-pill')) {
                const pill = document.createElement('span');
                pill.id = 'chat-right-pill';
                pill.className = 'chat-right-pill';
                pill.innerHTML = '<i></i><i></i><i></i>';
                document.body.appendChild(pill);
            }
            /* 2b. 左上角“收起键盘”小图标（键盘展开时显示，点击收起键盘） */
            if (!document.getElementById('chat-kb-collapse')) {
                const kb = document.createElement('span');
                kb.id = 'chat-kb-collapse';
                kb.className = 'chat-kb-collapse';
                kb.textContent = '∨';   /* 收起键盘的向下 chevron */
                kb.addEventListener('click', () => {
                    try { if (window.__wxKeyboard && window.__wxKeyboard.hide) window.__wxKeyboard.hide(); }
                    catch (e) { /* 忽略 */ }
                });
                document.body.appendChild(kb);
            }
            /* 3. 输入框内麦克风（注入到「键盘输入」容器，避免随语音容器被隐藏）
               换成参考图线稿麦克风（透明 PNG，见 /images/chatbar/mic_line.png） */
            if (!document.querySelector('.chat-way .chat-mic')) {
                const txt = document.querySelector('.chat-way .chat-txt');
                const way = txt ? txt.parentNode : null;
                if (way) {
                    const mic = document.createElement('span');
                    mic.className = 'chat-mic';
                    mic.innerHTML =
                        '<img src="/images/chatbar/mic_line.png" alt="语音" ' +
                        'style="display:block; width:21px; height:28px; object-fit:contain;">';
                    way.appendChild(mic);
                }
            }
            /* 4. 消息区顶部被裁切的贴纸（露下沿） */
            const sec = document.querySelector('.dialogue-section');
            if (sec && !sec.querySelector('.chat-clip-top')) {
                const clip = document.createElement('div');
                clip.className = 'chat-clip-top';
                clip.innerHTML = '<img src="/images/chat/sticker1.png">';
                sec.appendChild(clip);
            }
            /* 5. 键盘弹出时状态栏图标：定位 -> 静音 */
            if (!this._hooked) {
                this._hooked = true;
                const apply = () => {
                    if (!document.body.classList.contains('wx-chat')) return;
                    const pf = window.__wxPhoneFrame;
                    if (!pf) return;
                    pf.setLeftIcon(document.body.classList.contains('wxkb-open') ? 'mute' : 'loc');
                };
                if (window.MutationObserver) {
                    const obs = new MutationObserver(() => apply());
                    obs.observe(document.body, { attributes: true, attributeFilter: ['class'] });
                }
                setTimeout(apply, 0);
            }
            /* 6. 统一缩放聊天区所有图片气泡（含 Vue 渲染的历史会话图片，
               否则按原始尺寸显示会巨大）。监听子节点插入，新图片一上屏就按规则缩放。 */
            fitAllImageBubbles();
            if (window.MutationObserver) {
                const fitObs = new MutationObserver(() => fitAllImageBubbles());
                const secEl = document.querySelector('.dialogue-section');
                if (secEl) fitObs.observe(secEl, { childList: true, subtree: true });
            }
        },
    };

window.__wxChatExt = {
        /* ---- 我方 / 对方 图片消息 ----
           我方发图：不再弹「+」功能面板，而是直接闪黑跳转到图片预览页
           （复刻参考图：顶部返回/勾选、中间待发图、底部 编辑/原图/发送），
           预览页自动播放「发送」按压后，以「发送中」占位（半透明缩略图 +
           旋转进度圈）上屏，0.65s 后定格为完整图片。 */
        /* 直接上屏图片气泡（带发送中转圈动画），供预览页点发送后调用。
           ★ 入 store（Vue 渲染）保证「切页面再回来」图片不消失；
             渲染完成后在刚上屏的行上补「发送中」动画（半透明 + 转圈，0.65s 定格），
             尺寸由 imageDisplaySize 按面积恒定规则内联回填。 */
        selfImage(url, time) {
            const pushWithAnim = () => {
                const entry = pushStoreEntry(true, { text: '[图片]', image: url }, time, (fresh) => {
                    const p = fresh && fresh.querySelector('.text.msg-image');
                    if (!p) return;
                    p.classList.add('msg-sending');
                    const ring = document.createElement('span');
                    ring.className = 'sending-ring';
                    ring.innerHTML = '<span class="ring-inner"></span>';
                    p.appendChild(ring);
                    imageDisplaySize(url, (real) => {
                        p.style.width = real.w + 'px';
                        p.style.height = real.h + 'px';
                    });
                    setTimeout(() => {
                        p.classList.remove('msg-sending');
                        const r = p.querySelector('.sending-ring');
                        if (r) r.remove();
                    }, 650);
                });
                if (!entry) pushImageBubbleImage(url, time);   // store 不可用退回 DOM 直插
            };
            // 预览页未注入时，直接「入 store + 动画」上屏，不再退回旧 DOM 直插
            if (!window.__wxSendImage) {
                pushWithAnim();
                return true;
            }
            // 先收起手机键盘（若展开，避免与预览页重叠）
            try { if (window.__wxKeyboard && window.__wxKeyboard.hide) window.__wxKeyboard.hide(); } catch (e) { /* 忽略 */ }
            // 直接打开图片预览页（内部含「闪黑 → 预览图浮现 → 自动发送」）
            return window.__wxSendImage.open(url, pushWithAnim);
        },
        /* 对方发图：入 store；尺寸由 fitImageBubble 在渲染后回填（面积恒定规则） */
        peerImage(url, time) {
            if (pushStoreEntry(false, { text: '[图片]', image: url }, time, (fresh) => {
                const p = fresh && fresh.querySelector('.text.msg-image');
                if (p) fitImageBubble(p);
            })) return true;
            const row = appendRow(false, '', {
                size: imageDisplaySize(url, (real) => {
                    const p = row && row.querySelector('.text.msg-image');
                    if (p) { p.style.width = real.w + 'px'; p.style.height = real.h + 'px'; }
                }),
                innerHtml: '<img src="' + url + '" style="width:100%;height:100%;object-fit:contain;">',
            }, time);
            return !!row;
        },

        /* ---- 我方 / 对方 语音消息（入 store，dialogue.vue voiceBars 渲染，波形规则一致）---- */
        selfVoice(secs) {
            return !!pushStoreEntry(true, { voice: secs }) || !!appendRow(true, voiceHtml(secs, true));
        },
        peerVoice(secs) {
            return !!pushStoreEntry(false, { voice: secs }) || !!appendRow(false, voiceHtml(secs, false));
        },

        /* ---- 我方 / 对方 表情贴纸 ----
           我方发表情：底部表情面板滑出 → 点选 → 表情包上屏(pop-in) → 面板收起。
           脚本链路：面板自动高亮该 url 所在格 → 表情先上屏 → 再收起面板。
           time：时间标注（如 "18:22"），给出时该表情消息前显示一条时间分隔条。 */
        selfEmoji(url, time) {
            if (!url) return false;
            emojiSheet({ url: url }, function () {
                /* 入 store（Vue 渲染）保证「切页面再回来」表情不消失；store 不可用才退回 DOM 直插 */
                if (!pushEmojiToStore(true, url, time)) {
                    appendRow(true, '<p class="text msg-emoji"><img src="' + url + '"></p>', null, time);
                }
            });
            return true;
        },
        peerEmoji(url, time) {
            if (!url) return false;
            if (pushEmojiToStore(false, url, time)) return true;
            return !!appendRow(false, '<p class="text msg-emoji"><img src="' + url + '"></p>', null, time);
        },

        /* ---- 我方 / 对方 链接卡片（公众号文章 / 分享链接）----
           入 store（dialogue.vue msg-link 分支渲染，结构与 DOM 版一致），
           保证切画面回来不消失；store 不可用退回 DOM 直插。 */
        selfLink(title, img, source, time) {
            const t = String(title == null ? '' : title).trim();
            const s = String(source == null || source === '' ? '心灵知行' : source);
            if (t && pushStoreEntry(true, { text: '[链接]', link: { title: t, image: img || '', source: s } }, time)) return true;
            return !!linkCard(true, title, img, source, time);
        },
        peerLink(title, img, source, time) {
            const t = String(title == null ? '' : title).trim();
            const s = String(source == null || source === '' ? '心灵知行' : source);
            if (t && pushStoreEntry(false, { text: '[链接]', link: { title: t, image: img || '', source: s } }, time)) return true;
            return !!linkCard(false, title, img, source, time);
        },

        /* 撤回：删除最后一条消息并显示系统提示。
           ★ store 路径：弹出最后一条消息条目 + 写入 system 提示条目，两者都持久化
             （切页面回来撤回状态不回退）。store 不可用退回旧 DOM 直删。 */
        withdraw(isSelf) {
            try {
                const app = document.getElementById('app');
                const vm = app && app.__vue__;
                const mid = vm.$route.query.mid;
                const cur = vm.$store.state.msgList.baseMsg.find((it) => String(it.mid) === String(mid));
                if (cur && Array.isArray(cur.msg) && cur.msg.length) {
                    cur.msg.pop();
                    cur.msg.push({
                        system: isSelf ? '你撤回了一条消息' : '对方撤回了一条消息',
                        date: Date.now(),
                    });
                    if (vm.$forceUpdate) vm.$forceUpdate();
                    if (vm.$nextTick) vm.$nextTick(() => scrollBottom());
                    return true;
                }
            } catch (e) { /* store 不可用，走 DOM 兜底 */ }
            const sec = document.querySelector('.dialogue-section');
            if (!sec) return false;
            const rows = sec.querySelectorAll('.row');
            const last = rows[rows.length - 1];
            if (last) last.remove();
            const tip = document.createElement('div');
            tip.className = 'msg-system';
            tip.textContent = isSelf ? '你撤回了一条消息' : '对方撤回了一条消息';
            sec.appendChild(tip);
            scrollBottom();
            return true;
        },

        /* 转发：显示“转发：内容”（入 store，{{item.text}} 渲染天然防注入） */
        forward(text) {
            if (pushStoreEntry(true, { text: '转发：' + String(text == null ? '' : text) })) return true;
            return !!appendRow(true, '<p class="text">转发：' + text + '</p>');
        },

        /* @成员：把 @昵称 填进输入框（不发送，可配合“我方打字”） */
        mention(name) {
            const input = document.querySelector('.chat-txt');
            if (!input) return false;
            input.focus();
            input.value = '@' + name + ' ';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            return true;
        },

        /* 自定义系统提示（如 群公告 / 时间分隔）—— 入 store 持久化 */
        system(text) {
            if (pushStoreEntry(true, { system: String(text == null ? '' : text) })) return true;
            const sec = document.querySelector('.dialogue-section');
            if (!sec) return false;
            const tip = document.createElement('div');
            tip.className = 'msg-system';
            tip.textContent = text;
            sec.appendChild(tip);
            scrollBottom();
            return true;
        },

        /* ---- 转账（note/title 均可每次自定义卡片上的文字；title 优先级更高）----
           入 store：dialogue.vue 的 msg-transfer 分支用 transferCardInner 渲染
           （结构/配色/金额字号与 DOM 版完全一致），切画面回来卡片仍在；
           主页会话预览显示「[转账]」。store 不可用退回 DOM 直插。 */
        selfTransfer(recipient, amount, note, title) {
            const who = String(recipient == null || recipient === '' ? '对方' : recipient);
            const amt = String(amount == null || amount === '' ? '1.00' : amount);
            const nt = String(note == null ? '' : note);
            const subtitle = String(title == null ? '' : title).trim() || nt.trim() || '你发起了一笔转账';
            if (pushStoreEntry(true, { text: '[转账]', transfer: { amount: amt, title: subtitle } })) return true;
            return transferCard(true, who, amt, nt, title);
        },
        peerTransfer(recipient, amount, note, title) {
            const amt = String(amount == null || amount === '' ? '1.00' : amount);
            const subtitle = String(title == null ? '' : title).trim()
                || String(note == null ? '' : note).trim() || '对方发来一笔转账';
            if (pushStoreEntry(false, { text: '[转账]', transfer: { amount: amt, title: subtitle } })) return true;
            return transferCard(false, recipient, amount, note, title);
        },

        /* 供 dialogue.vue store 渲染转账卡片（返回 <p class="text msg-transfer"> 的内层） */
        transferCardHtml(t) { return transferCardInner(t); },
    };
})();
