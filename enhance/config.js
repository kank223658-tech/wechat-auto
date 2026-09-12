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
        bg: '/images/peer/peer_cover.jpg',
        signature: '填坑小能手',
        peerAvatar: '/images/avatar/2_20260831_184618_874.jpg',   // 聊天对方默认头像（可由脚本按联系人设置）
        chatBg: '',                                // 聊天页消息区背景（与朋友圈封面 bg 不同；空=默认深色）
        emojiLib: [],                              // 我方表情包库（main.py 离线解析时注入的 /images/... 路径）
    };

    /* 朋友圈动态数据（null = 使用前端硬编码的默认动态） */
    let momentsPosts = null;

    /* 对方（朋友圈主人）资料 + 对方朋友圈动态。
       由「打开个人主页 / 进入对方朋友圈」动作驱动，可被场景/脚本整体替换。 */
    let peerData = null;

    /* ---- 通讯录首字母：与场景编辑器示意稿同一套锚点表（zh locale 比较）----
       保证真机通讯录分组和编辑器里看到的完全一致 */
    function _pyInitial(name) {
        const m = (name || '').replace(/^\s+/, '').charAt(0) || '#';
        if (/[a-zA-Z]/.test(m)) return m.toUpperCase();
        if (/[\u4e00-\u9fa5]/.test(m)) {
            const anchors = [['阿','A'],['芭','B'],['擦','C'],['搭','D'],['鹅','E'],['发','F'],['噶','G'],['哈','H'],['击','J'],['喀','K'],['垃','L'],['妈','M'],['拿','N'],['哦','O'],['啪','P'],['七','Q'],['然','R'],['撒','S'],['塌','T'],['挖','W'],['昔','X'],['压','Y'],['匝','Z']];
            let cur = '#';
            anchors.forEach(pr => { try { if (m.localeCompare(pr[0], 'zh-Hans-CN') >= 0) cur = pr[1]; } catch (e) {} });
            return cur;
        }
        return '#';
    }

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

    /* ---- 身份随机生成：按名字稳定哈希 → 每人固定一套「女性 8 位微信号 + 大城市地区」----
       同一个人每次生成结果一致（跨天/跨会话不跳变），不同人互相独立。
       用于：setContacts 的场景联系人、对方主页（peer）默认人设。 */
    const _CITY_POOL = [
        ['广东', '深圳'], ['浙江', '杭州'], ['上海', '上海'], ['四川', '成都'],
        ['广东', '广州'], ['江苏', '南京'], ['湖北', '武汉'], ['重庆', '重庆'],
        ['陕西', '西安'], ['天津', '天津'], ['北京', '北京'], ['福建', '厦门'],
    ];
    const _FEMALE_PRE = ['xiao', 'tang', 'meng', 'qi', 'nuo', 'anqi', 'xike', 'wantang', 'su', 'moli',
                         'yanran', 'rou', 'nini', 'yaya', 'yuki', 'chenxi', 'ximan', 'yuqi', 'shanshan', 'keai'];
    const _FEMALE_NUM = ['0520', '520', '1314', '6688', '0721', '1024', '666', '888', '0913', '222',
                         '7788', '1121', '0308', '921', '1225'];

    function _hashName(name) {
        const s = String(name || '');
        let h = 5381;
        for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
        return h;
    }

    /* 女性风格 8 位微信号：字母开头、总长恰好 8 位（如 qiqi0520） */
    function genFemaleWxid(name) {
        const h = _hashName(name);
        let pre = _FEMALE_PRE[h % _FEMALE_PRE.length];
        if (pre.length > 5) pre = pre.slice(0, 5);
        const num = _FEMALE_NUM[(h >>> 7) % _FEMALE_NUM.length];
        let id = (pre + num).slice(0, 8);
        while (id.length < 8) id += String((h + id.length) % 10);
        return id;
    }

    /* 大城市地区：返回 [省, 市]（联系人用数组，peer 显示时 join(' ')） */
    function genCityArea(name) {
        const h = _hashName(name);
        return _CITY_POOL[(h >>> 3) % _CITY_POOL.length].slice();
    }

    /* 对方主页默认人设：不再内置任何硬编码旧人物（吴遂卿/餐车集装箱等已清理）。
       身份取场景主页第一个真人（非群聊），微信号/地区按名字随机生成。 */
    function _sceneFirstName() {
        const s = window.__wxDefaultScene;
        if (s && Array.isArray(s.home)) {
            for (let i = 0; i < s.home.length; i++) {
                const it = s.home[i];
                if (it && it.type !== 'group' && (it.name || it.nickname)) return it.name || it.nickname;
            }
        }
        return '';
    }
    function genPeerDefaults() {
        const name = _sceneFirstName() || '微信好友';
        return {
            name: name,
            wxid: genFemaleWxid(name),
            area: genCityArea(name).join(' '),
            gender: 0,
            avatar: '/images/avatar/2_20260831_184618_874.jpg',
            signature: '',
            cover: '/images/peer/peer_cover.jpg',
            momentsThumbs: [],
            video: null,
            posts: [],
        };
    }

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

    /* ---- 状态栏时钟同步：与开场锁屏时钟对齐 ----
       取「历史会话」里最后一次出现的时间标注（time 字段，按真实时刻取最大，
       解析规则同 parseTimeSpec，也和 准备制作界面/build_intro_config.py 的
       last_history_clock 一致），同步到手机状态栏，保证开场动画 → 主视频
       的时间逻辑连贯。整个场景没有任何时间标注时默认 00:00。
       仅当场景显式带 messages（真实脚本数据）时才同步：默认参考主页
       （applyPersistentDefaults）没有 messages，保持 18:36 的参考复刻不动。 */
    function syncStatusBarClock(homeItems) {
        let best = null;
        (homeItems || []).forEach(it => {
            const msgs = it && Array.isArray(it.messages) ? it.messages : [];
            msgs.forEach(m => {
                if (!m || m.time == null || String(m.time).trim() === '') return;
                const spec = parseTimeSpec(m.time);
                if (spec && (best === null || spec.ts > best)) best = spec.ts;
            });
        });
        let clock;
        if (best === null) {
            clock = '00:00';
        } else {
            const d = new Date(best);
            const pad = (n) => (n < 10 ? '0' : '') + n;
            clock = pad(d.getHours()) + ':' + pad(d.getMinutes());
        }
        if (window.__wxPhoneFrame && window.__wxPhoneFrame.setTime) {
            window.__wxPhoneFrame.setTime(clock);
        }
        return clock;
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
        get() { return { me, peer: peerData, peerPresets: {} }; },
        setMe(patch) { Object.assign(me, patch); },

        /* 对方资料：整体替换（null = 回到默认）或局部合并 */
        getPeer() { return peerData || genPeerDefaults(); },
        setPeer(data) {
            if (data == null) {
                peerData = null;
                return;
            }
            if (typeof data === 'string') {
                /* 预设名一律由 main.py 按 peer_presets.json 解析后再传入；
                   浏览器内不再内置任何预设，未知名字静默忽略 */
                return;
            }
            if (typeof data === 'object') {
                peerData = Object.assign({}, peerData || genPeerDefaults(), data);
                if (data.posts) peerData.posts = data.posts;
                if (data.momentsThumbs) peerData.momentsThumbs = data.momentsThumbs;
                if (data.video !== undefined) peerData.video = data.video;
            }
        },
        getPeerPresets() { return {}; },
        /* 表情包库：main.py 离线解析时注入我方发表情的表情图路径列表（去重）。 */
        setEmojiLib(lib) { me.emojiLib = Array.isArray(lib) ? lib : []; },
        getEmojiLib() { return me.emojiLib || []; },
        /* 时间标注解析：把「HH:MM / 昨天 HH:MM」等换算成 { ts, text }，给消息时间分隔条用 */
        parseTimeSpec(timeStr) { return parseTimeSpec(timeStr); },

        /* 把历史会话最后时刻同步到状态栏时钟（也可由编辑器/脚本手动触发） */
        syncStatusBarClock(homeItems) { return syncStatusBarClock(homeItems); },

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
                            return { wxid: 'wxid_' + m.name, headerUrl: m.avatar || '/images/avatar/2_20260831_184618_874.jpg',
                                     nickname: m.name, remark: m.name };
                        }
                        return find(m) || { wxid: 'wxid_' + m, headerUrl: '/images/avatar/2_20260831_184618_874.jpg', nickname: m, remark: m };
                    })
                    : [];
                const single = find(it.name) || {
                    wxid: 'wxid_' + (it.name || '朋友'),
                    headerUrl: it.avatar || '/images/avatar/2_20260831_184618_874.jpg',
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
                            (m.kind === 'image' ? '[图片]' :
                            (m.kind === 'voice' ? '[语音]' :
                            (m.kind === 'link' ? '[链接]' :
                            (m.kind === 'emoji' ? '[表情]' : (m.text || '')))));
                        const entry = {
                            text: text,
                            image: m.kind === 'image' ? (m.image || '') : '',
                            emoji: m.kind === 'emoji' ? (m.image || '') : '',
                            voice: m.kind === 'voice' ? (parseInt(m.seconds, 10) || 1) : 0,
                            link: m.kind === 'link' ? (() => {
                                const _img = (m.image || '').trim();
                                // 短名（不带 / 或 http）按链接卡片缩略图目录约定补前缀，
                                // 避免 `src="男生.jpg"` 这类相对路径在前端解析失败（破图）。
                                const _linkImg = (_img && !_img.startsWith('/') && !/^https?:/i.test(_img))
                                    ? '/images/link/' + _img : _img;
                                return {
                                    title: (m.title || m.text || ''),
                                    image: _linkImg,
                                    source: (m.source || '恋爱技巧'),
                                };
                            })() : null,
                            name: isMe ? (me.name || 'd') :
                                (group ? (m.sender || senderName) : senderName),
                            headerUrl: isMe ? (me.avatar || '/images/avatar/2_20260831_184618_874.jpg') :
                                (group ? '/images/avatar/2_20260831_184618_874.jpg' : single.headerUrl),
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
                        headerUrl: group ? '/images/avatar/2_20260831_184618_874.jpg' : single.headerUrl,
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
            // 历史会话带 messages（真实脚本数据）时，把最后时刻同步到状态栏时钟；
            // 默认参考主页（无 messages 字段）不同步，保留 18:36 复刻。
            if ((items || []).some(it => it && Array.isArray(it.messages))) {
                syncStatusBarClock(items);
            }
            if (vm.$forceUpdate) vm.$forceUpdate();
            this.apply();
            return true;
        },

        /* 重建通讯录：items = [{name, avatar, remark?, wxid?, signature?}]。
           直接替换 vuex allContacts（getter 会按 initial 自动分组排序），
           字段结构与模板 contacts.js 保持一致，保证详情页不缺数据。 */
        setContacts(items) {
            const vm = getVm();
            if (!vm || !vm.$store || !vm.$store.state) return false;
            const seen = {};
            const out = [];
            (items || []).forEach(it => {
                if (!it) return;
                const nm = it.name || it.nickname || '';
                if (!nm || seen[nm]) return;
                seen[nm] = 1;
                out.push({
                    /* 每个场景联系人自动生成稳定的「女性 8 位微信号 + 大城市地区」，
                       同名恒定、跨会话不跳变；场景显式给了 wxid/area 则尊重场景 */
                    wxid: it.wxid || genFemaleWxid(nm),
                    initial: _pyInitial(nm),
                    headerUrl: it.avatar || it.headerUrl || '/images/avatar/2_20260831_184618_874.jpg',
                    nickname: nm,
                    remark: it.remark || '',
                    sex: it.sex !== undefined ? it.sex : 0,
                    signature: it.signature || '',
                    telphone: '',
                    album: [],
                    area: genCityArea(nm),
                });
            });
            if (!out.length) return false;
            vm.$store.state.allContacts = out;
            if (vm.$forceUpdate) vm.$forceUpdate();
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
            /* 通讯录同步：显式 scene.contacts 优先；否则用主页会话里的人物
               （与场景编辑器示意稿同一份数据，群聊不算个人联系人）。
               没有任何场景人物时保留模板通讯录，避免出现空页。 */
            if (Array.isArray(scene.contacts)) {
                this.setContacts(scene.contacts);
                _sceneContactsApplied = true;
            } else if (Array.isArray(scene.home) && scene.home.length) {
                /* 注意不透传 home[].remark：编辑器旧数据里 remark 可能是历史模板名
                   （微信支付/服务号…），而通讯录行优先显示 remark，会把真名盖掉 */
                this.setContacts(scene.home
                    .filter(it => it && it.type !== 'group' && (it.name || it.nickname))
                    .map(it => ({ name: it.name || it.nickname, avatar: it.avatar || it.headerUrl })));
                _sceneContactsApplied = true;
            }
            if (Array.isArray(scene.moments)) momentsPosts = scene.moments;
            /* setPeer 只改数据；主页/朋友圈已打开时用 __wxPeer.apply 立即重绘，
               否则场景编辑器实时预览（和运行中 [应用场景]）会一直显示旧人物 */
            const peerApply = (data) => {
                if (data && window.__wxPeer && typeof window.__wxPeer.apply === 'function') {
                    window.__wxPeer.apply(data);
                } else {
                    this.setPeer(data);
                }
            };
            if (scene.peer !== undefined) peerApply(scene.peer);
            else if (Array.isArray(scene.peers) && scene.peers.length) {
                /* 新格式 scene.peers[]（多人物 × 多方案）：[应用场景] 取第一个人物的当前方案 */
                const pp = scene.peers[0];
                const plans = pp && typeof pp.plans === 'object' && !Array.isArray(pp.plans) ? pp.plans : {};
                const plan = (pp && plans[pp.activePlan]) || Object.values(plans)[0];
                if (plan) peerApply(plan);
            }
            if (scene.peerPreset) peerApply(scene.peerPreset);
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
    let _sceneContactsApplied = false;        // 场景通讯录已应用 → 默认名单不再覆盖
    function applyPersistentDefaults() {
        if (_defaultsApplied) return;
        const vm = getVm();
        if (!vm || !vm.$store) return;            // Vue 还未就绪，等 apply() 下一次调用再试
        _defaultsApplied = true;                    // 先置位：setHomeList 内部会回调 apply()，避免递归
        const s = window.__wxDefaultScene;
        if (s && (Array.isArray(s.home) || Array.isArray(s.moments) || s.me || s.peer)) {
            /* 默认界面 = 场景编辑器的 scene.json（main.py 注入 __wxDefaultScene）：
               主页会话 / 通讯录 / 朋友圈 / 对方人设全部来自场景，旧参考数据已清理。
               之后工作流显式 [应用场景] 仍会按其数据覆盖，语义不变。 */
            window.__wxConfig.applyScene(s);
        } else {
            /* 没有 scene.json 时的最小兜底：空主页，等场景/工作流填充 */
            momentsPosts = [];
            peerData = null;
            window.__wxConfig.setHomeList([]);
        }
    }
    // apply() 会被 Vue 组件在 mounted/路由切换等多处调用，这里逐个入口触发默认应用
    const _origApply = window.__wxConfig.apply.bind(window.__wxConfig);
    window.__wxConfig.apply = function () {
        applyPersistentDefaults();
        return _origApply();
    };
})();