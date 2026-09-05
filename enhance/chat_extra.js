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
      /* ---- 微信转账卡片气泡（对齐参考图片3：橙色底 + 左侧转账图标 + 白字大金额 + 「你发起了一笔转账」标题 + 左下「转账」角标） ---- */
      .row .text.msg-transfer, .row.self .text.msg-transfer {
        background: #e08a2c !important; color: #fff !important;
        padding: 12px 14px 14px; min-width: 184px; max-width: 72%;
        border-radius: 8px; box-shadow: none !important;
        position: relative;
      }
      /* 主区：图标 + 金额/标题 横向 */
      .msg-transfer .tf-main {
        display: flex; align-items: center; gap: 11px;
        margin-bottom: 10px;
      }
      /* 左侧转账图标：白描边交换箭头 + 半透明圆角底 */
      .msg-transfer .tf-icon {
        flex: 0 0 30px; width: 30px; height: 30px; border-radius: 8px;
        background: rgba(255, 255, 255, .22);
        display: flex; align-items: center; justify-content: center;
      }
      .msg-transfer .tf-icon svg { width: 22px; height: 22px; display: block; }
      .msg-transfer .tf-body { flex: 1; min-width: 0; }
      .msg-transfer .tf-amount {
        display: flex; align-items: baseline; gap: 3px;
        color: #fff; font-size: 32px; font-weight: 700;
        line-height: 1.1;
      }
      .msg-transfer .tf-amount .rmb { font-size: 22px; font-weight: 600; }
      .msg-transfer .tf-title {
        color: rgba(255, 255, 255, .95); font-size: 15px; font-weight: 500;
        letter-spacing: .3px; line-height: 1.5; margin-top: 3px;
      }
      .msg-transfer .tf-header {
        color: rgba(255, 255, 255, .92); font-size: 13px; line-height: 1.4;
      }
      .msg-transfer .tf-header b { font-weight: 600; color: #fff; }
      .msg-transfer .tf-note {
        color: rgba(255, 255, 255, .85); font-size: 12px; line-height: 1.4; margin-top: 2px;
      }
      .msg-transfer .tf-note:empty { display: none; }
      /* 左下角「转账」小标签：图片3 卡片底部有独立角标 */
      .msg-transfer .tf-badge {
        position: absolute; left: 14px; bottom: 8px;
        font-size: 12px; color: rgba(255, 255, 255, .75);
        letter-spacing: .3px;
      }
      /* 我方转账卡片气泡尖角指向右侧（橙色） */
      .row.self .text.msg-transfer:before {
        border-left-color: #e08a2c !important;
      }
      .row .text.msg-transfer:before {
        border-right-color: #e08a2c !important;
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

      /* ---- 表情包面板：底部滑出，网格排布表情贴纸 ---- */
      .wx-sheet .emoji-grid {
        display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 16px;
      }
      .wx-sheet .emoji-grid .emoji-cell {
        border-radius: 6px; overflow: hidden; background: #f5f5f5; aspect-ratio: 1 / 1;
        display: flex; align-items: center; justify-content: center;
      }
      .wx-sheet .emoji-grid .emoji-cell img { width: 68%; height: 68%; object-fit: contain; display: block; }

      /* ---- 底部弹出面板：深色模式统一（微信深色：金融/表情面板跟随深色） ---- */
      .wx-pop-mask .wx-sheet { background: #1c1c1e !important; color: #fff !important; }
      .wx-pop-mask .wx-sheet .sheet-title { color: #fff !important; }
      .wx-sheet .tf-confirm .cf-header { color: #8e8e93 !important; }
      .wx-sheet .tf-confirm .cf-amount { color: #07c160 !important; }
      .wx-sheet .tf-confirm .cf-note { color: #5a5a5e !important; }
      .wx-sheet .tf-btns .btn-cancel { background: #2e2e30 !important; color: #fff !important; }
      .wx-sheet .tf-btns .btn-ok { background: #07c160 !important; color: #fff !important; }
      .wx-sheet .emoji-grid .emoji-cell { background: #2c2c2e !important; }

      /* ---- 修正：我方图片气泡去掉绿底、转账卡片统一为橙色（贴合参考图片3）---- */
      .dialogue-section .row .text.msg-image,
      .dialogue-section .row.self .text.msg-image {
        background: transparent !important; padding: 4px !important; box-shadow: none !important;
      }
      .dialogue-section .row .text.msg-transfer,
      .dialogue-section .row.self .text.msg-transfer {
        background: #f5a623 !important; color: #fff !important;
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
      .row .text.msg-emoji img { width: 78px; height: 78px; object-fit: contain; display: block; }
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

    /* 转账卡片：金额 + 备注。isSelf 控制气泡在左还是右（对齐图片3：标题+金额+「转账」角标） */
    function transferCard(isSelf, recipient, amount, note) {
        const who = String(recipient == null || recipient === '' ? (isSelf ? '对方' : '我') : recipient);
        const amt = String(amount == null || amount === '' ? '50.00' : amount);
        const nt = String(note == null ? '' : note);
        const title = isSelf ? '你发起了一笔转账' : '对方发来一笔转账';
        const icon = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l4 4-4 4"/><path d="M19 9H8"/><path d="M9 19l-4-4 4-4"/><path d="M5 15h11"/></svg>';
        const html = '<p class="text msg-transfer">' +
            '<span class="tf-main">' +
                '<span class="tf-icon">' + icon + '</span>' +
                '<span class="tf-body">' +
                    '<span class="tf-amount"><span class="rmb">¥</span><span class="amt"></span></span>' +
                    '<span class="tf-title">' + title + '</span>' +
                '</span>' +
            '</span>' +
            '<span class="tf-header">转账给<b></b></span>' +
            '<span class="tf-note"></span>' +
            '<span class="tf-badge">转账</span>' +
            '</p>';
        const row = appendRow(isSelf, html);
        if (!row) return false;
        const b = row.querySelector('.tf-header b');
        if (b) b.textContent = who;
        const a = row.querySelector('.tf-amount .amt');
        if (a) {
            a.textContent = amt;
            a.style.fontSize = String(amt).length > 6 ? '22px' : '30px';
        }
        const n = row.querySelector('.tf-note');
        if (n) n.textContent = nt;
        return true;
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

    /* 表情面板：底部滑出，网格展示表情，居中高亮将发送的那个。
       自动「点选 → 收起 → 上屏」。 */
    function emojiSheet(url, onPick) {
        const cells = Array.from({ length: 10 }, (_, i) =>
            '<div class="emoji-cell" data-idx="' + i + '">' +
            (i === 2 ? '<img src="' + url + '">' : '') +
            '</div>').join('');
        const body = '<div class="emoji-grid">' + cells + '</div>';
        const mask = buildSheet('表情', body, '');
        const cell = mask.querySelector('.emoji-cell[data-idx="2"]');
        setTimeout(() => {
            if (cell) cell.style.background = '#d9f6e6';
            setTimeout(() => {
                closeSheet(mask);
                setTimeout(onPick, 120);
            }, 200);
        }, 700);
    }

    /* ============================================================
       输入框可换行自动增高
       ------------------------------------------------------------
       .chat-txt 已改为 <textarea>（dialogue.vue）。当文字换行到多行时，
       盒子随内容长高；输入工具栏/消息区随之联动（--chat-grow 驱动
       chat_exact.css），发送清空后自动回落。仅键盘展开（wxkb-open）生效。
       ============================================================ */
    const _GROW_BASE = 61;        // 必须与 --chat-box-base 一致
    const _GROW_LN_H = 38;        // 必须与 --chat-ln-h 一致
    const _GROW_MAX_LINES = 6;    // 达到该行数前输入框持续长高（真实微信“一直上移”），超出才转内部滚动
    const _growDoc = () => document.documentElement;

    const _chatGrowInput = () => {
        const ta = document.querySelector('.dialogue .chat-txt');
        return (ta && ta.tagName === 'TEXTAREA') ? ta : null;
    };
    const _wxChatKbOpen = () =>
        document.body.classList.contains('wx-chat') &&
        document.body.classList.contains('wxkb-open');

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
        if (!_wxChatKbOpen()) { _resetChatGrow(); return; }
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
        /* 键盘开/关（wxkb-open）时重置或触发 */
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
        /* 直接上屏图片气泡（带发送中转圈动画），供预览页点发送后调用 */
        selfImage(url, time) {
            // 预览页未注入时，退回旧「直接上屏」逻辑，避免报错
            if (!window.__wxSendImage) {
                return pushImageBubbleImage(url, time);
            }
            const doScreen = () => pushImageBubbleImage(url, time);   // 发送后上屏
            // 先收起手机键盘（若展开，避免与预览页重叠）
            try { if (window.__wxKeyboard && window.__wxKeyboard.hide) window.__wxKeyboard.hide(); } catch (e) { /* 忽略 */ }
            // 直接打开图片预览页（内部含「闪黑 → 预览图浮现 → 自动发送」）
            return window.__wxSendImage.open(url, doScreen);
        },
        /* 对方发图：按比例预设宽高后直接以 pop-in 入场（从左侧弹出） */
        peerImage(url, time) {
            const row = appendRow(false, '', {
                size: imageDisplaySize(url, (real) => {
                    const p = row && row.querySelector('.text.msg-image');
                    if (p) { p.style.width = real.w + 'px'; p.style.height = real.h + 'px'; }
                }),
                innerHtml: '<img src="' + url + '" style="width:100%;height:100%;object-fit:contain;">',
            }, time);
            return !!row;
        },

        /* ---- 我方 / 对方 语音消息 ---- */
        selfVoice(secs) { return !!appendRow(true, voiceHtml(secs, true)); },
        peerVoice(secs) { return !!appendRow(false, voiceHtml(secs, false)); },

        /* ---- 我方 / 对方 表情贴纸 ----
           我方发表情：底部表情面板滑出 → 点选 → 收起 → 贴纸气泡 pop-in。 */
        selfEmoji(url) {
            if (!url) return false;
            emojiSheet(url, function () { appendRow(true, '<p class="text msg-emoji"><img src="' + url + '"></p>'); });
            return true;
        },
        peerEmoji(url) {
            if (!url) return false;
            return !!appendRow(false, '<p class="text msg-emoji"><img src="' + url + '"></p>');
        },

        /* 撤回：删除最后一条消息并显示系统提示 */
        withdraw(isSelf) {
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

        /* 转发：显示“转发：内容” */
        forward(text) { return !!appendRow(true, '<p class="text">转发：' + text + '</p>'); },

        /* @成员：把 @昵称 填进输入框（不发送，可配合“我方打字”） */
        mention(name) {
            const input = document.querySelector('.chat-txt');
            if (!input) return false;
            input.focus();
            input.value = '@' + name + ' ';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            return true;
        },

        /* 自定义系统提示（如 群公告 / 时间分隔） */
        system(text) {
            const sec = document.querySelector('.dialogue-section');
            if (!sec) return false;
            const tip = document.createElement('div');
            tip.className = 'msg-system';
            tip.textContent = text;
            sec.appendChild(tip);
            scrollBottom();
            return true;
        },

        /* ---- 转账 ---- */
        selfTransfer(recipient, amount, note) {
            const who = String(recipient == null || recipient === '' ? '对方' : recipient);
            const amt = String(amount == null || amount === '' ? '1.00' : amount);
            const nt = String(note == null ? '' : note);
            return transferCard(true, who, amt, nt);
        },
        peerTransfer(recipient, amount, note) { return transferCard(false, recipient, amount, note); },
    };
})();
