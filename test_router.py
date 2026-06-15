# -*- coding: utf-8 -*-
import sys
import os

os.environ["VOLC_API_KEY"] = "ark-6ffdce0b-648e-47b5-8682-7b7f18179522-5ba2a"
os.environ["DASHSCOPE_API_KEY"] = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

sys.path.insert(0, r"D:\哆来咪爆破")

from app import router

# 测试 filter_models_by_type
vl_models = router.filter_models_by_type("image")
print(f"视觉模型数量: {len(vl_models)}")
print(f"视觉模型: {[m['name'] for m in vl_models[:5]]}")

# 过滤只选择 dashscope provider
vl_models = [m for m in vl_models if m.get("provider") == "dashscope"]
print(f"过滤后视觉模型数量: {len(vl_models)}")

# 测试 _pick_model
candidates = router._pick_model(100, None, vl_models)
print(f"候选模型数量: {len(candidates)}")
print(f"候选模型: {[c['name'] for c in candidates[:5]]}")
