# -*- coding: utf-8 -*-
"""把 _redesign/<name>_new.css 替换进 editor/<name>.html 的 <style> 块。
替换前校验：旧样式的每个选择器都必须出现在新样式中，防止漏掉规则导致布局坏掉。"""
import re, sys, io

BASE = r"G:\weixin-auto\editor"
FILES = ["index", "scene", "concurrent"]

SEL_RE = re.compile(r'([^{}]+)\{')

def selectors(css_text):
    sels = set()
    # 去掉注释
    css = re.sub(r'/\*.*?\*/', '', css_text, flags=re.S)
    for m in SEL_RE.finditer(css):
        chunk = m.group(1)
        # 忽略 @media 等头
        for part in chunk.split(','):
            p = part.strip()
            if not p or p.startswith('@') or p.endswith('{') is False and p == '':
                continue
            p = p.strip()
            if p.startswith('@'):
                continue
            sels.add(p)
    return sels

def splice(name):
    html_path = BASE + "\\" + name + ".html"
    css_path = BASE + "\\_redesign\\" + name + "_new.css"
    with io.open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    with io.open(css_path, "r", encoding="utf-8") as f:
        new_css = f.read()
    start = html.index("<style")
    cs = html.index(">", start) + 1
    ce = html.index("</style>", cs)
    old_css = html[cs:ce]
    old_sels = selectors(old_css)
    new_sels = selectors(new_css)
    missing = sorted(s for s in old_sels if s not in new_sels)
    if missing:
        print("[%s] MISSING %d selectors:" % (name, len(missing)))
        for s in missing:
            print("   ", s)
        return False
    html = html[:cs] + "\n" + new_css + "\n" + html[ce:]
    with io.open(html_path, "w", encoding="utf-8", newline="") as f:
        f.write(html)
    print("[%s] OK: replaced style block, old=%d chars -> new=%d chars, %d selectors matched" %
          (name, len(old_css), len(new_css), len(old_sels)))
    return True

if __name__ == "__main__":
    ok = True
    for n in (sys.argv[1:] or FILES):
        ok = splice(n) and ok
    sys.exit(0 if ok else 1)
