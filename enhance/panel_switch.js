/* ============================================================
   底部三面板「直接切换」驱动器（键盘 / 表情 / 更多）
   ------------------------------------------------------------
   解决的问题
   ----------
   以前三个面板各自为政：表情面板由 chat_extra.js 管、键盘由 keyboard.js 管、
   「+」面板由 transfer_ui.js 管，彼此只认「和收起态互切」。于是「表情开着想换
   更多」「更多开着想换键盘」都得先把面板收掉、退回聊天底部，再开另一个——画面
   上就是「先沉下去再升上来」两段跳，与真机不符。

   本模块提供唯一入口 window.__wxPanels.set(target)：
     · 输入栏/消息区由 --ps-h / --ps-sec 两个变量驱动，同一帧改写 →
       CSS 过渡直接从「当前位移」插值到「目标位移」，A→B 直线位移，不经过 0；
     · 旧面板下滑出屏、新面板同帧上滑入屏，五个联动件共用 230ms 对称 S 曲线
       （参考视频逐帧实测值，见 panel_switch.css 顶部注释）；
     · 切换期间坐标系与面板自己的稳态规则数值一致，摘掉 .wx-pswitch 后零跳变。

   与三个面板模块的协作
   --------------------
     __wxKeyboard.show({instant}) / hide({instant, keepSection})  —— 不做自身动画，
        位移交给本模块（否则会和 keyboard.js 的 rAF 动画抢同一个 transform）
     __wxEmojiPanel.open({view}) / close()                        —— 原样调用；
        滑入/滑出时长由 .wx-pswitch 的 CSS 覆盖成 230ms
     __wxTransfer.openPanel() / closePanel()                      —— 原样调用；
        同上，时长被 .wx-pswitch 覆盖

   对外 API（window.__wxPanels）
   ----------------------------
     .current()                  → 'none' | 'kb' | 'emoji' | 'attach'
     .set(target, opts)          → 直接切换；target 同上，也接受中文别名
     .toggle('emoji'|'attach')   → 输入栏笑脸/加号按钮的点击语义
     .heights()                  → 当前三档面板高度（调试用）
   ============================================================ */
