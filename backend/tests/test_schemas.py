"""Tests for Pydantic schemas — validation, serialization, edge cases."""

import sys
import os
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.schemas import (
    SimTaskCreate,
    SimTaskResponse,
    SimTaskStatusResponse,
    SimWorldlineResponse,
    SimWorldlineEventResponse,
    SimAgentResponse,
    SimReportResponse,
    GraphNodeResponse,
    GraphEdgeResponse,
    GraphResponse,
)
from memory.schemas import (
    EpisodeCreate,
    EpisodeResponse,
    EntityResponse,
    EntityEdgeResponse,
    SearchResponse,
    ContextResponse,
)


class TestSimTaskCreate:
    def test_minimal_create(self):
        task = SimTaskCreate(
            group_id="g1",
            title="Test",
            seed_content="Some content",
        )
        assert task.seed_type == "text"
        assert task.num_timelines == 3
        assert task.num_agents == 10
        assert task.num_rounds == 10
        assert task.scenario == "social_media"
        assert task.goal is None
        assert task.scene_type is None

    def test_full_create(self):
        task = SimTaskCreate(
            group_id="g1",
            title="Trade War Analysis",
            seed_content="Background material...",
            seed_type="document",
            goal="Evaluate impact on semiconductor supply chain",
            scene_type="geopolitics",
            scene_config={"extra": "param"},
            sim_start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            sim_end_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
            time_step_unit="month",
            num_timelines=5,
            num_agents=20,
            num_rounds=15,
        )
        assert task.num_timelines == 5
        assert task.scene_type == "geopolitics"
        assert task.time_step_unit == "month"

    def test_num_timelines_bounds(self):
        with pytest.raises(Exception):
            SimTaskCreate(group_id="g1", title="T", seed_content="C", num_timelines=0)
        with pytest.raises(Exception):
            SimTaskCreate(group_id="g1", title="T", seed_content="C", num_timelines=11)

    def test_num_agents_bounds(self):
        with pytest.raises(Exception):
            SimTaskCreate(group_id="g1", title="T", seed_content="C", num_agents=1)
        with pytest.raises(Exception):
            SimTaskCreate(group_id="g1", title="T", seed_content="C", num_agents=201)


class TestSimTaskResponse:
    def test_from_attributes(self):
        """SimTaskResponse should accept ORM-like objects via from_attributes."""
        now = datetime.now(timezone.utc)
        data = {
            "id": uuid.uuid4(),
            "group_id": "g1",
            "title": "Test",
            "seed_content": "content",
            "seed_type": "text",
            "goal": None,
            "scene_type": None,
            "num_timelines": 3,
            "num_agents": 10,
            "num_rounds": 10,
            "scenario": "social_media",
            "status": "pending",
            "progress": 0,
            "status_message": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        resp = SimTaskResponse(**data)
        assert resp.status == "pending"
        assert resp.progress == 0


class TestSimWorldlineResponse:
    def test_response_with_score(self):
        now = datetime.now(timezone.utc)
        resp = SimWorldlineResponse(
            id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            graph_namespace="task_123_wl_0",
            initial_assumption="Optimistic scenario",
            assumption_type="optimistic",
            status="completed",
            score=75.5,
            score_detail={"stability": {"score": 80}},
            verdict="above_water",
            created_at=now,
            updated_at=now,
        )
        assert resp.verdict == "above_water"
        assert resp.score == 75.5

    def test_response_without_score(self):
        now = datetime.now(timezone.utc)
        resp = SimWorldlineResponse(
            id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            graph_namespace="ns",
            assumption_type="neutral",
            status="pending",
            created_at=now,
            updated_at=now,
        )
        assert resp.score is None
        assert resp.verdict is None


class TestGraphResponse:
    def test_empty_graph(self):
        resp = GraphResponse(nodes=[], edges=[], total_nodes=0, total_edges=0)
        assert resp.total_nodes == 0

    def test_graph_with_data(self):
        now = datetime.now(timezone.utc)
        node = GraphNodeResponse(
            id="n1", name="USA", entity_type="organization",
            display_name="United States", group_id="g1",
        )
        edge = GraphEdgeResponse(
            id="e1", source_id="n1", target_id="n2",
            predicate="sanctions", fact="USA sanctions Russia",
            generated_by="extraction", confidence=0.9,
            valid_at=now, expired_at=None,
        )
        resp = GraphResponse(nodes=[node], edges=[edge], total_nodes=1, total_edges=1)
        assert resp.total_nodes == 1
        assert resp.edges[0].predicate == "sanctions"


class TestEpisodeCreate:
    def test_valid_roles(self):
        for role in ["user", "assistant", "system"]:
            ep = EpisodeCreate(
                group_id="g1",
                thread_id=uuid.uuid4(),
                role=role,
                content="test",
                valid_at=datetime.now(timezone.utc),
            )
            assert ep.role == role

    def test_invalid_role(self):
        with pytest.raises(Exception):
            EpisodeCreate(
                group_id="g1",
                thread_id=uuid.uuid4(),
                role="admin",
                content="test",
                valid_at=datetime.now(timezone.utc),
            )


class TestEntityEdgeResponse:
    def test_optional_score(self):
        now = datetime.now(timezone.utc)
        resp = EntityEdgeResponse(
            id=uuid.uuid4(),
            group_id="g1",
            source_entity_id=uuid.uuid4(),
            target_entity_id=uuid.uuid4(),
            predicate="works_at",
            fact="Alice works at Google",
            valid_at=now,
            created_at=now,
        )
        assert resp.score is None
        assert resp.expired_at is None
        assert resp.episode_ids == []
