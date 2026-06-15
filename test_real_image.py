# -*- coding: utf-8 -*-
import requests
import base64
from PIL import Image
import io
import os

os.environ["DASHSCOPE_API_KEY"] = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

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
    d = r.json()
    print("成功:", d.get("success"))
    if d.get("success"):
        print("模型:", d.get("model"))
        print("回复:", d.get("response", "")[:300], "...")
    else:
        print("错误:", d.get("error"))
except Exception as e:
    import traceback
    traceback.print_exc()
    print("异常:", e)
