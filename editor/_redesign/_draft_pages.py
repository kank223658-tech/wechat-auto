# -*- coding: utf-8 -*-
"""
scene.html 示意稿补全：通讯录 / 我 两页（同步 2026-09-11 新版真机 UI）
- 通讯录：搜索框 + 新的朋友/群聊/标签/公众号 四宫格入口 + 场景人物按拼音首字母分组 + 底部 Tab(通讯录亮)
- 我：头像/名字/微信号 + 相册/收藏/钱包/卡券/表情/设置 + 底部 Tab(我亮)
所有替换零命中即中止。
"""
import io, sys, re

PATH = r"G:\weixin-auto\editor\scene.html"
src = io.open(PATH, encoding="utf-8").read()
n_total = 0

def rep(old, new, expect=1, tag=""):
    global src, n_total
    n = src.count(old)
    if n != expect:
        print(f"[ABORT] {tag}: expect {expect} hit(s), got {n}")
        sys.exit(1)
    src = src.replace(old, new)
    n_total += n
    print(f"[ok] {tag}: {n} hit")

# 1) camView 注释
rep("let camView = 'list';       // list | moments | peer | peer-moments",
    "let camView = 'list';       // list | moments | peer | peer-moments | contacts | self",
    1, "camView 注释")

# 2) renderPhone 分发：插入 contacts / self 分支
rep("""  } else if (camView === 'peer-moments') {
    html += peerMomentsHtml();
  } else if (selIdx != null && scene.home[selIdx]) {""",
    """  } else if (camView === 'peer-moments') {
    html += peerMomentsHtml();
  } else if (camView === 'contacts') {
    html += contactsViewHtml();
  } else if (camView === 'self') {
    html += selfViewHtml();
  } else if (selIdx != null && scene.home[selIdx]) {""",
    1, "renderPhone 分发")

# 3) Tab 切换：通讯录/我 真正切页
rep("""      if (name === '微信') { camView = 'list'; selIdx = null; }
      else if (name === '发现') { camView = 'moments'; }
      else if (name === '我') { camView = 'moments'; }  // 简化：切朋友圈展示""",
    """      if (name === '微信') { camView = 'list'; selIdx = null; }
      else if (name === '通讯录') { camView = 'contacts'; }
      else if (name === '发现') { camView = 'moments'; }
      else if (name === '我') { camView = 'self'; }""",
    1, "Tab 处理")

# 4) tabbarHtml 支持指定高亮 Tab（默认微信，老调用不变）
rep("function tabbarHtml() {", "function tabbarHtml(activeName) {", 1, "tabbarHtml 签名")
rep("""'<div class="tab' + (t.active ? ' active' : '') + '" data-navtab="' + t.name + '" style="left:'""",
    """'<div class="tab' + (t.name === (activeName || '微信') ? ' active' : '') + '" data-navtab="' + t.name + '" style="left:'""",
    1, "tab 高亮逻辑")

