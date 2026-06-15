# -*- coding: utf-8 -*-
import sys
import os

os.environ["VOLC_API_KEY"] = "ark-6ffdce0b-648e-47b5-8682-7b7f18179522-5ba2a"
os.environ["DASHSCOPE_API_KEY"] = "sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY"

sys.path.insert(0, r"D:\哆来咪爆破")

from app import app
from PIL import Image
import io, base64

# 创建一个真正的测试图片
img = Image.new('RGB', (100, 100), color='blue')
buf = io.BytesIO()
img.save(buf, format='JPEG')
img_b64 = base64.b64encode(buf.getvalue()).decode()

with app.test_client() as client:
    print("=== 测试图片分析 ===")
    r = client.post("/api/upload-and-analyze", json={
        "image": img_b64,
        "question": "描述这张图片"
    })
    print(f"HTTP状态: {r.status_code}")
    print(f"响应: {r.get_json()}")
