"""Tests for simulation.scorer — worldline scoring logic."""

import json
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestScoreWorldlines:
    @patch("simulation.scorer._call_llm_for_score")
    def test_score_worldlines_updates_all(self, mock_llm):
        from simulation.scorer import score_worldlines

        mock_llm.return_value = {
            "scores": {"stability": {"score": 80, "rationale": "Stable"}},
            "total_score": 75.0,
            "verdict": "above_water",
            "summary": "Good outcome",
        }

        session = MagicMock()
        wl1 = MagicMock()
        wl1.id = uuid.uuid4()
        wl1.assumption_type = "optimistic"
        wl1.initial_assumption = "Good start"
        wl1.graph_namespace = "wl_0"

        wl2 = MagicMock()
        wl2.id = uuid.uuid4()
        wl2.assumption_type = "pessimistic"
        wl2.initial_assumption = "Bad start"
        wl2.graph_namespace = "wl_1"

        # Worldlines query
        wl_result = MagicMock()
        wl_result.scalars.return_value.all.return_value = [wl1, wl2]

        # Events query (empty for both)
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [wl_result, events_result, events_result]

        task = MagicMock()
        task.id = uuid.uuid4()
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.title = "Test"

        score_worldlines(session, task)

        assert wl1.score == 75.0
        assert wl1.verdict == "above_water"
        assert wl2.score == 75.0
        assert session.commit.called

    @patch("simulation.scorer._call_llm_for_score")
    def test_score_derives_verdict_from_score(self, mock_llm):
        from simulation.scorer import _score_one_worldline

        # LLM returns invalid verdict, should derive from score
        mock_llm.return_value = {
            "scores": {},
            "total_score": 35.0,
            "verdict": "some_invalid_value",
            "summary": "Bad outcome",
        }

        session = MagicMock()
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        session.execute.return_value = events_result

        task = MagicMock()
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.title = "Test"

        wl = MagicMock()
        wl.id = uuid.uuid4()
        wl.assumption_type = "pessimistic"
        wl.initial_assumption = "Bad"
        wl.graph_namespace = "wl_0"

        _score_one_worldline(session, task, wl)

        assert wl.score == 35.0
        assert wl.verdict == "below_water"  # < 40 → below_water

    @patch("simulation.scorer._call_llm_for_score")
    def test_score_neutral_range(self, mock_llm):
        from simulation.scorer import _score_one_worldline

        mock_llm.return_value = {
            "scores": {},
            "total_score": 50.0,
            "verdict": "wrong_value",
        }

        session = MagicMock()
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        session.execute.return_value = events_result

        task = MagicMock()
        task.scene_type = "finance"
        task.goal = "Test"
        task.title = "Test"

        wl = MagicMock()
        wl.id = uuid.uuid4()
        wl.assumption_type = "neutral"
        wl.initial_assumption = "Baseline"
        wl.graph_namespace = "wl_0"

        _score_one_worldline(session, task, wl)

        assert wl.verdict == "neutral"  # 40 <= 50 < 60

    @patch("simulation.scorer._call_llm_for_score")
    def test_score_fallback_on_empty_result(self, mock_llm):
        from simulation.scorer import _score_one_worldline

        mock_llm.return_value = {}  # Empty result

        session = MagicMock()
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []
        session.execute.return_value = events_result

        task = MagicMock()
        task.scene_type = "geopolitics"
        task.goal = "Test"
        task.title = "Test"

        wl = MagicMock()
        wl.id = uuid.uuid4()
        wl.assumption_type = "neutral"
        wl.initial_assumption = ""
        wl.graph_namespace = "wl_0"

        _score_one_worldline(session, task, wl)

        assert wl.score == 50.0
        assert wl.verdict == "neutral"
