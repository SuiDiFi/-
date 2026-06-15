# -*- coding: utf-8 -*-
"""
Flask Web 聊天应用 —— 把 ModelRouter 封装成 HTTP 接口
- 路由:
    GET  /              -> 聊天页面
    POST /api/chat      -> 发送消息，返回流式/非流式响应
    GET  /api/summary   -> 返回用量摘要（JSON）

使用:
    set VOLC_API_KEY=xxx
    set DASHSCOPE_API_KEY=yyy
    python app.py
    浏览器打开 http://127.0.0.1:8765
"""

import json
import os
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, render_template, Response, stream_with_context

from model_router import ModelRouter


# ========= 初始化 =========
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # 让 jsonify 输出中文

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_config.yaml")

# 全局只初始化一次 ModelRouter
_logger = logging.getLogger("WebApp")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                                      datefmt="%m-%d %H:%M:%S"))
    _logger.addHandler(_h)

_logger.info(f"正在加载 ModelRouter (配置: {CONFIG_FILE}) ...")
router = ModelRouter(CONFIG_FILE, log_level=logging.INFO)
_logger.info(f"ModelRouter 就绪，共 {len(router.models)} 个模型")

# ========= 全局错误处理 =========
@app.errorhandler(Exception)
def handle_exception(e):
    _logger.error(f"全局异常: {e}")
    import traceback
    _logger.error(traceback.format_exc())
    return jsonify({"error": str(e), "success": False}), 500

@app.errorhandler(500)
def handle_500(e):
    _logger.error(f"500 错误: {e}")
    return jsonify({"error": "Internal Server Error", "success": False}), 500


# ========= 页面路由 =========
@app.route("/")
def index():
    return render_template("index.html")


# ========= API: 非流式聊天 =========
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    system = data.get("system") or "你是一个乐于助人的 AI 助手。回答简洁准确。"
    preferred_provider = data.get("prefer_provider") or None
    preferred_model = data.get("prefer_model") or None
    temperature = float(data.get("temperature") or 0.7)
    stream = bool(data.get("stream", False))
    model_type = data.get("model_type") or None  # 手动指定模型类型
    detect_intent = bool(data.get("detect_intent", True))  # 是否自动检测意图

    if not prompt:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

    # 限制单次输入长度，防止滥用（可按需调整）
    if len(prompt) > 8000:
        return jsonify({"success": False, "error": "消息太长啦 (>8000 字符)"}), 400

    _logger.info(f"收到消息 [{len(prompt)} chars], prefer={preferred_provider or 'auto'}/{preferred_model or 'auto'}, model_type={model_type}")

    if stream:
        return _chat_stream(prompt, system, preferred_provider, preferred_model, temperature, model_type, detect_intent)

    # 非流式
    t0 = time.time()
    result = router.chat(
        prompt=prompt,
        system=system,
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
        temperature=temperature,
        model_type=model_type,
        detect_intent=detect_intent,
    )
    cost_ms = int((time.time() - t0) * 1000)
    result["cost_ms"] = cost_ms
    result["server_time"] = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    status = 200 if result["success"] else 503
    resp = jsonify(result)
    resp.status_code = status
    return resp


def _chat_stream(prompt, system, preferred_provider, preferred_model, temperature, model_type=None, detect_intent=True):
    """
    简化版"流式"：我们的 Provider 实际上是非流式返回的，
    这里用 SSE (Server-Sent Events) 把完整结果一次性推给前端，
    前端在收到前显示"思考中..."，体验更像流式聊天。
    """
    def generate():
        t0 = time.time()
        result = router.chat(
            prompt=prompt,
            system=system,
            preferred_provider=preferred_provider,
            preferred_model=preferred_model,
            temperature=temperature,
            model_type=model_type,
            detect_intent=detect_intent,
        )
        cost_ms = int((time.time() - t0) * 1000)

        if result["success"]:
            content = result["response"] or ""
            # 按字符逐字推送（模拟打字机效果，看起来更自然）
            buf = ""
            step = max(1, len(content) // 80)  # 大约分 80 次推送
            for i in range(0, len(content), step):
                chunk = content[i:i + step]
                buf += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'tokens_used': result['tokens_used'], 'model': result['model'], 'provider': result['provider'], 'cost_ms': cost_ms, 'intent': result.get('intent', 'text')}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'error': result.get('error', '未知错误'), 'attempted_models': result.get('attempted_models', [])}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# ========= API: 图像生成 =========
