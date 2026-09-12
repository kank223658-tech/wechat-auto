# -*- coding: utf-8 -*-
"""修复悬空图片引用（4 个已批准文件）。带备份 + 逐条命中校验。默认空转。

映射原则：
  1) 能按「人名」对应到 scene.json 里正在用的真实头像 → 直接沿用，保证观感一致
  2) 上游 demo 通讯录（白浅/关雎尔/三国人物）无对应 → 指向通用占位 /images/ref/D.png
  3) 封面类 → 指向 peer 目录下真实的封面图
"""
import os, sys, re, json, shutil, collections

ROOT = r"G:\weixin-auto"
IMG = os.path.join(ROOT, "vue-WeChat", "public", "images")
APPLY = len(sys.argv) > 1 and sys.argv[1] == "apply"

# ---- 从 scene.json 取「人名 -> 真实头像」，避免手抄长文件名出错 ----
sc = json.load(open(os.path.join(ROOT, "scene.json"), encoding="utf-8"))


def avatar_of(*keywords):
    """优先精确匹配 remark，其次精确匹配 name，最后才做包含匹配（避免「妍」撞上「妍妍」）。"""
    home = sc.get("home", [])
    for k in keywords:
        for x in home:
            if (x.get("remark") or "") == k:
                return x.get("avatar")
    for k in keywords:
        for x in home:
            if (x.get("name") or "") == k:
                return x.get("avatar")
    for k in keywords:
        for x in home:
            tag = (x.get("remark") or "") + "|" + (x.get("name") or "")
            if k in tag:
                return x.get("avatar")
    return None


m_me = (sc.get("me") or {}).get("avatar")
a_lux = avatar_of("陆香儿")
a_pay = avatar_of("微信支付")
a_fuwu = avatar_of("服务号")
a_gzh = avatar_of("公众号")
a_team = avatar_of("微信团队")
a_chenmo = avatar_of("沉默光环")
a_yan = avatar_of("妍")
a_qun = avatar_of("学员-小康") or avatar_of("梓康")

PLACEHOLDER = "/images/ref/D.png"      # 通用占位（真实存在）
PEER_AVATAR = "/images/peer/peer_avatar.jpg"
PEER_COVER = "/images/peer/peer_cover.jpg"
PEER_V1 = "/images/peer/peer_v1.jpg"

MAPPING = {
    # 1) 有真人对应
    "/images/ref/luxianger.png": a_lux,
    "/images/ref/pay.png": a_pay,
    "/images/ref/fuwu.png": a_fuwu,
    "/images/ref/gongzhong.png": a_gzh,
    "/images/ref/weixin_team.png": a_team,
    "/images/ref/chenmo.png": a_chenmo,
    "/images/ref/yan.png": a_yan,
    "/images/ref/qun.png": a_qun,
    # 2) 默认头像
    "/images/header/yehua.jpg": PEER_AVATAR,          # 对方默认
    "/images/header/header01.png": m_me,              # 我方默认
    "/images/header/header02.png": m_me,
    # 3) 上游 demo 通讯录 / 三国人物 → 占位
    "/images/album/baiqian/baiqian01.jpeg": PLACEHOLDER,
    "/images/album/baiqian/baiqian02.jpeg": PLACEHOLDER,
    "/images/album/guanyu/guanyu01.jpeg": PLACEHOLDER,
    "/images/album/guanyu/guanyu02.jpeg": PLACEHOLDER,
    "/images/header/baiqian.jpg": PLACEHOLDER,
    "/images/header/liubei.jpg": PLACEHOLDER,
    "/images/header/guangyu.jpg": PLACEHOLDER,
    "/images/header/zhugeliang.jpg": PLACEHOLDER,
    "/images/header/sunshangxiang.jpg": PLACEHOLDER,
    "/images/header/sunquan.jpg": PLACEHOLDER,
    "/images/header/huangyueying.jpg": PLACEHOLDER,
    "/images/header/zhenji.jpg": PLACEHOLDER,
    # 4) 封面/视频缩略图
    "/images/ref/lux_video.png": PEER_V1,
    "/images/ref/stitch.png": PLACEHOLDER,
    "/images/ref/grey_cover.png": PEER_COVER,
}

# 校验映射目标都存在
print("--- 映射目标存在性校验 ---")
badmap = []
for k, v in MAPPING.items():
    if not v:
        badmap.append((k, v, "空值"))
    elif not os.path.isfile(os.path.join(IMG, v[len("/images/"):].replace("/", os.sep))):
        badmap.append((k, v, "目标不存在"))
    else:
        print(f"  OK  {k:42s} -> {v}")
for k, v, why in badmap:
    print(f"  ✗✗  {k:42s} -> {v}   [{why}]")
if badmap:
    print("\n有映射目标缺失，已中止。")
    sys.exit(1)

TARGETS = [
    "vue-WeChat/src/vuex/store.js",
    "vue-WeChat/src/vuex/contacts.js",
    "scene.json",
    "reference_workflow.json",
]

print()
print("=" * 74)
print("替换预览" if not APPLY else "★ 实际执行 ★")
print("=" * 74)
total = 0
plans = {}
for t in TARGETS:
    fp = os.path.join(ROOT, t.replace("/", os.sep))
    txt = open(fp, "r", encoding="utf-8", errors="ignore").read()
    hits = {}
    for old, new in MAPPING.items():
        n = txt.count(old)
        if n:
            hits[old] = (n, new)
    plans[t] = hits
    cnt = sum(n for n, _ in hits.values())
    total += cnt
    print(f"\n--- {t}：{cnt} 处 ---")
    for old, (n, new) in sorted(hits.items()):
        print(f"    {n:3d}x  {old}")
        print(f"          -> {new}")

print(f"\n合计替换 {total} 处")

if not APPLY:
    print("\n（空转模式，未修改任何文件）")
    sys.exit(0)

print("\n开始替换……")
for t, hits in plans.items():
    fp = os.path.join(ROOT, t.replace("/", os.sep))
    bak = fp + ".bak_dangling"
    if not os.path.exists(bak):
        shutil.copy2(fp, bak)
        print(f"  备份 -> {t}.bak_dangling")
    txt = open(fp, "r", encoding="utf-8", errors="ignore").read()
    for old, (n, new) in hits.items():
        txt = txt.replace(old, new)
    open(fp, "w", encoding="utf-8", newline="").write(txt)
    # 复核
    left = [o for o in hits if o in open(fp, encoding="utf-8", errors="ignore").read()]
    print(f"  {t}: 替换完成，残留 {len(left)} 个")
