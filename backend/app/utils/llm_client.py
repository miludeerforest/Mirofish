"""
LLM客户端封装
统一使用OpenAI格式调用，支持自动重试
"""

import json
import logging
from typing import Optional, Dict, Any, List
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log
)

from ..config import Config

logger = logging.getLogger('mirofish.llm_client')


def _is_retryable_error(exception: BaseException) -> bool:
    """判断是否为可重试的错误"""
    # 连接和超时错误
    if isinstance(exception, (APIConnectionError, APITimeoutError)):
        return True
    # API 状态错误（500, 502, 503, 504, 529）
    if isinstance(exception, APIStatusError):
        return exception.status_code in (500, 502, 503, 504, 529)
    return False


class LLMClient:
    """LLM客户端（支持自动重试）"""
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_MIN_WAIT = 1  # 最小等待秒数
    RETRY_MAX_WAIT = 8  # 最大等待秒数
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def _call_api(self, **kwargs) -> Any:
        """带重试的 API 调用"""
        return self.client.chat.completions.create(**kwargs)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求（自动重试）
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            
        Returns:
            模型响应文本
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self._call_api(**kwargs)
        return response.choices[0].message.content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        # 不使用 response_format 参数，因为某些模型（如 Gemini）不支持
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # 尝试从响应中提取 JSON（处理可能的 markdown 代码块）
        text = response.strip()
        
        # 移除可能的 markdown 代码块标记
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        return json.loads(text.strip())

