# -*- coding: utf-8 -*-
"""UX 二轮优化：功能说明收进「?」、排版等高。
index.html —— 脚本/创作模式的「使用说明」大卡片收进标题旁问号弹层；左右栏等高填充
scene.html / concurrent.html —— 说明性 .hint 自动折叠成小问号（空状态/警告/含控件的保留）
铁律：只动展示层，不改任何 id 语义、data-page-node-id、画布样式、JS 数据契约。
"""
import io, sys

def load(p): return io.open(p, encoding="utf-8").read()
def save(p, s): io.open(p, "w", encoding="utf-8", newline="").write(s)

def must(cond, msg):
    if not cond:
        print("ABORT:", msg); sys.exit(1)

# ============================ index.html ============================
IDX = r"G:\weixin-auto\editor\index.html"
s = load(IDX)

# ---- 1) 脚本模式：使用说明卡片 → 问号弹层 ----
start = s.find('<div class="script-card hint-card">')
ol0 = s.find('<ol class="script-tips">', start)
close = s.find('</div>', s.find('</ol>', ol0)) + len('</div>')
must(start > 0 and ol0 > start and close > ol0, "script hint-card bounds")
block = s[start:close]
must('使用说明' in block, "script hint-card content")
ol_html = block[ol0 - start: block.find('</ol>', ol0 - start) + len('</ol>')]
src_div = '<div class="hq-src" id="scriptHelpSrc" hidden>' + ol_html + '</div>'
s = s[:start] + src_div + s[close:]
print("index: script hint-card ->", src_div[:60], "...")

old_title = '''<div class="script-card-title">剧本文本
                <span class="script-sub">支持标准格式，也支持松散自然语言</span>
              </div>'''
must(s.count(old_title) == 1, "script title anchor")
new_title = '''<div class="script-card-title">剧本文本
                <span class="script-sub">支持标准格式，也支持松散自然语言</span>
                <span class="hq-wrap"><button type="button" class="hq" data-help="#scriptHelpSrc" title="使用说明">?</button></span>
              </div>'''
s = s.replace(old_title, new_title, 1)

# ---- 2) 创作模式：同样处理 ----
start = s.find('<div class="create-card hint-card">')
ol0 = s.find('<ol class="script-tips">', start)
close = s.find('</div>', s.find('</ol>', ol0)) + len('</div>')
must(start > 0 and ol0 > start and close > ol0, "create hint-card bounds")
block = s[start:close]
must('使用说明' in block, "create hint-card content")
ol_html = block[ol0 - start: block.find('</ol>', ol0 - start) + len('</ol>')]
src_div = '<div class="hq-src" id="createHelpSrc" hidden>' + ol_html + '</div>'
s = s[:start] + src_div + s[close:]
print("index: create hint-card ->", src_div[:60], "...")

old_title = '''<div class="create-card-title">创作主题
                <span class="create-sub">一句话说清这段聊天教学要求</span>
              </div>'''
must(s.count(old_title) == 1, "create title anchor")
new_title = '''<div class="create-card-title">创作主题
                <span class="create-sub">一句话说清这段聊天教学要求</span>
                <span class="hq-wrap"><button type="button" class="hq" data-help="#createHelpSrc" title="使用说明">?</button></span>
              </div>'''
s = s.replace(old_title, new_title, 1)

# ---- 3) 布局：脚本模式左右等高，剧本文本撑满 ----
k = s.find('.script-layout {')
e = s.find('}', k)
must(k > 0 and 'align-items: start;' in s[k:e], "script-layout rule")
s = s[:k] + s[k:e].replace('align-items: start;', 'align-items: stretch;') + s[e:]

HQ_CSS = '''
/* ---------- 帮助问号（?）与说明浮层 ---------- */
.hq-wrap { position: relative; display: inline-flex; }
.hq {
  flex: none; width: 18px; height: 18px; display: inline-grid; place-items: center; padding: 0;
  border: 1px solid var(--line); border-radius: 50%; background: var(--panel-2);
  color: var(--muted); font-size: 11px; font-weight: 700; line-height: 1; cursor: help;
}
.hq:hover { color: var(--accent); border-color: var(--accent-border); background: var(--panel-3); }
.hq-pop {
  position: absolute; top: 26px; left: 0; z-index: 80;
  width: min(600px, 86vw); max-height: 68vh; overflow: auto; padding: 12px 14px;
  border: 1px solid var(--line-strong); border-radius: 12px;
  background: var(--panel); box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22); color: var(--text);
}
.hq-pop .script-tips { margin: 0; padding-left: 16px; color: var(--muted); font-size: 12px; line-height: 1.9; }

/* ---------- 脚本模式：左右等高，输入区撑满 ---------- */
.script-input-col { display: flex; flex-direction: column; min-width: 0; }
.script-input-col > .script-card { flex: 1; display: flex; flex-direction: column; }
.script-input-col .script-textarea { flex: 1; min-height: 380px; }
.script-result-col > .script-card { flex: 1; display: flex; flex-direction: column; }
.script-result-col .script-preview { flex: 1; }
</style>'''
must(s.count('</style>') == 1, "index style blocks")
s = s.replace('</style>', HQ_CSS, 1)

