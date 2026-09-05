# -*- coding: utf-8 -*-
"""把已有 base/ext/8105 复制到缓存，并下载缺失的雾凇文件到 vue-WeChat/public/engine/rime-ice/。"""
import os, urllib.request
NEED = {
 "rime_ice.schema.yaml": None, "default.yaml": None, "symbols_v.yaml": None, "rime_ice.dict.yaml": None,
 "cn_dicts/8105.dict.yaml": "enhance/rime-ice/8105.dict.yaml",
 "cn_dicts/base.dict.yaml": "enhance/rime-ice/base.dict.yaml",
 "cn_dicts/ext.dict.yaml": "enhance/rime-ice/ext.dict.yaml",
 "cn_dicts/tencent.dict.yaml": None, "cn_dicts/others.dict.yaml": None,
 "opencc/s2t.json": None, "opencc/STPhrases.ocd2": None, "opencc/STCharacters.ocd2": None,
 "lua/select_character.lua": None, "lua/date_translator.lua": None, "lua/lunar.lua": None, "lua/uuid.lua": None,
 "lua/unicode.lua": None, "lua/number_translator.lua": None, "lua/calc_translator.lua": None,
 "lua/force_gc.lua": None, "lua/corrector.lua": None, "lua/autocap_filter.lua": None, "lua/v_filter.lua": None,
 "lua/pin_cand_filter.lua": None, "lua/long_word_filter.lua": None, "lua/reduce_english_filter.lua": None,
 "lua/search.lua": None, "lua/convert_ar_num_to_zh.lua": None, "lua/convert_ar_num_to_zh/init.lua": None,
}
BASE = "https://raw.githubusercontent.com/iDvel/rime-ice/main/"
DEST = "vue-WeChat/public/engine/rime-ice"
ok = miss = 0
for f, local in NEED.items():
    p = os.path.join(DEST, f)
    if os.path.exists(p):
        ok += 1; continue
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if local and os.path.exists(os.path.join(os.path.dirname(__file__), local)):
        import shutil
        shutil.copy2(os.path.join(os.path.dirname(__file__), local), p); ok += 1; continue
    try:
        req = urllib.request.Request(BASE + f, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
        with open(p, "wb") as fh: fh.write(data)
        ok += 1
    except Exception as e:
        miss += 1; print("miss", f, e)
print(f"ok={ok} miss={miss}")
total = sum(os.path.getsize(os.path.join(DEST, f)) for f in NEED if os.path.exists(os.path.join(DEST, f)))
print("totalKB=", round(total/1024))