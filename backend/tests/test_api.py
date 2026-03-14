"""Tests for FastAPI API routes — health, auth, and simulation/memory endpoints."""

import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app
from app.database import get_session
from app.auth import require_api_key


def _override_session(mock_session):
    """Create a dependency override for get_session that yields mock_session."""
    async def _get_session_override():
        yield mock_session
    return _get_session_override


async def _skip_auth():
    """Skip auth for testing."""
    return "test"


@pytest.fixture
def client():
    """Create a test client with mocked DB session and skipped auth."""
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = _override_session(mock_session)
    app.dependency_overrides[require_api_key] = _skip_auth
    with TestClient(app) as c:
        yield c, mock_session
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health(self):
        with TestClient(app) as c:
            resp = c.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}


class TestScenesEndpoint:
    def test_list_scenes(self, client):
        c, _ = client
        resp = c.get("/simulation/scenes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 5
        scene_types = {s["scene_type"] for s in data}
        assert "geopolitics" in scene_types
        assert "finance" in scene_types


class TestAuthMiddleware:
    def test_dev_mode_no_auth_required(self):
        """When api_key is empty, auth is skipped."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.api_key = ""
            with TestClient(app) as c:
                resp = c.get("/simulation/scenes")
                assert resp.status_code == 200

    def test_auth_required_when_configured(self):
        """When api_key is set, requests without key should fail."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.api_key = "secret-key-123"
            with TestClient(app) as c:
                resp = c.get("/simulation/scenes")
                assert resp.status_code == 401

    def test_auth_passes_with_correct_key(self):
        """Correct X-API-Key header should pass auth."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.api_key = "secret-key-123"
            with TestClient(app) as c:
                resp = c.get(
                    "/simulation/scenes",
                    headers={"X-API-Key": "secret-key-123"},
                )
                assert resp.status_code == 200


class TestSimulationTaskEndpoints:
    def test_create_task_validation_error(self, client):
        """Missing required fields should return 422."""
        c, _ = client
        resp = c.post("/simulation/tasks", json={})
        assert resp.status_code == 422

    def test_get_task_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        task_id = uuid.uuid4()
        resp = c.get(f"/simulation/tasks/{task_id}")
        assert resp.status_code == 404

    def test_get_task_status_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        task_id = uuid.uuid4()
        resp = c.get(f"/simulation/tasks/{task_id}/status")
        assert resp.status_code == 404

    def test_list_tasks_requires_group_id(self, client):
        c, _ = client
        resp = c.get("/simulation/tasks")
        assert resp.status_code == 422  # Missing required query param


class TestSimulationReportEndpoints:
    def test_get_report_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        report_id = uuid.uuid4()
        resp = c.get(f"/simulation/reports/{report_id}")
        assert resp.status_code == 404


class TestSimulationWorldlineEndpoints:
    def test_get_worldline_events_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        wl_id = uuid.uuid4()
        resp = c.get(f"/simulation/worldlines/{wl_id}/events")
        assert resp.status_code == 404

    def test_get_worldline_snapshot_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        wl_id = uuid.uuid4()
        resp = c.get(f"/simulation/worldlines/{wl_id}/snapshot")
        assert resp.status_code == 404


class TestMemoryEndpoints:
    def test_create_episode_validation(self, client):
        c, _ = client
        resp = c.post("/memory/episodes", json={})
        assert resp.status_code == 422

    def test_search_requires_params(self, client):
        c, _ = client
        resp = c.get("/memory/search")
        assert resp.status_code == 422

    def test_entity_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        entity_id = uuid.uuid4()
        resp = c.get(f"/memory/entities/{entity_id}")
        assert resp.status_code == 404

    def test_facts_entity_not_found(self, client):
        c, mock_session = client
        mock_session.get.return_value = None

        entity_id = uuid.uuid4()
        resp = c.get(f"/memory/facts/{entity_id}")
        assert resp.status_code == 404


class TestGraphEndpoint:
    def test_graph_requires_group_id(self, client):
        c, _ = client
        resp = c.get("/simulation/graph")
        assert resp.status_code == 422

    def test_list_tasks_with_group_id(self, client):
        c, mock_session = client
        # Mock execute to return empty list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        resp = c.get("/simulation/tasks?group_id=test-group")
        assert resp.status_code == 200
        assert resp.json() == []
