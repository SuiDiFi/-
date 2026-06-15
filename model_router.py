# -*- coding: utf-8 -*-
"""
Model Router - 自动检测免费额度 + 自动切换模型的智能路由层
================================================================

核心功能：
    1. 预算预检查：调用前估算 tokens，确保不会超免费额度
    2. 加权路由：按模型剩余额度比例 + 优先级，自动选最富余的模型
    3. 用量追踪：每次调用精确累加，写 JSON 文件持久化
    4. 0 点重置：北京时间 0 点自动重置所有模型的当日用量
    5. 错误熔断：收到配额类错误立刻 BLOCK 该模型，切下一个重试
    6. 双阈值：90% 软阈值（降低权重），97% 硬阈值（直接 BLOCK）

使用示例：
    >>> from model_router import ModelRouter
    >>> router = ModelRouter("models_config.yaml")
    >>> result = router.chat("你好，介绍一下你自己")
    >>> print(result["response"])
    >>> print(f"使用模型: {result['model']}, 消耗: {result['tokens_used']} tokens")
"""

import json
import os
import re
import sys
import time
import random
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List, Any, Tuple

import requests
import yaml


# ============================================================
#   时区与时间工具
# ============================================================
TZ = ZoneInfo("Asia/Shanghai")


def today_str() -> str:
    """返回北京时间的日期字符串 yyyy-mm-dd"""
    return datetime.now(TZ).strftime("%Y-%m-%d")


def now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
#   Token 估算（简化版：按字符数粗略估算）
# ============================================================
def estimate_input_tokens(messages: List[Dict[str, str]]) -> int:
    """
    估算输入消息的 token 总数（保守高估 1.5 倍，宁多勿少）

    中文约 1.5 chars/token，英文约 4 chars/token，这里按保守 1.0 chars/token 计算
    实际上各家分词器不同，所以我们乘一个安全系数高估
    """
    total_chars = 0
    for msg in messages:
        if isinstance(msg.get("content"), str):
            total_chars += len(msg["content"])
        # role 也占一些 token
        total_chars += len(msg.get("role", ""))
    # 保守高估：chars * 1.2 + 每条消息 10 tokens 的格式开销
    estimated = int(total_chars * 1.2) + len(messages) * 10
    return max(estimated, 1)


# ============================================================
#   意图识别（判断用户是否想要生成图片/视频）
# ============================================================
class IntentDetector:
    """
    基于关键词的意图识别器，判断用户是否想要生成图片/视频/3D模型
    
    支持的意图类型：
        - text: 普通文本问答
        - image: 图片生成
        - image_3d: 3D模型生成
        - video: 视频生成/动画生成
    """
    
    # 图片生成关键词
    IMAGE_KEYWORDS = [
        "画", "画一幅", "画一个", "生成图片", "生成图", "创作图片",
        "图片", "图像", "照片", "照片生成", "photo", "image",
        "生成", "创作", "制作", "设计",
        "二次元", "动漫", "插画", "壁纸", "海报", "封面",
        "素描", "水彩", "油画", "摄影", "写实", "风格",
        "AI绘图", "AI生成", "stable diffusion", "midjourney", "dalle"
    ]
    
    # 3D模型关键词
    IMAGE_3D_KEYWORDS = [
        "3d", "3D", "三维", "立体", "建模", "模型",
        "渲染", "blender", "cinema4d", "maya"
    ]
    
    # 视频/动画关键词
    VIDEO_KEYWORDS = [
        "视频", "动画", "动图", "gif", "短片",
        "跳舞", "舞蹈", "动作", "动画生成", "视频生成"
    ]
    
    @classmethod
    def detect(cls, text: str) -> str:
        """检测用户意图，返回意图类型"""
        text_lower = text.lower().strip()
        
        # 先检查3D
        for kw in cls.IMAGE_3D_KEYWORDS:
            if kw.lower() in text_lower:
                return "image_3d"
        
        # 再检查视频
        for kw in cls.VIDEO_KEYWORDS:
            if kw.lower() in text_lower:
                return "video"
        
        # 最后检查图片
        for kw in cls.IMAGE_KEYWORDS:
            if kw.lower() in text_lower:
                return "image"
        
        # 默认文本问答
        return "text"
    
    @classmethod
    def is_image_intent(cls, text: str) -> bool:
        intent = cls.detect(text)
        return intent in ("image", "image_3d", "video")


