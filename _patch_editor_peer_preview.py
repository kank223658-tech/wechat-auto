# -*- coding: utf-8 -*-
# 编辑器对方主页预览对齐真机（scene.html）：
#   1) 预览 HTML 结构与 enhance/peer_pages.js 一致：昵称行/半角冒号/备注文案/性别徽章条件显示
#   2) 主页「朋友圈」展示框联动 posts（与真机同优先级），编辑动态配图时主页框实时跟着变
#   3) 编辑器预览关闭隐私模糊（body.wx-peer-no-blur），昵称/微信号看得清
#   4) 点「对方主页」面板 tab 自动把手机画面切到对方主页预览
#   5) 基本资料补「昵称行」编辑字段；「昵称」标签正名为「名字」
import io

P = r'editor\scene.html'
s = io.open(P, encoding='utf-8').read()
n0 = len(s)

# ---------- 1) 展示框取图助手（插在 peerThumbImgs 后面） ----------
old = """/* 解析对方动态里的视频：字符串 或 {src, cover}；无则 null。"""
new = """/* 主页「朋友圈」展示框取图：与运行端 enhance/peer_pages.js 同一套优先级，
   保证编辑器预览 = 成品：① 本人物 posts 的配图/视频封面 ② scene.moments 同名 author 的图 ③ momentsThumbs 兜底 */
function peerProfileThumbs(p) {
  const out = [];
  const push = (s) => { s = String(s || ''); if (s && out.indexOf(s) < 0) out.push(s); };
  (p.posts || []).forEach((post) => {
    const v = peerPostVideo(post);
    if (v && v.cover) push(v.cover);
    (post.images || []).forEach(push);
  });
  if (!out.length && p.name) {
    (scene.moments || []).forEach((m) => {
      if (String(m.author || '') === p.name) (m.images || []).forEach(push);
    });
  }
  return out;
}
/* 解析对方动态里的视频：字符串 或 {src, cover}；无则 null。"""
assert old in s and 'peerProfileThumbs' not in s
s = s.replace(old, new, 1)

# ---------- 2) peerProfileHtml 对齐真机 ----------
old = """  let h = '<div class="wx-peer-page open">' +
    '<div class="wpp-nav"><span class="wpp-back" data-nav="peer-back"></span>' +
    '<span class="wpp-more"><i></i><i></i><i></i></span></div>' +
    '<div class="wpp-scroll">' +
      '<div class="wpp-head">' +
        '<img class="wpp-avatar" data-path="' + B + '.avatar" src="' + esc(p.avatar || '') + '" onerror="onImgErr(this)" alt="">' +
        '<div class="wpp-meta">' +
          '<div class="wpp-name"><span class="wpp-name-t" data-path="' + B + '.name">' + esc(p.name || '') + '</span>' +
          '<i class="wpp-gender ' + gcls + '"></i></div>' +
          '<div class="wpp-wxid" data-path="' + B + '.wxid">微信号：' + esc(p.wxid || '') + '</div>' +
          '<div class="wpp-area" data-path="' + B + '.area">地区：' + esc(p.area || '') + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="wpp-group"><div class="wpp-cell wpp-friend-cell">' +
        '<div class="wpp-cell-main"><div class="wpp-cell-title">朋友资料</div>' +
        '<div class="wpp-cell-desc">添加朋友的备注名、电话、标签、备忘、照片等，并设置朋友权限。</div></div>' +
        '<span class="wpp-arrow"></span></div></div>' +
      '<div class="wpp-group"><div class="wpp-cell wpp-moments-cell" data-nav="peer-moments">' +
        '<div class="wpp-cell-title wpp-title-fixed">朋友圈</div>' +
        '<div class="wpp-thumbs">' + peerThumbImgs(p.momentsThumbs, B + '.momentsThumbs', 5) + '</div>' +
        '<span class="wpp-arrow"></span></div></div>';"""