# 5) 新页面渲染函数（插在 lastText 之前）
NEW_FUNCS = r"""/* ===== 通讯录 / 我 两页示意稿（2026-09-11 同步新版真机 UI） ===== */
function wxcIcon(bg, d) {
  return '<span class="wxc-ic" style="background:' + bg + '">' +
    '<svg viewBox="0 0 24 24" width="23" height="23" fill="#fff"><path d="' + d + '"/></svg></span>';
}
function pinyinInitial(name) {
  const m = (name || '').replace(/^\s+/, '').charAt(0) || '#';
  if (/[a-zA-Z]/.test(m)) return m.toUpperCase();
  if (/[\u4e00-\u9fa5]/.test(m)) {
    const anchors = [['阿','A'],['芭','B'],['擦','C'],['搭','D'],['鹅','E'],['发','F'],['噶','G'],['哈','H'],['击','J'],['喀','K'],['垃','L'],['妈','M'],['拿','N'],['哦','O'],['啪','P'],['七','Q'],['然','R'],['撒','S'],['塌','T'],['挖','W'],['昔','X'],['压','Y'],['匝','Z']];
    let cur = '#';
    anchors.forEach(pr => { try { if (m.localeCompare(pr[0], 'zh-Hans-CN') >= 0) cur = pr[1]; } catch (e) {} });
    return cur;
  }
  return '#';
}
function contactsViewHtml() {
  const funcs = [
    { name: '新的朋友', bg: '#dfa540', d: 'M15 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm-9-3V6h2v3h3v2H8v3H6v-3H3V9zm9 3c-3.3 0-8 1.7-8 5v2h16v-2c0-3.3-4.7-5-8-5z' },
    { name: '群聊', bg: '#63b45f', d: 'M16 11a3.2 3.2 0 1 0-3.2-3.2A3.2 3.2 0 0 0 16 11zm-8 0a3.2 3.2 0 1 0-3.2-3.2A3.2 3.2 0 0 0 8 11zm0 2c-2.8 0-7 1.4-7 4.2V19h7v-2a6.6 6.6 0 0 1 2-4.6 10 10 0 0 0-2-.4zm8 0a10 10 0 0 0-2 .4 6.6 6.6 0 0 1 2 4.6v2h7v-1.8c0-2.8-4.2-4.2-7-4.2z' },
    { name: '标签', bg: '#4f94e8', d: 'M21.4 11.6l-9-9A2 2 0 0 0 11 2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 .6 1.4l9 9a2 2 0 0 0 2.8 0l7-7a2 2 0 0 0 0-2.8zM7.5 9A1.5 1.5 0 1 1 9 7.5 1.5 1.5 0 0 1 7.5 9z' },
    { name: '公众号', bg: '#4f94e8', d: 'M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm-1.5 14.5L6 12l1.9-1.9 2.6 2.6 5.6-5.6L18 9z' },
  ];
  let h = '<div class="wx-header"><div class="c">通讯录</div></div>';
  h += searchHtml();
  h += '<div class="wxc-funcs">';
  funcs.forEach((f, i) => {
    h += '<div class="wxc-func" style="top:' + (i * 76) + 'px">' + wxcIcon(f.bg, f.d) +
      '<span class="wxc-flb">' + f.name + '</span></div>';
  });
  h += '</div>';
  /* 联系人 = 场景里的人物（与左侧会话列表同一份场景数据，可点头像换图） */
  const home = scene.home || [];
  const items = home.map((it, i) => ({ nm: it.name || '会话', ava: it.avatar || '/images/avatar/2_20260831_184618_874.jpg', p: 'home[' + i + '].avatar' }));
  items.sort((a, b) => a.nm.localeCompare(b.nm, 'zh-Hans-CN'));
  let lastL = '', y = 0;
  h += '<div class="wxc-list">';
  items.forEach(o => {
    const L = pinyinInitial(o.nm);
    if (L !== lastL) { h += '<div class="wxc-letter" style="top:' + y + 'px">' + L + '</div>'; y += 44; lastL = L; }
    h += '<div class="wxc-row" style="top:' + y + 'px">' + avatarHtml(o.ava, 'ava2', o.p) +
      '<span class="wxc-nm">' + esc(o.nm) + '</span></div>';
    y += 96;
  });
  h += '</div>';
  h += tabbarHtml('通讯录');
  return h;
}
function selfViewHtml() {
  const me = scene.me || {};
  let h = '<div class="wx-header"><div class="c">我</div></div>';
  h += '<div class="wxs-top">' +
    avatarHtml(me.avatar || '/images/avatar/2_20260831_184618_874.jpg', 'wxs-ava', 'me.avatar') +
    '<div class="wxs-name" data-path="me.name">' + esc(me.name || '未命名') + '</div>' +
    '<div class="wxs-wxid">微信号：' + esc(me.wxid || 'weixin') + '</div>' +
    '<span class="wxs-qr"><svg viewBox="0 0 24 24" width="34" height="34" fill="#9a9a9a"><path d="M3 3h8v8H3zm2 2v4h4V5zm10-2h6v6h-6zm2 2v2h2V5zM5 15h6v6H5zm2 2v2h2v-2zm8-2h2v2h-2zm4 0h2v2h-2zm-4 4h2v2h-2zm4 0h2v2h-2z"/></svg></span>' +
    '<span class="wxs-arrow">›</span></div>';
  const g1 = [
    { name: '相册', bg: '#5aa2e8', d: 'M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2zM8.5 13.5l2.5 3 3.5-4.5 4.5 6H5z' },
    { name: '收藏', bg: '#dfa540', d: 'M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.2 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8z' },
    { name: '钱包', bg: '#4f94e8', d: 'M21 7h-1V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-2h1a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1zm-3 10H5V5h13zm-6 6.5A1.5 1.5 0 1 0 10.5 12 1.5 1.5 0 0 0 12 13.5z' },
    { name: '卡券', bg: '#63b45f', d: 'M20 6H4a2 2 0 0 0-2 2v3a2 2 0 0 1 0 2v3a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-3a2 2 0 0 1 0-2V8a2 2 0 0 0-2-2zm-9 9H9v-2h2zm0-4H9V9h2z' },
  ];
  const g2 = [
    { name: '表情', bg: '#dfa540', d: 'M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zM8.5 10a1.5 1.5 0 1 1 1.5-1.5A1.5 1.5 0 0 1 8.5 10zm7 0a1.5 1.5 0 1 1 1.5-1.5A1.5 1.5 0 0 1 15.5 10zM12 18a5.5 5.5 0 0 1-5.2-3.6h10.4A5.5 5.5 0 0 1 12 18z' },
    { name: '设置', bg: '#5aa2e8', d: 'M19.4 13a7.6 7.6 0 0 0 0-2l2.1-1.6a.5.5 0 0 0 .1-.7l-2-3.4a.5.5 0 0 0-.6-.2l-2.5 1a7.7 7.7 0 0 0-1.7-1L14.4 2.4a.5.5 0 0 0-.5-.4h-4a.5.5 0 0 0-.5.4L9 4.9a7.7 7.7 0 0 0-1.7 1l-2.5-1a.5.5 0 0 0-.6.2l-2 3.4a.5.5 0 0 0 .1.7L4.6 11a7.6 7.6 0 0 0 0 2l-2.1 1.6a.5.5 0 0 0-.1.7l2 3.4a.5.5 0 0 0 .6.2l2.5-1a7.7 7.7 0 0 0 1.7 1l.4 2.5a.5.5 0 0 0 .5.4h4a.5.5 0 0 0 .5-.4l.4-2.5a7.7 7.7 0 0 0 1.7-1l2.5 1a.5.5 0 0 0 .6-.2l2-3.4a.5.5 0 0 0-.1-.7zM12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5z' },
  ];
  const cells = (rows, startTop) => {
    let s = '<div class="wxs-cells">';
    rows.forEach((r, i) => {
      s += '<div class="wxs-row" style="top:' + (startTop + i * 96) + 'px">' + wxcIcon(r.bg, r.d) +
        '<span class="wxc-flb">' + r.name + '</span></div>';
    });
    return s + '</div>';
  };
  h += cells(g1, 0);
  h += cells(g2, 96 * 4 + 16);
  h += tabbarHtml('我');
  return h;
}
"""
rep("function lastText(it) {", NEW_FUNCS + "function lastText(it) {", 1, "新页面函数")

