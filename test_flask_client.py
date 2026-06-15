# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"D:\哆来咪爆破")

# 设置环境变量
import os
os.environ["DASHSCOPE_API_KEY"] = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

from app import app

with app.test_client() as client:
    # 测试简单请求
    print("=== 测试简单请求 ===")
    r = client.post("/api/upload-and-analyze", json={
        "image": "test",
        "question": "测试"
    })
    print(f"HTTP状态: {r.status_code}")
    print(f"响应: {r.get_json()}")