@app.route("/api/generate-image", methods=["POST"])
def api_generate_image():
    """
    图像生成接口
    请求体: {
        "prompt": "一只可爱的小猫坐在月亮上",
        "size": "1024*1024",
        "reference_image": "base64编码的参考图（可选）"
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    size = data.get("size") or "1024*1024"
    reference_image = data.get("reference_image") or None

    if not prompt:
        return jsonify({"success": False, "error": "描述不能为空"}), 400

    # 限制长度
    if len(prompt) > 500:
        return jsonify({"success": False, "error": "描述太长"}), 400

    _logger.info(f"图像生成请求 [{prompt[:50]}] size={size}")

    t0 = time.time()
    result = router.generate_image(prompt, reference_image, size)
    cost_ms = int((time.time() - t0) * 1000)
    result["cost_ms"] = cost_ms

    status = 200 if result["success"] else 503
    resp = jsonify(result)
    resp.status_code = status
    return resp


# ========= API: 图片上传（使用视觉模型分析）=========
@app.route("/api/upload-and-analyze", methods=["POST"])
def api_upload_and_analyze():
    """
    上传图片并使用视觉模型进行分析
    请求体: {
        "image": "base64编码的图片",
        "question": "描述这张图片"  # 可选
    }
    """
    _logger.info("=== 图片分析请求开始 ===")
    try:
        data = request.get_json(force=True, silent=True) or {}
        _logger.info(f"JSON 解析成功，keys: {list(data.keys())}")
        image_b64 = data.get("image") or ""
        question = data.get("question") or "请描述这张图片的内容"

        if not image_b64:
            return jsonify({"success": False, "error": "没有上传图片"}), 400

        # 构建带图片的 messages
        image_url = f"data:image/jpeg;base64,{image_b64}" if not image_b64.startswith("data:") else image_b64
        messages = [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": question}
            ]}
        ]

        # 从路由器获取视觉模型列表（只选择 DashScopeProvider 的视觉模型）
        vl_models = router.filter_models_by_type("image")
        # 过滤掉图像生成模型（dashscope_image provider）
        vl_models = [m for m in vl_models if m.get("provider") == "dashscope"]
        _logger.info(f"找到视觉模型数量: {len(vl_models)}")
        _logger.info(f"视觉模型列表: {[m['name'] for m in vl_models[:5]]}")
        _logger.info(f"可用 Provider: {list(router.providers.keys())}")
        
        if not vl_models:
            # 回退：选择带 vl/vis 的模型（只选择 dashscope provider）
            vl_models = [m for m in router.models 
                        if ("vl" in m["name"].lower() or "vis" in m["name"].lower())
                        and m.get("provider") == "dashscope"]
            _logger.info(f"回退搜索 vl 模型: {len(vl_models)}")
        
        if not vl_models:
            return jsonify({"success": False, "error": "没有可用的视觉模型"}), 503

        # 按优先级排序，选择第一个可用模型
        candidates = router._pick_model(100, None, vl_models)
        _logger.info(f"候选模型数量: {len(candidates)}")
        
        last_error = "没有可用的视觉模型"
        for model_cfg in candidates[:5]:
            provider_name = model_cfg["provider"]
            model_name = model_cfg["name"]
            
            if provider_name not in router.providers:
                continue
                
            provider = router.providers[provider_name]
            _logger.info(f"尝试视觉模型: {provider_name}/{model_name}")
            
            try:
                result = provider.chat(model_name, messages, temperature=0.7)
                if result.get("success"):
                    _logger.info(f"视觉模型成功: {model_name}")
                    return jsonify(result)
                else:
                    last_error = result.get("error", "未知错误")
                    _logger.warning(f"视觉模型 {model_name} 失败: {last_error}")
            except Exception as e:
                last_error = str(e)
                _logger.error(f"视觉模型 {model_name} 异常: {e}")

        return jsonify({"success": False, "error": f"所有视觉模型均失败: {last_error}"}), 503
    except Exception as e:
        _logger.error(f"图片分析异常: {e}")
        import traceback
        _logger.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ========= API: 用量摘要 =========
@app.route("/api/summary")
def api_summary():
    """返回所有模型的用量摘要，供前端仪表盘使用"""
    models = []
    total_used = 0
    total_limit = 0
    blocked_count = 0

    for name, info in router.tracker.data.get("models", {}).items():
        used = int(info.get("tokens_used", 0))
        limit = int(info.get("daily_limit", 0))
        ratio = (used / limit * 100) if limit > 0 else 0
        blocked = bool(info.get("blocked"))
        if blocked:
            blocked_count += 1
        total_used += used
        total_limit += limit
        models.append({
            "name": name,
            "provider": info.get("provider"),
            "tokens_used": used,
            "daily_limit": limit,
            "ratio": round(ratio, 2),
            "calls": int(info.get("calls", 0)),
            "blocked": blocked,
        })

    models.sort(key=lambda m: (-m["ratio"], m["name"]))

    return jsonify({
        "date": router.tracker.data.get("date"),
        "total_models": len(models),
        "blocked_count": blocked_count,
        "total_tokens_used": total_used,
        "total_tokens_limit": total_limit,
        "total_ratio": round((total_used / total_limit * 100) if total_limit > 0 else 0, 2),
        "models": models[:60],  # 最多返回 60 个（最多消耗的）
    })


# ========= 启动 =========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "127.0.0.1")
    _logger.info(f"🌐 服务启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