(() => {
    if (window.__wxPanels) return;

    const DUR = 230;                                  /* 参考视频实测 230ms */
    const Z_TOP = '999995';                           /* 切换期间「进入的面板」临时抬到最上层 */

    /* 中文 / 英文别名 → 内部状态 */
    const ALIAS = {
        none: 'none', close: 'none', closed: 'none',
        收起: 'none', 关闭: 'none', 收面板: 'none', 收起面板: 'none',
        kb: 'kb', keyboard: 'kb', 键盘: 'kb',
        emoji: 'emoji', 表情: 'emoji', 表情面板: 'emoji',
        attach: 'attach', more: 'attach', plus: 'attach',
        更多: 'attach', 加号: 'attach', 更多面板: 'attach', 加号面板: 'attach', 附件: 'attach',
    };
    const norm = (t) => ALIAS[String(t == null ? '' : t).trim()] || null;

    const bodyCls = () => document.body.classList;

    /* ---- 当前处于哪个状态（以 body 上的类为准，三个模块都是这么标记的） ---- */
    function current() {
        const b = bodyCls();
        if (b.contains('wxp-open')) return 'attach';
        if (b.contains('wx-emoji-open')) return 'emoji';
        if (b.contains('wxkb-open')) return 'kb';
        return 'none';
    }

    /* ---- 读某个面板的「输入栏上移量」（必须与各面板稳态 CSS 的数值同源） ----
       ★ 一律读变量、不去量面板 DOM：面板自己的高（如表情面板 585）与稳态规则里
         用的上移量（--emoji-h）历史上可能不同步，量 DOM 会在切换收尾时闪跳几十像素。
         三个变量的定义处：panel_switch.css（--kb-h / --wxp-h）、chat_extra.js（--emoji-h）。 */
    function readVar(name, fallback) {
        const v = parseFloat(getComputedStyle(document.body).getPropertyValue(name));
        return isFinite(v) && v > 0 ? v : fallback;
    }
    function kbH() { return readVar('--kb-h', 513); }
    function emojiH() { return readVar('--emoji-h', 583); }
    function attachH() { return readVar('--wxp-h', 421); }

    function offsetOf(state) {
        if (state === 'kb') return kbH();
        if (state === 'emoji') return emojiH();
        if (state === 'attach') return attachH();
        return 0;
    }

    /* ---- 消息区目标高度：逐字复刻各稳态 CSS 的算式，保证摘掉 .wx-pswitch 时零跳变 ---- */
    function sectionH(state) {
        const sec = document.querySelector('.dialogue-section');
        if (!sec) return 0;
        if (state === 'none') return 1019;                       /* chat_exact.css 基础高度 */
        const rootCS = getComputedStyle(document.documentElement);
        const g = parseFloat(rootCS.getPropertyValue('--chat-grow')) || 0;   /* 0 是合法值 */
        if (state === 'kb') {
            return (parseFloat(rootCS.getPropertyValue('--chat-sec-base')) || 552) - g;
        }
        const barBase = parseFloat(rootCS.getPropertyValue('--chat-bar-base')) || 86;
        const host = sec.parentElement;
        const boxH = (host && host.clientHeight) || 1221;        /* .dialogue 高度 = 100% 的基准 */
        return boxH - 71 - g - offsetOf(state) - barBase;
    }

    function panelEl(state) {
        if (state === 'kb') return document.getElementById('wxkb');
        if (state === 'emoji') return document.querySelector('.wx-emoji-panel');
        if (state === 'attach') return document.getElementById('wxTransferPanel');
        return null;
    }

    /* ---- 让消息区底边跟随输入栏（内容溢出时逐帧贴底；未溢出时保持顶部锚定） ---- */
    function followBottom(durMs) {
        const sec = document.querySelector('.dialogue-section');
        if (!sec) return;
        const t0 = performance.now();
        const step = () => {
            const max = sec.scrollHeight - sec.clientHeight;
            if (max > 0) sec.scrollTop = max;
            if (performance.now() - t0 < durMs) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }

    /* ---- 三个面板模块的「无动画开/关」入口 ---- */
    function kbOn() {
        const k = window.__wxKeyboard;
        if (k && k.show) k.show({ instant: true });
    }
    function kbOff() {
        const k = window.__wxKeyboard;
        if (k && k.hide) k.hide({ instant: true, keepSection: true });
    }
    function emojiOn() {
        if (window.__wxEmojiPanel && window.__wxEmojiPanel.open) window.__wxEmojiPanel.open({ view: 'emoji' });
    }
    function emojiOff() {
        if (window.__wxEmojiPanel && window.__wxEmojiPanel.close) window.__wxEmojiPanel.close();
    }
    function attachOn() {
        return !!(window.__wxTransfer && window.__wxTransfer.openPanel && window.__wxTransfer.openPanel());
    }
    function attachOff() {
        if (window.__wxTransfer && window.__wxTransfer.closePanel) window.__wxTransfer.closePanel();
    }

    let busy = null;   /* 正在切换：{timer, to} */

    function settle() {
        if (!busy) return;
        clearTimeout(busy.timer);
        const el = busy.el;
        if (el) el.style.removeProperty('z-index');
        document.body.classList.remove('wx-pswitch');
        document.documentElement.style.removeProperty('--ps-dur');
        busy = null;
    }

    /* ============================================================
       核心：直接切换
       ============================================================ */
    function set(target, opts) {
        opts = opts || {};
        const to = norm(target);
        if (!to) return false;
        /* 三个面板都是聊天页专属组件；不在聊天页只允许「切到收起」 */
        if (!document.querySelector('.dialogue-section')) {
            if (to !== 'none') return false;
        }
        const from = current();
        if (from === to) return true;
        if (busy) settle();

        const dEl = document.documentElement;
        const footer = document.querySelector('.dialogue-footer');
        const sec = document.querySelector('.dialogue-section');
        const dur = Math.max(60, Number(opts.dur) || DUR);

        /* ---- ① 钉住现状：挂 .wx-pswitch + 写入当前位移/消息区高度。
               此刻 .wx-pswitch 的 !important 规则接管 footer/section，
               值就是它们当前的计算值 → 视觉零变化，且后面任何 reflow 都推不动它们。 ---- */
        const curH = offsetOf(from);
        const curSec = sec ? sec.getBoundingClientRect().height : sectionH(from);
        dEl.style.setProperty('--ps-h', curH + 'px');
        dEl.style.setProperty('--ps-sec', curSec.toFixed(2) + 'px');
        dEl.style.setProperty('--ps-dur', dur + 'ms');
        document.body.classList.add('wx-pswitch');
        if (footer) void footer.offsetHeight;              /* 提交「钉住」这一帧 */

        /* ---- ② 内容层换面板：此刻位移被钉住，看不到任何跳动 ---- */
        if (from === 'kb') kbOff();
        else if (from === 'emoji') emojiOff();
        else if (from === 'attach') attachOff();

        let ok = true;
        if (to === 'kb') kbOn();
        else if (to === 'emoji') emojiOn();
        else if (to === 'attach') ok = attachOn();
        if (!ok) {                                         /* 目标面板起不来：回滚 */
            if (from === 'kb') kbOn();
            else if (from === 'emoji') emojiOn();
            else if (from === 'attach') attachOn();
            document.body.classList.remove('wx-pswitch');
            dEl.style.removeProperty('--ps-dur');
            return false;
        }

        /* ---- ③ 切到目标值：CSS 过渡从「当前计算值」直接插值到目标位移 ---- */
        const tgtH = offsetOf(to);
        const tgtSec = sectionH(to);
        /* 进入的面板临时抬到最上层：否则「更多→表情」时新表情面板会被
           还盖在屏上的「+」面板（z 999981）压住，滑动过程看不到它升上来 */
        const inEl = panelEl(to);
        if (inEl) inEl.style.zIndex = Z_TOP;
        void (footer && footer.offsetHeight);
        dEl.style.setProperty('--ps-h', tgtH + 'px');
        dEl.style.setProperty('--ps-sec', tgtSec.toFixed(2) + 'px');
        followBottom(dur + 80);

        busy = { timer: setTimeout(settle, dur + 40), el: inEl };
        return true;
    }

    /* ============================================================
       输入栏按钮语义（对齐参考视频里的点击序列）
       ------------------------------------------------------------
       笑脸 😀 ：收起→表情 / 键盘→表情 / 表情→键盘 / 更多→表情
       加号 ➕ ：收起→更多 / 键盘→更多 / 表情→更多 / 更多→收起
       ============================================================ */
    function toggle(which) {
        const cur = current();
        if (which === 'emoji') return set(cur === 'emoji' ? 'kb' : 'emoji');
        if (which === 'attach') return set(cur === 'attach' ? 'none' : 'attach');
        return false;
    }
    /* ============================================================
       按参考视频节奏连续切换（整段交给浏览器定时，节奏可逐帧对齐）
       ------------------------------------------------------------
       seq: [{面板:'收起', 停留:1.83}, {面板:'键盘', 停留:1.75}, ...]
       语义：立刻切到「面板」，停留「停留」秒，再执行下一项。
       ★ 为什么放浏览器端：Python 每一步（evaluate / 等待 / 框架开销）会叠加
         0.5~1.3s 抖动，靠 Python 排节奏永远对不齐参考视频；浏览器 setTimeout
         的定时精度是毫秒级，且切换动画本身也是 CSS 驱动的，两者同源。
       返回总时长（秒），供 Python 端分片等待、同步派发 screencast 帧。
       ============================================================ */
    function runSequence(seq) {
        if (!Array.isArray(seq) || !seq.length) return 0;
        const items = [];
        seq.forEach((raw) => {
            const it = raw || {};
            const to = norm(it.to != null ? it.to
                : (it.panel != null ? it.panel : it['面板']));
            const hold = Number(it.hold != null ? it.hold
                : (it['停留'] != null ? it['停留'] : it['hold_ms'] / 1000));
            if (!to) return;
            items.push({ to: to, hold: isFinite(hold) && hold > 0 ? hold : 0 });
        });
        if (!items.length) return 0;
        let t = 0;
        items.forEach((it) => {
            setTimeout(() => set(it.to), Math.round(t * 1000));
            t += it.hold;
        });
        return t;
    }

    window.__wxPanels = {
        current: current,
        set: set,
        toggle: toggle,
        runSequence: runSequence,
        heights: () => ({ kb: kbH(), emoji: emojiH(), attach: attachH() }),
        version: 1,
    };

    /* 输入栏「+」键：托管点击（dialogue.vue 的 .more 原本没绑点击）。
       用 pointerdown 与 chat_extra.js 的笑脸键同一套事件委托方式，兼容 Vue 重建 DOM。 */
    document.addEventListener('pointerdown', (ev) => {
        const t = ev.target;
        const plus = t && t.closest && t.closest('.component-dialogue-bar-person .more');
        if (!plus) return;
        if (document.body.classList.contains('wx-chat')) toggle('attach');
    });
})();
