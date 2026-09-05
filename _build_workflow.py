# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import script_translator as st

# 兼容补丁：script_translator.ensure_all_contacts_in_home 引用了本应在 main.py 里的
# _extract_bg_queue_contacts（仅当步骤含「后台消息队列」时触发）。补一个同名实现。
def _extract_bg_queue_contacts(data):
    try:
        if isinstance(data, str):
            data = data.strip()
            if data.endswith(".json") and os.path.isfile(data):
                with open(data, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = json.loads(data)
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(it.get("联系", it.get("contact", "")) or "").strip()
            for it in data if isinstance(it, dict) and str(it.get("联系", it.get("contact", "")) or "").strip()]
st._extract_bg_queue_contacts = _extract_bg_queue_contacts

text = open(r"F:\weixin-auto\_repro_2s.txt", encoding="utf-8").read()
all_names = st._collect_text_person_names(text)
global_map = st.build_name_replacement_map(all_names)
history_steps, cleaned_text, hist_warnings, repl_map = st.split_history_block(text, pre_mapping=global_map)
full_map = {**global_map, **repl_map}
steps, warnings = st.translate_offline(cleaned_text)
steps = st.merge_typing_waits(steps, cleaned_text)
result = {"steps": steps, "warnings": warnings, "source": "offline"}
if history_steps:
    translated = [s for s in result["steps"] if s.get("action") != "编辑主页"]
    result["steps"] = history_steps + translated
st.normalize_step_people(result["steps"], pre_mapping=full_map)
st.cap_home_and_align_contacts(result["steps"], result["warnings"])
st.ensure_all_contacts_in_home(result["steps"])

print("总步骤数:", len(result["steps"]))
for i, s in enumerate(result["steps"][:14], 1):
    print(f"  {i:>2} {s.get('action')} {json.dumps(s.get('params'), ensure_ascii=False)[:140]}")
print("WARNINGS:", list(warnings), list(hist_warnings))

with open(r"F:\weixin-auto\_repro_workflow.json", "w", encoding="utf-8") as fh:
    json.dump({"name": "repro2s", "steps": result["steps"]}, fh, ensure_ascii=False, indent=2)
print("已写入 _repro_workflow.json")
