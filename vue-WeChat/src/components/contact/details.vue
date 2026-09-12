<template>
    <div class="profile">
        <header id="wx-header">
            <div class="center">
                <router-link to="/contact" tag="div" class="iconfont icon-return-arrow">
                    <span>通讯录</span>
                </router-link>
                <span>详细资料</span>
            </div>
        </header>
        <div class="weui-cells">
            <div class="weui-cell">
                <div class="weui-cell__hd"><img :src="userInfo.headerUrl" alt="" class="self-header" style="width:60px">
                </div>
                <div class="weui-cell__bd">
                    <h4 class="self-nickname">{{userInfo.nickname}}<span class="gender"
                            :class="[userInfo.sex===1?'gender-male':'gender-female']"></span></h4>
                    <p class="self-wxid" style="font-size: 13px;color: #999;">微信号: <span class="privacy-blur">{{userInfo.wxid}}</span></p>
                    <p class="nickname" style="font-size: 13px;color: #999;">昵称:{{userInfo.nickname||'无'}}</p>
                </div>
            </div>
        </div>
        <div class="weui-cells">
            <div class="weui-cell weui-cell_access">
                <div class="weui-cell__bd">
                    <p>设置备注和标签</p>
                </div>
                <div class="weui-cell__ft">

                </div>
            </div>
        </div>
        <div class="weui-cells">
            <div class="weui-cell">
                <div class="weui-cell__bd">
                    <p>地区</p>
                </div>
                <div class="weui-cell__ft" style="flex: 4;text-align: left;">
                    <span v-for="(item,index) in userInfo.area" :key="index"><span class="privacy-blur">{{item}}</span>&nbsp;&nbsp;&nbsp;</span>
                </div>
            </div>
            <div class="weui-cell weui-cell_access">
                <div class="weui-cell__bd">
                    <p>个人相册</p>
                </div>
                <div class="weui-cell__ft" style="flex: 4;text-align: left;">
                    <div class="album-list">
                        <img :src="item.imgSrc" style="width:50px;margin:0 5px" :key="index"
                            v-for="(item,index) in userInfo.album">
                    </div>
                </div>
            </div>
            <div class="weui-cell weui-cell_access">
                <div class="weui-cell__bd">
                    <p>更多</p>
                </div>
                <div class="weui-cell__ft">

                </div>
            </div>
        </div>

        <a href="javascript:;" class="weui-btn weui-btn_primary" style="width:90%;margin-top:20px;">发消息</a>
        <a href="javascript:;" class="weui-btn weui-btn_default" style="width:90%">视频</a>

    </div>
</template>
<script>
    import contact from "../../vuex/contacts"
    export default {
        data() {
            return {
                pageName: ""
            }
        },
        computed: {
            userInfo() {
                // 场景联系人优先：setContacts 写入 vuex allContacts（scene.json 数据），
                // 旧版 contacts.js 仅作兜底（现已清空）
                const wxid = this.$route.query.wxid
                const all = (this.$store && this.$store.state.allContacts) || []
                for (var i = 0; i < all.length; i++) {
                    if (all[i] && all[i].wxid === wxid) return all[i]
                }
                return contact.getUserInfo(wxid)
            }
        }
    }
</script>
<style>
    /* 隐私信息保护：微信号 / 地区 做高斯模糊，录制经过资料页时画面里自动不可辨认，无需后期剪辑 */
    .privacy-blur {
        display: inline-block;
        filter: blur(8px);
        user-select: none;
        -webkit-user-select: none;
        pointer-events: none;
    }
</style>