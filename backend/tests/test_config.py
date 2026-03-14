"""Tests for app.config — settings loading and computed fields."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings


class TestSettings:
    def test_default_database_url(self):
        s = Settings(
            postgres_host="localhost",
            postgres_port=5432,
            postgres_user="postgres",
            postgres_password="postgres",
            postgres_db="mirofish",
        )
        assert s.database_url == "postgresql+asyncpg://postgres:postgres@localhost:5432/mirofish"

    def test_custom_database_url(self):
        s = Settings(
            postgres_host="db.example.com",
            postgres_port=5433,
            postgres_user="fuxi",
            postgres_password="secret",
            postgres_db="fuxi_prod",
        )
        assert "db.example.com:5433" in s.database_url
        assert "fuxi:secret" in s.database_url
        assert "fuxi_prod" in s.database_url

    def test_default_llm_config(self):
        s = Settings()
        assert s.llm_model_name == "MiniMax-M2.5"
        assert "minimaxi" in s.llm_base_url

    def test_default_embedding_config(self):
        s = Settings()
        assert s.embedding_model == "embo-01"
        assert s.embedding_dimension == 1536

    def test_dev_mode_no_api_key(self):
        s = Settings()
        assert s.api_key == ""  # Dev mode: no auth

    def test_context_max_tokens(self):
        s = Settings()
        assert s.context_max_tokens == 4000

    def test_extra_env_vars_ignored(self):
        """Settings with extra='ignore' should not fail on unknown fields."""
        s = Settings(_env_file=None, UNKNOWN_VAR="should_be_ignored")
        assert s.app_env == "development"