# 6) CSS：追加到样式块尾部（</style> 前唯一锚点用 .tab-dot 行后）
NEW_CSS = """
  /* ---- 通讯录 / 我 示意稿（2026-09-11 同步新版真机 UI） ---- */
  .wxc-funcs { position: absolute; left: 0; top: 232px; width: 600px; height: 304px; background: #181818; z-index: 2; }
  .wxc-func { position: absolute; left: 0; width: 600px; height: 76px; background: #181818; }
  .wxc-func::after { content: ""; position: absolute; left: 96px; right: 0; bottom: 0; height: 1px; background: #292929; }
  .wxc-ic { position: absolute; left: 24px; top: 16px; width: 44px; height: 44px; border-radius: 9px; display: flex; align-items: center; justify-content: center; }
  .wxc-flb { position: absolute; left: 96px; top: 50%; transform: translateY(-50%); height: 32px; line-height: 32px; font-size: 25px; color: #d6d6d6; }
  .wxc-list { position: absolute; left: 0; top: 552px; width: 600px; height: 610px; overflow: hidden; background: #181818; z-index: 2; }
  .wxc-letter { position: absolute; left: 0; width: 600px; height: 44px; line-height: 44px; padding-left: 24px; font-size: 20px; color: #686868; background: #181818; box-sizing: border-box; }
  .wxc-row { position: absolute; left: 0; width: 600px; height: 96px; background: #181818; }
  .wxc-row::after { content: ""; position: absolute; left: 106px; right: 0; bottom: 0; height: 1px; background: #292929; }
  .wxc-row img.ava2 { position: absolute; left: 24px; top: 16px; width: 64px; height: 64px; border-radius: 7px; object-fit: cover; background: #2c2c2e; }
  .wxc-row .wxc-nm { position: absolute; left: 106px; top: 50%; transform: translateY(-50%); height: 32px; line-height: 32px; font-size: 25px; color: #d6d6d6; }
  .wxs-top { position: absolute; left: 0; top: 149px; width: 600px; height: 180px; background: #181818; z-index: 2; }
  .wxs-top img.wxs-ava { position: absolute; left: 24px; top: 36px; width: 108px; height: 108px; border-radius: 9px; object-fit: cover; background: #2c2c2e; }
  .wxs-top .wxs-name { position: absolute; left: 152px; top: 46px; height: 40px; line-height: 40px; font-size: 30px; font-weight: 600; color: #d6d6d6; }
  .wxs-top .wxs-wxid { position: absolute; left: 152px; top: 100px; height: 28px; line-height: 28px; font-size: 21px; color: #686868; }
  .wxs-top .wxs-qr { position: absolute; right: 74px; top: 72px; }
  .wxs-top .wxs-arrow { position: absolute; right: 30px; top: 64px; font-size: 36px; color: #555; }
  .wxs-cells { position: absolute; left: 0; top: 361px; width: 600px; height: 800px; background: #181818; z-index: 2; }
  .wxs-row { position: absolute; left: 0; width: 600px; height: 96px; background: #181818; }
  .wxs-row::after { content: ""; position: absolute; left: 96px; right: 0; bottom: 0; height: 1px; background: #292929; }
"""
rep("  .tabbar .tab-dot { position: absolute; left: 82px; top: 12px; width: 13px; height: 13px; border-radius: 50%; background: #fa5151; z-index: 3; }",
    "  .tabbar .tab-dot { position: absolute; left: 82px; top: 12px; width: 13px; height: 13px; border-radius: 50%; background: #fa5151; z-index: 3; }\n" + NEW_CSS,
    1, "CSS 追加")

# 7) 帮助文案同步
rep("通讯录 / 发现（朋友圈）/ 我（朋友圈，简化演示）。",
    "通讯录（场景人物分组）/ 发现（朋友圈）/ 我（个人信息示意）。",
    1, "帮助文案")

io.open(PATH, "w", encoding="utf-8", newline="\n").write(src)
print(f"ALL DONE, {n_total} replacements written")

# 落盘校验（防静默丢编辑）
chk = io.open(PATH, encoding="utf-8").read()
for mark in ["contactsViewHtml", "selfViewHtml", "wxc-funcs", "通讯录'] { camView = 'contacts'"]:
    print(mark, "->", chk.count(mark))
