<template>
    <div class="dialogue">
        <header id="wx-header">
            <div class="other">
                <router-link :to="{path:'/wechat/dialogue/dialogue-info',query: { msgInfo: msgInfo}}" tag="span"
                    class="iconfont icon-chat-group" v-show="$route.query.group_num&&$route.query.group_num!=1">
                </router-link>
                <router-link :to="{path:'/wechat/dialogue/dialogue-detail',query: { msgInfo: msgInfo}}" tag="span"
                    class="iconfont icon-chat-friends" v-show="$route.query.group_num==1"></router-link>
            </div>
            <div class="center">
                <router-link to="/" tag="div" class="iconfont icon-return-arrow">
                    <span>微信</span>
                </router-link>
                <span>{{pageName}}</span>
                <span class="parentheses"
                    v-show='$route.query.group_num&&$route.query.group_num!=1'>{{$route.query.group_num}}</span>
            </div>
        </header>
        <section class="dialogue-section clearfix" v-on:click="MenuOutsideClick">
            <template v-for="(item,index) in msgInfo.msg">
                <div class="msg-time" v-if="showTime(index, item)" :key="'t'+index">{{dividerText(item)}}</div>
                <!-- 系统提示（撤回/群公告等）：无头像的居中灰字条 -->
                <div class="msg-system" v-else-if="item.system" :key="'s'+index">{{item.system}}</div>
                <div class="row clearfix" v-else :class="{self: isSelf(item.name)}" :key="index">
                    <img :src="item.headerUrl" class="header">
                    <p class="text msg-image" v-if="item.image"><img :src="item.image"></p>
                    <p class="text msg-emoji" v-else-if="item.emoji"><img :src="item.emoji"></p>
                    <p class="text msg-voice" v-else-if="item.voice" v-html="voiceBars(item.voice)"></p>
                    <!-- 转账卡片：内层 HTML 由 chat_extra.js 的 transferCardHtml 生成
                         （与运行时 DOM 直插版结构/配色/金额字号规则一致） -->
                    <p class="text msg-transfer" v-else-if="item.transfer" v-html="transferHtml(item.transfer)"></p>
                    <p class="text msg-link" v-else-if="item.link">
                        <span class="lk-inner">
                            <span class="lk-title">{{item.link.title}}</span>
                            <span class="lk-source"><svg class="lk-ico" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4"/><path d="M12 11v10"/></svg><span class="lk-name">{{item.link.source}}</span></span>
                        </span>
                        <span class="lk-img" v-if="item.link.image"><img :src="item.link.image"></span>
                        <span class="lk-img lk-img-empty" v-else></span>
                    </p>
                    <p class="text" v-else v-more>{{item.text}}</p>
                </div>
            </template>
            <span class="msg-more" id="msg-more">
                <ul>
                    <li>复制</li>
                    <li>转发</li>
                    <li>收藏</li>
                    <li>删除</li>
                </ul>
            </span>
        </section>
        <footer class="dialogue-footer">
            <div class="component-dialogue-bar-person">
                <span class="iconfont icon-dialogue-jianpan" v-show="!currentChatWay"
                    v-on:click="currentChatWay=true"></span>
                <span class="iconfont icon-dialogue-voice" v-show="currentChatWay"
                    v-on:click="currentChatWay=false"></span>
                <div class="chat-way" v-show="!currentChatWay">
                    <div class="chat-say" v-press>
                        <span class="one">按住 说话</span>
                        <span class="two">松开 结束</span>
                    </div>
                </div>
                <div class="chat-way" v-show="currentChatWay">
                    <textarea class="chat-txt" rows="1" v-on:focus="focusIpt" v-on:blur="blurIpt"></textarea>
                </div>
                <span class="expression iconfont icon-dialogue-smile"></span>
                <span class="more iconfont icon-dialogue-jia"></span>
                <div class="recording" style="display: none;" id="recording">
                    <div class="recording-voice" style="display: none;" id="recording-voice">
                        <div class="voice-inner">
                            <div class="voice-icon"></div>
                            <div class="voice-volume">
                                <span></span>
                                <span></span>
                                <span></span>
                                <span></span>
                                <span></span>
                                <span></span>
                                <span></span>
                                <span></span>
                                <span></span>
                            </div>
                        </div>
                        <p>手指上划,取消发送</p>
                    </div>
                    <div class="recording-cancel" style="display: none;">
                        <div class="cancel-inner"></div>
                        <p>松开手指,取消发送</p>
                    </div>
                </div>
            </div>
        </footer>
    </div>