# ============================================================
#   用量追踪器
# ============================================================
class UsageTracker:
    """
    负责维护每个模型的当日用量与状态，持久化到 JSON 文件。

    存储结构（usage.json）：
    {
        "date": "2026-06-15",
        "models": {
            "DeepSeek-V4-flash": {
                "provider": "volc_ark",
                "daily_limit": 500000,
                "tokens_used": 148,
                "calls": 1,
                "last_call": "2026-06-15 14:23:01",
                "blocked": false,
                "block_reason": null,
                "avg_output_tokens": 850
            }
        }
    }
    """

    def __init__(self, persistent_file: str, logger: logging.Logger):
        self.file = persistent_file
        self.logger = logger
        self.data = {"date": today_str(), "models": {}}
        self._load()

    # --------- 持久化 ---------
    def _load(self):
        if not os.path.exists(self.file):
            self._save()
            return
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 日期不匹配 → 重置
            if data.get("date") != today_str():
                self.logger.info(f"日期变更: {data.get('date')} -> {today_str()}, 重置所有模型用量")
                self._save()
                return
            self.data = data
        except Exception as e:
            self.logger.warning(f"读取 {self.file} 失败: {e}, 重建空记录")
            self._save()

    def _save(self):
        tmp = self.file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.file)  # 原子替换，防写坏

    # --------- 公共接口 ---------
    def ensure_model(self, model_name: str, provider: str, daily_limit: int):
        """确保模型已初始化记录"""
        m = self.data["models"].get(model_name)
        if m is None or m.get("daily_limit") != daily_limit or m.get("provider") != provider:
            self.data["models"][model_name] = {
                "provider": provider,
                "daily_limit": daily_limit,
                "tokens_used": 0,
                "calls": 0,
                "last_call": None,
                "blocked": False,
                "block_reason": None,
                "avg_output_tokens": 0,  # 滑动平均
                "_output_accum": 0,      # 内部累加器
            }
            self._save()
        return self.data["models"][model_name]

    def get(self, model_name: str) -> Optional[Dict[str, Any]]:
        return self.data["models"].get(model_name)

    def remaining(self, model_name: str) -> int:
        m = self.data["models"].get(model_name)
        if not m:
            return 0
        return m["daily_limit"] - m["tokens_used"]

    def remaining_ratio(self, model_name: str) -> float:
        m = self.data["models"].get(model_name)
        if not m:
            return 1.0
        return max(0.0, 1.0 - m["tokens_used"] / m["daily_limit"])

    def is_blocked(self, model_name: str) -> bool:
        m = self.data["models"].get(model_name)
        return bool(m and m.get("blocked"))

    def add_usage(self, model_name: str, total_tokens: int, output_tokens: int):
        """累加用量 + 更新滑动平均输出长度"""
        m = self.data["models"].get(model_name)
        if not m:
            return
        m["tokens_used"] += total_tokens
        m["calls"] += 1
        m["last_call"] = now_str()
        # 滑动平均输出 tokens（新值占 30% 权重，历史占 70%）
        if m["avg_output_tokens"] == 0:
            m["avg_output_tokens"] = output_tokens
        else:
            m["avg_output_tokens"] = int(m["avg_output_tokens"] * 0.7 + output_tokens * 0.3)
        self._save()

    def block(self, model_name: str, reason: str):
        m = self.data["models"].get(model_name)
        if m:
            m["blocked"] = True
            m["block_reason"] = reason
            self.logger.warning(f"BLOCK 模型 [{model_name}], 原因: {reason}")
            self._save()

    def check_and_reset_date(self):
        """每次调用前检查日期，跨日则重置"""
        if self.data.get("date") != today_str():
            self.logger.info(f"触发日期重置: {self.data.get('date')} -> {today_str()}")
            new_models = {}
            for name, old in self.data["models"].items():
                # 保留配置元信息，清零用量与 BLOCK 状态
                new_models[name] = {
                    "provider": old["provider"],
                    "daily_limit": old["daily_limit"],
                    "tokens_used": 0,
                    "calls": 0,
                    "last_call": None,
                    "blocked": False,
                    "block_reason": None,
                    "avg_output_tokens": old.get("avg_output_tokens", 0),  # 历史平均保留
                    "_output_accum": 0,
                }
            self.data = {"date": today_str(), "models": new_models}
            self._save()

    def summary(self) -> str:
        """返回所有模型的用量摘要，供 CLI 查询使用"""
        total_used = 0
        total_limit = 0
        lines = []
        lines.append(f"=== 用量摘要 ({today_str()}) ===")
        for name, m in sorted(self.data["models"].items()):
            used = m["tokens_used"]
            limit = m["daily_limit"]
            ratio = used / limit * 100
            bar = "█" * int(ratio / 2) + "░" * (50 - int(ratio / 2))
            status = "🔴BLOCK" if m["blocked"] else "✅OK"
            lines.append(
                f"{status} [{m['provider']}] {name:<40s} "
                f"{bar} {used:>8d}/{limit:<8d} ({ratio:5.1f}%)"
                f"  calls:{m['calls']} avg_out:{m.get('avg_output_tokens', 0)}"
            )
            total_used += used
            total_limit += limit
        lines.append(f"汇总: {total_used:,} / {total_limit:,} tokens "
                     f"({total_used/total_limit*100:.2f}%)")
        return "\n".join(lines)


