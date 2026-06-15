# -*- coding: utf-8 -*-
import requests
import base64
from PIL import Image
import io

# 创建一个真正的测试图片
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
except Exception as e:
    import traceback
    traceback.print_exc()
    print("异常:", e)
