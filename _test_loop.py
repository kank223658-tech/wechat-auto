# -*- coding: utf-8 -*-
"""离线验证新生成主循环（不打真实大模型）。

把 editor_server._call_generate_deepseek 换成受控桩：
  第 1 轮返回「JSON 草稿」，第 2 轮返回「patches 补丁包」，
用来验证 JSON -> [指令] 渲染、定向补丁、严重度评分、自动沉淀这几段管道。
"""
import json
import sys

sys.path.insert(0, ".")
import editor_server as es
import script_generator as sg
import script_format as sf
import create_store as store

# --- 桩：假 API Key ---
_orig_load = es.script_translator.load_settings
es.script_translator.load_settings = lambda: {
    "deepseek_api_key": "sk-fake-for-test",
    "deepseek_model": "test-model",
    "deepseek_base_url": "http://127.0.0.1:1",
}

DRAFT = {
    "history": [
        {"contact": "susu", "messages": [
            {"who": "peer", "text": "那我先走了 | 23:21"},
            {"who": "me", "text": "好，路上慢点"},
            {"who": "peer", "text": "嗯"}]},
        {"contact": "小满", "messages": [
            {"who": "peer", "text": "[图片] 好显身材的连衣裙 | 19:15"}]},
    ],
    "steps": [
        {"action": "打开聊天", "params": {"联系人": "susu"}},
        {"action": "我方打字", "params": {"内容": "在干嘛"}},
        {"action": "打字不发", "params": {"内容": "故意否定制造反差", "停留": 0.5,
                                          "插话": "你这话什么意思"}},
        {"action": "删除文字", "params": {"数量": -1}},
        {"action": "切换底部面板", "params": {"面板": "表情", "停留": 0.8}},
        {"action": "发送emoji", "params": {"表情": "捂脸", "发送后": "键盘"}},
        {"action": "对方发消息", "params": {"内容": "你怎么突然这么会说话"}},
        {"action": "手机状态栏", "params": {"模式": "深夜"}},
        {"action": "转账", "params": {"接收人": "susu", "金额": "520.00", "备注": "别熬夜"}},
        {"action": "返回主页", "params": {"停留": 0.6}},
    ],
}

PATCH = {
    "patches": [{"find": "[手机状态栏] 深夜", "with": "[手机状态栏] 深夜 | 22:40"}],
    "append_steps": [{"action": "对方emoji", "params": {"表情": "害羞"}},
                     {"action": "我方打字", "params": {"内容": "我先睡了 你也早点休息"}}],
}

calls = {"n": 0}


def fake_call(api_key, system_prompt, user_msg, model, base_url):
    calls["n"] += 1
    if calls["n"] == 1:
        return json.dumps(DRAFT, ensure_ascii=False), None
    return json.dumps(PATCH, ensure_ascii=False), None


es._call_generate_deepseek = fake_call

result, err = es._generate_script({"brief": "女生已读不回怎么聊", "category": "美女", "max_rounds": 2})
print("err:", err)
if result:
    rep = result["report"]
    print("产出形态:", rep.get("produce_mode"), " 补丁轮次:", rep.get("patch_rounds"),
          " 尝试:", rep.get("attempts"), " 通过:", rep.get("passed"))
    print("步数:", len(result["steps"]), " 问题数:", len(rep["issues"]))
    print("自动沉淀:", result.get("auto_sunk_reference"), " ref:", result.get("reference_id"))
    print()
    print("---- 渲染出的剧本 ----")
    print(result["text"])
    print()
    print("---- 解析回步骤 ----")
    for s in result["steps"]:
        print("  ", s["action"], "|", str(s.get("params"))[:70])
    print()
    print("---- 前 8 条问题（应含篇幅类）----")
    for x in rep["issues"][:8]:
        print("   -", x[:100])

# --- 单独测自动沉淀的幂等与上限 ---
print()
print("---- _sink_reference ----")
r1 = es._sink_reference("这是一份测试用的剧本片段\n[打开聊天] 测试\n", "测试主题", "美女")
print("首次入库:", bool(r1), (r1 or {}).get("title"))
r2 = es._sink_reference("这是一份测试用的剧本片段\n[打开聊天] 测试\n", "测试主题", "美女")
print("重复入库返回 None:", r2 is None)
es.script_translator.load_settings = _orig_load
