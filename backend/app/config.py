from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL（从独立字段组装 database_url）
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "mirofish"

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimaxi.com/v1"
    llm_model_name: str = "MiniMax-M2.5"

    # Embedding
    embedding_model: str = "embo-01"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.minimaxi.com/v1"
    embedding_dimension: int = 1536

    # Context assembly
    context_max_tokens: int = 4000  # token budget for assembled context

    # App
    app_env: str = "development"
    api_key: str = ""  # empty = skip auth (dev mode)

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
