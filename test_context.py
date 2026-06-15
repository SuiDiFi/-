# -*- coding: utf-8 -*-
import sys
import os

# 设置环境变量
os.environ["VOLC_API_KEY"] = "ark-6ffdce0b-648e-47b5-8682-7b7f18179522-5ba2a"
os.environ["DASHSCOPE_API_KEY"] = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

sys.path.insert(0, r"D:\哆来咪爆破")

from app import app

# 测试使用 test_request_context
with app.test_request_context('/api/upload-and-analyze', method='POST',
                              data='{"image":"test","question":"test"}',
                              content_type='application/json'):
    from flask import request
    print("request:", request)
    print("JSON:", request.get_json())
