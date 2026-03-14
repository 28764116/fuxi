"""Shared test fixtures for the Fuxi backend test suite."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Patch heavy dependencies BEFORE importing app modules
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Override settings to avoid connecting to real services."""
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "test_mirofish")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("API_KEY", "")  # dev mode — skip auth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_uuid() -> uuid.UUID:
    return uuid.uuid4()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