</template>
<script>
    export default {
        data() {
            return {
                pageName: this.$route.query.name,
                currentChatWay: true, //ture为键盘打字 false为语音输入
                timer: null
                // sayActive: false // false 键盘打字 true 语音输入
            }
        },
        beforeRouteEnter(to, from, next) {
            next(vm => {
                vm.$store.commit("setPageName", vm.$route.query.name)
            })
        },
        mounted() {
            // 聊天页像素级覆盖（chat_exact.css）作用域标记：进入聊天页时挂到 body
            document.body.classList.add('wx-chat');
            // 注入聊天页专属结构：未读胶囊 / 三点悬浮胶囊 / 输入框麦克风 / 状态栏定位图标
            try {
                if (window.__wxChatPage) window.__wxChatPage.mount();
            } catch (e) { /* 忽略 */ }
            // 低电量红条 + 定位图标（参考图状态）
            try {
                const pf = window.__wxPhoneFrame;
                if (pf) { pf.setBattery(3); pf.setBatteryLow(true); pf.setLeftIcon('loc'); }
            } catch (e) { /* 忽略 */ }
            // 进入聊天页立即滚到底部：后台追加的消息在会话底部，若不先滚，要等
            // Python 侧 open_chat 在转场动画（.34s）结束后的 _scroll_chat_bottom 才滚，
            // 结果就是「点进去时消息在底部看不到、转场后几帧才出现」（成片里像在加载）。
            // 这里在组件挂载（内容已 v-for 渲染、滑入动画刚开始）就滚到底，
            // 让最新消息随页面滑入即已可见。未满（不可滚动）时 __wxSmoothScrollBottom
            // 会贴顶，不影响短会话。
            try {
                const scrollToBottom = () => {
                    const sec = document.querySelector('.dialogue-section');
                    if (sec && window.__wxSmoothScrollBottom) window.__wxSmoothScrollBottom(sec);
                };
                scrollToBottom();
                // nextTick + 短延时各补一次：等图片/贴纸异步撑开高度后仍停在底部，
                // 避免「初始按未撑开高度滚动、图片加载后底部又被顶下去」。
                this.$nextTick(scrollToBottom);
                setTimeout(scrollToBottom, 120);
            } catch (e) { /* 忽略 */ }
        },
        beforeDestroy() {
            // 摘掉聊天页专属注入结构（右侧三点胶囊），避免返回主页后残留
            const pill = document.getElementById('chat-right-pill');
            if (pill) pill.remove();
            // 延后到下一帧再摘掉 wx-chat：保证整段离场动画期间聊天页仍保持精修样式，
            // 不会被回退成未精修布局或让贴纸失去尺寸约束（产生巨大笑脸）。
            requestAnimationFrame(() => document.body.classList.remove('wx-chat'));
        },
        computed: {
            msgInfo() {
                for (var i in this.$store.state.msgList.baseMsg) {
                    if (this.$store.state.msgList.baseMsg[i].mid == this.$route.query.mid) {
                        return this.$store.state.msgList.baseMsg[i]
                    }
                }
                return {}
            }
        },
        directives: {
            press: {
                inserted(element) {
                    var recording = document.querySelector('.recording'),
                        recordingVoice = document.querySelector('.recording-voice'),
                        recordingCancel = document.querySelector('.recording-cancel'),
                        // startTx,
                        startTy

                    element.addEventListener('touchstart', function (e) {
                        // 用bind时，vue还没插入到dom,故dom获取为 undefine，用 inserted 代替 bind,也可以开个0秒的定时器
                        element.className = "chat-say say-active"
                        recording.style.display = recordingVoice.style.display = "block"
                        var touches = e.touches[0]
                        // startTx = touches.clientX
                        startTy = touches.clientY
                        e.preventDefault()
                    }, false)
                    element.addEventListener('touchend', function (e) {
                        /*var touches = e.changedTouches[0];
                        var distanceY = startTy - touches.clientY;
                        if (distanceY > 50) {
                            console.log("取消发送信息");
                        }else{
                            console.log("发送信息");
                        }*/

                        element.className = "chat-say"
                        recordingCancel.style.display = recording.style.display = recordingVoice.style.display = "none"
                        e.preventDefault()
                    }, false)
                    element.addEventListener('touchmove', function (e) {
                        var touches = e.changedTouches[0],
                            // endTx = touches.clientX,
                            endTy = touches.clientY,
                            // distanceX = startTx - endTx,
                            distanceY = startTy - endTy;

                        if (distanceY > 50) {
                            element.className = "chat-say"
                            recordingVoice.style.display = "none"
                            recordingCancel.style.display = "block"
                        } else {
                            element.className = "chat-say say-active"
                            recordingVoice.style.display = "block"
                            recordingCancel.style.display = "none"
                        }
                        // 阻断事件冒泡 防止页面被一同向上滑动
                        e.preventDefault()
                    }, false);
                }
            },
            more: {
                bind(element) {
                    var startTx, startTy
                    element.addEventListener('touchstart', function (e) {
                        var msgMore = document.getElementById('msg-more'),
                            touches = e.touches[0];
                        startTx = touches.clientX
                        startTy = touches.clientY

                        clearTimeout(this.timer)
                        this.timer = setTimeout(() => {
                            // 控制菜单的位置
                            msgMore.style.left = ((startTx - 18) > 180 ? 180 : (startTx - 18)) + 'px'
                            msgMore.style.top = (element.offsetTop - 33) + 'px'
                            msgMore.style.display = "block"
                            element.style.backgroundColor = '#e5e5e5'
                        }, 500)

                    }, false)
                    element.addEventListener('touchmove', function (e) {
                        var touches = e.changedTouches[0],
                            disY = touches.clientY;
                        if (Math.abs(disY - startTy) > 10) {
                            clearTimeout(this.timer)
                        }
                    }, false)
                    element.addEventListener('touchend', function () {
                        clearTimeout(this.timer)
                    }, false)
                }
            }
        },
        methods: {
            // 判断该消息是否是「我」发的：按名字与配置里的我的昵称比较，决定气泡靠右(绿色)
            isSelf(name) {
                let meName = 'd';
                try {
                    const cfg = window.__wxConfig && window.__wxConfig.get();
                    if (cfg && cfg.me && cfg.me.name) meName = cfg.me.name;
                } catch (e) { /* 忽略 */ }
                return name === meName;
            },
            // 生成语音气泡的波形 HTML（秒数决定波形长短）
            voiceBars(secs) {
                const s = parseInt(secs, 10) || 1;
                const n = Math.max(4, Math.min(14, Math.round(s * 2.2)));
                let bars = '';
                for (let i = 0; i < n; i++) {
                    const h = 6 + Math.round(Math.abs(Math.sin(i * 1.7)) * 10) + 2;
                    bars += '<i style="height:' + h + 'px"></i>';
                }
                return '<span class="voice-wave">' + bars + '</span><span class="voice-dur">' + s + '"</span>';
            },
            // 转账卡片内层 HTML：委托给注入的 chat_extra.js（含 HTML 转义防注入）；
            // 未注入时回退为纯文字占位，避免白卡
            transferHtml(t) {
                if (window.__wxChatExt && window.__wxChatExt.transferCardHtml) {
                    return window.__wxChatExt.transferCardHtml(t);
                }
                const o = t || {};
                return '<span class="tf-main"><span class="tf-body">' +
                    '<span class="tf-amount"><span class="rmb">¥</span>' +
                    '<span class="amt">' + (o.amount || '1.00') + '</span></span>' +
                    '<span class="tf-title"></span></span></span>' +
                    '<span class="tf-badge">转账</span>';
            },
            // 时间分隔条：只有「标注了时间」（forceTime）的消息才显示，其它一律不出。
            // 之前「首条带时间 / 距上一条超过 5 分钟」的自动规则已按需求移除，
            // 改为完全由脚本/场景里的时间标注控制（时间占位）。
            showTime(index, item) {
                return !!(item && item.forceTime);
            },
            // 分隔条文字：优先按标注原样显示（timeText），否则用时间戳格式化为 HH:MM
            dividerText(item) {
                if (item && item.timeText) return item.timeText;
                return this.formatTime(item && item.date);
            },
            // 时间分隔条：把消息时间戳格式化为 HH:MM（仅无标注时的兜底）
            formatTime(date) {
                const d = new Date(Number(date) || Date.now());
                const pad = (n) => (n < 10 ? '0' : '') + n;
                return pad(d.getHours()) + ':' + pad(d.getMinutes());
            },
            // 解决输入法被激活时 底部输入框被遮住问题
            // 注：本项目用注入式手机键盘覆盖层模拟输入，输入框不会被系统输入法遮住；
            //    原实现的 document.body.scrollTop = scrollHeight 会把整个 #app 往上顶约 210px
            //    （overflow:hidden 无法阻止程序化滚动），导致“弹出把消息/页面顶上顶、收起错乱”。
            //    这里不再滚动 body。保留 blurIpt 结构以维持 focus/blur 配对。
            focusIpt() {
                this.timer = setInterval(function () {
                    // 不滚动：聊天页是固定 600×1300 画布，本就不该滚。
                }, 100)
            },
            blurIpt() {
                clearInterval(this.timer)
            },
            // 点击空白区域，菜单被隐藏
            MenuOutsideClick(e) {
                var container = document.querySelectorAll('.text'),
                    msgMore = document.getElementById('msg-more')
                if (e.target.className !== 'text') {
                    msgMore.style.display = 'none'
                    container.forEach(item => item.style.backgroundColor = '#fff')
                }
            }
        }
    }
</script>
<style lang="less">
    @import "../../assets/less/dialogue.less";

    .say-active {
        background: #c6c7ca;
    }
</style>