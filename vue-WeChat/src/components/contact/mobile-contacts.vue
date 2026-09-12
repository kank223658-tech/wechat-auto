<template>
    <!--手机联系人组件：数据来自 vuex allContacts（scene.json 场景人物），
        不再硬编码上游演示人物（白浅/夜华/三国人物等已移除）-->
    <div :class="{'search-open-contact':!$store.state.headerStatus}">
    <header id="wx-header">
            <div class="center">
                <router-link to="/contact/new-friends" tag="div" class="iconfont icon-return-arrow">
                    <span>新的朋友</span>
                </router-link>
                <span>通讯录朋友</span>
            </div>
        </header>
        <!--这里的 search 组件的样式也需要修改一下-->
        <search></search>
        <section>
            <div v-for="letter in letters" :key="'g-' + letter">
                <div class="weui-cells__title">{{ letter }}</div>
                <div class="weui-cells">
                    <div class="weui-cell weui-cell_access" v-for="c in grouped[letter]" :key="c.wxid">
                        <div class="weui-cell__hd"><img :src="c.headerUrl" class="home__mini-avatar___1nSrW"></div>
                        <div class="weui-cell__bd">
                            {{ c.remark || c.nickname }}
                        </div>
                    </div>
                </div>
            </div>
        </section>
    </div>
</template>
<script>
    import search from "../common/search"
    export default {
        mixins: [window.mixin],
        components: {
            search
        },
        computed: {
            letters() {
                return (this.$store && this.$store.getters.contactsInitialList) || []
            },
            grouped() {
                return (this.$store && this.$store.getters.contactsList) || {}
            }
        },
        data() {
            return {
                pageName: "通讯录朋友"
            }
        }
    }
</script>
