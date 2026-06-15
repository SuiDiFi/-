# -*- coding: utf-8 -*-
import requests
import json

DASHSCOPE_API_KEY = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

# 测试常见的图像生成模型名
models_to_test = [
    "qwen-image-v2",
    "qwen-image-plus",
    "qwen-image-max",
    "qwen-image-turbo",
    "qwen-image-2512",
    "qwen2.5-image-2.0-pro",
    "qwen2.5-image-2.0-flash",
    "wanx-v1",
    "wanx-v2",
    "wanx-3.0-flash",
    "wanx-3.0-pro",
    "qwen3-image-flash",
    "qwen3-image-plus",
]

headers = {
    "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    "Content-Type": "application/json"
}

print("测试 DashScope 图像生成模型...\n")

for model_name in models_to_test:
    try:
        payload = {
            "model": model_name,
            "input": {"prompt": "一只小猫"},
            "parameters": {"size": "1024*1024"}
        }
        
        resp = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        result = resp.json()
        
        if result.get("output", {}).get("task_id") or (resp.status_code == 200 and result.get("code") != "InvalidParameter"):
            # 有任务ID说明模型可能有效（或至少被接受）
            code = result.get("code", "")
            msg = result.get("message", "")[:80]
            print(f"✅ {model_name:35s} -> status:{resp.status_code}, code:{code}, msg:{msg}")
            
            # 如果成功，进一步检查结果
            task_id = result.get("output", {}).get("task_id")
            if task_id:
                print(f"   -> 任务ID: {task_id}")
                # 轮询结果
                import time
                time.sleep(10)
                poll_resp = requests.get(f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}", 
                                         headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
                                         timeout=30)
                poll_data = poll_resp.json()
                print(f"   -> 状态: {poll_data.get('output', {}).get('task_status', 'N/A')}")
                print(f"   -> 数据: {json.dumps(poll_data.get('output', {}).get('results', []))[:200]}")
        else:
            print(f"❌ {model_name:35s} -> {resp.status_code}: {result.get('code', '')} {result.get('message', '')[:80]}")
    except Exception as e:
        print(f"⚠️ {model_name:35s} -> 异常: {e}")
