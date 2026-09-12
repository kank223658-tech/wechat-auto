<template>
<!--可复用的相册组件 这里只完成静态页面 不涉及数据-->
    <div class="album">
        <header id="wx-header">
            <div class="center">
                <router-link to="/self" tag="div" class="iconfont icon-return-arrow">
                    <span>我</span>
                </router-link>
                <span>相册</span>
            </div>
        </header>
        <div class="home-pic">
            <div class="home-pic-base">
                <div class="top-pic">
                    <div class="top-pic-inner">
                        <img :src="meInfo.avatar">
                    </div>
                </div>
                <div class="top-name _ellipsis">{{ meInfo.name }}</div>
            </div>
            <p class="sign">{{ meInfo.signature }}</p>
        </div>
        <section class="album-box clearfix" v-if="!meInfo.name">
            <div class="post-content">
                <div class="thumb-desc">暂无相册内容</div>
            </div>
        </section>
    </div>
</template>
<script>
    export default {
        computed: {
            // 姓名/头像/签名从注入配置读取（scene.json 场景数据），不再硬编码上游演示内容
            meInfo() {
                const cfg = (window.__wxConfig && window.__wxConfig.get()) || {}
                const me = cfg.me || {}
                return {
                    name: me.name || '',
                    avatar: me.avatar || '/images/avatar/2_20260831_184618_874.jpg',
                    signature: me.signature || ''
                }
            }
        }
    }
</script>
<style lang="less">
    @import "../../assets/less/album.less";
</style>