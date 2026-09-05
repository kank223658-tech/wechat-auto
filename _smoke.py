# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r"F:\weixin-auto")
os.chdir(r"F:\weixin-auto")
import main as M
b = M.WeChatAuto(headless=True)
M.ensure_frontend_running()
b.start()
import json
args = json.loads(json.dumps(getattr(b.browser, "_impl_obj", None) and getattr(b.browser, "_impl_obj", "?"))) if False else None
print("SMOKE OK")
b.stop()