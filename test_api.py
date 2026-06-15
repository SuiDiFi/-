# -*- coding: utf-8 -*-
import requests
import json

print('=== 测试聊天接口 ===')

# 测试1: 普通文本
print('\n1. 测试文本问答:')
try:
    r = requests.post('http://127.0.0.1:8765/api/chat', 
                     json={'prompt': '你好', 'stream': False},
                     timeout=30)
    print('HTTP状态:', r.status_code)
    d = r.json()
    print('成功:', d.get('success'))
    if d.get('success'):
        print('意图:', d.get('intent'))
        print('模型:', d.get('provider'), '/', d.get('model'))
        print('回复:', d.get('response', '')[:50], '...')
    else:
        print('错误:', d.get('error'))
except Exception as e:
    print('异常:', e)

# 测试2: 图片意图
print('\n2. 测试图片生成意图:')
try:
    r = requests.post('http://127.0.0.1:8765/api/chat', 
                     json={'prompt': '画一幅日落风景', 'stream': False},
                     timeout=30)
    print('HTTP状态:', r.status_code)
    d = r.json()
    print('成功:', d.get('success'))
    if d.get('success'):
        print('意图:', d.get('intent'))
        print('模型:', d.get('provider'), '/', d.get('model'))
    else:
        print('错误:', d.get('error'))
except Exception as e:
    print('异常:', e)

# 测试3: 获取摘要
print('\n3. 测试用量摘要:')
try:
    r = requests.get('http://127.0.0.1:8765/api/summary', timeout=10)
    print('HTTP状态:', r.status_code)
    d = r.json()
    print('模型总数:', d.get('total_models'))
    print('用量:', d.get('total_tokens_used'), '/', d.get('total_tokens_limit'))
except Exception as e:
    print('异常:', e)