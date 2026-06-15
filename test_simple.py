# -*- coding: utf-8 -*-
import requests

print("=== 测试空请求 ===\n")
try:
    r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze",
                     json={},
                     timeout=10)
    print("HTTP状态:", r.status_code)
    print("响应:", r.text[:200])
except Exception as e:
    print("异常:", e)

print("\n=== 测试简单请求 ===\n")
try:
    r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze",
                     json={
                         "image": "test",
                         "question": "测试"
                     },
                     timeout=10)
    print("HTTP状态:", r.status_code)
    print("响应:", r.text[:500])
except Exception as e:
    print("异常:", e)
