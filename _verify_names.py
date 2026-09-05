# -*- coding: utf-8 -*-
"""验证:剧本离线转换后,编辑主页人物与打开聊天人物是否一致。"""
import sys, json, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"F:\weixin-auto")
import script_translator

SCRIPT = """[历史会话]
[会话] o 泡 河南 156
o 泡 河南 156：不是哥们，我都已经吃完了
[会话] 粉丝 fang
粉丝 fang：[链接] 聊天案例解析 (必看)
[会话] 敷衍女 7.12
敷衍女 7.12：你多久没理我了
[会话] 林林
林林：宝宝贴贴
[会话] 172 小前 欧美风
172 小前 欧美风：我邻居昨晚都投诉了 好尴尬
[会话] 瓦学妹
瓦学妹：你每次都在厕所半个小时才出来什么意思
[会话] 156 白半自富美 专一硕士
156 白半自富美 专一硕士：你要来参加我的毕业典礼
[会话] 东南女神 御姐 s 做饭好吃 生日 6.29
东南女神 御姐 s 做饭好吃 生日 6.29：我老公不在家啊
[会话] 173 手舞舞蹈生 活泼大方好相处
173 手舞舞蹈生 活泼大方好相处：用完就不能甩纸包好
[会话] 沙拉拉拉
沙拉拉拉：[未点开的会话内容]
[历史会话结束]
[打开聊天] o 泡 河南 156
[我方打字] ?
[返回主页]
[等待] 0.2
[打开聊天] 鱼丸卡莉
[打字不发] 你也来测试我？
[删除文字] -1
[打字不发] 那我最好建议你不要这么发
[删除文字] -1
[我方打字] 那我最好建议你不要这么发
[打字不发] 不正面回复 制造悬念
[删除文字] -1
[等待] 0.3
[对方发消息] 啊？为什么
[等待] 0.3
[对方发消息] 我说认真的啊
[打字不发] 你是真单纯还是缺心眼啊
[删除文字] -1
[我方打字] 你闺蜜都没认真
[我方打字] 你还当上像机了
[打字不发] 还尬上了
[删除文字] -1
[打字不发] 直接戳穿 | 0.3 | 我感觉她挺喜欢你的；回来之后一直在夸你帅啊什么的
[删除文字] -1
[打字不发] 别信啊 这都是测试
[删除文字] -1
[我方打字] 是么
[我方打字] 但是你第一句话好像打错了吧
[打字不发] 转一下注意力
[删除文字] -1
[返回主页]
[等待] 0.2
[打开聊天] jueer
[对方发图片] [图片] {在这里填这张图的描述}
"""

# 复用 editor_server 的转换逻辑(离线)
from editor_server import _parse_script_to_steps
steps, warnings, source = _parse_script_to_steps(SCRIPT, offline=True)

print("=== source:", source)
print("=== warnings ===")
for w in warnings:
    print("  W:", w)

home_names = []
open_names = []
for s in steps:
    a = s.get("action")
    p = s.get("params") or {}
    if a == "编辑主页":
        for it in p.get("数据", []):
            home_names.append(it.get("name"))
    elif a == "打开聊天":
        open_names.append(p.get("联系人"))

print("=== 编辑主页人物(%d) ===" % len(home_names))
print(json.dumps(home_names, ensure_ascii=False))
print("=== 打开聊天人物 ===")
print(json.dumps(open_names, ensure_ascii=False))
print("=== 打开聊天是否都在主页里 ===")
for n in open_names:
    print("  %s -> %s" % (n, n in home_names))

with open(r"F:\weixin-auto\_verify_out.json", "w", encoding="utf-8") as fh:
    json.dump(steps, fh, ensure_ascii=False, indent=2)
print("已写出 _verify_out.json")
