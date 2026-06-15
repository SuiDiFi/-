# -*- coding: utf-8 -*-
import requests

# 测试所有 API 端点
print("=== 测试根路径 ===")
r = requests.get("http://127.0.0.1:8765/")
print(f"状态: {r.status_code}, 长度: {len(r.text)}")

print("\n=== 测试 /api/summary ===")
r = requests.get("http://127.0.0.1:8765/api/summary")
print(f"状态: {r.status_code}")

print("\n=== 测试 /api/chat ===")
r = requests.post("http://127.0.0.1:8765/api/chat", json={"prompt": "hi"})
print(f"状态: {r.status_code}")

print("\n=== 测试 /api/upload-and-analyze (空) ===")
r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze", json={})
print(f"状态: {r.status_code}, 响应: {r.text[:100]}")

print("\n=== 测试 /api/upload-and-analyze (假数据) ===")
r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze", json={"image": "x", "question": "test"})
print(f"状态: {r.status_code}, 响应: {r.text[:100]}")

print("\n=== 测试 /api/upload-and-analyze (真实图片) ===")
from PIL import Image
import io, base64

img = Image.new('RGB', (100, 100), color='blue')
buf = io.BytesIO()
img.save(buf, format='JPEG')
img_b64 = base64.b64encode(buf.getvalue()).decode()

r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze", 
                 json={"image": img_b64, "question": "描述这张图"})
print(f"状态: {r.status_code}")
print(f"响应: {r.text[:500] if r.text else '(空)'}")
