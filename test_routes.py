# -*- coding: utf-8 -*-
import sys
import os

os.environ["VOLC_API_KEY"] = "ark-6ffdce0b-648e-47b5-8682-7b7f18179522-5ba2a"
os.environ["DASHSCOPE_API_KEY"] = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

sys.path.insert(0, r"D:\哆来咪爆破")

from app import app

# 打印错误处理器
print("Error handlers:", app.error_handler_spec)

# 打印所有路由
print("\n所有路由:")
for rule in app.url_map.iter_rules():
    print(f"  {rule.endpoint}: {rule.methods}")
