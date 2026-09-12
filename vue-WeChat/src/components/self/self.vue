<template>
  <!--我 组件（像素级复刻：参考图片/我界面.jpg，规格见 enhance/self_exact.css）-->
  <div id="self">
    <!--头像区：头像/名字/微信号/二维码箭头/扫一扫/状态-->
    <router-link to="/self/profile" class="self-profile" data-me-block>
      <img :src="me.avatar" data-me-avatar alt="" class="self-header">
      <h4 class="self-nickname" data-me-name>{{ me.name }}</h4>
      <p class="self-wxid">微信号：{{ me.wxid }}</p>
    </router-link>
    <router-link to="/self/my-qrcode" class="self-scan"><img src="/images/replica/self_scan.png" alt=""></router-link>
    <div class="self-status-pills"><img src="/images/replica/self_pills.png" alt="+状态"></div>

    <!--分组1：服务-->
    <router-link to="/self/album" class="self-row row-0">
      <img class="self-row-ic" src="/images/replica/self_row0.png" alt="">
      <span class="self-row-txt">服务</span>
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>

    <!--行分隔线-->
    <i class="self-sep sep-0"></i>
    <i class="self-sep sep-1"></i>
    <i class="self-sep sep-2"></i>
    <i class="self-sep sep-3"></i>

    <!--分组间隙（原图裁切贴图）-->
    <img class="self-gap gap-0" src="/images/replica/self_gap.png" alt="">

    <!--分组2：收藏/朋友圈/作品/卡包/表情-->
    <router-link to="/self/album" class="self-row row-1">
      <img class="self-row-ic" src="/images/replica/self_row1.png" alt="">
      <span class="self-row-txt">收藏</span>
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>
    <router-link to="/explore" class="self-row row-2">
      <img class="self-row-ic" src="/images/replica/self_row2.png" alt="">
      <span class="self-row-txt">朋友圈</span>
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>
    <router-link to="/self/album" class="self-row row-3">
      <img class="self-row-ic" src="/images/replica/self_row3.png" alt="">
      <span class="self-row-txt">作品</span>
      <span class="self-row-hint">添加第 1 个作品</span>
      <img class="self-row-dot" src="/images/replica/reddot.png" alt="">
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>
    <router-link to="/self/album" class="self-row row-4">
      <img class="self-row-ic" src="/images/replica/self_row4.png" alt="">
      <span class="self-row-txt">卡包</span>
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>
    <router-link to="/self/album" class="self-row row-5">
      <img class="self-row-ic" src="/images/replica/self_row5.png" alt="">
      <span class="self-row-txt">表情</span>
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>

    <!--分组间隙2-->
    <img class="self-gap gap-1" src="/images/replica/self_gap2.png" alt="">

    <!--分组3：设置-->
    <router-link to="/self/settings" class="self-row row-6">
      <img class="self-row-ic" src="/images/replica/self_row6.png" alt="">
      <span class="self-row-txt">设置</span>
      <img class="self-row-arrow" src="/images/replica/chevron.png" alt="">
    </router-link>
  </div>
</template>
<script>
  export default {
    mixins: [window.mixin],
    computed: {
      me() {
        const cfg = (window.__wxConfig && window.__wxConfig.get()) || {}
        return cfg.me || { name: '微信用户', wxid: 'wx_user', avatar: '/images/avatar/2_20260831_184618_874.jpg' }
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
      // 「我」页专属深色皮肤（无标题栏/状态栏 #191919/像素级行布局）由 body.wx-on-self 驱动
      document.body.classList.add("wx-on-self");
    },
    deactivated() {
      document.body.classList.remove("wx-on-self");
    }
  }
</script>
<style lang="less">
  @import "../../assets/less/self.less";
</style>
