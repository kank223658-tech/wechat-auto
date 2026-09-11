# -*- coding: utf-8 -*-
"""控件审计：列出每个静态 HTML 控件，以及它在 JS 中的绑定方式。
输出：每个页面的 控件清单（id、标签文本、事件绑定），以及没有任何 JS 引用的死控件。"""
import io, re, json

BASE = r"G:\weixin-auto\editor"

def audit(f):
    s = io.open(BASE + "\\" + f, encoding="utf-8").read()
    scripts = [m.group(1) for m in re.finditer(r'<script[^>]*>(.*?)</script>', s, re.S)]
    all_js = "\n".join(scripts)
    noscript = re.sub(r'<script[^>]*>.*?</script>', '', s, flags=re.S)

    handled = set(re.findall(r'getElementById\(\s*["\']([\w-]+)["\']', all_js))
    handled |= set(re.findall(r'\$\(\s*["\']([\w-]+)["\']', all_js))
    handled |= set(re.findall(r'\$\$\(\s*["\']#?([\w-]+)["\']', all_js))
    qs = set(re.findall(r'querySelector(?:All)?\(\s*["\']#([\w-]+)["\']', all_js))
    dyn = set(re.findall(r'id=\\?"([\w-]+)\\?"', all_js))

    # 静态控件
    controls = []
    for m in re.finditer(r'<(button|input|select|textarea)\b[^>]*>', noscript):
        tag_full = m.group(0)
        tag = m.group(1)
        idm = re.search(r'id="([\w-]+)"', tag_full)
        eid = idm.group(1) if idm else None
        if not eid:
            continue
        # 提取按钮文本
        text = ""
        if tag == "button":
            # 找配对 </button>
            end = noscript.find("</button>", m.end())
            seg = noscript[m.end():end]
            text = re.sub(r"<[^>]+>", "", seg).strip()[:22]
        else:
            pm = re.search(r'placeholder="([^"]{0,20})', tag_full)
            text = pm.group(1) if pm else ""
        refs = []
        if eid in handled: refs.append("getByID")
        if eid in qs: refs.append("qs")
        if eid in dyn: refs.append("dyn-id")
        # onclick 内联
        if re.search(r'on\w+\s*=\s*["\'][^"\']*' + eid, tag_full):
            refs.append("inline")
        controls.append((eid, tag, text, refs))

    print("=" * 8, f, "controls:", len(controls))
    for eid, tag, text, refs in controls:
        flag = "  <== NO JS REF" if not refs else ""
        print("  %-22s %-8s %-22s %s%s" % (eid, tag, text, ",".join(refs) or "-", flag))

for f in ["index.html", "scene.html", "concurrent.html"]:
    audit(f)
