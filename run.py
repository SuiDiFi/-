# -*- coding: utf-8 -*-
import os
import subprocess
import sys

# 设置环境变量
os.environ['VOLC_API_KEY'] = 'ark-6ffdce0b-648e-47b5-8682-7b7f18179522-5ba2a'
os.environ['DASHSCOPE_API_KEY'] = 'sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY'

# 检查依赖
try:
    import flask, yaml, requests
    print('✅ 依赖已就绪')
except ImportError:
    print('安装依赖...')
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'flask', 'pyyaml', 'requests'])

# 打开浏览器
import webbrowser
webbrowser.open('http://127.0.0.1:8765')

# 启动 Flask 服务
from app import app
app.run(host='127.0.0.1', port=8765, debug=False, threaded=True, use_reloader=False)
