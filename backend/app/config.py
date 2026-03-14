from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "fuxi"

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Neo4j 图数据库
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimaxi.com/v1"
    llm_model_name: str = "MiniMax-M2.5"

    # Embedding
    embedding_model: str = "embo-01"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.minimaxi.com/v1"
    embedding_dimension: int = 1536

    # 向量搜索
    vector_search_top_k: int = 5

    # 文件上传
    max_content_length: int = 50 * 1024 * 1024  # 50MB
    upload_folder: str = "uploads"
    allowed_extensions: set = {"pdf", "md", "txt", "markdown"}

    # 文本处理
    default_chunk_size: int = 800
    default_chunk_overlap: int = 100

    # Context assembly
    context_max_tokens: int = 4000

    # App
    app_env: str = "development"
    api_key: str = ""


settings = Settings()
