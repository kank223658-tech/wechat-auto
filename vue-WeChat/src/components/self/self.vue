<template>
  <!--我 组件-->
  <div id="self">
    <div class="weui-tab__content" style="display: block;">
      <div class="weui-cells">
        <router-link to="/self/profile" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img :src="me.avatar" data-me-avatar alt="" class="self-header">
          </div>
          <div class="weui-cell__bd">
            <h4 class="self-nickname" data-me-name>{{ me.name }}</h4>

            <p class="self-wxid">微信号: {{ me.wxid }}</p>
          </div>
          <div class="weui-cell__ft">
            <img src="/images/chat-info-qr.png">
          </div>
        </router-link>
      </div>
      <div class="weui-cells">
        <router-link to="/self/album" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img src="/images/me_more-my-album.png">
          </div>
          <div class="weui-cell__bd">
            <p>相册</p>
          </div>
        </router-link>
        <router-link to="/self/album" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img src="/images/me_more-my-favorites.png">
          </div>
          <div class="weui-cell__bd">
            <p>收藏</p>
          </div>
        </router-link>
        <router-link to="/self/album" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img src="/images/me_more-my-bank-card.png">
          </div>
          <div class="weui-cell__bd">
            <p>钱包</p>
          </div>
        </router-link>
        <router-link to="/self/album" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img src="/images/me_my-card-package-icon.png">
          </div>
          <div class="weui-cell__bd">
            <p>卡券</p>
          </div>
        </router-link>
      </div>
      <div class="weui-cells">
        <router-link to="/self/album" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img src="/images/me_more-expression.png">
          </div>
          <div class="weui-cell__bd">
            <p>表情</p>
          </div>
        </router-link>
      </div>
      <div class="weui-cells">
        <router-link to="/self/settings" class="weui-cell weui-cell_access">
          <div class="weui-cell__hd">
            <img src="/images/me_more-setting.png">
          </div>
          <div class="weui-cell__bd">
            <p>设置</p>
          </div>
        </router-link>
      </div>
    </div>
  </div>
</template>
<script>
  export default {
    mixins: [window.mixin],
    computed: {
      me() {
        const cfg = (window.__wxConfig && window.__wxConfig.get()) || {}
        return cfg.me || { name: '阿荡', wxid: 'zhaohd', avatar: '/images/header/header01.png' }
      }
    },
    data() {
      return {
        "pageName": "我"
      }
    },
    mounted() {
      this.$store.commit("toggleTipsStatus", -1)
      if (window.__wxConfig) window.__wxConfig.apply()
    },
    activated() {
      this.$store.commit("toggleTipsStatus", -1)
    }
  }
</script>
<style lang="less">
  @import "../../assets/less/self.less";
</style>