/* ============================================================
 * enhance/_embed_boot.js —— 浏览器内「注入层引导」
 *
 * 作用：在**不启动 playwright** 的情况下，把 main.py inject_overlays() 注入的
 *      同一套 enhance 资源按**完全相同的顺序**注入当前页面。
 *      这样任何页面都能同源 iframe 真实前端（vue-WeChat dev server），得到与
 *      成片逐像素同源的画面 —— 用于编辑器里的「实时预览」。
 *
 * 顺序必须与 main.py::inject_overlays() 保持一致（见该函数注释）：
 *   1) 先隐藏欢迎页
 *   2) 基础皮肤 CSS（字体 / 手机框 / 现代皮肤 / 各业务 UI）
 *   3) 业务 JS（配置 / 聊天 / 朋友圈 / 手机框 / 表情 / 转账 / 朋友圈页 / 埋点）
 *   4) 后置 CSS（像素级精确覆盖：聊天 / 面板 / 图标 / 朋友圈 / 发现）
 *   5) 画布修复（600×1300 固定画布 + 转场闪帧修复）
 *
 * 刻意**不注入**的资源（编辑器预览不需要，体积/耗时极大）：
 *   pinyin_data.js（12MB 词库）、keyboard.js（89KB 键盘覆盖层）、rime WASM 引擎、
 *   page.evaluate 形式的内联 ENHANCE_JS / panel_switch.js / human_actions.js。
 *   需要键盘 / 三面板动画时仍请走真机画面（main.py --editmode）。
 * ============================================================ */
(function () {
  if (window.__wxEmbedBooted) return;
  window.__wxEmbedBooted = true;

  var E = '/enhance/';

  // 1) 欢迎页永久隐藏（与 main.py 一致：不要用 .remove()，Vue 会重建）
  // 2) 顺手关掉 webpack-dev-server 的错误浮层「吃点击」：
  //    它是 document 级全屏 iframe（z-index 顶格、pointer-events:auto），
  //    即使没报错、不显示，也照样把预览里的所有鼠标点击吞掉（实测：
  //    编辑器内点会话行毫无反应，而 elementFromPoint 命中的就是它）。
  //    只关指针事件、不隐藏 —— 真报错时错误信息仍然看得见。
  var BOOT_CSS = [
    '.welcome { display: none !important; }',
    '#webpack-dev-server-client-overlay { pointer-events: none !important; }'
  ];

  // 2) 基础皮肤（顺序敏感）
  var CSS_BASE = [
    'harmony_font.css',
    'keyboard.css',
    'iphone_frame.css',
    'weui_tokens.css',
    'wechat_modern.css',
    'human_actions.css',
    'transfer_ui.css',
    'transfer_detail.css',
    'send_image_ui.css',
    'peer_pages.css',
    'block_ui.css',
    'video_player.css',
    'homepage_exact.css'
  ];

  // 3) 业务 JS（顺序敏感：后一个依赖前一个的全局）
  var JS_ORDER = [
    'config.js',
    'chat_extra.js',
    'moments_extra.js',
    'iphone_frame.js',
    'wxemoji_map.js',
    'emoji_map.js',
    'transfer_ui.js',
    'transfer_detail.js',
    'send_image_ui.js',
    'video_player.js',
    'peer_pages.js',
    'block_ui.js',
    'homepage.js'
  ];

  // 4) 后置皮肤：必须在上面 JS 运行完（它们会插入自己的 <style>）之后再追加，
  //    否则会被 JS 运行时插入的样式反压 —— 这是 main.py 里反复强调的顺序契约。
  var CSS_POST = [
    'chat_exact.css',
    'panel_switch.css',
    'wx_icons.css',
    'moments_exact.css',
    'discover_exact.css'
  ];

  // 5) 画布修复：600×1300 固定画布 + 转场「缩左/黑边」闪帧修复（照搬 main.py）
  var CSS_CANVAS = [
    'html, body { height: 100% !important; overflow: clip !important;' +
      ' contain: paint !important; width: 600px !important; max-width: 600px !important; }' +
      '#app { overflow: clip !important; position: relative !important;' +
      ' contain: paint !important;' +
      ' width: 600px !important; max-width: 600px !important;' +
      ' height: 100% !important; min-height: 100% !important; }',
    '.outter.hideLeft { transform: none !important;' +
      ' opacity: 1 !important; transition: opacity .3s ease !important; }',
    '.dialogue-footer { position: absolute !important; left: 0 !important;' +
      ' right: 0 !important; width: 100% !important; }'
  ];

  function addStyle(text) {
    var s = document.createElement('style');
    s.textContent = text;
    (document.head || document.documentElement).appendChild(s);
    return s;
  }

  function getText(name) {
    return fetch(E + name, { cache: 'force-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error(name + ' HTTP ' + r.status);
        return r.text();
      });
  }

  function addScript(name) {
    return getText(name).then(function (code) {
      return new Promise(function (resolve) {
        var el = document.createElement('script');
        el.textContent = code;
        el.onerror = function () { resolve(false); };
        document.body.appendChild(el);
        resolve(true);
      });
    }).catch(function (e) {
      console.warn('[embed] 跳过 ' + name + '：' + e.message);
      return false;
    });
  }

  function addStyleFile(name) {
    return getText(name).then(function (t) { addStyle(t); })
      .catch(function (e) { console.warn('[embed] 跳过 ' + name + '：' + e.message); });
  }

  function seq(list, fn) {
    return list.reduce(function (p, name) {
      return p.then(function () { return fn(name); });
    }, Promise.resolve());
  }

  // 等 vue 挂载：轮询直到 #app 出现且有子节点
  function whenMounted() {
    return new Promise(function (resolve) {
      var t0 = Date.now();
      (function poll() {
        var app = document.getElementById('app');
        if ((app && app.children.length) || Date.now() - t0 > 15000) return resolve();
        setTimeout(poll, 50);
      })();
    });
  }

  window.__wxEmbedReady = false;
  window.__wxEmbedErrors = [];

  BOOT_CSS.forEach(addStyle);

  whenMounted()
    .then(function () { return seq(CSS_BASE, addStyleFile); })
    .then(function () {
      window.__wxDebugAgent = false;
      return seq(JS_ORDER, addScript);
    })
    .then(function () { return seq(CSS_POST, addStyleFile); })
    .then(function () { CSS_CANVAS.forEach(addStyle); })
    .then(function () {
      window.__wxEmbedReady = true;
      document.documentElement.setAttribute('data-wx-embed', 'ready');
    })
    .catch(function (e) {
      window.__wxEmbedErrors.push(String(e));
      console.error('[embed] 注入失败', e);
      document.documentElement.setAttribute('data-wx-embed', 'error');
    });
})();