# ============================================================
#   Provider 适配层
# ============================================================
class BaseProvider:
    """统一接口，子类只需实现 _build_request 与 _parse_response/_is_quota_error"""

    def __init__(self, api_key: str, timeout: int = 60):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ------- 子类实现 -------
    def endpoint(self) -> str:
        raise NotImplementedError

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # ------- 公共调用 -------
    def chat(self, model_name: str, messages: List[Dict[str, str]],
             temperature: float = 0.7, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        调用模型，返回统一格式：
        {
            "success": True/False,
            "response": "模型输出文本",
            "total_tokens": 1234,
            "output_tokens": 567,
            "model": "实际使用的模型名",
            "error": "错误信息（失败时）",
            "is_quota_error": True/False,
        }
        """
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            resp = self.session.post(
                self.endpoint(),
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"网络错误: {type(e).__name__}: {e}",
                "is_quota_error": False,
                "total_tokens": 0,
                "output_tokens": 0,
            }

        # 非 200
        if resp.status_code != 200:
            text = resp.text[:500]
            is_quota = self._is_status_quota_error(resp.status_code, text)
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {text}",
                "is_quota_error": is_quota,
                "total_tokens": 0,
                "output_tokens": 0,
            }

        # 解析 JSON
        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "error": f"响应非 JSON: {resp.text[:300]}",
                "is_quota_error": False,
                "total_tokens": 0,
                "output_tokens": 0,
            }

        # OpenAI 兼容格式：choices[0].message.content
        content = ""
        choices = data.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content", "")
        else:
            # 某些平台的其他格式
            content = data.get("output", {}).get("text", "") if isinstance(data.get("output"), dict) else ""
            if not content:
                content = data.get("text", "") or data.get("result", "") or str(data)

        usage = data.get("usage") or {}
        total_tokens = int(usage.get("total_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)

        # 如果没返回 usage，按字符数估算（保底，防止漏记）
        if total_tokens == 0:
            total_tokens = estimate_input_tokens(messages) + int(len(str(content)) * 1.2)
            output_tokens = int(len(str(content)) * 1.2)

        return {
            "success": True,
            "response": content,
            "total_tokens": total_tokens,
            "output_tokens": output_tokens,
            "model": data.get("model", model_name),
        }

    # ------- 配额错误识别（可被子类覆盖）-------
    _QUOTA_KEYWORDS = [
        "quota", "insufficient", "exceed", "limit", "额度", "限额", "超限",
        "rate limit", "rate_limit", "429", "throttl",
        "余额不足", "欠费", "balance", "out of",
    ]

    def _is_status_quota_error(self, status_code: int, text: str) -> bool:
        """基于 HTTP 状态码 + 响应文本的启发式识别配额错误"""
        text_lower = text.lower()
        if status_code in (402, 429):
            return True
        for kw in self._QUOTA_KEYWORDS:
            if kw.lower() in text_lower:
                return True
        return False


class VolcArkProvider(BaseProvider):
    """火山方舟"""

    def endpoint(self) -> str:
        return "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

    # 火山还有一种错误格式，在响应体里用 code/msg，父类的关键词匹配已经足够
    _QUOTA_KEYWORDS = BaseProvider._QUOTA_KEYWORDS + [
        "InsufficientQuota", "QuotaExhausted", "BillingQuotaExhausted",
    ]


class DashScopeProvider(BaseProvider):
    """阿里云百炼（OpenAI 兼容模式）"""

    def endpoint(self) -> str:
        return "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    _QUOTA_KEYWORDS = BaseProvider._QUOTA_KEYWORDS + [
        "InvalidApiKey", "AccessDenied", "ApiKeyExpired",
        "Throttling", "Throttling.RateExceeded",
    ]


class DashScopeImageProvider:
    """
    阿里云百炼图像生成 - 使用 DashScope 的异步任务模式
    支持: qwen2.5-image-2.0-pro, qwen2.5-image-2.0-flash 等
    """

    def __init__(self, api_key: str, timeout: int = 300):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        })

    def generate(self, model_name: str, prompt: str, 
                 reference_image: str = None,  # base64 编码的参考图
                 size: str = "1024*1024") -> Dict[str, Any]:
        """
        文生图 / 图生图（两步：先提交任务，再轮询结果）
        
        返回: {
            "success": True/False,
            "image_urls": ["https://...", "..."],
            "total_tokens": 1,  # 图像模型按"张"计费
            "output_tokens": 1,
            "model": model_name,
            "error": "错误信息",
            "is_quota_error": True/False,
        }
        """
        # 1. 提交任务
        task_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        payload = {
            "model": model_name,
            "input": {"prompt": prompt},
            "parameters": {"size": size},
        }
        
        # 如果有参考图，添加到输入
        if reference_image:
            payload["input"]["reference_image"] = reference_image

        try:
            resp = self.session.post(task_url, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"网络错误: {type(e).__name__}: {e}",
                "is_quota_error": False,
                "image_urls": [],
                "total_tokens": 0,
                "output_tokens": 0,
            }

        if resp.status_code != 200:
            text = resp.text[:500]
            is_quota = ("quota" in text.lower() or 
                      "insufficient" in text.lower() or
                      "limit" in text.lower() or
                      "exceed" in text.lower())
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {text}",
                "is_quota_error": is_quota,
                "image_urls": [],
                "total_tokens": 0,
                "output_tokens": 0,
            }

        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "error": f"响应非 JSON: {resp.text[:300]}",
                "is_quota_error": False,
                "image_urls": [],
                "total_tokens": 0,
                "output_tokens": 0,
            }

        # 获取任务ID
        task_id = data.get("output", {}).get("task_id") or data.get("task_id")
        if not task_id:
            return {
                "success": False,
                "error": f"未获取到任务ID: {data}",
                "is_quota_error": False,
                "image_urls": [],
                "total_tokens": 0,
                "output_tokens": 0,
            }

        # 2. 轮询结果（最多 180 秒，图像生成可能需要 10-40 秒）
        result_url = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}".format(task_id=task_id)
        max_wait = 180
        waited = 0
        poll_interval = 10
        
        while waited < max_wait:
            try:
                poll_resp = self.session.get(result_url, timeout=self.timeout)
                if poll_resp.status_code != 200:
                    time.sleep(poll_interval)
                    waited += poll_interval
                    continue

                poll_data = poll_resp.json()
                status = poll_data.get("output", {}).get("task_status")

                if status == "SUCCEEDED":
                    # 获取图片URL
                    results = poll_data.get("output", {}).get("results", [])
                    image_urls = []
                    for item in results:
                        if isinstance(item, dict) and item.get("url"):
                            image_urls.append(item["url"])
                    return {
                        "success": True,
                        "image_urls": image_urls,
                        "total_tokens": 1,  # 图像模型按张计算
                        "output_tokens": 1,
                        "model": model_name,
                    }
                elif status in ("FAILED", "ERROR"):
                    message = poll_data.get("output", {}).get("message", str(poll_data))
                    is_quota = ("quota" in message.lower() or 
                               "insufficient" in message.lower() or
                               "limit" in message.lower() or
                               "exceed" in message.lower())
                    return {
                        "success": False,
                        "error": f"任务失败: {message}",
                        "is_quota_error": is_quota,
                        "image_urls": [],
                        "total_tokens": 0,
                        "output_tokens": 0,
                    }
                else:
                    # 仍在处理中
                    time.sleep(poll_interval)
                    waited += poll_interval
            except requests.RequestException:
                time.sleep(poll_interval)
                waited += poll_interval

        return {
            "success": False,
            "error": f"图像生成超时({max_wait}秒未完成)",
            "is_quota_error": False,
            "image_urls": [],
            "total_tokens": 0,
            "output_tokens": 0,
        }


# ============================================================
#   ModelRouter - 主入口
# ============================================================
class ModelRouter:
    """
    核心路由类：从 YAML 读取模型配置，维护 Provider，选模型，调用。

    用法：
        router = ModelRouter("models_config.yaml")
        result = router.chat("你好")
        print(result["response"])
    """

    def __init__(self, config_file: str, log_level=logging.INFO):
        self.config_file = config_file
        self.logger = self._setup_logger(log_level)
        self.cfg = self._load_config()

        g = self.cfg["global"]
        self.soft_pct = g["soft_threshold_pct"] / 100.0
        self.hard_pct = g["hard_threshold_pct"] / 100.0
        self.safety_pct = g["safety_buffer_pct"] / 100.0
        self.default_estimated_output = g["default_estimated_output_tokens"]

        # 展开：每个模型 → 独立配置项
        self.models: List[Dict[str, Any]] = []  # [{name, provider, daily_limit, priority, base_weight}]
        self._expand_models()

        # 初始化用量追踪器
        self.tracker = UsageTracker(g["persistent_file"], self.logger)
        for m in self.models:
            self.tracker.ensure_model(m["name"], m["provider"], m["daily_limit"])

        # 初始化 Provider
        api_keys = g["api_keys"]
        volc_key = self._resolve_api_key(api_keys.get("volc_ark", ""))
        dash_key = self._resolve_api_key(api_keys.get("dashscope", ""))
        self.providers: Dict[str, Any] = {}
        if volc_key and volc_key != "":
            self.providers["volc_ark"] = VolcArkProvider(volc_key)
        else:
            self.logger.warning("VOLC_API_KEY 未设置，火山模型将被跳过")
        if dash_key and dash_key != "":
            self.providers["dashscope"] = DashScopeProvider(dash_key)
            self.providers["dashscope_image"] = DashScopeImageProvider(dash_key)
        else:
            self.logger.warning("DASHSCOPE_API_KEY 未设置，百炼模型将被跳过")

        if not self.providers:
            self.logger.error("⚠️  没有任何可用 Provider，请设置 API Key！")

        self.logger.info(f"ModelRouter 初始化完成: {len(self.models)} 个模型, "
                         f"{len(self.providers)} 个 Provider")

    # -------- 初始化辅助 --------
    def _setup_logger(self, level) -> logging.Logger:
        logger = logging.getLogger("ModelRouter")
        logger.setLevel(level)
        if not logger.handlers:
            h = logging.StreamHandler(sys.stdout)
            h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                                             datefmt="%m-%d %H:%M:%S"))
            logger.addHandler(h)
        return logger

    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_file, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not cfg or "global" not in cfg:
            raise ValueError("配置文件缺少 global 段")
        return cfg

    def _expand_models(self):
        """把 YAML 里按组的模型展开成一维列表"""
        for section_key, section in self.cfg.items():
            if section_key == "global":
                continue
            if not isinstance(section, dict) or "models" not in section:
                continue
            if section.get("disabled"):
                self.logger.info(f"跳过禁用组: {section_key}")
                continue
            model_type = section.get("model_type", "text")
            for model_name in section["models"]:
                self.models.append({
                    "name": model_name,
                    "provider": section["provider"],
                    "daily_limit": int(section["daily_limit"]),
                    "priority": section.get("priority", 1),
                    "base_weight": float(section.get("base_weight", 1.0)),
                    "model_type": model_type,
                })
        # 按 priority 降序预排一次，保证优先级高的在同等条件下先被尝试
        self.models.sort(key=lambda x: (-x["priority"], -x["daily_limit"]))
        self.logger.info(f"展开得到 {len(self.models)} 个模型")

    def filter_models_by_type(self, model_type: str) -> List[Dict[str, Any]]:
        """按模型类型筛选模型"""
        if not model_type or model_type == "text":
            return [m for m in self.models if m["model_type"] == "text"]
        # 图片意图可以匹配多种类型
        if model_type in ("image", "image_3d", "video"):
            return [m for m in self.models if m["model_type"] in ("image", "image_3d", "text_to_image")]
        return [m for m in self.models if m["model_type"] == model_type]

    @staticmethod
    def _resolve_api_key(val: str) -> str:
        """支持 ${ENV_VAR} 语法读取环境变量"""
        if not val:
            return ""
        m = re.match(r"^\$\{([A-Z_][A-Z0-9_]*)\}$", val.strip())
        if m:
            return os.environ.get(m.group(1), "")
        return val

    # -------- 预算检查 --------
    def _estimate_output(self, model_name: str) -> int:
        """估算输出长度：优先用历史平均值，否则用默认值"""
        m = self.tracker.get(model_name)
        if m and m.get("avg_output_tokens", 0) > 0:
            # 取历史平均值的 1.2 倍作为保守估算
            return int(m["avg_output_tokens"] * 1.2)
        return self.default_estimated_output

    def _check_budget(self, model_cfg: Dict[str, Any], input_tokens_est: int) -> Tuple[bool, str]:
        """
        返回 (是否允许调用, 详细原因)
        """
        name = model_cfg["name"]
        m = self.tracker.get(name)
        if not m:
            return False, "模型未初始化"

        if m["blocked"]:
            return False, f"模型已 BLOCK ({m.get('block_reason', '')})"

        hard_limit = model_cfg["daily_limit"] * self.hard_pct
        if m["tokens_used"] >= hard_limit:
            return False, f"已达硬阈值 ({m['tokens_used']} / {int(hard_limit)})"

        estimated_output = self._estimate_output(name)
        safety_buffer = int(model_cfg["daily_limit"] * self.safety_pct)
        projected = m["tokens_used"] + input_tokens_est + estimated_output + safety_buffer

        if projected > model_cfg["daily_limit"]:
            return False, (f"预估超限额: used({m['tokens_used']}) + in({input_tokens_est}) "
                           f"+ out({estimated_output}) + buf({safety_buffer}) = {projected} "
                           f"> limit({model_cfg['daily_limit']})")
        return True, "OK"

    # -------- 模型选择算法 --------
    def _pick_model(self, input_tokens_est: int,
                    preferred_provider: Optional[str] = None,
                    model_list: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        按分数从高到低返回候选模型列表。
        分数 = 剩余比例 * priority * base_weight * (soft_threshold 后的衰减)
        
        参数：
            model_list: 可选的模型列表，不传则使用全部模型
        """
        candidates = []
        models_to_check = model_list if model_list else self.models
        
        for model_cfg in models_to_check:
            # 只选可用的 Provider
            if model_cfg["provider"] not in self.providers:
                continue
            # Provider 偏好
            if preferred_provider and model_cfg["provider"] != preferred_provider:
                continue

            ok, _ = self._check_budget(model_cfg, input_tokens_est)
            if not ok:
                continue

            name = model_cfg["name"]
            remaining_ratio = self.tracker.remaining_ratio(name)

            # 超过软阈值后做衰减：剩余比例从 10% 开始权重逐渐降低
            soft_threshold = self.soft_pct
            if remaining_ratio < (1.0 - soft_threshold):
                decay = remaining_ratio / (1.0 - soft_threshold)
                decay = max(0.1, decay)
            else:
                decay = 1.0

            score = remaining_ratio * model_cfg["priority"] * model_cfg["base_weight"] * decay
            candidates.append((score, model_cfg))

        # 按 score 降序
        candidates.sort(key=lambda x: -x[0])
        return [c[1] for c in candidates]

    # -------- 主调用入口 --------
    def chat(self, prompt: str, system: str = None,
             preferred_model: str = None,
             preferred_provider: str = None,
             temperature: float = 0.7,
             max_tokens: Optional[int] = None,
             max_retries_per_model: int = 1,
             max_total_attempts: int = 5,
             detect_intent: bool = True,
             model_type: str = None) -> Dict[str, Any]:
        """
        发起一次聊天，自动选择 & 切换模型。

        参数：
            prompt: 用户输入
            system: 可选的 system prompt
            preferred_model: 优先尝试某个具体模型（如 "DeepSeek-V4-flash"）
            preferred_provider: 优先尝试某平台（"volc_ark" 或 "dashscope"）
            temperature, max_tokens: 传递给模型
            max_retries_per_model: 单个模型重试次数（非配额类错误才重试）
            max_total_attempts: 最多尝试多少个不同模型
            detect_intent: 是否自动检测用户意图（图片生成等）
            model_type: 指定模型类型（text/image/image_3d/video），设为 None 则自动检测

        返回：
            dict: {success, response, model, provider, tokens_used, total_attempts,
                   attempted_models, error, intent}
        """
        # 1. 日期检查（0 点重置）
        self.tracker.check_and_reset_date()

        # 2. 意图检测
        detected_intent = model_type
        if detect_intent and not model_type:
            detected_intent = IntentDetector.detect(prompt)
        self.logger.info(f"检测意图: {detected_intent}")

        # 3. 构造 messages
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        input_tokens_est = estimate_input_tokens(messages)

        # 4. 根据意图筛选模型
        filtered_models = self.filter_models_by_type(detected_intent)
        self.logger.info(f"意图 {detected_intent} 筛选出 {len(filtered_models)} 个模型")
        
        # 如果该类型没有可用模型，回退到文本模型
        if not filtered_models and detected_intent != "text":
            self.logger.warning(f"意图 {detected_intent} 没有可用模型，回退到文本模型")
            filtered_models = self.filter_models_by_type("text")
            detected_intent = "text"  # 更新意图为文本

        # 5. 构造候选队列
        candidates: List[Dict[str, Any]] = []

        # 如果指定了优先模型，先试它
        if preferred_model:
            for m in filtered_models:
                if m["name"].lower() == preferred_model.lower():
                    ok, reason = self._check_budget(m, input_tokens_est)
                    if ok and m["provider"] in self.providers:
                        candidates.append(m)
                    else:
                        self.logger.info(f"优先模型 [{m['name']}] 不满足预算: {reason}")
                    break

        # 其余候选按分数排序
        normal_candidates = self._pick_model(input_tokens_est, preferred_provider, filtered_models)
        for c in normal_candidates:
            if c not in candidates:  # 避免重复
                candidates.append(c)

        if not candidates:
            return {
                "success": False,
                "error": "没有任何模型满足预算要求（全部达阈值或已 BLOCK）",
                "attempted_models": [],
                "total_attempts": 0,
            }

        self.logger.info(f"候选模型: {[c['name'] for c in candidates[:5]]}... (共 {len(candidates)} 个)")

        # 4. 逐个尝试
        last_error = ""
        attempted = []
        attempts = 0

        for model_cfg in candidates[:max_total_attempts]:
            name = model_cfg["name"]
            provider_key = model_cfg["provider"]
            provider = self.providers[provider_key]

            attempts += 1
            attempted.append(name)

            # 重试循环（非配额错误才重试）
            for retry in range(max_retries_per_model + 1):
                self.logger.info(f"[{attempts}/{min(len(candidates), max_total_attempts)}] "
                                 f"尝试 {provider_key}:{name} (retry={retry})")

                result = provider.chat(name, messages, temperature=temperature, max_tokens=max_tokens)

                if result["success"]:
                    # 记账
                    self.tracker.add_usage(name, result["total_tokens"], result["output_tokens"])
                    self.logger.info(f"✅ {name} 成功, tokens={result['total_tokens']} "
                                     f"(剩余 {self.tracker.remaining(name):,})")
                    return {
                        "success": True,
                        "response": result["response"],
                        "model": result["model"],
                        "provider": provider_key,
                        "tokens_used": result["total_tokens"],
                        "total_attempts": attempts,
                        "attempted_models": attempted,
                        "intent": detected_intent,
                    }

                # 调用失败
                last_error = result.get("error", "")
                self.logger.warning(f"❌ {name} 失败: {last_error}")

                if result.get("is_quota_error"):
                    # 配额错误 → BLOCK 该模型，切下一个
                    self.tracker.block(name, f"quota_error: {last_error[:80]}")
                    break  # 跳出重试循环，切下一模型
                else:
                    # 其他错误 → 重试
                    if retry < max_retries_per_model:
                        time.sleep(0.5 * (retry + 1))  # 退避
                        continue
                    # 非配额错误过多，标记 BLOCK 10 分钟（这里简单处理：不 BLOCK，让它继续下一个）
                    break

        # 全部模型都试失败了
        return {
            "success": False,
            "error": f"所有候选模型均失败 ({len(attempted)} 个). 最后错误: {last_error}",
            "attempted_models": attempted,
            "total_attempts": attempts,
        }

    # -------- 图像生成 --------
    def generate_image(self, prompt: str, reference_image: str = None,
                       size: str = "1024*1024", max_attempts: int = 3) -> Dict[str, Any]:
        """
        文生图/图生图，自动选择额度充足的图像模型。
        
        参数:
            prompt: 图片描述提示词
            reference_image: base64编码的参考图片（可选）
            size: 图片尺寸，如 "1024*1024"
            max_attempts: 最多尝试多少个不同模型
            
        返回: {
            "success": True/False,
            "image_urls": ["...", "..."],
            "model": "qwen2.5-image-2.0-pro",
            "provider": "dashscope_image",
            "tokens_used": 1,
            "error": "错误信息"
        }
        """
        # 1. 日期检查
        self.tracker.check_and_reset_date()

        # 2. 筛选可用图像生成模型
        image_models = [m for m in self.models 
                       if m.get("model_type") == "text_to_image" 
                       and m["provider"] in self.providers]
        
        if not image_models:
            return {
                "success": False,
                "error": "没有可用的图像生成模型，请检查配置",
                "image_urls": [],
                "tokens_used": 0,
            }

        # 3. 按剩余额度排序
        image_models.sort(key=lambda m: (-self.tracker.remaining_ratio(m["name"]), -m.get("priority", 0)))

        # 4. 逐个尝试
        last_error = ""
        for model_cfg in image_models[:max_attempts]:
            name = model_cfg["name"]
            
            # 检查是否已 BLOCK
            if self.tracker.is_blocked(name):
                self.logger.info(f"跳过已 BLOCK 的模型: {name}")
                continue
            
            # 检查额度
            remaining = self.tracker.remaining(name)
            if remaining <= 0:
                self.logger.info(f"模型 {name} 额度用尽，跳过")
                self.tracker.block(name, "daily_limit_reached")
                continue

            self.logger.info(f"尝试图像生成: {name} (剩余{remaining}张)")

            try:
                provider = self.providers["dashscope_image"]
                result = provider.generate(name, prompt, reference_image, size)
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"{name} 异常: {e}")
                continue

            if result["success"]:
                # 记账（图像模型按张计算，每次+1）
                self.tracker.add_usage(name, 1, 1)
                self.logger.info(f"✅ {name} 图像生成成功 (剩余 {self.tracker.remaining(name)})")
                return {
                    "success": True,
                    "image_urls": result["image_urls"],
                    "model": name,
                    "provider": "dashscope_image",
                    "tokens_used": 1,
                }
            
            last_error = result.get("error", "")
            self.logger.warning(f"❌ {name} 失败: {last_error}")
            
            if result.get("is_quota_error"):
                self.tracker.block(name, f"quota_error: {last_error[:80]}")

        return {
            "success": False,
            "error": f"图像生成失败. 最后错误: {last_error}",
            "image_urls": [],
            "tokens_used": 0,
        }

    # -------- 调试与监控 --------
    def show_summary(self):
        print(self.tracker.summary())


