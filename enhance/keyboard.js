/* ============================================================
   注入式手机键盘覆盖层（main.py 注入，仅在录屏浏览器内生效）
   ------------------------------------------------------------
   视觉参考：iPhone 15（iOS 17）深色「中文拼音」QWERTY 键盘 + 微信候选词条。
   交互逻辑与真机一致：
   - Shift 三态：点按切换大小写键面（单次点亮 ⇧，下一字母后自动回弹），
     双击进入大写锁定（⇧ 带下划线）；
   - [123] / [abc] / [#+=] 切换数字符号页（共两页，与 iOS 一致）；
   - 键盘按键可直接点击输入（聚焦输入框时），退格/空格/发送同样生效；
   - 候选条随拼音出现/收起（--kb-cand-h 控制键盘整体高度，真机行为）；
   - 发送键：无文字灰色「换行」，有文字变绿色「发送」；
   - 按数字/符号自动切到数字布局，按字母自动切回。

   对外 API（幂等，可反复调用）：
   window.__wxKeyboard.show / hide / pressKey / setShift / showCandidates /
   tapCandidate / clearCandidates / setSendText
   ============================================================ */
(() => {
    if (window.__wxKeyboard) return;

    /* ---- 键盘布局：字母 4 行 + 数字符号 2 页 ---- */
    const LAYOUT_LETTERS = [
        { keys: ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'] },
        { keys: ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'] },
        { keys: ['shift', 'z', 'x', 'c', 'v', 'b', 'n', 'm', 'backspace'], wide: { shift: 1.5, backspace: 1.5 } },
        { keys: ['123', 'smile', 'space', 'send'], wide: { '123': 1.1, smile: 1.2, space: 6, send: 1.4 } },
    ];
    const LAYOUT_SYMBOLS = [
        { keys: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'] },
        { keys: ['-', '/', ':', ';', '(', ')', '￥', '@', '“', '”'] },
        { keys: ['#+=', '。', ',', '\\', '?', '!', '.', 'backspace'], wide: { '#+=': 1.3, backspace: 1.3 } },
        { keys: ['abc', 'smile', 'space', 'send'], wide: { 'abc': 1.26, smile: 1.26, space: 5.7, send: 2.62 } },
    ];
    const LAYOUT_SYMBOLS2 = [
        { keys: ['[', ']', '{', '}', '#', '%', '^', '*', '+', '='] },
        { keys: ['_', '\\', '|', '~', '<', '>', '€', '£', '¥', '•'] },
        { keys: ['123', ',', '.', '?', '!', 'backspace'], wide: { '123': 1.7, backspace: 1.5 } },
        { keys: ['abc', 'space', 'send'], wide: { 'abc': 1.25, space: 7, send: 1.4 } },
    ];
    const KEY_LABEL = {
        shift: '⇧', backspace: '⌫', space: '\u00a0', '123': '123', abc: '拼音', '#+=': '#+=',
        ':': '：', ';': '；', '(': '（', ')': '）',
        ',': '，', '.': '。', '!': '！', '?': '？',
        send: '发送',
    };
    const FN_KEYS = new Set(['shift', 'backspace', '123', 'abc', '#+=', 'smile', 'globe', 'mic']);
    /* 图标键：以背景图(透明线稿)呈现，不显示文字；data-key 仍用于点击处理 */
    const ICON_KEYS = {
        smile: '/images/chatbar/kb_smile.png',
        globe: '/images/chatbar/globe_line.png',
        mic: '/images/chatbar/mic_line.png',
    };
    const LETTER_KEYS = new Set('qwertyuiopasdfghjklzxcvbnm'.split(''));
    /* 数字/符号第一页（真机中文键盘「123」页）：数字 + - / : ; ( ) ￥ @ “ ” + 。，\\?!. */
    const SYMBOL_KEYS1 = new Set(('1234567890-/:;()￥@“”。,\\?!.').split(''));
    const SYMBOL_KEYS2 = new Set(('[]{}#%^*+=_\\|~<>€£¥•123').split(''));

    /* ---- 构建键盘 DOM ---- */
    const root = document.createElement('div');
    root.id = 'wxkb';
    root.innerHTML = '<div class="kb-cand"><div class="kb-cand-list" id="kbCandList"></div><div class="kb-cand-more"><span class="kb-cand-more-arrow"></span></div></div><div class="kb-rows" id="kbRows"></div><div class="kb-dict" id="kbDict"></div>';
    document.body.appendChild(root);

    const candBar = root.querySelector('.kb-cand');
    const candList = root.querySelector('#kbCandList');
    const rowsEl = root.querySelector('#kbRows');
    const dictEl = root.querySelector('#kbDict');
    let _lastCandSig = '';          /* 候选渲染去重：内容与上次完全一致则跳过重建（消引擎/本地重复渲染） */
    let _lastShownN = 0;

    const applyIcon = (el, k) => {
        const img = ICON_KEYS[k];
        if (!img) return false;
        el.classList.add('kb-icon');
        el.style.backgroundImage = "url('" + img + "')";
        el.style.fontSize = '0';
        el.innerHTML = '';
        return true;
    };

    const buildGrid = (rows) => {
        const grid = document.createElement('div');
        grid.className = 'kb-grid';
        rows.forEach(row => {
            const rowEl = document.createElement('div');
            rowEl.className = 'kb-row';
            row.keys.forEach(k => {
                const el = document.createElement('i');
                el.className = 'kb-key';
                if (k === 'space') el.classList.add('kb-space');
                else if (k === 'send') el.classList.add('kb-send');
                else if (FN_KEYS.has(k)) el.classList.add('kb-fn');
                if (row.wide && row.wide[k]) el.style.flex = String(row.wide[k]);
                el.dataset.key = k;
                if (!applyIcon(el, k)) {
                    el.textContent = KEY_LABEL[k] || k;
                }
                rowEl.appendChild(el);
            });
            grid.appendChild(rowEl);
        });
        return grid;
    };

    /* 底部听写行：地球(语言切换)靠左、麦克风(听写)靠右，横向分开 */
    const buildDict = () => {
        dictEl.innerHTML = '';
        ['globe', 'mic'].forEach(k => {
            const el = document.createElement('i');
            el.className = 'kb-key kb-dict-key';
            el.dataset.key = k;
            applyIcon(el, k);
            dictEl.appendChild(el);
        });
    };

    const gridLetters = buildGrid(LAYOUT_LETTERS);
    const gridSymbols = buildGrid(LAYOUT_SYMBOLS);
    const gridSymbols2 = buildGrid(LAYOUT_SYMBOLS2);
    rowsEl.appendChild(gridLetters);
    rowsEl.appendChild(gridSymbols);
    rowsEl.appendChild(gridSymbols2);
    gridSymbols.style.display = 'none';
    gridSymbols2.style.display = 'none';
    buildDict();

    let currentLayout = 'letters';
    const keys = {};                       /* 当前布局的按键映射 data-key -> 元素 */

    const collectKeys = () => {
        for (const k in keys) delete keys[k];
        const grid = currentLayout === 'letters' ? gridLetters : (currentLayout === 'symbols2' ? gridSymbols2 : gridSymbols);
        grid.querySelectorAll('.kb-key').forEach(el => { keys[el.dataset.key] = el; });
        /* 底部听写行（地球/麦克风）不随布局切换，始终在 keys 映射中 */
        dictEl.querySelectorAll('.kb-key').forEach(el => { keys[el.dataset.key] = el; });
    };
    collectKeys();

    /* 贴图键盘(body.wx-chat / body.wx-on-moments)判定：键盘是一整张贴图
       （字母页 kb_body.png / 数字页 kb_body_num.png，由 .kb-num 类切换背景），
       热区为透明层、按贴图逐键坐标对齐。第二符号页( symbols2 )尚未做贴图，
       贴图模式下不切过去（避免露字母贴图穿帮）；数字页已完整适配可正常切换。 */
    const isWxChat = () => !!(document.body && document.body.classList.contains('wx-chat'));
    const isTexKb = () => !!(document.body &&
        (document.body.classList.contains('wx-chat') ||
         document.body.classList.contains('wx-on-moments')));

    /* ---- 布局切换（真机「123」/「拼音」/「#+=」键行为） ---- */
    function switchLayout(to) {
        if (to === currentLayout) return;
        /* 贴图模式下第二符号页未适配：拦截，其余页正常切换。 */
        if (isTexKb() && to === 'symbols2') return;
        if (_pendingFlipT) { clearTimeout(_pendingFlipT); _pendingFlipT = null; }
        gridSymbols.style.display = 'none';
        gridSymbols2.style.display = 'none';
        gridLetters.style.display = 'none';
        currentLayout = to;
        (to === 'letters' ? gridLetters : (to === 'symbols2' ? gridSymbols2 : gridSymbols)).style.display = 'flex';
        /* 贴图键盘：数字页换背景贴图（kb_body.png <-> kb_body_num.png） */
        root.classList.toggle('kb-num', isTexKb() && to === 'symbols');
        collectKeys();
        setShiftState(0);          /* 切到数字/符号时大小写复位（真机行为） */
        applyImeKey();
        applySendState();
        _syncComposeUI();          /* 数字页空格键文字也要跟随组合态（选定/空白） */
    }

    /* ---- 布局切换动画节拍：显式按「123」/「拼音」键时，先闪布局键、
       稍延迟再翻页（真机：按下高亮、松手翻页）。延迟随 holdMs 缩放
       （打字倍速下被同比例压缩，30x 时近乎硬切，与真机快速连打一致）。
       自动翻页（打数字/字母时按字符所属布局切换）走 switchLayout 硬切。 ---- */
    let _pendingFlipT = null;
    function flipByKey(flipKey, to, holdMs) {
        if (window.__wxKeyboard && window.__wxKeyboard.visible) {
            const el = keys[flipKey];
            if (el) pressFx(el, holdMs || 150);
        }
        if (_pendingFlipT) clearTimeout(_pendingFlipT);
        _pendingFlipT = setTimeout(() => {
            _pendingFlipT = null;
            if (currentLayout !== to) switchLayout(to);
        }, Math.max(50, Math.min(holdMs || 150, 200)));
    }

    /* ---- Shift 三态：0=关 1=单次 2=大写锁定 ---- */
    let shiftState = 0;
    function setShiftState(s) {
        shiftState = s;
        const shiftKey = keys['shift'];
        if (shiftKey) {
            shiftKey.classList.toggle('kb-shift-on', s !== 0);
            shiftKey.classList.toggle('kb-shift-caps', s === 2);
        }
        applyLetterCase();
    }
    function applyLetterCase() {
        const upper = shiftState !== 0;
        document.querySelectorAll('#wxkb .kb-key[data-key]').forEach(el => {
            const k = el.dataset.key;
            if (LETTER_KEYS.has(k)) el.textContent = upper ? k.toUpperCase() : k;
        });
    }
    function toggleShift() {
        setShiftState(shiftState === 0 ? 1 : (shiftState === 1 ? 2 : 0));
    }

    /* ---- 拼音引擎：逐键联想（离线词库 window.__WX_PINYIN） ---- */
    const _WX = window.__WX_PINYIN || {};
    const S = _WX.s || {};   // 单字：音节 -> [候选字]
    const P = _WX.p || {};   // 词组：拼音串 -> [候选词]
    const SF = _WX.sf || {}; // 音节 -> 最高频字次数(打分)
    const PF = _WX.pf || {}; // 拼音串 -> 最高频词次数(打分)
    const BG = _WX.bg || {}; // 二元模型：前词 -> {后词: 权重}

    /* 保底候选：当无拼音、无联想时也显示的常用词/字，保证候选条永不为空（真实输入法不收起打字框） */
    const DEFAULT_CANDS = ['你好', '好的', '在', '的', '了', '是', '我', '你', '他',
        '我们', '什么', '可以', '这个', '因为', '所以', '现在', '已经', '知道', '觉得', '一起'];
    /* 句子助词/常见补足字，用于无二元联想时的动态兜底（不是固定这一批，随上下文微调顺序） */
    const PARTICLES = ['吗', '呢', '吧', '啊', '了', '的', '呀', '哦', '嗯', '好'];
    /* 高频常用字词兜底（候选永不为空时用） */
    const COMMON_FALLBACK = ['我', '你', '是', '好', '不', '这', '在', '就', '都', '也',
        '吧', '啊', '呢', '了', '的', '呀', '吗', '嗯', '哦', '哈'];

    /* 全部词/字的集合：用于从已输入文本里识别"末尾的词"，做真实词边界联想。 */
    const WORD_SET = new Set();
    for (const k in P) { const a = P[k]; for (let i = 0; i < a.length; i++) WORD_SET.add(a[i]); }
    for (const k in S) { const a = S[k]; for (let i = 0; i < a.length; i++) WORD_SET.add(a[i]); }

    /* 单字候选上限：只取该音节最高频的若干常用字，压掉 阆/塭/撾/渥 这类生僻或错音字。 */
    const MAX_COMMON_CHARS = 9;
    const commonS = (py) => { const a = S[py]; return a ? a.slice(0, MAX_COMMON_CHARS) : a; };

    /* 预排序拼音串键 + 二分前缀索引，避免每键遍历上万键做 startsWith（导致候选条跟不上）。 */
    const P_KEYS = Object.keys(P).sort();
    const S_KEYS = Object.keys(S).sort();
    function firstIndex(sorted, prefix) {
        let lo = 0, hi = sorted.length;
        while (lo < hi) { const mid = (lo + hi) >> 1; if (sorted[mid] < prefix) lo = mid + 1; else hi = mid; }
        return lo;
    }
    /* 取所有「拼音以 prefix 开头」的词，按词频(PF)降序、限量（确保高频词如「明天」不被低频邻居挤出）。
       不再把整段前缀键先收集再全量排序（单字母前缀动辄上万键，每键一次大排序 → 打字掉帧）：
       只维护 ≤limit 的 Top 候选（升序数组、末尾即最差），一趟扫描 O(范围×limit) 完成。 */
    function topKeysByPrefix(prefix, limit, minKeyLen) {
        const i0 = firstIndex(P_KEYS, prefix);
        const tk = [];     // 候选 key，按 PF 升序（末尾最差，便于淘汰）
        const tf = [];
        for (let i = i0; i < P_KEYS.length; i++) {
            const k = P_KEYS[i];
            if (!k.startsWith(prefix)) break;
            if (k.length < minKeyLen) continue;
            const f = PF[k] || 0;
            const L = tk.length;
            if (L < limit) {
                let j = L;
                tk.push(k); tf.push(f);
                while (j > 0 && tf[j - 1] > f) {
                    const tkj = tk[j], tfj = tf[j];
                    tk[j] = tk[j - 1]; tf[j] = tf[j - 1];
                    tk[j - 1] = tkj; tf[j - 1] = tfj; j--;
                }
            } else if (f > tf[limit - 1]) {
                let j = limit - 1;
                tk[j] = k; tf[j] = f;   /* 替换末尾最差后再插排 */
                while (j > 0 && tf[j - 1] > f) {
                    const tkj = tk[j], tfj = tf[j];
                    tk[j] = tk[j - 1]; tf[j] = tf[j - 1];
                    tk[j - 1] = tkj; tf[j - 1] = tfj; j--;
                }
            }
        }
        return tk;   /* 升序（PF 由低到高） */
    }
    function wordsByPrefix(prefix, limit, minKeyLen) {
        limit = limit || 12; minKeyLen = minKeyLen || 0;
        const ks = topKeysByPrefix(prefix, limit, minKeyLen);
        const res = [];
        for (let i = ks.length - 1; i >= 0; i--) {   /* 降序输出：高频 key 的词在前 */
            const k = ks[i];
            for (const w of P[k]) { res.push(w); if (res.length >= limit) return res; }
        }
        return res;
    }
    /* 是否存在以 partial 开头的音节 */
    function syHasPrefix(partial) {
        const i0 = firstIndex(S_KEYS, partial);
        return i0 < S_KEYS.length && S_KEYS[i0].startsWith(partial);
    }

    /* 贪婪地把一串拼音切成音节(优先最长音节)，仅用于词内拆字/兜底。
       如 'womenmingtian' -> ['wo','men','ming','tian'] */
    function splitSyllables(buf) {
        const syls = [];
        let i = 0;
        const n = buf.length;
        while (i < n) {
            let best = null;
            for (let L = Math.min(6, n - i); L >= 1; L--) {
                const c = buf.slice(i, i + L);
                if (S[c]) { best = c; break; }
            }
            if (!best) best = buf.slice(i, i + 1);
            syls.push(best);
            i += best.length;
        }
        return syls;
    }

    /* 频率加权 Viterbi 解码：把整段拼音切成「词 + 音节 + 尾部未完成音节」。
       得分 = log(词频/字频) - LAMBDA*token数；单音节一律按单字(见优先于吉安)，
       长串按词频分句(我们+明天 胜过 我们+命题+案件)。 */
    const LAMBDA = 13;
    /* 把某个拼音串的候选词，按「前一词 -> 本词」的 bigram 权重重排（高频/常见搭配靠前） */
    function rankWords(sub, prevWord) {
        const arr = P[sub];
        if (!arr) return [];
        if (!prevWord || !BG[prevWord]) return arr;
        const scored = arr.map((w, i) => ({ w, s: (BG[prevWord][w] || 0) - i * 0.01 }));
        scored.sort((a, b) => b.s - a.s);
        return scored.map(x => x.w);
    }
    function viterbiDecode(buf) {
        const n = buf.length;
        if (!n) return [];
        const BOS = '\u0000';                          // 句首哨兵
        // dp[i] = Map(当前词 -> {score, isWord, prev:{i, curLast, sub, isWord, isPartial, word}})
        const dp = Array.from({ length: n + 1 }, () => new Map());
        dp[0].set(BOS, { score: 0, isWord: false, prev: null });
        for (let i = 0; i < n; i++) {
            for (const [curLast, st] of dp[i]) {
                const maxL = Math.min(10, n - i);
                for (let L = 1; L <= maxL; L++) {
                    const sub = buf.slice(i, i + L);
                    let sc = -Infinity, isWord = false, isPartial = false;
                    if (S[sub]) { sc = Math.log(SF[sub] || 1) - LAMBDA; }
                    else if (P[sub] && PF[sub]) { sc = Math.log(PF[sub]) - LAMBDA; isWord = true; }
                    else if (i + L === n && syHasPrefix(sub)) { sc = -LAMBDA + sub.length * 2.5; isPartial = true; }
                    else { continue; }
                    const cands = isWord ? P[sub].slice(0, 3) : (isPartial ? [''] : S[sub].slice(0, 1));
                    for (const cand of cands) {
                        let extra = 0;
                        // 二元模型：仅当"前一词"与"当前词"都是整词时加分(我们->明天)
                        if (isWord && st.isWord && curLast !== BOS && BG[curLast]) {
                            const w = BG[curLast][cand];
                            if (w) extra = Math.log(1 + w);
                        }
                        const nv = st.score + sc + extra;
                        const j = i + L;
                        const cur = dp[j].get(cand) || { score: -Infinity };
                        if (nv > cur.score) {
                            dp[j].set(cand, { score: nv, isWord, prev: { i, curLast, sub, isWord, isPartial, word: cand } });
                        }
                    }
                }
            }
        }
        let bestLast = null, bestScore = -Infinity;
        for (const [last, st] of dp[n]) if (st.score > bestScore) { bestScore = st.score; bestLast = last; }
        if (bestLast === null) {                          // 兜底：按贪心音节
            const toks = []; let pos = 0;
            for (const sy of splitSyllables(buf)) { toks.push({ start: pos, sub: sy, isWord: false, isPartial: false, word: S[sy] ? S[sy][0] : sy }); pos += sy.length; }
            return toks;
        }
        const toks = []; let pos = n, last = bestLast;
        while (pos > 0) {
            const st = dp[pos].get(last);
            if (!st || !st.prev) break;
            toks.unshift(st.prev);
            pos = st.prev.i; last = st.prev.curLast;
        }
        return toks;
    }

    /* 候选-上屏首位对齐：当前拼音若正是 main.py 预告的目标词拼音，就把目标词顶到候选第一位。
       目标词不在候选里也前置（保证候选首位 == 上屏文字）；数量封顶 10。 */
    function _alignHint(cands, prefix) {
        if (!_topHint || !_topHint.word || prefix !== _topHint.py) return cands;
        const w = _topHint.word;
        if (cands[0] === w) return cands;
        const out = [w];
        for (let i = 0; i < cands.length && out.length < 10; i++) {
            if (cands[i] !== w) out.push(cands[i]);
        }
        return out;
    }

    /* 查询拼音前缀候选（逐键随敲键收窄，长文本不卡）。
       核心逻辑见 queryPinyinBase；queryPinyin 只做结果缓存 + 候选-上屏首位对齐。 */
    const _Q_CACHE = new Map();          // 按 prefix 缓存 Base 结果（同前缀不重复扫词库）
    const _Q_CACHE_MAX = 400;            // 简单 FIFO 淘汰
    function queryPinyinBase(prefix) {
        prefix = String(prefix || '').toLowerCase();
        if (!prefix) return [];
        const toks = viterbiDecode(prefix);
        const out = [], seen = new Set();
        /* 整句候选：优先「真实词」，避免拼出乱串（如 kaix -> 岂西）。
           分级规则（贴近真机）：
             - 完整音节(wo/ka/xin)   -> 首选单字(我/开/新)
             - 完整词(we/women/kaixin)-> 该词(我们/开心)
             - 敲到一半(kaix/womenx) -> 前缀补全的高频词(开心)
           仅当以上都取不到时才回退到「解码拼接」的字符。 */
        const joinedPhrase = toks.map(t => {
            if (t.isPartial) return '';
            if (!t.isWord && t.sub.length === 1) return '';
            return t.word || (t.isWord ? (P[t.sub] && P[t.sub][0]) : (S[t.sub] && S[t.sub][0])) || '';
        }).join('');
        let topPhrase = '';
        if (S[prefix] && S[prefix].length) topPhrase = S[prefix][0];                       // 完整音节 -> 单字
        else if (P[prefix] && P[prefix].length) topPhrase = P[prefix][0];                   // 完整词 -> 该词
        else if (prefix.length >= 2) {                                                       // 敲到一半 -> 前缀高频词
            const wp = wordsByPrefix(prefix, 1, prefix.length);
            if (wp.length) topPhrase = wp[0];
        }
        if (!topPhrase) topPhrase = joinedPhrase;
        const add = (arr, cap) => {
            if (!arr) return false;
            let n = 0;
            for (let i = 0; i < arr.length; i++) {
                if (out.length >= 10) return true;      // 先判满，避免超填
                const c = arr[i];
                if (seen.has(c)) continue;
                seen.add(c); out.push(c);
                if (++n >= cap) break;
            }
            return out.length >= 10;
        };
        if (topPhrase) add([topPhrase], 1);   // 整句候选置顶(真实词/单字)
        /* 1) 主序：按解码顺序，每个词/音节各出 1 个主要候选 —— 反映整串拼音的「对应字体」 */
        let prevW = null;
        for (const t of toks) {
            if (t.isWord) { add(rankWords(t.sub, prevW), 1); prevW = t.word; }
            else if (!t.isPartial) { const s = commonS(t.sub); if (s) add(s, 1); prevW = t.word; }
            else { prevW = null; }
        }
        /* 2) 次级：每个词补少量同音 + 词内音节单字（限量，避免单一词刷屏） */
        for (const t of toks) {
            if (t.isWord) {
                add(P[t.sub], 2);
                const sy = splitSyllables(t.sub);
                for (const x of sy) { const s = commonS(x); if (s) add(s, 1); }
            } else if (!t.isPartial) {
                const s = commonS(t.sub); if (s) add(s, 2);
            }
        }
        /* 3) 末段补全：明天(mi+ng+tian)；末段未完成音节补全字(天/田) */
        const last = toks[toks.length - 1];
        if (last && last.sub) {
            const isTail = last.isPartial || (last.sub.length <= 6 && syHasPrefix(last.sub) && !S[last.sub]);
            const prevToks = toks.slice(0, -1);
            for (let k = 1; k <= 2 && k <= prevToks.length; k++) {
                const prePy = prevToks.slice(-k).map(t => t.sub).join('');
                for (const ks in S) { if (ks.startsWith(last.sub)) { const cand = prePy + ks; if (P[cand]) add(P[cand], 1); } }
            }
            if (isTail) {
                for (const ks in S) { if (ks.startsWith(last.sub)) { const s = commonS(ks); if (s) add(s, 2); } }
            } else if (last.isWord && last.sub.length >= 2) {
                add(wordsByPrefix(last.sub, 4, last.sub.length + 1), 4);   // 只补更长拼音(明天)，排除同音洪泛
            }
        }
        /* 4) 兜底：前缀音节单字(保证不空) */
        for (const k in S) { if (k.startsWith(prefix)) { if (add(commonS(k), 20)) return out; } }
        return out.slice(0, 10);
    }
    /* 缓存版查询：同 prefix 直接命中 Base；_topHint 对齐每次现算（开销极小）。 */
    function queryPinyin(prefix) {
        prefix = String(prefix || '').toLowerCase();
        if (!prefix) return [];
        let base = _Q_CACHE.get(prefix);
        if (base === undefined) {
            base = queryPinyinBase(prefix);
            if (_Q_CACHE.size >= _Q_CACHE_MAX) _Q_CACHE.delete(_Q_CACHE.keys().next().value);
            _Q_CACHE.set(prefix, base);
        }
        return _alignHint(base, prefix);
    }

    /* 中文/英文输入模式（不影响英文字母直输；拼音模式下候选行才出现） */
    let imeMode = 'pinyin';
    let pyBuffer = '';       /* 未上屏的拼音字母串（组合区） */
    let _suppressComposeOnce = false;  /* replaceBuffer 上屏后下一次 input 不重新组字
        （「确认」原样上屏拼音时，value 结尾仍是 [a-z]，不抑制会立刻重新进入组合态死循环） */
    let pyStart = -1;        /* 组合区在输入框内的起始下标 */
    /* 主驱动（main.py）预告的"本段目标词"：敲该词拼音时把候选首位对准它将上屏的字词，
       保证候选条第一项 == 上屏文字（候选-上屏首位对齐微调）。commit 后自动清除。 */
    let _topHint = null;     /* { py: <完整拼音>, word: <目标字/词> } */

    function applyImeKey() {
        root.classList.toggle('kb-ime-pinyin', imeMode === 'pinyin');
    }

    /* ---- 组合态（拼音候选未选定）同步：#wxkb 挂 .kb-composing ----
       参考视频「发送按键的变化规律.mp4」逐帧实测：拼音有候选未选定时，
       空格键文字变「选定」、右下角发送键从蓝色「发送」整体变为深灰「确认」
       （键面颜色 = 功能键灰）。选定/清空后瞬间切回「空格」+「发送」。
       切换为 1 帧硬切、无过渡动画（30fps 相邻帧直接切换）。
       所有 pyBuffer 被赋值/清空、imeMode 切换的路径最终都会走到这里。 */
    function _syncComposeUI() {
        const composing = !!(pyBuffer && imeMode === 'pinyin');
        root.classList.toggle('kb-composing', composing);
        const sk = keys['space'];
        if (sk) sk.textContent = composing ? '选定' : '\u00a0';
        applySendState();   /* 组合态时发送键文字由 applySendState 统一判成「确认」 */
    }
    function setImeMode(mode) {
        imeMode = (mode === 'english' || mode === 'abc') ? 'english' : 'pinyin';
        if (!pyBuffer) { pyStart = -1; }
        applyImeKey();
        _syncComposeUI();
    }
    function toggleImeMode() { setImeMode(imeMode === 'pinyin' ? 'english' : 'pinyin'); }

    /* 在拼音模式下,根据输入框「结尾的字母串」实时刷新候选行。
       这样无论用真实键盘事件(page.keyboard.type)还是点击按键,都会自动预选。 */
    /* 必有候选的统一入口：返回一个永远非空的候选数组。
       优先「组合拼音预选」→「已提交文本的二元联想」→「保底常用词」。 */
    /* 候选条装饰：文字候选为主，仅在少数位置点缀表情/颜文字，避免一堵文字墙。
       - 首位（上屏字/词）恒保留在 0 号位（候选-上屏首位对齐不受影响）。
       - 文字候选命中 __WX_EMOJI（词 -> 苹果 emoji）时，把该 emoji「紧跟在其词后」插入
         （真输入法"打词出表情"行为，保留）。
       - 未命中表情的文字候选：只在「每隔 4 位」的稀疏位置补 1 个颜文字或表情，
         整排至多补 2 个装饰——不密集，但靠**大而多变的装饰池**保证每次出现的花样不重复：
         颜文字/表情池各 16+ 种，覆盖笑脸、爱心、手势、动物、花草、庆祝等不同"种类"，
         两类交替穿插、整行不重样，且不同候选行接着上次游标继续轮，避免来回就那几种。
       - 装饰轮换游标放模块级：不同候选行接着上一次往下轮，避免每行都从同一个符号开始。
       - 表情/符号对象 {type:'emoji'|'symbol', ...} 不参与自动 commitByPhrase 索引。 */
    const KAOMOJI_POOL = ["(●'◡'●)", "(｡•̀ᴗ-)✧", "(≧▽≦)", "(￣▽￣)", "(´▽`)♡",
        "(๑•̀ㅂ•́)و✧", "( ͡° ͜ʖ ͡°)", "(⊙o⊙)", "(¬‿¬)", "٩(◕‿◕)۶", "(´･ᴗ･`)", "(｡•́︿•̀｡)",
        "(T_T)", "ʕ•ᴥ•ʔ", "(^・ω・^)", "ヽ(>∀<)ﾉ", "✧(≖ ◡ ≖✿)", "(๑´ㅂ`๑)", "(￢‿￢ )", "(>_<)"];
    const EMOJI_FILL = [
        { code: "1f60a", emoji: "😊" }, { code: "1f602", emoji: "😂" },
        { code: "1f44d", emoji: "👍" }, { code: "2764-fe0f", emoji: "❤️" },
        { code: "1f60d", emoji: "😍" }, { code: "1f923", emoji: "🤣" },
        { code: "1f970", emoji: "🥰" }, { code: "1f929", emoji: "🤩" },
        { code: "1f618", emoji: "😘" }, { code: "1f60e", emoji: "😎" },
        { code: "1f389", emoji: "🎉" }, { code: "2728", emoji: "✨" },
        { code: "1f338", emoji: "🌸" }, { code: "1f493", emoji: "💓" },
        { code: "1f44f", emoji: "👏" }, { code: "1f431", emoji: "🐱" },
    ];
    /* 微信小表情图集（build_wxemoji.py 生成 enhance/wxemoji_map.js）：
       list = 候选条装饰池（全部图轮换出现），words = 词->图（语义命中，优先于苹果 emoji）。
       这些图以真实 <img> 挂进候选条，比纯文字/苹果 emoji 更贴近微信原版小表情，
       让候选条图片更丰富、不重样。 */
    const WX = window.__WX_WXEMOJI || {};
    const WX_LIST = WX.list || [];
    const WX_WORD = WX.words || {};
    /* 装饰取图：轮换「颜文字 / 微信小表情图 / 苹果表情图」三种。
       用**候选文本内容哈希做种子**生成本行装饰游标（不再用模块级全局游标）。
       修复：旧实现 pickDeco 推进模块级全局游标，导致「同一批候选文字」无论同步渲染还是
       引擎异步回填(refreshFromEngine)都会走到不同的装饰位 —— 表现为候选条文字没变、
       但第 3 个表情独立跳变(😍→🙋)。改为按候选全文确定性播种：同一批文字永远得到同一组装饰，
       异步回填不再跳变；不同候选行因文本不同自然错开，依旧不重样。 */
    function _hashSeed(str) {
        let h = 2166136261;
        for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
        return h >>> 0;
    }
    /* 候选条图片预热：键盘/候选首次渲染前，把微信小表情图与常用苹果表情图预解码进浏览器缓存。
       这 71 张微信小表情图不在页面 DOM 里，只有候选条渲染时才会被引用——若不预热，
       候选条第一次出现图片会闪一下/掉帧。此处预先 new Image() 触发下载+解码，首现即就绪。 */
    (function preheatCandImages() {
        const seen = new Set();
        const pre = (src) => { if (src && !seen.has(src)) { seen.add(src); const im = new Image(); im.src = src; } };
        (WX_LIST || []).forEach(w => pre(w.src));
        (EMOJI_FILL || []).forEach(f => pre('/images/emoji/' + f.code + '.png'));
    })();
    function attachEmoji(cands) {
        const EMOJI = window.__WX_EMOJI || {};
        const out = [];
        const pushObj = (o) => { if (out.length < 12) out.push(o); };
        let deco = 0;                 // 本行已插入的装饰数（命中表情 + 补位），上限 3
        /* 装饰起点由候选文本整体哈希决定：同一批候选 -> 同一组装饰位（异步回填不再跳变），
           不同候选行因文本不同而错开（依旧不重样）。 */
        const key = cands.map(c => typeof c === 'object' ? (c.src || c.emoji || c.code || '') : String(c)).join('|');
        const seed = _hashSeed(key);
        let symIdx = seed % KAOMOJI_POOL.length;
        let fillIdx = (seed >>> 2) % EMOJI_FILL.length;
        let wxIdx = (seed >>> 3) % (WX_LIST.length || 1);
        let decoIdx = (seed >>> 1) % 3;
        const nextDeco = () => {
            const kind = decoIdx % 3;
            decoIdx++;
            if (kind === 0) return { type: 'symbol', text: KAOMOJI_POOL[symIdx++ % KAOMOJI_POOL.length] };
            if (kind === 1 && WX_LIST.length) {
                const w = WX_LIST[wxIdx++ % WX_LIST.length];
                return { type: 'wximg', src: w.src, code: String(w.id || ''), emoji: '' };
            }
            const f = EMOJI_FILL[fillIdx++ % EMOJI_FILL.length];
            return { type: 'emoji', code: f.code, emoji: f.emoji };
        };
        for (let i = 0; i < cands.length; i++) {
            const c = cands[i];
            if (out.length >= 12) break;              // 候选总量上限
            if (typeof c === 'object') { out.push(c); continue; }   // 已是表情/符号对象则保留
            out.push(c);
            const wm = WX_WORD[c];
            const m = EMOJI[c];
            if (wm) {
                /* 命中微信小表情词表：紧跟其词上图（更贴近微信原版小表情），优先于苹果 emoji。 */
                pushObj({ type: 'wximg', src: wm });
                deco++;
            } else if (m && deco < 3) {
                /* 命中真实表情：紧跟其词（真输入法打词出表情）。此为"有意义"的装饰，计入上限。
                   ⚠️ 不做「逢 N 位随机补位装饰」：装饰宽度(36~89px)与文字项差异大，且在缺
                   emoji 字体的录制环境里会渲染成不可见空槽，把文字候选挤得忽远忽近（间距乱）。
                   纯文字行交给 space-between 均匀铺满，才是真输入法的排布。 */
                pushObj({ type: 'emoji', code: m.code, emoji: m.emoji });
                deco++;
            }
        }
        /* 若整排仍是纯文字（无任何表情/符号），才补 1 个颜文字占位兜底（保证有变化但不密集） */
        let hasDeco = out.some((x) => typeof x === 'object');
        if (!hasDeco && out.length < 12) {
            pushObj({ type: 'symbol', text: KAOMOJI_POOL[symIdx++ % KAOMOJI_POOL.length] });
        }
        return out;
    }
    /* 从文本末尾取出"最后一个词/字"：贪心匹配最长的词典词，用于词边界联想。
       例：'我很开心' -> '开心'；'我' -> '我'；'我很' -> '很'（'我很'非词典词则退到单字）。 */
    function lastWordOf(text) {
        text = text || '';
        const n = text.length;
        for (let L = Math.min(6, n); L >= 1; L--) {
            const tail = text.slice(n - L);
            if (WORD_SET.has(tail)) return tail;
        }
        return '';
    }
    /* 动态兜底：无词/字联想时，给「句子助词 + 高频字词」候选；并尽量让首项贴合文末语义。
       真实输入法从不给固定同一批，这里按【末尾词的首字/文末】微调顺序，避免每次一模一样。 */
    function dynamicFallback(context) {
        context = context || '';
        const last = context.slice(-1);
        const out = [];
        // 把常见补足字排在前面
        for (const p of PARTICLES) if (!out.includes(p)) out.push(p);
        // 高频常用字词跟着补
        for (const w of COMMON_FALLBACK) if (!out.includes(w)) out.push(w);
        // 末尾有一个字时，把它的联想/同音常用字提前（若有）—— 用已输入文本的尾字自然衔接
        if (last && WORD_SET.has(last) && last.length === 1) {
            // 让尾字的基础候选（若这是单字音）靠前
            const idx = out.indexOf(last);
            if (idx > 0) { out.splice(idx, 1); out.unshift(last); }
        }
        return out.slice(0, 10);
    }
    function ensureCandidates(context) {
        const m = /([a-z]+)$/.exec(context || '');
        if (m) {
            const cands = queryPinyin(m[1]);
            if (cands.length) return attachEmoji(cands);      // 组合拼音预选(+表情)
        }
        /* 联想词太少（删除/无拼音时二元表往往只有两三个后接）→ 用通用兜底词补足，
           避免候选条只剩两三个字显得空旷。补到至少 8 个文本候选，再交 attachEmoji 加装饰。 */
        const finish = (arr) => {
            arr = Array.isArray(arr) ? arr.slice(0, 8) : [];
            if (arr.length < 8) {
                const fb = dynamicFallback(context);
                for (let i = 0; i < fb.length && arr.length < 10; i++) {
                    if (!arr.includes(fb[i])) arr.push(fb[i]);
                }
            }
            return attachEmoji(arr);
        };
        if (context) {
            /* 词边界联想：取文本末尾的词，查其二元后接（我们->明天/一起；我->们/在/要；开心->吗/了/的）。 */
            const word = lastWordOf(context);
            if (word) {
                const nxt = BG[word];
                if (nxt && Object.keys(nxt).length) return finish(Object.keys(nxt));
            }
            /* 次级：末尾单字的二元后接（很->好/多/久；你->好/们/在）。 */
            const lastChar = /[\u4e00-\u9fff]$/.test(context) ? context.slice(-1) : '';
            if (lastChar && lastChar !== word) {
                const nxt = BG[lastChar];
                if (nxt && Object.keys(nxt).length) return finish(Object.keys(nxt));
            }
            /* 兜底：按旧法对末尾 1~2 字建索引。 */
            const nxt = BG[context.slice(-2)] || BG[context.slice(-1)];
            if (nxt && Object.keys(nxt).length) return finish(Object.keys(nxt));
        }
        return attachEmoji(dynamicFallback(context));          // 动态兜底(非固定)
    }
    function _clearCand() {
        candList.innerHTML = '';
        setCandHeight(0);
    }
    /* 候选条首位的纯文字候选（空格「选定」用）：emoji/颜文字候选不算，取不到返回 '' */
    function _firstCandidateText() {
        const first = candList && candList.querySelector('.kb-cand-item:not(.kb-cand-emoji):not(.kb-cand-symbol)');
        const ch = first && first.dataset ? first.dataset.chars : '';
        return (typeof ch === 'string' && ch) ? ch : '';
    }
    function _showCand(pinyin, chars) {
        if (window.__wxKeyboard && window.__wxKeyboard.showCandidates) {
            window.__wxKeyboard.showCandidates(pinyin, chars);
        } else {
            setCandHeight(0);
        }
    }
    /* 真 Rime 引擎候选：引擎就绪时用真实候选替换候选条；拼音已变则丢弃过期结果（提交仍走 commitByPhrase 保证文字一致）。
       ⚠️ 引擎 process() 是「按键会话式」的：每次调用=向当前会话追加按键，不是无状态查询。
       必须增量喂键（_engSent 追踪会话内容）：变长只发增量；变短发 {BackSpace}；交叉变更/清空发 {Escape}
       （my-rime 支持原始按键序列语法）。否则会话里 n/ni/nih 反复叠加，候选全乱
       （首候选滚成「那你你好你好很好密码」这类拼接串）。 */
    let _engSent = '';   /* 引擎会话当前持有的拼音串 */
    function refreshFromEngine(prefix) {
        const E = window.__rimeEngine;
        if (!E || !E.ready) { _engSent = ''; return; }
        if (prefix === _engSent) return;   // 已同步，无需喂键
        const snap = prefix;
        let p;
        if (prefix.startsWith(_engSent) && _engSent.length > 0) {
            p = E.process(prefix.slice(_engSent.length));                       // 变长：只发增量
        } else if (_engSent.startsWith(prefix) && prefix.length > 0) {
            p = E.process('{BackSpace}'.repeat(_engSent.length - prefix.length)); // 变短：逐字退格
        } else if (_engSent.length > 0) {
            p = E.process('{Escape}');                                          // 交叉变更/清空：清组合区
        } else {
            p = E.process(prefix);                                              // 空会话首次：全量
        }
        _engSent = prefix;
        p.then((txt) => {
            if (pyBuffer !== snap) return;      // 用户已继续打字，丢弃过期候选
            let chars = [];
            try {
                const r = JSON.parse(txt);
                chars = (r.candidates || []).map(c => c.text);
            } catch (e) {}
            // #region agent log
            _dbgD('keyboard.js:refreshFromEngine', 'ENGINE_RAW', { snap: snap, txtHead: String(txt || '').slice(0, 120), charsLen: chars.length, chars: chars.slice(0, 6), pyNow: pyBuffer });
            // #endregion
            if (chars.length) { _perfMark('★引擎候选回填(相对首键的延迟)');
                // #region agent log
                _dbgD('keyboard.js:refreshFromEngine', 'ASYNC_CAND', {
                    snap: snap, chars: chars.slice(0, 6), pyNow: pyBuffer, started: Date.now() % 1e5
                });
                // #endregion
                _showCand(pyBuffer, attachEmoji(_alignHint(chars, pyBuffer))); }
        }).catch((e) => { _dbgD('keyboard.js:refreshFromEngine', 'ENGINE_ERR', { snap: prefix, err: String(e && e.message || e) }); _engSent = ''; });
    }
    /* ---- 首键 / 打开键盘 性能探针：仅 window.__wxPerf=true 时启用（默认关闭，零开销）----
       定位「键盘打开后前 2 秒打不出字」落到哪一档。只把结果写进 window.__wxPerfLog（不刷 console），
       main.py 录完或 devtools 执行 console.table(window.__wxPerfLog) 即可查看。
       __wxPerfLog 每项：{label, dt:本阶段耗时, total:本轮累计}；longtask 项为主线程同步卡顿。 */
    const _perf = { t0: 0, last: 0 };
    function _perfReset() {
        const now = performance.now();
        _perf.t0 = now; _perf.last = now;
    }
    function _perfMark(label) {
        if (!window.__wxPerf) return;
        const now = performance.now();
        const dt = _perf.last ? (now - _perf.last) : 0;
        const total = _perf.t0 ? (now - _perf.t0) : dt;
        const log = (window.__wxPerfLog = window.__wxPerfLog || []);
        if (log.length < 800) log.push({ label, dt: Math.round(dt), total: Math.round(total) });
        _perf.last = now;
    }
    /* 长任务监听常驻注册；收到事件且 __wxPerf 开启时才落档（便于运行中切 window.__wxPerf=true） */
    try {
        new PerformanceObserver((list) => {
            if (!window.__wxPerf) return;
            for (const e of list.getEntries()) {
                const log = (window.__wxPerfLog = window.__wxPerfLog || []);
                if (log.length < 800) log.push({ label: 'longtask', dt: Math.round(e.duration), total: Math.round(e.startTime) });
            }
        }).observe({ entryTypes: ['longtask'] });
    } catch (e) { /* 个别环境不支持 longtask，忽略 */ }

    function tryImeCompose(el, skipCompose) {
        _perfReset();
        const v = el.value || '';
        // #region agent log
        _dbgD('keyboard.js:tryImeCompose', 'KEY_EVT', { valLen: v.length, imeMode: imeMode, hasRime: !!(window.__rimeEngine && window.__rimeEngine.ready), t: Math.round(performance.now()) });
        // #endregion
        if (imeMode === 'pinyin' && !skipCompose) {
            const m = /([a-z]+)$/.exec(v);
            if (m) {
                pyBuffer = m[1];
                pyStart = m.index;
                _perfMark('取拼音+设组合区');
                renderComposition(el);
                _perfMark('renderComposition');
                const cands = attachEmoji(queryPinyin(pyBuffer));
                _perfMark('queryPinyin+attachEmoji');
                if (cands.length) { _showCand(pyBuffer, cands); _perfMark('_showCand'); refreshFromEngine(pyBuffer); _perfMark('refreshFromEngine(派发引擎)'); return; }
            }
        }
        pyBuffer = ''; pyStart = -1;
        refreshFromEngine('');   // 组合消失 -> 同步清引擎会话（{Escape}）
        renderComposition(el);   // 无组合/英文 -> 若聚焦则画空闲绿色光标，未聚焦则隐藏
        _perfMark('renderComposition(无拼音)');
        _showCand('', ensureCandidates(v));   // 无组合/英文 -> 联想或保底，永不空
        _perfMark('_showCand(联想/兜底)');
    }
    document.addEventListener('input', (e) => {
        const el = e.target;
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
            const skip = _suppressComposeOnce; _suppressComposeOnce = false;
            tryImeCompose(el, skip);
        }
    }, true);
    /* 聚焦/失焦：聚焦时绘制空闲绿色光标，失焦时隐藏覆盖层（回到原生隐藏光标状态） */
    const isComposeTarget = (el) => !!(el && el.classList && (
        el.classList.contains('chat-txt') || el.id === 'momentCommentInput'));
    document.addEventListener('focusin', (e) => {
        const el = e.target;
        if (isComposeTarget(el)) renderComposition(el);
    }, true);
    document.addEventListener('focusout', (e) => {
        const el = e.target;
        if (isComposeTarget(el)) clearComposition();
    }, true);

    /* 上屏一段文字（可单字也可词组）：把输入框结尾的组合拼音替换为实际文字,
       保证最终文字与脚本一致。
       返回 Date.now()（毫秒墙钟）：这是「字真正写入输入框」的视觉时刻，
       main.py 用它放置上屏相关音效，避免声音锚定在 Python 发命令时刻（偏早）。 */
    function replaceBuffer(text) {
        const el = inputTarget();
        if (!el) return false;
        const v = el.value || '';
        const m = /([a-z]+)$/.exec(v);
        const start = m ? m.index : v.length;   /* 没有组合拼音时直接追加 */
        el.value = v.slice(0, start) + text;
        _suppressComposeOnce = true;   /* 本次上屏不重新组字（确认拼音原样上屏时 value 仍以 [a-z] 结尾） */
        el.dispatchEvent(new Event('input', { bubbles: true }));   // 触发 tryImeCompose(无拼音 -> 清空候选)
        pyBuffer = ''; pyStart = -1;
        refreshFromEngine('');                                     // 上屏 -> 清引擎组合会话
        _topHint = null;                                           // 已上屏，本段目标词预告失效
        renderComposition(el);                                     // 仍聚焦 -> 重画整段文本 + 空闲绿色光标
        syncSendState();
        predictNext(el.value);                                     // 之后用二元模型显示"下一个词"联想
        return Date.now();
    }
    function commitByChar(ch) { return replaceBuffer(ch); }
    function commitByPhrase(word) { return replaceBuffer(word); }

    /* 联想：提交候选后，用二元模型显示"下一个可能词/字"（如 我 -> 们/在/要；我们 -> 明天/一起）。
       这是真实输入法选中一个字后继续出预测字的行为，避免候选条被清空。 */
    function predictNext(text) {
        _showCand('', ensureCandidates(text));   // 联想或保底，永不空
    }

    /* ---- 发送键状态：有文字绿色「发送」，无文字灰色「换行」 ----
       组合态（拼音候选未选定，.kb-composing）优先显示「确认」：
       参考视频「发送按键的变化规律.mp4」——右下角键在打字全程随候选出现/消失
       在 蓝「发送」↔ 灰「确认」间瞬时切换，空格键文字同步 空白/「空格」↔「选定」。 */
    let sendOn = false;
    function applySendState() {
        const el = keys['send'];
        if (!el) return;
        const composing = !!(pyBuffer && imeMode === 'pinyin');
        el.classList.toggle('kb-send-on', sendOn && !composing);
        el.textContent = composing ? '确认' : (sendOn ? '发送' : '换行');
    }

    /* ---- 输入目标：当前聚焦的输入框/文本域 ---- */
    function inputTarget() {
        const el = document.activeElement;
        if (!el || !el.tagName) return null;
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return el;
        if (el.isContentEditable) return el;
        return null;
    }

    /* ---- 直接把字符写入输入框（供手动点击 / 候选点击使用） ---- */
    function insertChar(ch) {
        const el = inputTarget();
        if (!el) return;
        if (el.isContentEditable) { el.textContent += ch; }
        else { el.value = (el.value || '') + ch; }
        // #region agent log
        if (/[\uD800-\uDFFF]/.test(ch) || (typeof ch === 'string' && ch.length > 1)) {
            _dbgD('keyboard.js:insertChar', 'INSERT', { chHex: Array.from(ch).map(_hex), chLen: ch.length, valueLen: (el.value||'').length });
        }
        // #endregion
        el.dispatchEvent(new Event('input', { bubbles: true }));
        syncSendState();
        if (/[\u4e00-\u9fff]/.test(ch)) predictNext(el.value);   // 提交汉字后继续联想(链式)
    }
    // #region agent log (delete surrogate-pair diagnosis)
    function _dbgD(loc, msg, data) {
        // 仅在 agent 调试开启（WX_DEBUG_AGENT=1 注入的 __wxDebugAgent）时才记录，
        // 生产跑批不攒几千条 __wxDelDebug、也不发 7808 fetch，避免拖慢/看门狗误杀。
        if (!window.__wxDebugAgent) return;
        try {
            (window.__wxDelDebug = window.__wxDelDebug || []).push({ location: loc, message: msg, data: data || {}, t: Date.now() });
        } catch (e) {}
        // #region agent log (debug-mode NDJSON bridge)
        try {
            fetch('http://127.0.0.1:7808/ingest/0a5e3db5-64c1-4ff6-9da8-2bcd1ad0722e', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Debug-Session-Id': '189770' },
                body: JSON.stringify({ sessionId: '189770', location: loc, message: msg, data: data || {}, timestamp: Date.now() })
            }).catch(() => {});
        } catch (e) {}
        // #endregion
    }
    function _hex(u) { return u == null ? '' : u.toString(16); }
    // 按「字素簇」删除最后一个字符：正确处理代理对(emoji)/变体选择符/ZWJ 组合。
    // 旧实现 slice(0,-1) 只删一个 UTF-16 码元，会把 emoji 拆成孤立代理 → 文字先变/先消失。
    function _graphemePop(s) {
        if (!s) return s;
        try {
            if (typeof Intl !== 'undefined' && Intl.Segmenter) {
                const seg = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
                const parts = Array.from(seg.segment(s));
                if (parts.length <= 1) return '';
                return parts.slice(0, -1).map(function (p) { return p.segment; }).join('');
            }
        } catch (e) {}
        const cps = Array.from(s);        // 按码点拆分（正确处理代理对）兜底
        cps.pop();
        return cps.join('');
    }
    // #endregion
    function deleteLastChar() {
        const el = inputTarget();
        if (!el) return;
        const before = el.isContentEditable ? (el.textContent || '') : (el.value || '');
        const u = before.length ? before.charCodeAt(before.length - 1) : null;       // 最后一个码元
        const afterSlice = before.slice(0, -1);                                       // 旧逻辑去掉一个码元后（仅用于对比日志）
        const tail = afterSlice.length ? afterSlice.charCodeAt(afterSlice.length - 1) : null;
        const isHighSur = (v) => v != null && v >= 0xD800 && v <= 0xDBFF;
        const isLowSur = (v) => v != null && v >= 0xDC00 && v <= 0xDFFF;
        const last2 = before.slice(-2);
        const afterFull = _graphemePop(before);                                        // 按字素簇删（修复后，避免拆孤立代理）
        // #region agent log
        _dbgD('keyboard.js:deleteLastChar', 'DEL', {
            beforeLen: before.length, beforeCp: (function(){ try{return Array.from(before).length;}catch(e){return -1;} })(),
            lastUnitHex: _hex(u), lastUnitIsLowSur: isLowSur(u),
            last2units: Array.from(last2).map(_hex),
            orphanTailHighSur: isHighSur(tail), afterLen: afterSlice.length,
            fixedAfter: afterFull
        });
        // #endregion
        if (el.isContentEditable) { el.textContent = afterFull; }
        else { el.value = afterFull; }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        syncSendState();
    }

    /* ---- 输入状态轮询 + input 事件即时同步：自动判断发送键 ---- */
    let sendTimer = null;
    function syncSendState() {
        if (!window.__wxKeyboard.visible) return;
        let has = false;
        const el = document.activeElement;
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') &&
            typeof el.value === 'string' && el.value.trim()) has = true;
        if (has !== sendOn) { sendOn = has; applySendState(); }
    }
    document.addEventListener('input', syncSendState, true);

    /* ---- 按键按下高亮 + iOS 键盘字符浮层 ---- */
    let popEl = null;
    let popupOn = true;   /* 字符浮层总开关：高速打字(由 main.py 按倍速设置)时关掉，避免满屏气泡高速跳动 */
    /* 高亮 / 浮层的最小停留：真人/手动点按约 150ms；快速打字(倍速)时按下时长可能
       只有几十毫秒，浮层弹出动画(≈160ms)若按原来的 100ms 门槛会被跳过，
       于是 30 倍速打字时「逐键上浮放大字符」这一核心动画直接消失（用户反馈的
       「打字动画没了」）。因此把门槛从 100ms 降到 30ms（≈ KEY_HOLD_MIN_MS 附近），
       让高速连打时每个字母键也弹出浮层；浮层显示时长=MAX(holdMs,320) 不受影响，
       仍 ≥320ms，连打时只是随按键快速跳位，观感是「快打时字母跟着飞」。
       关键：浮层只限「字母/数字」实体键；功能键(backspace/shift/123/空格等)一律不弹，
       尤其回退键在真机上只有按压变色，没有上浮气泡。 */
    const pressFx = (el, ms) => {
        if (!el) return false;
        el.classList.add('kb-press');
        const label = el.dataset.key;
        const holdMs = Math.max(1, ms || 150);
        if (popupOn && label && /^[a-z0-9]$/i.test(label) && !FN_KEYS.has(label) && holdMs >= 30) {
            if (!popEl) {
                popEl = document.createElement('div');
                popEl.className = 'kb-pop';
                document.body.appendChild(popEl);
            }
            const r = el.getBoundingClientRect();
            popEl.textContent = el.textContent;   /* 跟随键面当前显示（大写/小写/数字） */
            /* 防边缘超屏：气泡默认居中在键中心，但把它夹在左右各留 6px 边距内；
               被钳制时用 --kb-pop-tail 让箭尖(::after)仍对准被按键中心（不影响其它动画）。 */
            popEl.style.left = Math.round(r.left + r.width / 2) + 'px';
            const kc = r.left + r.width / 2;               /* 键中心(视口x) */
            const half = popEl.offsetWidth / 2;            /* 气泡半宽(含实际内容) */
            const margin = 6;
            const vw = window.innerWidth;
            const lo = half + margin, hi = vw - half - margin;
            const clamped = lo <= hi ? Math.min(Math.max(kc, lo), hi) : kc;
            const boxLeft = clamped - half;
            popEl.style.left = Math.round(clamped) + 'px';
            popEl.style.setProperty('--kb-pop-tail', Math.round(kc - boxLeft) + 'px');
            popEl.style.top = (r.top - 98) + 'px';
            popEl.classList.add('kb-pop-show');
            clearTimeout(popEl._t);
            popEl._t = setTimeout(() => popEl.classList.remove('kb-pop-show'), Math.max(holdMs, 320));
        }
        setTimeout(() => el.classList.remove('kb-press'), holdMs);
        return true;
    };

    /* ---- 候选条高度（真机：拼音出现时键盘才长高） ---- */
    function setCandHeight(px) {
        document.documentElement.style.setProperty('--kb-cand-h', px + 'px');
    }

    /* ---- 键盘区点击：真实键入（供编辑模式人工点按 / 手动演示） ---- */
    root.addEventListener('pointerdown', (e) => {
        if (!window.__wxKeyboard.visible) return;
        const key = e.target.closest('.kb-key');
        if (!key) return;
        e.preventDefault();
        const label = key.dataset.key;
        if (label === 'shift') { toggleShift(); return; }
        if (label === 'globe') { pressFx(key, 150); toggleImeMode(); return; }
        if (label === 'smile') {
            pressFx(key, 150);
            // 点键盘笑脸：收起键盘 → 表情面板从底部滑入（真实微信）
            if (window.__wxEmojiPanel && window.__wxEmojiPanel.open) window.__wxEmojiPanel.open({ view: 'emoji' });
            return;
        }
        if (label === 'mic') { pressFx(key, 150); return; }
        if (label === '123' || label === 'abc' || label === '#+=') {
            /* 显式按布局键：先闪键，稍延迟翻页（flipByKey，倍速下自动压缩） */
            flipByKey(label, label === 'abc' ? 'letters' : (label === '123' ? 'symbols' : 'symbols2'), 150);
            return;
        }
        if (label === 'backspace') { pressFx(keys['backspace'], 150); deleteLastChar(); return; }
        if (label === 'space') {
            pressFx(keys['space'], 150);
            /* 组合态按空格 = 「选定」：上屏候选首位（真机行为），非组合才输入空格 */
            const first = _firstCandidateText();
            if (imeMode === 'pinyin' && pyBuffer && first) { replaceBuffer(first); return; }
            insertChar(' '); return;
        }
        if (label === 'send') {
            pressFx(keys['send'], 170);
            const el = inputTarget();
            /* 组合态发送键 = 「确认」：把未上屏拼音原样上屏（真机 iOS 行为） */
            if (imeMode === 'pinyin' && pyBuffer) { replaceBuffer(pyBuffer); return; }
            if (sendOn && el) {
                el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            }
            return;
        }
        /* 字母 / 数字 / 符号：写入输入框并切换布局（自动翻页=硬切，真机同速） */
        let ch = label;
        if (LETTER_KEYS.has(label)) {
            if (currentLayout !== 'letters') switchLayout('letters');
            ch = shiftState !== 0 ? label.toUpperCase() : label;
        } else if (SYMBOL_KEYS1.has(label)) {
            if (currentLayout !== 'symbols') switchLayout('symbols');
        } else if (SYMBOL_KEYS2.has(label)) {
            if (currentLayout !== 'symbols2') switchLayout('symbols2');
        }
        const el = keys[label] || keys[label.toLowerCase()];
        pressFx(el, 150);
        insertChar(ch);
        if (LETTER_KEYS.has(label) && shiftState === 1) setShiftState(0);
    });

    /* ---- 候选词条点击：候选字/词上屏替换组合区（拼音模式下） ---- */
    candList.addEventListener('click', (e) => {
        const item = e.target.closest('.kb-cand-item');
        if (!item) return;
        const ch = item.dataset.chars;
        if (ch) {
            if (imeMode === 'pinyin' && pyBuffer) replaceBuffer(ch);
            else insertChar(ch);
        }
        pressFx(item, 170);
    });

    /* ---- 键盘开合过渡期间：消息区(.dialogue-section)高度收缩/恢复 + 持续贴底 ----
       旧实现：CSS transition:height(主线程布局动画) 逐帧排版 + _scroll_chat_bottom 每帧抢写
       scrollTop，等于动画期间「每帧两次 layout」，主线程被拖住导致合成器断帧。
       新实现：把「设高度」和「钉 scrollTop」放进同一个 rAF，用 inline !important 逐帧写高度，
       一次读到 scrollHeight 后把 scrollTop 钉到新底——同一帧的读写共享一次布局，每帧只排一次版。
       同时避开 CSS height 过渡（chat_exact.css 已去掉该 transition）。 */
    function _chatSecGeom() {
        const sec = document.querySelector('.dialogue-section');
        if (!sec) return null;   // 非聊天页(朋友圈评论等)无此容器，安全跳过
        const cs = getComputedStyle(document.documentElement);
        const base = parseFloat(cs.getPropertyValue('--chat-sec-base')) || 552;
        const grow = parseFloat(cs.getPropertyValue('--chat-grow')) || 0;
        return { sec, open: base - grow, closed: 1019 };
    }
    function _animChatSection(from, to, durMs) {
        const g = _chatSecGeom();
        if (!g) return;
        const sec = g.sec;
        const t0 = performance.now();
        const ease = t => 1 - (1 - t) * (1 - t);          // easeOutQuad，与 #wxkb 一致
        /* 动画期间关掉 CSS height 过渡：否则 CSS 合成器逐帧排版 与 本次 JS 写高度 会争抢，
           又回到「一帧两次 layout」。结束后恢复，让打字时 --chat-grow 增高仍平滑。 */
        sec.style.setProperty('transition', 'none');
        /* Plan B：弹/收期间消息内容不变，scrollHeight 只读一次并缓存；逐帧只写 height(一次布局)
           + scrollTop(滚动)，不再每帧读 scrollHeight —— 那会强制同步布局，是主线程掉帧的一大来源。 */
        const sh0 = sec.scrollHeight;
        const tick = () => {
            const p = Math.min(1, (performance.now() - t0) / durMs);
            const h = from + (to - from) * ease(p);
            sec.style.setProperty('height', h.toFixed(2) + 'px', 'important');
            // 贴底：内容高于容器时钉到新底(用缓存 sh0，不再每帧强制布局)
            if (sh0 > h) sec.scrollTop = sh0 - h;
            if (p < 1) requestAnimationFrame(tick);
            else {
                // 交还 CSS(--wxkb-open) 稳态高度并恢复过渡；终值=CSS 目标值，故无跳变
                sec.style.removeProperty('height');
                sec.style.removeProperty('transition');
            }
        };
        requestAnimationFrame(tick);
    }

    /* ---- 键盘上滑/下滑动画：JS 显式驱动 transform，不再依赖 CSS transition。
       CSS 那种 transition + visibility + will-change 的组合，在开合瞬间容易把动画「跳成闪出/闪没」
       (合成层时序/过渡被跳过)，观感就是键盘直接弹出来没动画。这里与 _animChatSection 一样：
       先提交起始值(强制 reflow)，再逐帧 translateY，最后交还 CSS 稳态；期间锁定 visibility:visible，
       保证下滑收起时不会因 class 切换在屏幕上瞬间消失。 */
    function _animKb(fromPct, toPct, durMs, finalize) {
        const t0 = performance.now();
        const ease = t => 1 - (1 - t) * (1 - t);          // easeOutQuad，与消息区一致
        root.style.setProperty('transition', 'none');
        root.style.setProperty('visibility', 'visible'); // 滑动期间始终可见
        root.style.setProperty('transform', 'translateY(' + fromPct + '%)');
        void root.offsetWidth;                            // 提交起始值，避免跳变到终点
        const tick = () => {
            const p = Math.min(1, (performance.now() - t0) / durMs);
            const v = fromPct + (toPct - fromPct) * ease(p);
            root.style.transform = 'translateY(' + v.toFixed(2) + '%)';
            if (p < 1) requestAnimationFrame(tick);
            else if (finalize) finalize();
        };
        requestAnimationFrame(tick);
    }

    /* ---- 组合区覆盖层：拼音组合期间，在聊天输入框内渲染真机「绿色下划线拼音 + 音节分格 + 绿色光标」。
       原生 textarea 无法给子串加下划线，故用一块与 .chat-txt 完全同盒的覆盖层，把「已上屏文本 +
       组合拼音(绿色下划线) + 光标」整体绘制在 textarea 之上（不透明底色遮蔽下方裸拼音字母），
       不改动 textarea 的 value / 发送 / 校验链路。仅对聊天输入(.chat-txt)启用。 ---- */
    let composeEl = null;
    let _lastGeoRafT = 0;      /* 合成层几何 rAF 重读的节流时间戳 */
    function ensureComposeHost(el) {
        if (composeEl && composeEl.parentElement !== el.parentElement) composeEl.remove();
        if (!composeEl) {
            composeEl = document.createElement('div');
            composeEl.className = 'wxkb-compose';
        }
        const host = el.parentElement;
        if (host && composeEl.parentElement !== host) host.appendChild(composeEl);
        return composeEl;
    }
    let _styleCache = { el: null, ts: 0, cs: null };   /* 合成层样式缓存：字体/行高在打字中不变，200ms 才重读一次 */
    function _applyComposeBoxStyle(el, box) {
        const now = performance.now();
        let cs = _styleCache.cs && _styleCache.el === el && (now - _styleCache.ts) < 200
            ? _styleCache.cs : null;
        if (!cs) {
            cs = getComputedStyle(el);
            _styleCache = { el: el, ts: now, cs: cs };
        }
        box.style.fontFamily = cs.fontFamily;
        box.style.fontWeight = cs.fontWeight;
        box.style.fontSize = cs.fontSize;
        box.style.lineHeight = cs.lineHeight;
        box.style.letterSpacing = cs.letterSpacing;
        box.style.wordSpacing = cs.wordSpacing;
        box.style.color = cs.color;
        box.style.paddingLeft = cs.paddingLeft;
        box.style.paddingRight = cs.paddingRight;
        box.style.paddingTop = cs.paddingTop;
        box.style.paddingBottom = cs.paddingBottom;
    }
    function clearComposition() {
        if (composeEl) { composeEl.innerHTML = ''; composeEl.style.display = 'none'; }
    }
    function renderComposition(el) {
        _syncComposeUI();   /* 组合态(空格「选定」/发送「确认」)随 pyBuffer 即时同步（见 _syncComposeUI） */
        if (!el || !isComposeTarget(el)) { clearComposition(); return; }
        const py = pyBuffer || '';
        /* 空闲态渲染：输入框聚焦且无组合拼音时，也绘制「整段已上屏文本 + 同一根绿色光标」，
           覆盖 textarea 原生的细光标，让「未打字但聚焦」也显示同一条柔和绿线。 */
        if (!py) {
            if (document.activeElement !== el) { clearComposition(); return; }
        } else if (imeMode !== 'pinyin') {
            clearComposition(); return;
        }
        /* 无拼音 -> 整段已上屏文本；有拼音 -> 截到组合区起点（旧 slice(0, pyStart) 在 pyStart=-1 会截掉末字符） */
        const committed = py ? (el.value || '').slice(0, pyStart) : (el.value || '');
        const box = ensureComposeHost(el);
        _applyComposeBoxStyle(el, box);
        box.style.position = 'absolute';
        box.style.left = el.offsetLeft + 'px';
        box.style.top = el.offsetTop + 'px';
        box.style.width = el.offsetWidth + 'px';
        box.style.height = el.offsetHeight + 'px';
        box.style.display = 'block';
        box.innerHTML = '';
        const cNode = document.createElement('span');
        cNode.className = 'wxkb-compose-committed';
        cNode.textContent = committed;
        box.appendChild(cNode);
        const syls = splitSyllables(py);          /* 按音节分格，复用既有拆分逻辑 */
        const last = syls.length - 1;
        syls.forEach((s, i) => {
            const sp = document.createElement('span');
            sp.className = 'wxkb-compose-syl';
            sp.textContent = s;
            box.appendChild(sp);
            if (i < last) box.appendChild(document.createTextNode(' '));
        });
        const cur = document.createElement('span');
        cur.className = 'wxkb-compose-cursor';
        box.appendChild(cur);
        // #region agent log
        _dbgD('keyboard.js:renderComposition', 'OVL', {
            committedLen: committed.length, py: py, valLen: (el.value || '').length,
            active: document.activeElement === el, imeMode: imeMode, started: Date.now() % 1e5
        });
        // #endregion
        /* 等一帧再校正盒子几何：确保 --chat-grow 已把 textarea 增高后再对齐，避免 1 帧错位。
           几何重读按 ~2 帧节流：40 倍速连打时一帧常有多个按键，不必每键都排一次强制布局。 */
        const now = performance.now();
        if (now - _lastGeoRafT > 33) {
            _lastGeoRafT = now;
            requestAnimationFrame(() => {
                if (!composeEl || composeEl.style.display === 'none') return;
                composeEl.style.left = el.offsetLeft + 'px';
                composeEl.style.top = el.offsetTop + 'px';
                composeEl.style.width = el.offsetWidth + 'px';
                composeEl.style.height = el.offsetHeight + 'px';
            });
        }
    }

    /* ---- 对外 API（由 Playwright / main.py 调用） ---- */
    window.__wxKeyboard = {
        visible: false,

        /* 设置字符浮层开关：高速打字(main.py 按倍速判定)时置 false，
           避免 40 倍速下每键弹泡、满屏高速跳动显得眼花缭乱；低速仍保留。 */
        setPopupEnabled(v) { popupOn = !!v; return popupOn; },

        /* 弹出键盘（带动画）
           opts.instant = true：不做自身动画（不跑 _animKb/_animChatSection，也不写 inline
           height），只切类与状态。供 panel_switch.js 的「底部面板直接切换」使用——那套切换
           要给 #wxkb 与输入栏/消息区统一挂 230ms 同一条曲线，键盘自己再跑一套 rAF 会抢同一个
           transform（inline 覆盖 CSS），并与面板位移脱帧。 */
        show(opts) {
            const instant = !!(opts && opts.instant);
            _perfReset(); _perfMark('show() 开始');
            /* 先把消息区高度钉在起点（收起态 1019px），避免类切换瞬间闪现收缩后的高度，
               再交给 _animChatSection 统一逐帧收放。仅「收起→弹出」真过渡才做高度动画；
               若已处于弹出态(连续会话之间键盘常开)则空跑，靠 main 的 _scroll_chat_bottom 贴底。 */
            const wasVisible = this.visible;
            const g0 = _chatSecGeom();
            if (g0 && !wasVisible && !instant) g0.sec.style.setProperty('height', g0.closed + 'px', 'important');
            root.classList.add('kb-open');
            document.body.classList.add('wxkb-open');
            this.visible = true;
            pyBuffer = ''; pyStart = -1;
            refreshFromEngine('');   // 键盘弹出 -> 引擎会话清零对齐
            _syncComposeUI();
            applyImeKey();
            if (sendTimer) clearInterval(sendTimer);
            sendTimer = setInterval(syncSendState, 350);
            syncSendState();
            _showCand('', ensureCandidates(inputTarget() ? inputTarget().value : ''));
            _perfMark('show() 候选渲染');
            if (g0 && !wasVisible && !instant) _animChatSection(g0.closed, g0.open, 180);   // 高度收缩+贴底，单帧一次排版
            if (!wasVisible) {
                if (instant) {
                    /* 交还 CSS 稳态：清掉上一次动画可能残留的 inline 值，让 .kb-open 的
                       translateY(0) + 面板切换层的过渡接管。 */
                    root.style.removeProperty('transform');
                    root.style.removeProperty('transition');
                    root.style.removeProperty('visibility');
                } else {
                    // 键盘显式上滑（不靠 CSS 过渡，保证一定有动画）；结束后交还 CSS 稳态。
                    _animKb(100, 0, 180, () => {
                        root.style.removeProperty('transform');
                        root.style.removeProperty('transition');
                        root.style.removeProperty('visibility');
                    });
                }
            }
            _perfMark('show() 贴底派发');
        },

        /* 收起键盘
           opts.keepSection = true：跳过消息区高度动画（由面板接管）
           opts.instant     = true：不做自身动画，只切类与状态（同 show） */
        hide(opts) {
            const keepSection = !!(opts && opts.keepSection);   // 表情面板打开时跳过消息区高度动画，由面板接管
            const instant = !!(opts && opts.instant);
            /* 仅「弹出→收起」真过渡才做高度动画；已收起则不空跑。 */
            const wasVisible = this.visible;
            const g = _chatSecGeom();
            if (g && wasVisible && !keepSection && !instant) g.sec.style.setProperty('height', g.open + 'px', 'important');
            root.classList.remove('kb-open');
            document.body.classList.remove('wxkb-open');
            this.visible = false;
            if (sendTimer) { clearInterval(sendTimer); sendTimer = null; }
            pyBuffer = ''; pyStart = -1;
            refreshFromEngine('');   // 键盘收起 -> 清引擎组合会话
            _topHint = null;
            _syncComposeUI();
            clearComposition();
            setShiftState(0);
            if (g && wasVisible && !keepSection && !instant) _animChatSection(g.open, g.closed, 180);   // 高度恢复+贴底，单帧一次排版
            if (wasVisible) {
                if (instant) {
                    root.style.removeProperty('transform');
                    root.style.removeProperty('transition');
                    root.style.removeProperty('visibility');
                } else {
                    // 键盘显式下滑；结束后交还 CSS 稳态(translateY(100%) + visibility:hidden)。
                    _animKb(0, 100, 180, () => {
                        root.style.removeProperty('transform');
                        root.style.removeProperty('transition');
                        root.style.removeProperty('visibility');
                    });
                }
            }
            /* 候选词延后清空：让候选条随键盘整体下滑（与弹出时候选条随键盘上升对称），
               等键盘滑出屏幕(过渡仅 .18s)后再 clear，避免收起瞬间候选行突兀消失的拼接感。 */
            clearTimeout(this._candHideT);
            this._candHideT = setTimeout(() => this.clearCandidates(), 235);
        },

        /* 设置大小写状态：off / on（单次）/ caps（锁定） */
        setShift(state) {
            if (state === true || state === 'on' || state === 1) setShiftState(1);
            else if (state === 'caps' || state === 2) setShiftState(2);
            else setShiftState(0);
            return shiftState;
        },

        /* 强制切换到指定布局：'letters' | 'symbols' | 'symbols2'。
           供鼠标驱动/main.py 在删除等场景保证退格键显示在字母布局（位置一致）。 */
        switchLayout(to) {
            if (to === 'letters' || to === 'symbols' || to === 'symbols2') switchLayout(to);
            return to;
        },

        /* 按下一个键（自动切换数字/符号布局，只做按键高亮动画）。
           label: a~z / 0~9 / shift / backspace / space / send / 123 / abc / #+= / 标点等
           holdMs: 按键按压时长(毫秒)。由 Python 端传入与真实 hold 一致的值；
                   手动点击(默认 150)不传则用真人手感时长。
           返回 Date.now()（毫秒墙钟）：按键高亮真正发生的视觉时刻，main.py 用于对齐音效。 */
        pressKey(label, holdMs) {
            label = String(label);
            holdMs = (typeof holdMs === 'number' && holdMs > 0) ? holdMs : 150;
            /* 先切换布局：字母→letters，数字/符号→symbols（或第二页）。
               自动翻页=硬切（真机同速，翻页后当帧即可高亮目标键）。 */
            let target = null;
            if (/^[a-zA-Z]$/.test(label)) target = 'letters';
            else if (SYMBOL_KEYS1.has(label)) target = 'symbols';
            else if (SYMBOL_KEYS2.has(label)) target = 'symbols2';
            if (target && target !== currentLayout) switchLayout(target);

            /* 功能键 */
            if (label === 'shift') { toggleShift(); return Date.now(); }
            if (label === 'globe') { toggleImeMode(); return Date.now(); }
            if (label === 'smile') {
                pressFx(keys[label], holdMs);
                if (window.__wxEmojiPanel && window.__wxEmojiPanel.open) window.__wxEmojiPanel.open({ view: 'emoji' });
                return Date.now();
            }
            if (label === 'mic') { pressFx(keys[label], holdMs); return Date.now(); }
            if (label === 'backspace' || label === 'space' || label === 'send') {
                pressFx(keys[label], holdMs);
                return Date.now();
            }
            if (label === '123' || label === 'abc' || label === '#+=') {
                /* 显式按布局键：先闪键，稍延迟翻页（flipByKey，倍速下自动压缩） */
                flipByKey(label, label === 'abc' ? 'letters' : (label === '123' ? 'symbols' : 'symbols2'), holdMs);
                return Date.now();
            }
            /* 字母：若传入大写，表示该键在大写状态下按下（确保 shift 生效） */
            if (/^[a-zA-Z]$/.test(label) && label !== label.toLowerCase() && shiftState === 0) {
                setShiftState(1);
            }
            const el = keys[label.toLowerCase()] || keys[label];
            /* 目标布局里没有的键（如第一页没有 & "）：pressFx(null) 静默跳过；
               这里仍返回视觉时刻，保证打字声锚点不因跳页而漂移。 */
            const ok = el ? pressFx(el, holdMs) : true;
            /* 大写单次：按完一个字母后自动回弹小写 */
            if (/^[a-zA-Z]$/.test(label) && shiftState === 1) setShiftState(0);
            return ok ? Date.now() : false;
        },

        /* 一次调用完成「插入字符」+「按键高亮」（等价于 pressKey + insertChar）。
           供 main.py 在高倍速(如 30x)下把每个字母原来的 2 次 Playwright 往返
           (keyboard.type + pressKey) 压成 1 次，避免被 CDP 往返卡成 ~15x。
           行为与 pointerdown 手动点按完全一致：先切布局、再高亮并真正写入字符。
           返回 Date.now()（毫秒墙钟）：写入+高亮完成的视觉时刻。 */
        pressType(label, holdMs) {
            label = String(label);
            holdMs = (typeof holdMs === 'number' && holdMs > 0) ? holdMs : 150;
            let target = null;
            if (/^[a-zA-Z]$/.test(label)) target = 'letters';
            else if (SYMBOL_KEYS1.has(label)) target = 'symbols';
            else if (SYMBOL_KEYS2.has(label)) target = 'symbols2';
            if (target && target !== currentLayout) switchLayout(target);

            if (label === 'space') {
                pressFx(keys['space'], holdMs);
                /* 组合态按空格 = 「选定」：上屏候选首位（真机行为），与点击路径一致 */
                const first = _firstCandidateText();
                if (imeMode === 'pinyin' && pyBuffer && first) { replaceBuffer(first); return Date.now(); }
                insertChar(' '); return Date.now();
            }
            if (label === 'backspace') { pressFx(keys['backspace'], holdMs); deleteLastChar(); return Date.now(); }
            if (label === 'send' || label === 'shift' || label === 'globe' ||
                label === 'smile' || label === 'mic' || label === '123' ||
                label === 'abc' || label === '#+=') {
                return pressKey(label, holdMs);   /* 功能键走原逻辑 */
            }
            if (/^[a-zA-Z]$/.test(label) && label !== label.toLowerCase() && shiftState === 0) {
                setShiftState(1);
            }
            const el = keys[label.toLowerCase()] || keys[label];
            /* 目标布局里没有的键：只写入字符、跳过按键高亮。 */
            const ok = el ? pressFx(el, holdMs) : true;
            let ch = label;
            if (LETTER_KEYS.has(label)) ch = shiftState !== 0 ? label.toUpperCase() : label;
            insertChar(ch);
            if (LETTER_KEYS.has(label) && shiftState === 1) setShiftState(0);
            return ok ? Date.now() : false;
        },

        /* 批量打一段拼音（一次往返敲多个字母）：同 deleteHold 思路，把「逐键高亮+写入字符」
           交给浏览器按 cadence 节奏推进，避免 Python 每字母一趟 page.evaluate 被 CDP 往返
           切成错位帧（高倍速下正是「打字一顿一顿、打一半卡一下」的来源）。
           首字母同步立即触发，其后 setTimeout(cadence) 排队；浏览器主线程每键约 6~8ms 渲染，
           实际节奏按 max(cadence, 渲染耗时) 走，天然均匀、无往返抖动。
           hintWord/hintPy：本段目标词预告（等价一次 setTopHint），随批一次传入省一趟往返。
           每键墙钟毫秒写入 window.__typeWalls；打字中 typingBusy=true。 */
        pressRun(letters, cadenceMs, displayMs, hintWord, hintPy) {
            letters = letters && letters.length ? Array.from(letters) : [];
            const el = inputTarget();
            if (!el) return { ok: false, n: 0 };
            if (hintWord && hintPy) _topHint = { py: String(hintPy), word: String(hintWord) };
            /* 首批含字母则确保字母布局（自动翻页=硬切） */
            if (letters.length && /^[a-z]$/.test(String(letters[0])) && currentLayout !== 'letters') {
                switchLayout('letters');
            }
            this._typing = true;
            window.__typeWalls = [];
            const walls = window.__typeWalls;
            let i = 0;
            const step = () => {
                if (this._typing !== true || i >= letters.length ||
                    !this.visible || inputTarget() !== el) {
                    this._typing = false;
                    return;
                }
                const lb = String(letters[i]);
                let ch = lb;
                if (/^[a-z]$/.test(lb)) {
                    const key = keys[lb] || keys[lb.toLowerCase()];
                    pressFx(key, displayMs);
                    ch = (typeof shiftState === 'number' && shiftState !== 0) ? lb.toUpperCase() : lb;
                    if (shiftState === 1) setShiftState(0);
                } else if (lb === 'space') {
                    pressFx(keys['space'], displayMs);
                    ch = ' ';
                } else {
                    pressFx(keys[lb] || keys[lb.toLowerCase()] || null, displayMs);
                }
                walls.push(Date.now());
                insertChar(ch);
                i++;
                if (i >= letters.length) { this._typing = false; return; }
                setTimeout(step, cadenceMs);
            };
            step();
            return { ok: true, n: letters.length };
        },
        get typingBusy() { return this._typing === true; },

        /* 长按退格连续删字：删字节奏交给浏览器 rAF，**每显示帧删 1 字**。
           高倍速下真实每字间隔已不足一帧（如 40x ≈ 2~3ms），Python 逐字往返会把
           高亮与删字切成错位帧 → 观感掉帧。改由这里帧对齐删除，均匀且无 CDP 抖动。
           返回起始墙钟毫秒；删除中 deleteBusy=true；每字视觉时刻写入 window.__delWalls
           （Python 端读完用于音效锚点）。 */
        deleteHold(n, intervalMs) {
            if (this._delHolding) return 0;
            const el = inputTarget();
            if (!el) return 0;
            this._delHolding = true;
            const t0 = Date.now();
            window.__delWalls = [];
            let left = Math.max(1, n | 0);
            /* 每字间隔直接由外部(DELETE_SPEED)给定，与打字速度(TYPE_SPEED)完全解耦：
               intervalMs 越大删得越慢、越小删得越快；小于一帧(约16.7ms)时在单帧内补删多字，
               但仍按理想间隔打时间戳(音效锚点均匀)；由浏览器 rAF 帧对齐、无 CDP 抖动。
               interval=0/缺省 时保留旧行为「每显示帧删 1 字」（供调试脚本用）。 */
            const interval = Number(intervalMs) || 0;
            let next = interval > 0 ? (t0 + interval) : t0;
            const tick = () => {
                if (!this._delHolding) return;
                if (!this.visible || left <= 0 || inputTarget() !== el) {
                    this._delHolding = false;   /* 删完 / 键盘收起 / 焦点离开 → 停止 */
                    return;
                }
                const now = Date.now();
                if (interval > 0 ? (now >= next) : true) {
                    pressFx(keys['backspace'], interval > 0 ? Math.max(45, interval) : 45);  /* 退格键长按高亮：间隔越大高亮越持久 */
                    // #region agent log
                    _dbgD('keyboard.js:deleteHold.tick', 'DELHOLD', { left: left, interval: interval, curLen: (el.value||'').length, curCp: (function(){try{return Array.from(el.value||'').length;}catch(e){return -1;}})() });
                    // #endregion
                    if (interval > 0) {
                        while (left > 0 && next <= now) {   /* 落后多个间隔→一帧补删多字，仍按理想间隔打戳 */
                            deleteLastChar();
                            window.__delWalls.push(next);
                            left--;
                            next += interval;
                        }
                        if (left > 0 && next <= now) next = now + interval;  /* 防长时间卡顿后连续抢删 */
                    } else {
                        deleteLastChar();
                        window.__delWalls.push(now);
                        left--;
                    }
                }
                requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
            return t0;
        },
        get deleteBusy() { return !!this._delHolding; },

        /* 显示拼音候选词条：chars=候选字/词数组（第一个即为最贴合文字）。
           候选按内容宽度排布，一行放满即止：候选越长放得越少（输入越长预选词越少），
           避免长词挤进窄槽溢出、与相邻候选重叠。首个（整句/最贴合）候选始终保留。
           性能：同一份候选内容不重复重建 DOM（Rime 引擎结果与本地一致时省掉一半重绘）；
           宽度测量只在装好后一次 scrollWidth 校验，不再「每加一项都读一次」强制重排。 */
        showCandidates(pinyin, chars) {
            chars = Array.isArray(chars) ? chars : (typeof chars === 'string' ? chars.split('') : []);
            if (!chars.length) {
                candList.innerHTML = '';
                candBar.classList.remove('has-cand');
                setCandHeight(0);
                _lastCandSig = ''; _lastShownN = 0;
                return 0;
            }
            /* 去重：候选内容与上次显示完全一致 → 跳过整个 DOM 重建（引擎重复刷同一批） */
            const sig = chars.map((ch) => typeof ch === 'string' ? ch
                : (ch && (ch.type === 'emoji' || ch.type === 'wximg')
                    ? 'e:' + (ch.code || ch.src || ch.emoji)
                    : 's:' + (ch.text || ''))
            ).join('|');
            if (sig === _lastCandSig) return _lastShownN;
            _lastCandSig = sig;
            // #region agent log
            _dbgD('keyboard.js:showCandidates', 'CAND', {
                py: pinyin, chars: sig.slice(0, 160),
                valLen: (function () { const e = document.querySelector('textarea.chat-txt'); return e ? e.value.length : -1; })(),
                ovlNow: (function () { const c = document.querySelector('.wxkb-compose-committed'); return c ? c.textContent : ''; })(),
                started: Date.now() % 1e5
            });
            // #endregion
            candList.innerHTML = '';
            candBar.classList.remove('has-cand');
            setCandHeight(0);   /* 候选栏为绝对定位叠放，不再撑高键盘，变量置0 */
            /* 真机容量：候选条尽量出满 8 个（引擎页大小 10），不再随已敲拼音变长而缩到 4 个。
               - 单字候选（一个拼音）一行 8 个；多字词候选字符更宽，同上限下按宽度自然
                 裁到 ~7 个（正常间距，不强行挤 8 个）——超出容量的由右侧「翻页箭头」暗示；
               - 首个（整句/最贴合）候选恒保留。 */
            let cap = 8;
            /* 候选条可视宽度（left:0/right:0 铺满整屏，约 viewport-左右 padding） */
            const listW = () => candList.clientWidth
                || (candList.parentElement ? candList.parentElement.clientWidth : 0);
            const frag = document.createDocumentFragment();
            let shown = 0;
            for (let i = 0; i < chars.length && shown < cap; i++) {
                const ch = chars[i];
                /* 引擎会返回 emoji 字符候选（🈴️/🆗️ 等）：以文字渲染，在缺彩色 emoji 字体的
                   录制环境里是「看不见的宽空槽」，把文字候选挤得忽远忽近（间距乱）。一律跳过，
                   让后续文字候选自然顶上（cap 之前过滤，行内只留真实文字，space-between 均匀铺满）。 */
                if (typeof ch === 'string' && ch.length > 0 &&
                    /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/u.test(ch)) {
                    continue;
                }
                const b = document.createElement('button');
                b.className = 'kb-cand-item';
                b.dataset.candIndex = String(i);
                const isEmoji = ch && typeof ch === 'object' && ch.type === 'emoji';
                const isSymbol = ch && typeof ch === 'object' && ch.type === 'symbol';
                const isWxImg = ch && typeof ch === 'object' && ch.type === 'wximg';
                if (isEmoji || isWxImg) {
                    /* 表情候选：苹果彩色 emoji 图片；微信小表情图为真实 PNG（wxemoji/）。缺图时回退。 */
                    b.classList.add('kb-cand-emoji');
                    if (isWxImg) {
                        b.classList.add('kb-cand-wximg');
                        b.dataset.chars = ch.emoji || '';   // 纯图无上屏字，保留点击高亮
                        b.dataset.src = ch.src;
                    } else {
                        b.dataset.chars = ch.emoji;
                        b.dataset.code = ch.code;
                    }
                    const img = document.createElement('img');
                    img.alt = '';
                    img.src = isWxImg ? ch.src : ('/images/emoji/' + ch.code + '.png');
                    img.onerror = function () {
                        /* 微信小表情图已由 preheat 预载，此处仅兜底：缺图整槽隐藏（display:none
                           保留 DOM 占位、tapCandidate 按子节点序号取用不串位），不留空槽破坏间距 */
                        if (isWxImg) { this.closest('.kb-cand-item').style.display = 'none'; }
                        else { this.outerHTML = '<span class="kb-emoji-text">(＾▽＾)</span>'; }
                    };
                    b.appendChild(img);
                } else if (isSymbol) {
                    /* 颜文字/符号候选：作为文字上屏（commitByPhrase 可插入），字号略小、与文字错开占位 */
                    b.classList.add('kb-cand-symbol');
                    b.dataset.chars = ch.text;
                    b.innerHTML = '<b>' + ch.text + '</b>';
                } else {
                    b.dataset.chars = ch;
                    /* 多字词候选（两个拼音/三字词）挂 .kb-cand-multi 作为标记位：
                       当前不做特殊收紧（词行按宽度自然 ~7 个），留着方便以后按需定向调整样式。 */
                    if (ch.length > 1) b.classList.add('kb-cand-multi');
                    b.innerHTML = '<b>' + ch + '</b>';
                }
                frag.appendChild(b);
                shown++;
            }
            candList.appendChild(frag);     /* 一次挂载后统一测量，最多裁剪一次末尾超出的候选 */
            const room = Math.max(listW(), 40);
            while (candList.scrollWidth > room && candList.childElementCount > 1) {
                candList.removeChild(candList.lastElementChild);
                shown--;
            }
            _lastShownN = shown;
            if (shown) candBar.classList.add('has-cand');
            return shown;
        },

        /* 点击第 index 个候选字（高亮动画） */
        tapCandidate(index) {
            const el = candList.children[index];
            return pressFx(el, 170);
        },

        /* 清空候选词条（键盘回落） */
        clearCandidates() {
            candList.innerHTML = '';
            candBar.classList.remove('has-cand');
            setCandHeight(0);
            _lastCandSig = ''; _lastShownN = 0;
            clearComposition();
        },

        /* 强制设置发送键状态（有/无文字），供外部驱动时即时同步 */
        setSendText(hasText) {
            sendOn = !!hasText;
            applySendState();
        },

        /* ---- 拼音引擎对外 API（由 main.py / 编辑器调用） ---- */

        /* 查询拼音前缀的候选字（如 query('w') → ['我','问','文',...]） */
        query(prefix) { return queryPinyin(prefix); },

        /* 预告"本段目标词"（候选-上屏首位对齐微调）：main.py 敲一段拼音前调用 (word, fullPy)，
           敲到该完整拼音时把候选首位对准 word；commit 上屏后自动清除。传空则清除。 */
        setTopHint(word, py) {
            _topHint = (word && py) ? { py: py, word: word } : null;
            return !!_topHint;
        },

        /* 中文/英文输入模式：'pinyin' | 'english'（'abc' 同 'english'） */
        setImeMode(mode) { setImeMode(mode); return imeMode; },
        toggleImeMode() { toggleImeMode(); return imeMode; },
        getImeMode() { return imeMode; },

        /* 上屏一个汉字：把输入框结尾的组合拼音替换为该字（保证剧本文字一致） */
        commitByChar(ch) { return commitByChar(ch); },

        /* 上屏一个词组：把输入框结尾的组合拼音替换为该词（如 commitByPhrase('我们')） */
        commitByPhrase(word) { return commitByPhrase(word); },

        /* 上屏候选列表里第 index 个字：先高亮动画，再真正提交 */
        commit(index) {
            const item = candList.children[index];
            if (item) pressFx(item, 170);
            return commitByChar(item && item.dataset.chars);
        },

        /* 直接输入一个拼音字母（等价于真实键盘敲入；自动触发联想）。
           供不走 Playwright 键盘事件的调用方使用。 */
        typeLetter(letter) {
            const el = inputTarget();
            if (!el) return false;
            el.value = (el.value || '') + String(letter).toLowerCase();
            el.dispatchEvent(new Event('input', { bubbles: true }));
            return true;
        },
    };
})();
