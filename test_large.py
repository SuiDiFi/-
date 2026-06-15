# -*- coding: utf-8 -*-
import requests

# 测试大 JSON
large_data = {"image": "x" * 10000, "question": "test"}

print("=== 测试大 JSON ===")
r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze", json=large_data)
print(f"状态: {r.status_code}")
print(f"响应: {r.text[:200]}")
