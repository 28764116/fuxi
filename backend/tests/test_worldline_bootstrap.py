"""Tests for simulation.worldline_bootstrap — graph cloning and assumption generation."""

import json
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.worldline_bootstrap import _default_assumptions


class TestDefaultAssumptions:
    def test_three_assumptions(self):
        result = _default_assumptions(3)
        assert len(result) == 3
        types = [a["assumption_type"] for a in result]
        assert types == ["optimistic", "neutral", "pessimistic"]

    def test_more_than_three(self):
        result = _default_assumptions(5)
        assert len(result) == 5
        # Cycles: optimistic, neutral, pessimistic, optimistic, neutral
        assert result[3]["assumption_type"] == "optimistic"
        assert result[4]["assumption_type"] == "neutral"

    def test_single_assumption(self):
        result = _default_assumptions(1)
        assert len(result) == 1
        assert result[0]["assumption_type"] == "optimistic"

    def test_all_have_required_keys(self):
        for n in [1, 3, 5]:
            for a in _default_assumptions(n):
                assert "assumption_type" in a
                assert "title" in a
                assert "assumption" in a
                assert "key_conditions" in a


class TestBootstrapWorldlines:
    @patch("simulation.worldline_bootstrap._generate_assumptions")
    @patch("simulation.worldline_bootstrap._clone_graph")
    @patch("simulation.worldline_bootstrap.temporal_upsert")
    def test_bootstrap_creates_worldlines(self, mock_upsert, mock_clone, mock_gen):
        from simulation.worldline_bootstrap import bootstrap_worldlines

        mock_gen.return_value = [
            {"assumption_type": "optimistic", "title": "Best case", "assumption": "Things go well", "key_conditions": []},
            {"assumption_type": "neutral", "title": "Baseline", "assumption": "Status quo", "key_conditions": []},
            {"assumption_type": "pessimistic", "title": "Worst case", "assumption": "Things go badly", "key_conditions": []},
        ]
        mock_clone.return_value = 5

        session = MagicMock()
        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_timelines = 3
        task.goal = "Test goal"
        task.title = "Test"
        task.created_at = datetime.now(timezone.utc)

        result = bootstrap_worldlines(session, task, "base_ns", "task123")

        assert len(result) == 3
        assert mock_clone.call_count == 3
        assert session.commit.called

    @patch("simulation.worldline_bootstrap._generate_assumptions")
    @patch("simulation.worldline_bootstrap._clone_graph")
    @patch("simulation.worldline_bootstrap.temporal_upsert")
    def test_bootstrap_fallback_when_llm_fails(self, mock_upsert, mock_clone, mock_gen):
        from simulation.worldline_bootstrap import bootstrap_worldlines

        mock_gen.return_value = []  # LLM returned nothing
        mock_clone.return_value = 0

        session = MagicMock()
        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_timelines = 3
        task.goal = None
        task.title = "Fallback Test"
        task.created_at = datetime.now(timezone.utc)

        result = bootstrap_worldlines(session, task, "base_ns", "task456")

        assert len(result) == 3
        # Verify fallback assumptions were used
        types = [wl.assumption_type for wl in result]
        assert "neutral" in types

    @patch("simulation.worldline_bootstrap._generate_assumptions")
    @patch("simulation.worldline_bootstrap._clone_graph")
    @patch("simulation.worldline_bootstrap.temporal_upsert")
    def test_bootstrap_pads_when_llm_returns_fewer(self, mock_upsert, mock_clone, mock_gen):
        from simulation.worldline_bootstrap import bootstrap_worldlines

        # LLM returns only 1, but we want 3
        mock_gen.return_value = [
            {"assumption_type": "optimistic", "title": "Only one", "assumption": "Only one scenario", "key_conditions": []},
        ]
        mock_clone.return_value = 0

        session = MagicMock()
        task = MagicMock()
        task.id = uuid.uuid4()
        task.num_timelines = 3
        task.goal = "Test"
        task.title = "Padding Test"
        task.created_at = datetime.now(timezone.utc)

        result = bootstrap_worldlines(session, task, "base_ns", "task789")

        assert len(result) == 3


class TestGenerateAssumptions:
    @patch("simulation.worldline_bootstrap.OpenAI")
    def test_generate_assumptions_success(self, mock_openai_class):
        from simulation.worldline_bootstrap import _generate_assumptions

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([
            {"assumption_type": "optimistic", "title": "Good", "assumption": "Good start", "key_conditions": ["peace"]},
            {"assumption_type": "neutral", "title": "Base", "assumption": "Normal", "key_conditions": []},
            {"assumption_type": "pessimistic", "title": "Bad", "assumption": "Crisis", "key_conditions": ["war"]},
        ])
        mock_client.chat.completions.create.return_value = mock_response

        task = MagicMock()
        task.scene_type = "geopolitics"
        task.goal = "Analyze conflict"
        task.title = "Test"
        task.seed_content = "Background material..." * 100

        result = _generate_assumptions(task, 3)
        assert len(result) == 3
        assert result[0]["assumption_type"] == "optimistic"

    @patch("simulation.worldline_bootstrap.OpenAI")
    def test_generate_assumptions_llm_error(self, mock_openai_class):
        from simulation.worldline_bootstrap import _generate_assumptions

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        task = MagicMock()
        task.scene_type = "finance"
        task.goal = "Test"
        task.title = "Test"
        task.seed_content = "Content"
        task.id = uuid.uuid4()

        result = _generate_assumptions(task, 3)
        assert result == []
