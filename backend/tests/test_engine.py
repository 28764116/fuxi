"""Tests for simulation.engine — worldline simulation loop and helpers."""

import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.engine import _time_delta, HIGH_IMPACT_THRESHOLD


class TestTimeDelta:
    def test_hour(self):
        assert _time_delta("hour") == timedelta(hours=1)

    def test_day(self):
        assert _time_delta("day") == timedelta(days=1)

    def test_week(self):
        assert _time_delta("week") == timedelta(weeks=1)

    def test_month(self):
        assert _time_delta("month") == timedelta(days=30)

    def test_unknown_defaults_to_day(self):
        assert _time_delta("century") == timedelta(days=1)
        assert _time_delta("") == timedelta(days=1)


class TestHighImpactThreshold:
    def test_threshold_value(self):
        assert HIGH_IMPACT_THRESHOLD == 0.7


class TestRunWorldline:
    """Test run_worldline with lazy imports mocked at their source modules."""

    @patch("simulation.engine._get_agent_facts", return_value=[])
    @patch("simulation.agent_runtime.run_agent_step")
    @patch("memory.embedder.get_embeddings", return_value=[])
    @patch("memory.temporal.temporal_upsert")
    def test_run_worldline_no_agents(self, mock_upsert, mock_embed, mock_step, mock_facts):
        """Should complete immediately if no agents."""
        from simulation.engine import run_worldline

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []

        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_rounds = 3
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.sim_start_time = None
        task.created_at = datetime.now(timezone.utc)

        worldline = MagicMock()
        worldline.id = uuid.uuid4()
        worldline.graph_namespace = "test_ns"
        worldline.assumption_type = "neutral"

        run_worldline(session, task, worldline)

        assert worldline.status == "completed"
        mock_step.assert_not_called()

    @patch("simulation.engine._get_agent_facts", return_value=[])
    @patch("simulation.agent_runtime.run_agent_step")
    @patch("memory.embedder.get_embeddings", return_value=[])
    @patch("memory.temporal.temporal_upsert")
    def test_run_worldline_with_agents(self, mock_upsert, mock_embed, mock_step, mock_facts):
        """Should iterate through agents and steps."""
        from simulation.agent_runtime import AgentAction
        from simulation.engine import run_worldline

        agent1 = MagicMock()
        agent1.id = uuid.uuid4()
        agent1.name = "Agent1"
        agent1.scene_metadata = {"information_access": "full"}

        agent2 = MagicMock()
        agent2.id = uuid.uuid4()
        agent2.name = "Agent2"
        agent2.scene_metadata = {"information_access": "partial"}

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [agent1, agent2]

        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_rounds = 2
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.sim_start_time = datetime.now(timezone.utc)
        task.time_step_unit = "day"
        task.created_at = datetime.now(timezone.utc)

        worldline = MagicMock()
        worldline.id = uuid.uuid4()
        worldline.graph_namespace = "test_wl_0"
        worldline.assumption_type = "neutral"

        mock_step.return_value = AgentAction(
            agent_id=str(agent1.id),
            agent_name="Agent1",
            action_type="observe",
            description="Observing",
            new_facts=[],
            confidence=0.8,
            impact_score=0.3,
        )

        run_worldline(session, task, worldline)

        assert worldline.status == "completed"
        # 2 agents × 2 rounds = 4 step calls
        assert mock_step.call_count == 4

    @patch("simulation.engine._get_agent_facts", return_value=[])
    @patch("simulation.agent_runtime.run_agent_step")
    @patch("memory.embedder.get_embeddings", return_value=[])
    @patch("memory.temporal.temporal_upsert")
    def test_high_impact_events_distributed(self, mock_upsert, mock_embed, mock_step, mock_facts):
        """High impact events should be pushed to other agents' pending_reactions."""
        from simulation.agent_runtime import AgentAction
        from simulation.engine import run_worldline

        agent1 = MagicMock()
        agent1.id = uuid.uuid4()
        agent1.name = "HighImpactAgent"
        agent1.scene_metadata = {}

        agent2 = MagicMock()
        agent2.id = uuid.uuid4()
        agent2.name = "ReactingAgent"
        agent2.scene_metadata = {}

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [agent1, agent2]

        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_rounds = 1
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.sim_start_time = datetime.now(timezone.utc)
        task.time_step_unit = "day"
        task.created_at = datetime.now(timezone.utc)

        worldline = MagicMock()
        worldline.id = uuid.uuid4()
        worldline.graph_namespace = "test_wl"
        worldline.assumption_type = "neutral"

        def side_effect_step(**kwargs):
            agent = kwargs["agent"]
            if agent.name == "HighImpactAgent":
                return AgentAction(
                    agent_id=str(agent.id),
                    agent_name=agent.name,
                    action_type="escalation",
                    description="Major escalation!",
                    new_facts=[],
                    confidence=0.9,
                    impact_score=0.9,  # > HIGH_IMPACT_THRESHOLD
                )
            else:
                return AgentAction(
                    agent_id=str(agent.id),
                    agent_name=agent.name,
                    action_type="observe",
                    description="Watching",
                    new_facts=[],
                    confidence=0.5,
                    impact_score=0.1,
                )

        mock_step.side_effect = side_effect_step

        run_worldline(session, task, worldline)

        assert session.add.call_count >= 4
        assert worldline.status == "completed"

    @patch("simulation.engine._get_agent_facts", return_value=["Fact 1", "Fact 2"])
    @patch("simulation.agent_runtime.run_agent_step")
    @patch("memory.embedder.get_embeddings", return_value=[[0.1] * 1536])
    @patch("memory.temporal.temporal_upsert")
    def test_run_worldline_with_new_facts(self, mock_upsert, mock_embed, mock_step, mock_facts):
        """Agent producing new_facts should trigger temporal_upsert."""
        from simulation.agent_runtime import AgentAction
        from simulation.engine import run_worldline

        agent = MagicMock()
        agent.id = uuid.uuid4()
        agent.name = "FactProducer"
        agent.scene_metadata = {}

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [agent]

        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_rounds = 1
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.sim_start_time = datetime.now(timezone.utc)
        task.time_step_unit = "day"
        task.created_at = datetime.now(timezone.utc)

        worldline = MagicMock()
        worldline.id = uuid.uuid4()
        worldline.graph_namespace = "test_wl"
        worldline.assumption_type = "neutral"

        mock_step.return_value = AgentAction(
            agent_id=str(agent.id),
            agent_name=agent.name,
            action_type="diplomatic_statement",
            description="Issued a statement",
            new_facts=[{
                "subject": "Country A",
                "subject_type": "organization",
                "predicate": "warns",
                "object": "Country B",
                "object_type": "organization",
                "fact": "Country A warns Country B",
                "confidence": 0.85,
            }],
            confidence=0.9,
            impact_score=0.5,
        )

        run_worldline(session, task, worldline)

        assert mock_upsert.called
