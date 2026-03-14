"""Tests for simulation.reporter — report generation logic."""

import json
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_worldline(score=65.0, verdict="above_water", assumption_type="neutral"):
    wl = MagicMock()
    wl.id = uuid.uuid4()
    wl.assumption_type = assumption_type
    wl.initial_assumption = "Baseline assumption"
    wl.graph_namespace = "wl_0"
    # Use real float values to avoid f-string format issues
    wl.score = score
    wl.verdict = verdict
    wl.score_detail = {"stability": {"score": 70}}
    return wl


class TestGenerateWorldlineReports:
    @patch("simulation.reporter._call_llm")
    def test_generates_worldline_and_summary_reports(self, mock_llm):
        from simulation.reporter import generate_worldline_reports

        mock_llm.return_value = "# Report\n\nThis is a test report."

        session = MagicMock()

        wl = _make_worldline()

        # Mock agent
        agent = MagicMock()
        agent.id = uuid.uuid4()
        agent.name = "TestAgent"
        agent.influence_weight = 0.8

        # Mock event
        event = MagicMock()
        event.step_index = 0
        event.agent_id = agent.id
        event.action_type = "observe"
        event.description = "Watching"
        event.impact_score = 0.3

        # Worldlines query
        wl_result = MagicMock()
        wl_result.scalars.return_value.all.return_value = [wl]

        # Agents query
        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = [agent]

        # Events query
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [event]

        session.execute.side_effect = [wl_result, agents_result, events_result]

        task = MagicMock()
        task.id = uuid.uuid4()
        task.goal = "Test"
        task.title = "Test Task"
        task.scene_type = "geopolitics"

        generate_worldline_reports(session, task)

        # Should add worldline report + summary report = 2
        assert session.add.call_count == 2
        assert session.commit.called
        assert mock_llm.call_count == 2  # 1 worldline + 1 summary

    @patch("simulation.reporter._call_llm")
    def test_fallback_when_llm_fails(self, mock_llm):
        from simulation.reporter import generate_worldline_reports

        mock_llm.return_value = ""  # LLM fails

        session = MagicMock()

        wl = _make_worldline(score=30.0, verdict="below_water", assumption_type="pessimistic")

        wl_result = MagicMock()
        wl_result.scalars.return_value.all.return_value = [wl]

        agents_result = MagicMock()
        agents_result.scalars.return_value.all.return_value = []

        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [wl_result, agents_result, events_result]

        task = MagicMock()
        task.id = uuid.uuid4()
        task.goal = "Test"
        task.title = "Fallback Test"
        task.scene_type = "geopolitics"

        generate_worldline_reports(session, task)

        # Still should add reports (with fallback content)
        assert session.add.call_count == 2