HQ_JS = '''    /* 帮助问号：点「?」弹出对应说明（纯展示层） */
    document.addEventListener("click", (event) => {
      const q = event.target.closest(".hq");
      document.querySelectorAll(".hq-pop").forEach((p) => {
        if (!q || p.parentElement.querySelector(".hq") !== q) p.remove();
      });
      if (!q) return;
      event.preventDefault();
      const src = document.querySelector(q.getAttribute("data-help"));
      if (!src) return;
      const pop = document.createElement("div");
      pop.className = "hq-pop";
      pop.innerHTML = src.innerHTML;
      q.parentElement.appendChild(pop);
    });
    /* 键盘快捷键：焦点在输入框里时不拦截 */'''
must(s.count('    /* 键盘快捷键：焦点在输入框里时不拦截 */') == 1, "keydown anchor")
s = s.replace('    /* 键盘快捷键：焦点在输入框里时不拦截 */', HQ_JS, 1)
save(IDX, s)
print("index.html saved")

# ============================ scene.html / concurrent.html ============================
HINT_CSS = '''
/* ---------- 说明文字折叠成「?」 ---------- */
.hint.compacted { display: flex; align-items: flex-start; gap: 7px; }
.hint-q {
  flex: none; width: 16px; height: 16px; display: inline-grid; place-items: center; padding: 0;
  border: 1px solid var(--line); border-radius: 50%; background: var(--panel-2);
  color: var(--muted); font-size: 10.5px; font-weight: 700; line-height: 1; cursor: help;
}
.hint-q:hover { color: var(--accent); border-color: var(--accent-border); background: var(--panel-3); }
.hint-body { display: none; flex: 1; }
.hint.compacted.open .hint-body { display: block; }
</style>'''

HINT_JS = '''
/* ---------- 说明性 hint 折叠成小问号（空状态/警告/含控件的保留） ---------- */
const HINT_KEEP = ['还没有', '先在上方', '这套方案还没有', '⚠', '加载失败', '请确认'];
function compressHints(root) {
  (root || document).querySelectorAll('.hint').forEach(h => {
    if (h.querySelector('.hint-q')) return;
    if (h.querySelector('button, input, select, textarea, video, a')) return;
    const t = (h.textContent || '').trim();
    if (!t || HINT_KEEP.some(k => t.includes(k))) return;
    if (t.length < 12) return;
    h.classList.add('compacted');
    const q = document.createElement('button');
    q.type = 'button';
    q.className = 'hint-q';
    q.title = '点开查看说明';
    const body = document.createElement('div');
    body.className = 'hint-body';
    while (h.firstChild) body.appendChild(h.firstChild);
    h.appendChild(q);
    h.appendChild(body);
    q.onclick = (e) => { e.stopPropagation(); h.classList.toggle('open'); };
  });
}
let _hintObsT = null;
new MutationObserver(() => {
  if (_hintObsT) clearTimeout(_hintObsT);
  _hintObsT = setTimeout(() => compressHints(document.body), 120);
}).observe(document.body, { childList: true, subtree: true });
compressHints(document.body);
'''

for path, after_anchor in [
    (r"G:\weixin-auto\editor\scene.html", "cardFoldState = new Map();"),
    (r"G:\weixin-auto\editor\concurrent.html", None),
]:
    s = load(path)
    # CSS
    must(s.count('</style>') == 1, path + " style blocks")
    s = s.replace('</style>', HINT_CSS, 1)
    # JS：插在主 script 块末尾（</script> 前的第二处，避开菜单小脚本）
    if after_anchor:
        must(s.count(after_anchor) == 1, path + " anchor")
        k = s.find(after_anchor)
        ins = s.find('\n', k) + 1
        s = s[:ins] + HINT_JS + s[ins:]
    else:
        k = s.find("document.addEventListener('DOMContentLoaded', init);")
        must(k > 0, path + " domcontentloaded anchor")
        ins = s.find('\n', k) + 1
        s = s[:ins] + HINT_JS + s[ins:]
    save(path, s)
    print(path, "saved")

print("ALL DONE")
