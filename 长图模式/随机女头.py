# -*- coding: utf-8 -*-
"""随机女头抽取器 —— AI 制片标准件。

用法:
    py 长图模式/随机女头.py            # 随机抽 1 张，打印 URL 路径
    py 长图模式/随机女头.py -n 3      # 抽 3 张候选
    py 长图模式/随机女头.py --avoid dygirl_06,dygirl_09   # 避开最近用过的

规则（头像选角表.md 第二节）:
  - 只从「精选 34 张」女头池里抽，绝不踩禁用清单。
  - 男生头像固定 男_竹林幽经.jpg，与本脚本无关。
"""
import argparse
import random
import sys
import io
from pathlib import Path

# 精选池 = 头像选角表.md 第四节全部女头（人设, 文件名）
POOL = [
    ("甜美软妹", "dygirl_06.jpg"), ("甜美软妹", "dygirl_09.jpg"),
    ("甜美软妹", "dygirl_17.jpg"), ("甜美软妹", "dygirl_08.jpg"),
    ("清纯学生", "dygirl_03.jpg"), ("清纯学生", "dygirl_11.jpg"),
    ("清纯学生", "dygirl_19.jpg"), ("清纯学生", "dygirl_15.jpg"),
    ("元气活泼", "dygirl_12.jpg"), ("元气活泼", "dygirl_04.jpg"),
    ("元气活泼", "dygirl_07.jpg"), ("元气活泼", "dygirl_14.jpg"),
    ("气质知性", "dygirl_45.jpg"), ("气质知性", "dygirl_43.jpg"),
    ("气质知性", "dygirl_44.jpg"),
    ("气质知性", "我先康康_这天气穿什么__1_EB怀特_来自小红书网页版_20260902_180814_755.jpg"),
    ("气质知性", "街头白衬衫.jpg"),
    ("御姐", "御一下_1_涔涔_来自小红书网页版_20260831_184719_470.jpg"),
    ("御姐", "dygirl_20.jpg"),
    ("御姐", "照片输出_1_楠柒_来自小红书网页版_20260902_180914_204.jpg"),
    ("御姐", "𝙒𝙚𝘾𝙝𝙖𝙩___御姐感女头_1_Jin_Junuary-Cap03_来自小红书_20260831_190001_316.jpg"),
    ("御姐", "这样穿真的很有美女感__1_涂涂的life_来自小红书网页版_20260831_20260831_184528_168.jpg"),
    ("个性酷妹", "dygirl_10.jpg"), ("个性酷妹", "dygirl_13.jpg"),
    ("个性酷妹", "Dark_高质量女头__1_Dark__来自小红书网页版_20260831_185822_457.jpg"),
    ("个性酷妹", "Jennie头像_1_PP酱v_来自小红书网页版_20260831_185616_327.jpg"),
    ("文艺背影", "dygirl_55.jpg"), ("文艺背影", "樱花树下白裙.jpg"),
    ("文艺背影", "黄昏街头背影随手拍.jpg"),
    ("文艺背影", "Share___招财好运捧花女生头像_1_捂耳听风__来自小红书网页版_20260902_180759_080.jpg"),
]

ROOT = Path(__file__).resolve().parent.parent
AV_DIR = ROOT / "vue-WeChat" / "public" / "images" / "avatar"

# 抽取结果落盘，下次自动避开最近用过的（保持"每次不一样"）
HISTORY = Path(__file__).resolve().parent / "_随机女头_历史.txt"


def load_history():
    if HISTORY.exists():
        return [l.strip() for l in HISTORY.read_text("utf-8").splitlines() if l.strip()]
    return []


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=1)
    ap.add_argument("--avoid", default="", help="逗号分隔的文件名，额外避开")
    a = ap.parse_args()

    avoid = {x.strip() for x in a.avoid.split(",") if x.strip()}
    used = set(load_history())
    pool = [(t, f) for t, f in POOL if f not in avoid and f not in used]
    if not pool:                       # 全用过就重置历史
        pool = [(t, f) for t, f in POOL if f not in avoid]
        used = set()

    picks = random.sample(pool, min(a.n, len(pool)))
    for t, f in picks:
        exists = (AV_DIR / f).exists()
        print(f"[{t}] /images/avatar/{f}   库内存在={exists}")

    if a.n == 1 and picks:
        t, f = picks[0]
        hist = load_history()[-5:] + [f]     # 只记最近 5 张
        HISTORY.write_text("\n".join(hist), "utf-8")


if __name__ == "__main__":
    main()