new = """  const genderHtml = (Number(p.gender) === 1 || Number(p.gender) === 2)
    ? '<i class="wpp-gender ' + gcls + '"></i>' : '';
  /* 展示框：动态配图联动（同真机）；没配动态时退回 momentsThumbs（可点选改） */
  const linkedThumbs = peerProfileThumbs(p);
  const thumbsHtml = linkedThumbs.length
    ? linkedThumbs.slice(0, 5).map((t) =>
        '<img src="' + esc(t) + '" onerror="onImgErr(this)" title="来自朋友圈动态配图，改动态配图即自动更新" alt="">').join('')
    : peerThumbImgs(p.momentsThumbs, B + '.momentsThumbs', 5);
  let h = '<div class="wx-peer-page open">' +
    '<div class="wpp-nav"><span class="wpp-back" data-nav="peer-back"></span>' +
    '<span class="wpp-more"><i></i><i></i><i></i></span></div>' +
    '<div class="wpp-scroll">' +
      '<div class="wpp-head">' +
        '<img class="wpp-avatar" data-path="' + B + '.avatar" src="' + esc(p.avatar || '') + '" onerror="onImgErr(this)" alt="">' +
        '<div class="wpp-meta">' +
          '<div class="wpp-name"><span class="wpp-name-t" data-path="' + B + '.name">' + esc(p.name || '') + '</span>' +
          genderHtml + '</div>' +
          (p.nickname ? '<div class="wpp-nick" data-path="' + B + '.nickname">昵称:' + esc(p.nickname) + '</div>' : '') +
          '<div class="wpp-wxid" data-path="' + B + '.wxid">微信号:' + esc(p.wxid || '') + '</div>' +
          '<div class="wpp-area" data-path="' + B + '.area">地区:' + esc(p.area || '') + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="wpp-group"><div class="wpp-cell wpp-friend-cell">' +
        '<div class="wpp-cell-main"><div class="wpp-cell-title">朋友资料</div>' +
        '<div class="wpp-cell-desc">添加朋友的备注名、电话、标签、备注、照片等，并设置朋友权限。</div></div>' +
        '<span class="wpp-arrow"></span></div></div>' +
      '<div class="wpp-group"><div class="wpp-cell wpp-moments-cell" data-nav="peer-moments">' +
        '<div class="wpp-cell-title wpp-title-fixed">朋友圈</div>' +
        '<div class="wpp-thumbs">' + thumbsHtml + '</div>' +
        '<span class="wpp-arrow"></span></div></div>';"""
assert old in s, 'peerProfileHtml 原文不匹配'
s = s.replace(old, new, 1)

# ---------- 3) 预览关闭隐私模糊 ----------
old = """function renderPhone() {
  const inner = $('phoneInner');"""
new = """function renderPhone() {
  /* 编辑器预览不是录制端：关掉真机的隐私模糊，昵称/微信号要看得清才好编辑 */
  document.body.classList.add('wx-peer-no-blur');
  const inner = $('phoneInner');"""
assert old in s
s = s.replace(old, new, 1)

# ---------- 4) 面板 tab「对方主页」自动切预览视图 ----------
old = """function setPanelTab(tab) {
  panelTab = tab;
  document.querySelectorAll('.panel-tabs button').forEach(x => x.classList.toggle('active', x.getAttribute('data-tab') === tab));
  renderPanel();
}"""
new = """function setPanelTab(tab) {
  panelTab = tab;
  /* 编辑对方主页时，手机画面自动跟着切到对方主页预览（所见即所得） */
  if (tab === 'peer' && camView !== 'peer' && camView !== 'peer-moments') camView = 'peer';
  document.querySelectorAll('.panel-tabs button').forEach(x => x.classList.toggle('active', x.getAttribute('data-tab') === tab));
  renderPanel();
  if (camView === 'peer') renderPhone();
}"""
assert old in s
s = s.replace(old, new, 1)

# ---------- 5) 基本资料：名字标签正名 + 补昵称行字段 ----------
old = """    fieldText(B + '.name', '昵称', p.name) +"""
new = """    fieldText(B + '.name', '名字（主页大字）', p.name) +
    fieldText(B + '.nickname', '昵称行（主页「昵称:」一行，留空不显示）', p.nickname || '') +"""
assert old in s
s = s.replace(old, new, 1)

io.open(P, 'w', encoding='utf-8').write(s)
print('patched, %d -> %d chars' % (n0, len(s)))
