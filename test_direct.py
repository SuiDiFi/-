# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"D:\哆来咪爆破")

from app import app, router

with app.test_client() as client:
    # 测试空请求
    print("=== 测试空请求 ===")
    r = client.post("/api/upload-and-analyze", json={})
    print(f"HTTP状态: {r.status_code}")
    print(f"响应: {r.get_json()}")
    
    # 测试简单请求
    print("\n=== 测试简单请求 ===")
    r = client.post("/api/upload-and-analyze", json={
        "image": "test",
        "question": "测试"
    })
    print(f"HTTP状态: {r.status_code}")
    print(f"响应: {r.get_json()}")
