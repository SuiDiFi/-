# -*- coding: utf-8 -*-
import requests
import time

DASHSCOPE_API_KEY = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

headers = {
    "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    "Content-Type": "application/json"
}

models_to_test = [
    "qwen-image-plus",
    "wanx-v1",
    "wanx-v1.2",
    "qwen-image-v1",
    "qwen-image-2.0-pro",
]

task_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"

for model_name in models_to_test:
    print(f"\n测试模型: {model_name}")
    print("-" * 50)
    
    try:
        # 提交异步任务（X-DashScope-Async header）
        task_headers = dict(headers)
        task_headers["X-DashScope-Async"] = "enable"
        
        payload = {
            "model": model_name,
            "input": {"prompt": "一只可爱的小猫坐在花园里"},
            "parameters": {"size": "1024*1024"}
        }
        
        submit_resp = requests.post(task_url, headers=task_headers, json=payload, timeout=30)
        submit_data = submit_resp.json()
        print(f"提交结果: {submit_data}")
        
        task_id = submit_data.get("output", {}).get("task_id") or submit_data.get("task_id")
        
        if task_id:
            print(f"任务ID: {task_id}")
            
            # 轮询最多3次，每次等待10秒
            poll_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            for attempt in range(3):
                time.sleep(15)
                poll_resp = requests.get(poll_url, headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}, timeout=30)
                poll_data = poll_resp.json()
                status = poll_data.get("output", {}).get("task_status", "UNKNOWN")
                print(f"  轮询{attempt+1}: 状态={status}")
                
                if status == "SUCCEEDED":
                    results = poll_data.get("output", {}).get("results", [])
                    print(f"  ✅成功! 图片URL: {results[:2]}")
                    break
                elif status in ("FAILED", "ERROR"):
                    message = poll_data.get("output", {}).get("message", "未知错误")
                    print(f"  ❌失败: {message}")
                    break
        else:
            print(f"  未获取到任务ID")
            
    except Exception as e:
        print(f"  异常: {e}")
