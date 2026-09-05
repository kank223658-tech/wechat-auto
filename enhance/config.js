/* ============================================================
   微信个人资料 / 朋友圈数据配置（main.py 注入）
   ------------------------------------------------------------
   作用：让「头像 / 昵称 / 背景 / 朋友圈动态」都可以被脚本运行时
   修改。所有带 data-me-avatar / data-me-bg / data-me-name 标记的
   元素，在调用 apply() 后立即同步更新，无需刷新页面。
   ============================================================ */
(() => {
    if (window.__wxConfig) return;

    const me = {
        name: 'd',
        wxid: 'zhaohd',
        avatar: '/images/avatar/IMG_0491_20260903_144508_035.png',
        bg: '/images/bg/cover.jpg',
        signature: '填坑小能手',
        peerAvatar: '/images/header/yehua.jpg',   // 聊天对方默认头像（可由脚本按联系人设置）
        chatBg: '',                                // 聊天页消息区背景（与朋友圈封面 bg 不同；空=默认深色）
    };

    /* 朋友圈动态数据（null = 使用前端硬编码的默认动态） */
    let momentsPosts = null;

    /* ---- 参考图时间轴：按「相对当前时刻」计算，保证录制时出现
       今天(HH:MM) / 昨天(HH:MM) / 上星期日(星期X) 的正确时间标签 ---- */
    const _M = 60000, _H = 3600000;
    function _todayAt(hh, mm) {
        const d = new Date();
        d.setHours(hh, mm, 0, 0);
        const t = d.getTime();
        // 避免录到「未来时刻」：若已超时则退回 2 分钟前
        return t > Date.now() ? Date.now() - 2 * _M : t;
    }
    function _dayAt(offsetDays, hh, mm) {
        const d = new Date();
        d.setDate(d.getDate() - offsetDays);
        d.setHours(hh, mm, 0, 0);
        return d.getTime();
    }
    function _lastSunday() {
        const d = new Date();
        const dow = d.getDay();                  // 0=周日..6=周六
        d.setDate(d.getDate() - (dow === 0 ? 7 : dow));
        d.setHours(12, 0, 0, 0);
        return d.getTime();
    }

    /* ---- 持久化默认：参考图数据（注入即生效，无需依赖工作流） ---- */
    const DEFAULT_HOME = [
        { 'name': '微信支付', 'text': '已支付 ¥11.65', 'avatar': '/images/ref/pay.png',
          'read': false, 'newMsgCount': 9, 'timestamp': _todayAt(18, 22) },
        { 'name': '梓康群', 'text': '下午看得怎么样', 'avatar': '/images/ref/qun.png',
          'quiet': true, 'read': false, 'timestamp': _todayAt(18, 16) },
        { 'name': '陆香儿', 'text': '我也吃饭去了', 'avatar': '/images/ref/luxianger.png',
          'read': false, 'newMsgCount': 1, 'timestamp': _todayAt(18, 16) },
        { 'name': '服务号', 'text': '广东联网售票：已上线！全省客运线路实现 “一…',
          'avatar': '/images/ref/fuwu.png', 'quiet': true, 'read': false, 'timestamp': _todayAt(17, 29) },
        { 'name': '公众号', 'text': '快讯：自动驾驶首次被写入法律',
          'avatar': '/images/ref/gongzhong.png', 'quiet': true, 'read': false, 'timestamp': _todayAt(10, 57) },
        { 'name': '微信团队', 'text': '登录操作通知', 'avatar': '/images/ref/weixin_team.png',
          'read': true, 'timestamp': _todayAt(0, 49) },
        { 'name': '沉默光环', 'text': '拍得', 'avatar': '/images/ref/chenmo.png',
          'read': true, 'timestamp': _dayAt(1, 23, 52) },
        { 'name': 'D', 'text': '给 Cursor 的精准开发提示词（复制即用）# 任…',
          'avatar': '/images/ref/D.png', 'read': true, 'timestamp': _dayAt(1, 22, 28) },
        { 'name': '妍', 'text': '在吗', 'avatar': '/images/ref/yan.png',
          'read': true, 'timestamp': _lastSunday() },
    ];
    const DEFAULT_MOMENTS = [{
        'author': '陆香儿', 'avatar': '/images/ref/luxianger.png',
        'text': '就这么丝滑的下班。',
        'images': ['/images/ref/lux_video.png'],
        // 参考图：配图下方的来源标注（视频号 · xxx），buildPost 会渲染成灰色小字
        'source': '视频号 · 小陆AI搜索推广获客',
        'time': '35分钟前', 'likes': [],
        'comments': [{ 'name': '陆香儿', 'text': '没有保持苹果肌扁平的义务。' }],
    }];

    /* 把「HH:MM」之类的时间字符串解析成当天的数值时间戳（供 fmtDate 使用） */
    /* ---- 时间标注解析：把「时间分隔条」用的时刻字符串换算成时间戳 + 显示文本 ----
       支持：HH:MM[:SS]、昨天 HH:MM、星期X/周X [HH:MM]、M月D日 HH:MM、N分钟/小时/天前、
       纯毫秒时间戳。返回 { ts, text }（text=按标注原样显示），无法识别返回 null。 */
    function fmtHMS(ts) {
        const d = new Date(Number(ts) || Date.now());
        const pad = (n) => (n < 10 ? '0' : '') + n;
        return pad(d.getHours()) + ':' + pad(d.getMinutes());
    }
    function parseTimeSpec(timeStr) {
        const s = String(timeStr || '').trim();
        if (!s) return null;
        if (/^\d{9,}$/.test(s)) return { ts: Number(s), text: fmtHMS(Number(s)) };
        const mk = (daysAgo, hh, mm, ss) => {
            const d = new Date();
            d.setDate(d.getDate() - daysAgo);
            d.setHours(hh, mm, ss || 0, 0);
            return d.getTime();
        };
        let m;
        // 今天 HH:MM[:SS]
        if ((m = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(s))) {
            return { ts: mk(0, Number(m[1]), Number(m[2]), m[3] ? Number(m[3]) : 0), text: s };
        }
        // 昨天 HH:MM[:SS]
        if ((m = /^昨天\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(s))) {
            return { ts: mk(1, Number(m[1]), Number(m[2]), m[3] ? Number(m[3]) : 0), text: s };
        }
        // 星期X / 周X [HH:MM]
        if ((m = /^(?:星期|周)([一二三四五六日天])(?:\s*(\d{1,2}):(\d{2}))?$/.exec(s))) {
            const dowMap = { '日': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '天': 0 };
            let diff = (new Date().getDay() - dowMap[m[1]] + 7) % 7;
            if (diff === 0) diff = 7;   // 不落今天，取上一个星期X
            return { ts: mk(diff, m[2] ? Number(m[2]) : 12, m[3] ? Number(m[3]) : 0, 0), text: s };
        }
        // M月D日 HH:MM
        if ((m = /^(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(s))) {
            const d = new Date();
            d.setMonth(Number(m[1]) - 1, Number(m[2]));
            d.setHours(Number(m[3]), Number(m[4]), m[5] ? Number(m[5]) : 0, 0);
            return { ts: d.getTime(), text: s };
        }
        // N分钟前 / N小时前 / N天前
        if ((m = /^(\d+)\s*分钟前$/.exec(s))) return { ts: Date.now() - Number(m[1]) * 60000, text: s };
        if ((m = /^(\d+)\s*小时前$/.exec(s))) return { ts: Date.now() - Number(m[1]) * 3600000, text: s };
        if ((m = /^(\d+)\s*天前$/.exec(s))) return { ts: Date.now() - Number(m[1]) * 86400000, text: s };
        return null;
    }
    // 向后兼容：只把「HH:MM」换算成当天时间戳（历史库里仍用 time 字段，靠 parseTimeSpec 统一）
    function _timeToDate(timeStr) {
        const p = parseTimeSpec(timeStr);
        return p ? p.ts : (typeof timeStr === 'number' ? timeStr : Date.now());
    }

    /* 拿到 Vue 根实例，便于更新由 vuex store 驱动的列表 */
    function getVm() {
        const root = document.getElementById('app');
        return root && root.__vue__;
    }

    /* 在「微信」主页把当前未读数显示到标题，如 微信 (3)。其它页保持纯净标题。 */
    function updateHeaderCount() {
        try {
            const vm = getVm();
            if (!vm || !vm.$store) return;
            const center = document.querySelector('#wx-header .center');
            if (!center) return;
            let nameSpan = null;
            for (const c of center.childNodes) {
                if (c.nodeType === 3) continue;          // 跳过热文本
                if (c.nodeType === 1 && !c.classList.contains('parentheses') &&
                    !c.classList.contains('peer-typing')) {
                    nameSpan = c;                        // 第一个非角标/非打字提示的 span 即标题
                    break;
                }
            }
            let count = center.querySelector('.wx-header-count');
            if (vm.$route.path === '/') {
                if (!nameSpan) return;
                if (!count) {
                    count = document.createElement('span');
                    count.className = 'wx-header-count';
                    nameSpan.after(count);
                }
                // 用 store 里真实未读总数替代写死的 "99"，让标题「微信 (N)」与实际一致
                const total = Number(vm.$store.state.newMsgCount) || 0;
                count.textContent = total > 0 ? ' (' + total + ')' : '';
            } else if (count) {
                count.remove();
            }
        } catch (e) { /* 标题计数失败不影响其它功能 */ }
    }

    window.__wxConfig = {
        get() { return { me }; },
        setMe(patch) { Object.assign(me, patch); },
        /* 时间标注解析：把「HH:MM / 昨天 HH:MM」等换算成 { ts, text }，给消息时间分隔条用 */
        parseTimeSpec(timeStr) { return parseTimeSpec(timeStr); },

        /* 设置头像：替换所有 data-me-avatar 元素并同步 store 列表 */
        setAvatar(url) {
            me.avatar = url;
            this.apply();
        },

        /* 设置朋友圈封面/背景：替换所有 data-me-bg 元素 */
        setBg(url) {
            me.bg = url;
            this.apply();
        },

        /* 设置聊天页消息区背景（深色蒙层，气泡无需改透明度）。
           空/未设置时回退为默认深色 #101010。与 me.bg（朋友圈封面）相互独立。 */
        setChatBg(url) {
            me.chatBg = url || '';
            this.apply();
        },

        getChatBg() { return me.chatBg; },

        /* 把聊天背景转成可在 CSS 里直接用作 background 的值：
           底层图片 cover 平铺，叠一层深色蒙层，透明/浅色图片也能被压暗到深色主题。 */
        chatBgValue() {
            const u = (me.chatBg || '').trim();
            if (!u) return '#101010';
            return "linear-gradient(rgba(16,16,16,.82), rgba(16,16,16,.82)), url('" + u + "') center / cover no-repeat #101010";
        },

        /* 修改我的昵称 */
        setName(name) {
            this.setMe({ name });
            this.apply();
        },

        /* 修改个性签名 */
        setSignature(signature) {
            this.setMe({ signature });
            this.apply();
        },

        /* 设置聊天对方头像（每条对方消息/图片都用这个头像，保证与列表一致） */
        setPeerAvatar(url) {
            this.setMe({ peerAvatar: url });
            this.apply();
        },

        getPeerAvatar() { return me.peerAvatar; },

        getMomentsPosts() { return momentsPosts; },
        setMomentsPosts(posts) { momentsPosts = posts; },

        /* 按配置重建「微信」主页的会话列表（支持私聊/群聊/未读/免打扰） */
        setHomeList(items) {
            // work清单显式重建主页：立即置位 defaults 标记，阻止 applyPersistentDefaults
            // 在 setHomeList 末尾的 this.apply() 里把刚写入的工作流数据清空、强制回退默认参考主页。
            _defaultsApplied = true;
            const vm = getVm();
            if (!vm || !vm.$store) return false;
            // 每次重建主页都递增渲染代号，让 wechat.vue 的 :key 跟着变，
            // 强制 Vue 重挂载会话行 → msg-item 本地 read 复位，
            // 避免「上上次 read=true / 打开过会话 read=true」的残留把未读角标藏掉。
            const homeGen = (window.__wxHomeGen = (window.__wxHomeGen || 0) + 1);
            const all = Array.isArray(vm.$store.state.allContacts) ? vm.$store.state.allContacts : [];
            const find = (name) => all.find(c => c && (c.nickname === name || c.remark === name));
            const baseMsg = (items || []).map((it, i) => {
                const group = !!it.group;
                const members = group
                    ? (it.members || [it.name || '群成员']).map(m => {
                        // 允许成员直接给对象 { name, avatar }，便于还原群头像九宫格
                        if (m && typeof m === 'object' && m.name) {
                            return { wxid: 'wxid_' + m.name, headerUrl: m.avatar || '/images/header/header01.png',
                                     nickname: m.name, remark: m.name };
                        }
                        return find(m) || { wxid: 'wxid_' + m, headerUrl: '/images/header/header01.png', nickname: m, remark: m };
                    })
                    : [];
                const single = find(it.name) || {
                    wxid: 'wxid_' + (it.name || '朋友'),
                    headerUrl: it.avatar || '/images/header/yehua.jpg',
                    nickname: it.name || '朋友',
                    remark: it.name || '朋友',
                };
                // unread 数字角标 = 该会话消息条数；支持外部指定 newMsgCount 决定角标数字
                const nMsg = Math.max(1, parseInt(it.newMsgCount, 10) || 1);
                const senderName = group ? (it.sender || it.name || '成员') : (it.name || '');
                // 优先用外部编排的 messages 精确还原对话历史（支持 我/对方、文字/图片/语音）；
                // 未提供 messages 时退回旧逻辑：用 lastMsg 复制 nMsg 条。
                let msg = [];
                let unreadCount = 0;   // 我最后一条回复之后，对方发的消息数（未读数）
                if (Array.isArray(it.messages) && it.messages.length) {
                    for (const m of it.messages) {
                        const isMe = m.dir === 'me';
                        const text = m.kind === 'text' ? (m.text || '') :
                            (m.kind === 'image' ? '[图片]' : (m.kind === 'voice' ? '[语音]' : (m.text || '')));
                        const entry = {
                            text: text,
                            image: m.kind === 'image' ? (m.image || '') : '',
                            voice: m.kind === 'voice' ? (parseInt(m.seconds, 10) || 1) : 0,
                            name: isMe ? (me.name || 'd') :
                                (group ? (m.sender || senderName) : senderName),
                            headerUrl: isMe ? (me.avatar || '/images/header/header01.png') :
                                (group ? '/images/header/yehua.jpg' : single.headerUrl),
                        };
                        // 消息显式带 time 才生成时间分隔条（标注了时刻 → 强制显示，时间占位）
                        if (m.time != null && String(m.time).trim() !== '') {
                            const spec = parseTimeSpec(m.time);
                            entry.forceTime = true;             // 标注了时间：不受任何自动规则过滤
                            if (spec) {
                                entry.date = spec.ts;           // 供排序 / 主页列表时间显示
                                entry.timeText = spec.text;     // 分隔条按标注原样显示
                            } else {
                                entry.date = Date.now();        // 无法解析：给个时间戳兜底
                                entry.timeText = String(m.time);
                            }
                        }
                        msg.push(entry);
                    }
                    // 推算未读数：以「我最后一条回复」为界，数其后对方（非我）发的消息条数。
                    // 数据源显式给出 read/unread/newMsgCount 时不在这里覆盖，交由下方 return 分支决定。
                    let lastMe = -1;
                    for (let i = it.messages.length - 1; i >= 0; i--) {
                        if (it.messages[i].dir === 'me') { lastMe = i; break; }
                    }
                    for (let i = lastMe + 1; i < it.messages.length; i++) {
                        if (it.messages[i].dir !== 'me') unreadCount++;
                    }
                } else {
                    const lastMsg = {
                        text: it.text || it.lastText || '',
                        date: it.timestamp || Date.now(),
                        name: senderName,
                        headerUrl: group ? '/images/header/yehua.jpg' : single.headerUrl,
                    };
                    for (let k = 0; k < nMsg; k++) msg.push(Object.assign({}, lastMsg));
                }
                return {
                    mid: 1000 + i,
                    _rk: homeGen,          // 渲染代号：每次重建自增，供 :key 强制重挂载，复位未读角标
                    type: group ? 'group' : 'friend',
                    group_name: group ? it.group : '',
                    read: it.read !== undefined ? !!it.read :
                          (it.unread === undefined ? (unreadCount <= 0) : (Number(it.unread) <= 0)),
                    newMsgCount: it.newMsgCount != null ? it.newMsgCount :
                          (it.unread !== undefined ? (it.unread || 0) : unreadCount),
                    quiet: !!it.quiet,
                    msg: msg,
                    user: group ? members : [single],
                };
            });
            vm.$store.state.msgList.baseMsg = baseMsg;
            // 重算未读总数（标题「微信 (N)」与底部角标）：未读且非免打扰会话按消息条数累加
            let total = 0;
            baseMsg.forEach(it => {
                if (it.read === false && !it.quiet) total += (it.newMsgCount || 1);
            });
            vm.$store.state.newMsgCount = total;
            if (vm.$forceUpdate) vm.$forceUpdate();
            this.apply();
            return true;
        },

        /* 应用一整份场景：我的资料 + 主页会话(含消息历史) + 朋友圈动态，一步到位 */
        applyScene(scene) {
            if (!scene || typeof scene !== 'object') return false;
            if (scene.me) {
                this.setMe({
                    name: scene.me.name || me.name,
                    avatar: scene.me.avatar || me.avatar,
                    signature: scene.me.signature || me.signature,
                    bg: scene.me.bg || me.bg,
                    chatBg: scene.me.chatBg || me.chatBg,
                });
            }
            const okHome = this.setHomeList(Array.isArray(scene.home) ? scene.home : []);
            if (Array.isArray(scene.moments)) momentsPosts = scene.moments;
            this.apply();
            return okHome;
        },

        /* 把当前配置同步到页面（幂等），并同步 vuex store 驱动的列表 */
        apply() {
            /* 聊天背景：写入 --wx-chat-bg，聊天页 .dialogue-section 据此渲染。
               无背景时移除变量，回退到 chat_exact.css 里的默认 #101010。 */
            try {
                const root = document.documentElement;
                if (!root) return;
                const v = this.chatBgValue ? this.chatBgValue() : '#101010';
                if (v === '#101010') root.style.removeProperty('--wx-chat-bg');
                else root.style.setProperty('--wx-chat-bg', v);
            } catch (e) { /* 背景设置失败不影响其它 */ }
            document.querySelectorAll('[data-me-avatar]').forEach(el => {
                el.setAttribute('src', me.avatar);
            });
            document.querySelectorAll('[data-me-bg]').forEach(el => {
                el.style.backgroundImage = "url('" + me.bg + "')";
                // 有封面照片时标记 data-cover="set"，无则 "unset"，CSS 据此决定是否显示「轻触设置相册封面」提示
                el.setAttribute('data-cover', me.bg ? 'set' : 'unset');
            });
            document.querySelectorAll('[data-me-name]').forEach(el => {
                el.textContent = me.name;
            });

            /* 同步 store：主页会话列表 / 通讯录 / 我的资料里的自己 */
            const vm = getVm();
            if (vm && vm.$store) {
                const list = vm.$store.state.msgList && vm.$store.state.msgList.baseMsg;
                if (Array.isArray(list)) {
                    list.forEach(it => {
                        if (it && Array.isArray(it.user)) {
                            it.user.forEach(u => {
                                if (u && u.wxid === me.wxid) {
                                    u.headerUrl = me.avatar;
                                    u.nickname = me.name;
                                    u.remark = me.name;
                                }
                            });
                        }
                    });
                }
                const all = vm.$store.state.allContacts;
                if (Array.isArray(all)) {
                    all.forEach(u => {
                        if (u && u.wxid === me.wxid) {
                            u.headerUrl = me.avatar;
                            u.nickname = me.name;
                            u.remark = me.name;
                            u.signature = me.signature;
                        }
                    });
                }
                if (vm.$forceUpdate) vm.$forceUpdate();
            }
            /* 注册一次路由切页回调，让「微信 (N)」计数随页面切换实时更新 */
            if (vm.$router && !vm.$router.__wxCountHooked) {
                vm.$router.__wxCountHooked = true;
                vm.$router.afterEach(() => { updateHeaderCount(); });
            }
            updateHeaderCount();
        },
    };

    /* ---- 持久化默认：注入后自动应用参考图数据（幂等）----
       让「主页会话列表 / 朋友圈动态 / 我的资料」在每次注入时都呈现参考图，
       不再依赖某个工作流去重建，从而被编辑器或任意流程运行后都保留。 */
    let _defaultsApplied = false;
    function applyPersistentDefaults() {
        if (_defaultsApplied) return;
        const vm = getVm();
        if (!vm || !vm.$store) return;            // Vue 还未就绪，等 apply() 下一次调用再试
        _defaultsApplied = true;                    // 先置位：setHomeList 内部会回调 apply()，避免递归
        momentsPosts = DEFAULT_MOMENTS;
        vm.$store.state.msgList.baseMsg = [];      // 先清空，避免默认列表残留
        window.__wxConfig.setHomeList(DEFAULT_HOME);
    }
    // apply() 会被 Vue 组件在 mounted/路由切换等多处调用，这里逐个入口触发默认应用
    const _origApply = window.__wxConfig.apply.bind(window.__wxConfig);
    window.__wxConfig.apply = function () {
        applyPersistentDefaults();
        return _origApply();
    };
})();