# -*- coding: utf-8 -*-
import requests

print("=== 测试根路径 ===")
r = requests.get("http://127.0.0.1:8765/")
print(f"状态: {r.status_code}")
print(f"内容长度: {len(r.text)}")

print("\n=== 测试简单 POST ===")
r = requests.post("http://127.0.0.1:8765/api/chat",
                  json={"prompt": "hi"},
                  timeout=10)
print(f"状态: {r.status_code}")
print(f"响应: {r.text[:200]}")

print("\n=== 测试摘要 ===")
r = requests.get("http://127.0.0.1:8765/api/summary")
print(f"状态: {r.status_code}")
print(f"响应: {r.text[:200]}")
