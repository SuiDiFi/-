# -*- coding: utf-8 -*-
import requests
import base64
from PIL import Image
import io

# 创建一个简单的测试图片
img = Image.new('RGB', (200, 200), color=(73, 109, 137))
buf = io.BytesIO()
img.save(buf, format='JPEG')
img_b64 = base64.b64encode(buf.getvalue()).decode()

print("=== 测试图片分析 ===\n")
try:
    r = requests.post("http://127.0.0.1:8765/api/upload-and-analyze",
                     json={
                         "image": img_b64,
                         "question": "请描述这张图片的内容"
                     },
                     timeout=60)
    print("HTTP状态:", r.status_code)
    print("响应头:", dict(r.headers))
    print("响应内容:", r.text[:500] if r.text else "(空)")
    
    if r.status_code == 200:
        d = r.json()
        print("成功:", d.get("success"))
        if d.get("success"):
            print("模型:", d.get("model"))
            print("回复:", d.get("response", "")[:200], "...")
        else:
            print("错误:", d.get("error"))
except Exception as e:
    import traceback
    traceback.print_exc()
    print("异常:", e)
