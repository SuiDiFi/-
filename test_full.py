# -*- coding: utf-8 -*-
import requests
import json

print("=== 测试文本聊天 ===\n")
try:
    r = requests.post("http://127.0.0.1:8765/api/chat",
                      json={"prompt": "你好", "stream": False},
                      timeout=30)
    print("HTTP状态:", r.status_code)
    d = r.json()
    print("成功:", d.get("success"))
    if d.get("success"):
        print("意图:", d.get("intent"))
        print("模型:", d.get("provider"), "/", d.get("model"))
        print("回复:", d.get("response", "")[:80], "...")
    else:
        print("错误:", d.get("error"))
except Exception as e:
    print("异常:", e)

print("\n=== 测试图片生成 ===\n")
try:
    r = requests.post("http://127.0.0.1:8765/api/generate-image",
                      json={"prompt": "一只可爱的小猫", "size": "1024*1024"},
                      timeout=120)
    print("HTTP状态:", r.status_code)
    d = r.json()
    print("成功:", d.get("success"))
    if d.get("success"):
        print("图片数量:", len(d.get("image_urls", [])))
        for i, url in enumerate(d.get("image_urls", [])):
            print(f"  图片{i+1}: {url[:80]}...")
    else:
        print("错误:", d.get("error"))
except Exception as e:
    print("异常:", e)

print("\n=== 测试用量摘要 ===\n")
try:
    r = requests.get("http://127.0.0.1:8765/api/summary", timeout=10)
    print("HTTP状态:", r.status_code)
    d = r.json()
    print("模型总数:", d.get("total_models"))
    print("用量:", d.get("total_tokens_used"), "/", d.get("total_tokens_limit"))
except Exception as e:
    print("异常:", e)
