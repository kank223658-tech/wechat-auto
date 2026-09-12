<template>
    <div id="contact">
        <section>
            <div class="weui-cells_contact-head weui-cells weui-cells_access" style="margin-top:-1px">
                <router-link to="/contact/new-friends" class="weui-cell">
                    <div class="weui-cell_hd"> <img class="img-obj-cover"
                            src="/images/replica/contact_fn_new_friends.png"> </div>
                    <div class="weui-cell_bd weui-cell_primary">
                        <p>新的朋友</p>
                    </div>
                </router-link>
                <router-link to="/contact/group-list" class="weui-cell">
                    <div class="weui-cell_hd"> <img class="img-obj-cover"
                            src="/images/replica/contact_fn_groups.png"> </div>
                    <div class="weui-cell_bd weui-cell_primary">
                        <p>群聊</p>
                    </div>
                </router-link>
                <router-link to="/contact/tags" class="weui-cell">
                    <div class="weui-cell_hd"> <img class="img-obj-cover"
                            src="/images/replica/contact_fn_tags.png">
                    </div>
                    <div class="weui-cell_bd weui-cell_primary">
                        <p>标签</p>
                    </div>
                </router-link>
                <router-link to="/contact/official-accounts" class="weui-cell">
                    <div class="weui-cell_hd"><img class="img-obj-cover"
                            src="/images/replica/contact_fn_official.png"></div>
                    <div class="weui-cell_bd weui-cell_primary">
                        <p>公众号</p>
                    </div>
                </router-link>
                <router-link to="/contact/official-accounts" class="weui-cell">
                    <div class="weui-cell_hd"><img class="img-obj-cover"
                            src="/images/replica/contact_fn_service.png"></div>
                    <div class="weui-cell_bd weui-cell_primary">
                        <p>服务号</p>
                    </div>
                </router-link>
                <router-link to="/contact/new-friends" class="weui-cell">
                    <div class="weui-cell_hd"><img class="img-obj-cover"
                            src="/images/replica/contact_fn_wework.png"></div>
                    <div class="weui-cell_bd weui-cell_primary">
                        <p>企业微信联系人</p>
                    </div>
                </router-link>
            </div>
            <!--联系人集合-->
            <template v-for="(value,key) in contactsList">
                <!--首字母-->
                <div :ref="`key_${key}`" :key="key" class="weui-cells__title">{{key}}</div>
                <div class="weui-cells" :key="key+1">
                    <router-link :key="item.wxid" :to="{path:'/contact/details',query:{wxid:item.wxid}}"
                        class="weui-cell weui-cell_access" v-for="item in value" tag="div">
                        <div class="weui-cell__hd">
                            <img :src="item.headerUrl" class="home__mini-avatar___1nSrW">
                        </div>
                        <div class="weui-cell__bd">
                            {{item.remark?item.remark:item.nickname}}
                        </div>
                    </router-link>
                </div>
            </template>
        </section>
        <!--检索-->
        <div class="initial-bar"><span @click="toPs(i)" :key="i+1" v-for="i in contactsInitialList">{{i}}</span></div>
    </div>
</template>
<script>
    export default {
        mixins: [window.mixin],
        data() {
            return {
                "pageName": "通讯录"
            }
        },
        mounted() {
            // mutations.js中有介绍
            this.$store.commit("toggleTipsStatus", -1)
        },
        activated() {
            this.$store.commit("toggleTipsStatus", -1)
            // 通讯录专属深色皮肤（#191919 底/像素级行布局/字母索引）由 body.wx-on-contact 驱动
            document.body.classList.add("wx-on-contact");
        },
        deactivated() {
            document.body.classList.remove("wx-on-contact");
        },
        computed: {
            contactsInitialList() {
                return this.$store.getters.contactsInitialList
            },
            contactsList() {
                return this.$store.getters.contactsList
            }
        },
        methods: {
            toPs(i) {
                window.scrollTo(0, this.$refs['key_' + i][0].offsetTop)
            }
        }
    }
</script>
<style lang="less">
    @import "../../assets/less/contact.less";
</style>
