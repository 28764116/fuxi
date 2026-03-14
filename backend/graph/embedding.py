"""
Embedding 服务
"""

import logging
from typing import List, Optional
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Embedding 客户端"""
    
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        dimension: int = None
    ):
        self.api_key = api_key or settings.embedding_api_key
        self.base_url = base_url or settings.embedding_base_url
        self.model = model or settings.embedding_model
        self.dimension = dimension or settings.embedding_dimension
        
        if not self.api_key:
            raise ValueError("EMBEDDING_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """生成 embedding 向量"""
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]


# 全局客户端
_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> Optional[EmbeddingClient]:
    """获取 embedding 客户端"""
    global _embedding_client
    if _embedding_client is None:
        try:
            _embedding_client = EmbeddingClient()
        except Exception as e:
            logger.warning("EmbeddingClient 初始化失败: %s", e)
            return None
    return _embedding_client
