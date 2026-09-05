import json, io, sys
sys.stdout.reconfigure(encoding='utf-8')
wf = json.load(open(r"F:\weixin-auto\_stall_workflow.json", encoding="utf-8"))
S = wf["steps"]
home = S[0]["params"]["数据"]
print("历史会话检测 -> 首页联系人:")
for c in home:
    ms = c.get("messages", [])
    txt = " | ".join(m["text"] for m in ms[:2])
    print(f"  {c['name']}   串首: {txt}")
print()
print("打开聊天 目标:", [s["params"].get("联系人") for s in S if s["action"] == "打开聊天"])
