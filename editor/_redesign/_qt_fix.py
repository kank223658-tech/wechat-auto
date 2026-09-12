# -*- coding: utf-8 -*-
"""替换三页已注入的 qtTipsJs：scroll 改为重定位；decorate 改为可补角标。"""
import re, shutil, sys, io
BASE = r"G:\weixin-auto\editor"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

NEW_JS_TEMPLATE = """<script id="qtTipsJs">
(function () {
  var VOID_TAGS = { INPUT: 1, SELECT: 1, TEXTAREA: 1, IMG: 1, BR: 1 };
  var DYN_IDS = __DYN_IDS__;
  function ensureBadge(el) {
    if (VOID_TAGS[el.tagName]) return;
    if (!el.querySelector(':scope > .qt-badge')) {
      var b = document.createElement('i');
      b.className = 'qt-badge'; b.textContent = '?';
      el.appendChild(b);
    }
  }
  function decorate(el) {
    if (!el || !el.classList) return;
    el.classList.add('qt-host');
    ensureBadge(el);
  }
  function adoptTitles() {
    DYN_IDS.forEach(function (id) {
      var el = document.getElementById(id);
      if (el && el.hasAttribute('title') && !el.hasAttribute('data-tip')) {
        el.setAttribute('data-tip', el.getAttribute('title'));
        el.removeAttribute('title');
      }
    });
  }
  function scan() {
    adoptTitles();
    document.querySelectorAll('[data-tip]').forEach(decorate);
  }
  scan();
  var moT = null;
  new MutationObserver(function () {
    clearTimeout(moT); moT = setTimeout(scan, 200);
  }).observe(document.body, { childList: true, subtree: true });
  var pop = null, cur = null;
  function ensure() {
    if (!pop) { pop = document.createElement('div'); pop.className = 'qt-pop'; document.body.appendChild(pop); }
    return pop;
  }
  function place(host) {
    var tip = host.getAttribute('data-tip'); if (!tip) return false;
    var p = ensure(); p.textContent = tip;
    var r = host.getBoundingClientRect();
    var pw = p.offsetWidth, ph = p.offsetHeight;
    var x = Math.min(Math.max(8, r.left + r.width / 2 - pw / 2), window.innerWidth - pw - 8);
    var y = r.bottom + 7;
    if (y + ph > window.innerHeight - 8) y = r.top - ph - 7;
    p.style.left = x + 'px'; p.style.top = Math.max(8, y) + 'px';
    return true;
  }
  function show(host) { if (place(host)) { ensure().classList.add('show'); cur = host; } }
  function hide() { if (pop) pop.classList.remove('show'); cur = null; }
  document.addEventListener('mouseover', function (e) {
    var h = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (h !== cur) { h ? show(h) : hide(); }
  });
  document.addEventListener('click', hide);
  window.addEventListener('scroll', function () {
    if (cur && document.contains(cur) && cur.getBoundingClientRect().height > 0) place(cur);
    else hide();
  }, true);
  window.addEventListener('resize', hide);
})();
</script>
"""

DYN = {"index.html": [], "scene.html": [], "concurrent.html": ["libSort", "libUpcat", "libMove", "libCatMgr"]}
new_js = {f: NEW_JS_TEMPLATE.replace("__DYN_IDS__", repr(ids)) for f, ids in DYN.items()}

pat = re.compile(r'<script id="qtTipsJs">.*?</script>', re.S)
for f, nj in new_js.items():
    path = f"{BASE}\\{f}"
    s = open(path, encoding="utf-8").read()
    n = len(pat.findall(s))
    print(f, "旧块命中:", n)
    if n != 1:
        print("  !! 预期 1 处，跳过"); continue
    shutil.copy2(path, path + ".bak_qt2")
    s = pat.sub(lambda m: nj, s, count=1)
    open(path, "w", encoding="utf-8", newline="").write(s)
    print("  OK 替换")
print("done")
