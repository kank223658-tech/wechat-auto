<template>
    <!--消息列表组件 数据交互频繁-->
    <!--进入 dialogue 页面，携带参数 mid name group_num -->
    <li :class="{'item-hide':deleteMsg}">
        <!--自定义指令 v-swiper 用于对每个消息进行滑动处理-->
        <router-link
            :to="{ path: '/wechat/dialogue', query: { mid: item.mid,name:item.group_name||(item.user[0].remark||item.user[0].nickname),group_num:item.user.length}}"
            tag="div" class="list-info" v-swiper v-on:click.native="toggleMsgRead($event,'enter')">
            <div class="header-box">
                <!--未读并且未屏蔽 才显示新信息数量-->
                <i class="new-msg-count" v-show="!item.read&&!item.quiet">{{item.newMsgCount || item.msg.length}}</i>
                <!--未读并且屏蔽 只显示小红点-->
                <i class="new-msg-dot" v-show="!item.read&&item.quiet"></i>
                <!--如果是私聊，只显示一个头像； 如果是群聊，则显示多个头像，flex 控制样式-->
                <div class="header" :class="[item.type=='group'?'multi-header':'']">
                    <img v-for="(userInfo,index) in item.user" :key="index" :src="userInfo.headerUrl">
                </div>
            </div>
            <div class="desc-box">
                <!--使用过滤器 fmtDate 格式化时间-->
                <div class="desc-time">{{item.msg[item.msg.length-1].date | fmtDate('hh:mm')}}</div>
                <div class="desc-author" v-if="item.type=='group'">{{item.group_name}}</div>
                <!--如果没有备注好友，则显示微信昵称-->
                <div class="desc-author" v-else>{{item.user[0].remark||item.user[0].nickname}}</div>
                <div class="desc-msg">
                    <div class="desc-mute iconfont icon-mute" v-show="item.quiet">
                    </div>
                    <span v-show="item.type=='group'">{{item.msg[item.msg.length-1].name}}:</span>
                    <span>{{item.msg[item.msg.length-1].text}}</span>
                </div>
            </div>
        </router-link>
        <div class="operate-box">
            <div class="operate-unread" v-if="item.read" v-on:click="toggleMsgRead">标为未读</div>
            <div class="operate-read" v-else v-on:click="toggleMsgRead">标为已读</div>
            <div class="operate-del" v-on:click="deleteMsgEvent">删除</div>
        </div>
    </li>
</template>
<script>
    export default {
        props: ["item"],
        data() {
            return {
                deleteMsg: false
            }
        },
        methods: {
            //切换消息未读/已读状态
            toggleMsgRead(event, status) {
                if (status === 'enter') {
                    if (this.item.read) {
                        return ''
                    }
                    this.item.read = true
                    // 进入会话即视为已读：清零本会话未读角标（newMsgCount）。
                    // 否则「对方后台发消息」会在历史未读数上继续 +1，
                    // 把整段历史会话的未读一起算进去（角标 = 历史 + 后台，而非仅后台条数）。
                    this.item.newMsgCount = 0
                } else {
                    this.item.read = !this.item.read
                    // 「标为未读」：给一个至少 1 的未读数，避免 newMsgCount 为 0 时
                    // 角标回退到 item.msg.length（整段历史）而再次把历史全算进去。
                    if (!this.item.read && !Number(this.item.newMsgCount)) this.item.newMsgCount = 1
                }
                // 按列表重算全局未读总数（标题「微信 (N)」与底部「微信」角标），
                // 与 main.py 注入的 recomputeNewMsgCount 同一口径，避免 ±1 与真实未读数不符。
                const base = (this.$store.state.msgList && this.$store.state.msgList.baseMsg) || []
                let total = 0
                base.forEach(it => {
                    if (it && it.read === false && !it.quiet) total += (Number(it.newMsgCount) || 1)
                })
                this.$store.state.newMsgCount = total

                event.target.parentNode.parentNode.firstChild.style.marginLeft = 0 + "px"
            },
            deleteMsgEvent() {
                this.deleteMsg = true
                if (!this.item.quiet) {
                    if (!this.item.read) {
                        this.$store.commit('minusNewMsg')
                    }
                }
            }
        },
        // 参考 https://vuefe.cn/v2/guide/custom-directive.html
        directives: {
            swiper: {
                bind: function (element) {
                    var isTouchMove, startTx, startTy
                    element.addEventListener('touchstart', function (e) {
                        var touches = e.touches[0]
                        startTx = touches.clientX
                        startTy = touches.clientY
                        isTouchMove = false;
                    });
                    element.addEventListener('touchmove', function (e) {
                        e.preventDefault();
                        var touches = e.changedTouches[0],
                            endTx = touches.clientX,
                            endTy = touches.clientY,
                            distanceX = startTx - endTx,
                            distanceY = startTy - endTy;
                        if (distanceX < 0) { //右滑
                            if (Math.abs(distanceX) >= Math.abs(distanceY)) {
                                if (Math.abs(distanceX) > 20) {
                                    element.style.transition = "0.3s"
                                    element.style.marginLeft = 0 + "px"
                                }
                            }
                        } else { //左滑
                            if (Math.abs(distanceX) >= Math.abs(distanceY)) {
                                if (distanceX < 156 && distanceX > 20) {
                                    element.style.transition = "0s"
                                    element.style.marginLeft = -distanceX + "px"
                                    isTouchMove = true
                                }
                            }
                        }
                    }, { passive: false });
                    element.addEventListener('touchend', function (e) {
                        if (!isTouchMove) {
                            return;
                        }
                        var touches = e.changedTouches[0],
                            endTx = touches.clientX,
                            endTy = touches.clientY,
                            distanceX = startTx - endTx,
                            distanceY = startTy - endTy
                        // isSwipe = false
                        if (Math.abs(distanceX) >= Math.abs(distanceY)) {
                            if (distanceX < 0) {
                                return;
                            }
                            if (Math.abs(distanceX) < 60) {
                                // isSwipe = true
                                element.style.transition = "0.3s"
                                element.style.marginLeft = 0 + "px"
                            } else {
                                element.style.transition = "0.3s"
                                element.style.marginLeft = "-156px"
                            }
                        }
                    });
                }
            }
        }
    }
</script>