"""
向量存储服务
基于 pgvector 的语义搜索
"""

import uuid
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

import psycopg2
from psycopg2 import sql
from app.config import settings


@dataclass
class VectorChunk:
    """向量片段"""
    uuid: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    created_at: Optional[str] = None


class VectorStore:
    """向量存储服务"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None
    ):
        self.host = host or settings.postgres_host
        self.port = port or settings.postgres_port
        self.user = user or settings.postgres_user
        self.password = password or settings.postgres_password
        self.database = database or settings.postgres_db

        if not self.password:
            raise ValueError("POSTGRES_PASSWORD 未配置")

        self._conn = None
        self._ensure_extension()
        self._ensure_table()

    @property
    def conn(self):
        """获取连接"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
        return self._conn

    def _ensure_extension(self):
        """确保 pgvector 扩展已安装"""
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        self.conn.commit()

    def _ensure_table(self):
        """确保向量表已创建"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS graph_vectors (
                    id SERIAL PRIMARY KEY,
                    uuid VARCHAR(255) NOT NULL,
                    graph_id VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(%s),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """, (settings.embedding_dimension,))
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_graph_vectors_graph_id 
                ON graph_vectors(graph_id)
            """)
            
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_graph_vectors_embedding 
                ON graph_vectors 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                WHERE graph_id IS NOT NULL
            """)
        self.conn.commit()

    def add_texts(self, graph_id: str, texts: List[str], metadata: List[Dict[str, Any]] = None):
        """添加文本向量"""
        if not texts:
            return

        from graph.embedding import get_embedding_client
        embedding_client = get_embedding_client()
        if not embedding_client:
            return
            
        metadata = metadata or [{}] * len(texts)
        
        try:
            embeddings = embedding_client.embed(texts)
            with self.conn.cursor() as cur:
                for text, embedding, meta in zip(texts, embeddings, metadata):
                    cur.execute("""
                        INSERT INTO graph_vectors (uuid, graph_id, content, embedding, metadata)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        str(uuid.uuid4()),
                        graph_id,
                        text,
                        embedding,
                        psycopg2.extras.Json(meta)
                    ))
            self.conn.commit()
        except Exception as e:
            logger.warning("添加向量失败: %s", e)
            self.conn.rollback()

    def search(self, graph_id: str, query: str, limit: int = 5) -> List[VectorChunk]:
        """向量语义搜索"""
        from graph.embedding import get_embedding_client
        embedding_client = get_embedding_client()
        
        query_embedding = embedding_client.embed([query])[0]
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT uuid, content, metadata, 
                       1 - (embedding <=> %s) as similarity,
                       created_at
                FROM graph_vectors
                WHERE graph_id = %s
                ORDER BY embedding <=> %s
                LIMIT %s
            """, (query_embedding, graph_id, query_embedding, limit))
            
            results = cur.fetchall()
            
        return [
            VectorChunk(
                uuid=row[0],
                content=row[1],
                metadata=row[2] or {},
                score=row[3],
                created_at=row[4].isoformat() if row[4] else None
            )
            for row in results
        ]

    def delete_by_graph_id(self, graph_id: str):
        """删除图谱相关的向量"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM graph_vectors WHERE graph_id = %s", (graph_id,))
        self.conn.commit()

    def close(self):
        """关闭连接"""
        if self._conn and not self._conn.closed:
            self._conn.close()


# 全局向量存储客户端
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> Optional[VectorStore]:
    """获取向量存储客户端"""
    global _vector_store
    if _vector_store is None:
        try:
            _vector_store = VectorStore()
        except Exception as e:
            logger.warning("VectorStore 初始化失败: %s", e)
            return None
    return _vector_store
