# -*- coding: utf-8 -*-
import requests

print('=== 测试意图识别 ===')

# 测试文本问答
r1 = requests.post('http://127.0.0.1:8765/api/chat', json={'prompt': '解释一下量子纠缠', 'stream': False})
d1 = r1.json()
print('1. 文本问答 -> 意图:', d1.get('intent', '未知'), ', 模型:', d1.get('model', '')[:30])

# 测试图片生成意图
r2 = requests.post('http://127.0.0.1:8765/api/chat', json={'prompt': '画一幅美丽的日落风景', 'stream': False})
d2 = r2.json()
print('2. 图片生成 -> 意图:', d2.get('intent', '未知'), ', 模型:', d2.get('model', '')[:30])

# 测试3D模型意图
r3 = requests.post('http://127.0.0.1:8765/api/chat', json={'prompt': '创建一个3D卡通角色模型', 'stream': False})
d3 = r3.json()
print('3. 3D模型 -> 意图:', d3.get('intent', '未知'), ', 模型:', d3.get('model', '')[:30])

# 测试视频意图
r4 = requests.post('http://127.0.0.1:8765/api/chat', json={'prompt': '生成一个跳舞的动画视频', 'stream': False})
d4 = r4.json()
print('4. 视频动画 -> 意图:', d4.get('intent', '未知'), ', 模型:', d4.get('model', '')[:30])

print()
print('=== 意图识别测试完成 ===')