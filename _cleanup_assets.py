# -*- coding: utf-8 -*-
"""老画面清理：上游宣传素材 + 空目录 + avatar 重复/误传文件。默认空转。"""
import os, sys, shutil, hashlib

ROOT = r"G:\weixin-auto"
IMGDIR = os.path.join(ROOT, "vue-WeChat", "public", "images")
APPLY = len(sys.argv) > 1 and sys.argv[1] == "apply"

# ---- 1. 上游开源项目的宣传/演示素材（零引用）----
upstream = [
    "launchimage.png", "find-bg.png",
    "url-qrcode-both3.jpg", "url-qrcode-both2.jpg", "url-qrcode-both4.jpg",
    "demo-qrcode-gitee.png", "demo-qrcode-github.png",
    "url-qrcode-bak.png", "url-qrcode.png", "url-qrcode-bak.jpg",
    "url-qrcode.jpg",
    "mobile.png", "vue-WeChat-chart.png", "mobile-dev-guide.png",
    "find_icon-shopping.png", "find_icon-shake.png", "find_icon-bottle.png",
    "find_icon-locationservice.png", "find_icon-moregame.png", "find_icon-qrcode.png",
    "recording-signa-l008.png",
]

# ---- 2. 上游自带的空目录 ----
empty_dirs = [
    "OfficialAccount", "gif", "screenshot", "header", "chat", "sticker",
    "album/baiqian", "album/guanyu",
]

# ---- 3. avatar 库：重复文件（保留每个更早日期的那份；哭泣猫咪例外已核实）----
dup_delete = [
    "枯木_20260908_153043_003.jpg",
    "女生约出来喝酒_20260905_175037_862.jpg",
    "女生喝酒聊天记录2_20260905_175051_462.jpg",
    "女生喝酒聊天记录3_20260905_175100_372.jpg",
    "哭泣猫咪_20260908_163147_885.jpg",
]
dup_delete = ["avatar/" + f for f in dup_delete]

# ---- 4. avatar 库：明显误传的大文件 ----
misupload = [
    "avatar/ComfyUI_00001_cqpki_1788164517_20260831_214430_849.png",
    "avatar/学习急救班素材_20260908_155548_722.png",
    "avatar/IMG_0512_20260901_140118_982.png",
    "avatar/女友生气怎么哄教学_20260905_155312_388.png",
    "avatar/聊天技巧图片_20260905_154410_890.png",
    "avatar/洗姨妈内裤_20260905_174959_756.jpg",
]

groups = [("上游宣传素材", upstream), ("avatar 重复文件", dup_delete),
          ("avatar 误传大文件", misupload)]

print("=" * 70)
print("空转预览" if not APPLY else "★ 实际执行 ★")
print("=" * 70)
total = 0
for name, lst in groups:
    sz = 0
    miss = []
    for rel in lst:
        p = os.path.join(IMGDIR, rel)
        if os.path.isfile(p):
            sz += os.path.getsize(p)
        else:
            miss.append(rel)
    total += sz
    print(f"\n--- {name}：{len(lst) - len(miss)} 个文件，{sz/1e6:.2f} MB ---")
    for rel in lst:
        print("   ", rel)
    for m in miss:
        print("    (不存在)", m)

dsz = 0
print(f"\n--- 空目录：{len(empty_dirs)} 个 ---")
for d in empty_dirs:
    print("   ", "images/" + d)

print(f"\n合计释放约：{(total + dsz)/1e6:.2f} MB")

if APPLY:
    print("\n开始删除……")
    ok = err = 0
    for _, lst in groups:
        for rel in lst:
            p = os.path.join(IMGDIR, rel)
            if not os.path.isfile(p):
                continue
            try:
                os.remove(p)
                ok += 1
            except Exception as e:
                err += 1
                print(f"   [失败] {rel}: {e}")
    for d in empty_dirs:
        p = os.path.join(IMGDIR, d)
        if os.path.isdir(p):
            try:
                # 只删空目录；非空则跳过（防误删）
                if not os.listdir(p):
                    os.rmdir(p)
                    ok += 1
                else:
                    print(f"   [跳过非空] images/{d}")
            except Exception as e:
                err += 1
                print(f"   [失败] images/{d}: {e}")
    print(f"完成：成功 {ok} 项，失败 {err} 项")
else:
    print("\n（空转模式，未删除任何文件）")
