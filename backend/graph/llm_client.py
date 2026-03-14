"""
LLM 客户端
"""
import json
import re
from typing import Dict, Any, List, Optional

from openai import OpenAI
from app.config import settings


def clean_json_response(content: str) -> str:
    """清理 LLM 响应中的 JSON"""
    if not content:
        return content
    # 移除 <think> 块
    content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
    if '<think>' in content:
        idx = content.find('<think>')
        after = content[idx + len('<think>'):].strip()
        before = content[:idx].strip()
        content = after if after else before
    # 移除 markdown 代码块
    content = re.sub(r'^```(?:json)?\s*\n?', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\n?```\s*$', '', content)
    content = content.strip()
    # 移除单行注释 (LLM 常见错误: // comment)
    content = re.sub(r'//[^\n]*', '', content)
    # 移除多行注释
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)
    # 移除 trailing commas (LLM 常见错误: [1, 2,] 或 {"a": 1,})
    # 循环处理以覆盖嵌套场景
    prev = None
    while prev != content:
        prev = content
        content = re.sub(r',\s*([}\]])', r'\1', content)
    return content


class LLMClient:
    """LLM 客户端"""
    
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model_name
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        """发送聊天请求"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """发送聊天请求并解析 JSON，解析失败时自动重试一次"""
        response = self.chat(messages, temperature, max_tokens)
        cleaned = clean_json_response(response)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 重试：让 LLM 修复自己的 JSON
        retry_messages = messages + [
            {"role": "assistant", "content": response},
            {"role": "user", "content": (
                "你上面的输出不是合法 JSON，请修复并重新输出。"
                "只输出纯 JSON，不要用 markdown 代码块包裹，不要加注释。"
            )}
        ]
        response2 = self.chat(retry_messages, temperature=0.1, max_tokens=max_tokens)
        cleaned2 = clean_json_response(response2)
        try:
            return json.loads(cleaned2)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM 返回的内容无法解析为 JSON（已重试）: {e}\n"
                f"--- 首次清理后内容(前500字) ---\n{cleaned[:500]}\n"
                f"--- 重试清理后内容(前500字) ---\n{cleaned2[:500]}"
            ) from e


# 全局客户端
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
