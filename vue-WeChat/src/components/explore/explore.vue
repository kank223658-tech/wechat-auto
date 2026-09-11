<template>
  <!--发现组件（像素级复刻深色发现页，规格见 enhance/discover_exact.css）
      图标一律使用参考图原图裁剪（vue-WeChat/public/images/disc/），不手绘-->
  <div id="explore">
    <div class="disc-groups">

      <div class="disc-group">
        <router-link to="/explore/moments" class="disc-cell" tag="div"
          data-wx-action="moments" v-on:click.native="momentNewMsg=false">
          <span class="disc-ic"><img src="/images/disc/ic_moments.png" alt=""></span>
          <span class="disc-label">朋友圈</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </router-link>
      </div>

      <div class="disc-group">
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_channels.png" alt=""></span>
          <span class="disc-label">视频号</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_live.png" alt=""></span>
          <span class="disc-label">直播</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
      </div>

      <div class="disc-group">
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_scan.png" alt=""></span>
          <span class="disc-label">扫一扫</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_listen.png" alt=""></span>
          <span class="disc-label">听一听</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
      </div>

      <div class="disc-group">
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_look.png" alt=""></span>
          <span class="disc-label">看一看</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_search.png" alt=""></span>
          <span class="disc-label">搜一搜</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
      </div>

      <div class="disc-group">
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_nearby.png" alt=""></span>
          <span class="disc-label">附近的人</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
      </div>

      <div class="disc-group">
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_game.png" alt=""></span>
          <span class="disc-label">游戏</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
        <div class="disc-cell">
          <span class="disc-ic"><img src="/images/disc/ic_miniapp.png" alt=""></span>
          <span class="disc-label">小程序</span>
          <span class="disc-arrow"><img src="/images/disc/arrow.png" alt=""></span>
        </div>
      </div>

    </div>

    <!-- 状态栏外卖胶囊（参考图：送货中 21:07送达），仅发现页显示 -->
    <div id="wx-delivery-pill" aria-hidden="true">
      <span class="dp-left">
        <span class="dp-emoji"><img src="/images/disc/scooter.png" alt=""></span>
        <span class="dp-txt">送货中</span>
      </span>
      <span class="dp-right"><b>21:07</b><i>送达</i></span>
    </div>
  </div>
</template>
<script>
  export default {
    mixins: [window.mixin],
    data() {
      return {
        pageName: "发现",
        momentNewMsg: true
      }
    },
    activated() {
      this.$store.commit("toggleTipsStatus", -1);
      // 胶囊克隆到 body 下：#app 有 contain:paint 形成层叠上下文，
      // 固定定位的胶囊会被不透明的状态栏(#ios-statusbar, z 2147483646)盖住
      const src = this.$el ? this.$el.querySelector('#wx-delivery-pill') : null;
      if (src && !document.getElementById('wx-delivery-pill-clone')) {
        const clone = src.cloneNode(true);
        clone.id = 'wx-delivery-pill-clone';
        document.body.appendChild(clone);
      }
      // 发现页专属深色皮肤（状态栏/导航/底部Tab）由 body.wx-on-explore 驱动
      document.body.classList.add("wx-on-explore");
    },
    deactivated() {
      document.body.classList.remove("wx-on-explore");
    }
  }
</script>
<style lang="less">
  @import "../../assets/less/explore.less";
</style>
<style>
  /* 旧版小图标/角标细节保留（moments 入口角标等仍可能用到） */
  #explore .wx-ic { display: inline-block; vertical-align: middle; }
  #explore .wx-sub { color: #8e8e93; font-size: 14px; margin-right: 6px; vertical-align: middle; }
  #explore .wx-heart { color: #fa5151; font-size: 13px; }
  #explore .weui-cell__ft { display: flex; align-items: center; }
</style>