# ============================================================
#   CLI 入口
# ============================================================
def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="ModelRouter - 免费额度自动切换")
    parser.add_argument("--config", default="models_config.yaml", help="配置文件路径")
    parser.add_argument("--show", action="store_true", help="仅显示当前用量摘要")
    parser.add_argument("--prefer-model", help="优先尝试某个模型")
    parser.add_argument("--prefer-provider", help="优先某平台: volc_ark / dashscope")
    parser.add_argument("--temp", type=float, default=0.7, help="temperature")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示日志")
    parser.add_argument("prompt", nargs="*", help="你的问题（多词会被合并成一句话）")
    args = parser.parse_args()

    # 找到配置文件
    config_path = args.config
    if not os.path.isabs(config_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for p in [config_path, os.path.join(script_dir, config_path)]:
            if os.path.exists(p):
                config_path = p
                break

    log_level = logging.DEBUG if args.verbose else logging.INFO
    router = ModelRouter(config_path, log_level=log_level)

    if args.show:
        router.show_summary()
        return

    if not args.prompt:
        print("请输入问题: ", end="", flush=True)
        try:
            prompt = input().strip()
        except EOFError:
            prompt = ""
    else:
        prompt = " ".join(args.prompt)

    if not prompt:
        print("空输入，退出")
        return

    result = router.chat(
        prompt,
        preferred_model=args.prefer_model,
        preferred_provider=args.prefer_provider,
        temperature=args.temp,
    )

    print()
    print("=" * 60)
    if result["success"]:
        print(f"🤖 模型: {result['provider']} / {result['model']}")
        print(f"📊 消耗 tokens: {result['tokens_used']}")
        print(f"🔁 尝试次数: {result['total_attempts']}")
        print("-" * 60)
        print(result["response"])
    else:
        print(f"❌ 失败: {result['error']}")
        print(f"尝试过: {result.get('attempted_models', [])}")
    print("=" * 60)


if __name__ == "__main__":
    _cli()
