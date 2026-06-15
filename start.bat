@echo off
chcp 65001 >nul

set VOLC_API_KEY=ark-6ffdce0b-648e-47b5-8682-7b7f18179522-5ba2a
set DASHSCOPE_API_KEY=sk-ws-H.RELXYEY.Ad7O.MEUCIBy4na3T87NfUuSql9y80MoV8ErdhM8wISt2F59Mr6hiAiEA8c-hxdpYpxyOyFTbLVR89gkMMB5agyUHbnSGtp2MghY

python -c "import flask, yaml, requests" 2>nul
if errorlevel 1 (
  echo 正在安装依赖...
  pip install flask pyyaml requests
)

echo 启动服务...
start http://127.0.0.1:8765
python app.py
