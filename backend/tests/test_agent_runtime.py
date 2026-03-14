"""Tests for simulation.agent_runtime — parsing, prompt building, and fallback logic."""

import json
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.agent_runtime import AgentAction, _clamp, _parse_action


def _make_agent(**overrides) -> MagicMock:
    """Create a mock SimAgent."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "TestAgent",
        "role": "Analyst",
        "background": "Expert in geopolitics",
        "personality": "Cautious",
        "ideology": "Neutral",
        "influence_weight": 0.7,
        "risk_tolerance": 0.4,
        "change_resistance": 0.5,
        "scene_metadata": {"information_access": "partial"},
    }
    defaults.update(overrides)
    agent = MagicMock()
    for k, v in defaults.items():
        setattr(agent, k, v)
    return agent


class TestClamp:
    def test_clamp_normal(self):
        assert _clamp(0.5) == 0.5

    def test_clamp_below(self):
        assert _clamp(-0.3) == 0.0

    def test_clamp_above(self):
        assert _clamp(1.5) == 1.0

    def test_clamp_invalid_string(self):
        assert _clamp("invalid") == 0.5

    def test_clamp_none(self):
        assert _clamp(None) == 0.5

    def test_clamp_custom_range(self):
        assert _clamp(5, lo=0, hi=10) == 5
        assert _clamp(15, lo=0, hi=10) == 10


class TestParseAction:
    def test_parse_valid_json(self):
        agent = _make_agent()
        raw = json.dumps({
            "action_type": "diplomatic_statement",
            "description": "Issued a diplomatic warning",
            "new_facts": [
                {
                    "subject": "Country A",
                    "predicate": "warned",
                    "object": "Country B",
                    "fact": "Country A issued a warning to Country B",
                    "confidence": 0.9,
                }
            ],
            "confidence": 0.85,
            "impact_score": 0.6,
            "reasoning": "Strategic positioning",
        })
        valid_types = ["diplomatic_statement", "observe", "escalation"]
        result = _parse_action(raw, agent, valid_types)

        assert isinstance(result, AgentAction)
        assert result.action_type == "diplomatic_statement"
        assert result.description == "Issued a diplomatic warning"
        assert len(result.new_facts) == 1
        assert result.confidence == 0.85
        assert result.impact_score == 0.6

    def test_parse_invalid_action_type_falls_back_to_observe(self):
        agent = _make_agent()
        raw = json.dumps({
            "action_type": "fly_to_moon",
            "description": "Attempted something invalid",
        })
        valid_types = ["diplomatic_statement", "observe"]
        result = _parse_action(raw, agent, valid_types)
        assert result.action_type == "observe"

    def test_parse_empty_string_returns_fallback(self):
        agent = _make_agent()
        result = _parse_action("", agent, ["observe"])
        assert result.action_type == "observe"
        assert "观望" in result.description

    def test_parse_invalid_json_returns_fallback(self):
        agent = _make_agent()
        result = _parse_action("not json at all {{{", agent, ["observe"])
        assert result.action_type == "observe"

    def test_parse_non_list_new_facts_normalized(self):
        agent = _make_agent()
        raw = json.dumps({
            "action_type": "observe",
            "description": "Watching",
            "new_facts": "not a list",
        })
        result = _parse_action(raw, agent, ["observe"])
        assert result.new_facts == []

    def test_parse_out_of_range_values_clamped(self):
        agent = _make_agent()
        raw = json.dumps({
            "action_type": "observe",
            "description": "Test",
            "confidence": 5.0,
            "impact_score": -1.0,
        })
        result = _parse_action(raw, agent, ["observe"])
        assert result.confidence == 1.0
        assert result.impact_score == 0.0

    def test_agent_id_and_name_set(self):
        agent = _make_agent(name="特朗普")
        raw = json.dumps({"action_type": "observe", "description": "Observing"})
        result = _parse_action(raw, agent, ["observe"])
        assert result.agent_name == "特朗普"
        assert result.agent_id == str(agent.id)


class TestRunAgentStep:
    @patch("simulation.agent_runtime._call_llm")
    def test_run_agent_step_calls_llm(self, mock_llm):
        from simulation.agent_runtime import run_agent_step

        mock_llm.return_value = json.dumps({
            "action_type": "observe",
            "description": "Watching carefully",
            "new_facts": [],
            "confidence": 0.8,
            "impact_score": 0.1,
            "reasoning": "Not enough info",
        })

        agent = _make_agent()
        result = run_agent_step(
            agent=agent,
            facts=["Fact 1", "Fact 2"],
            pending_reactions=[],
            scene_type="geopolitics",
            sim_time=datetime.now(timezone.utc),
            goal="Test goal",
        )

        assert mock_llm.called
        assert result.action_type == "observe"
        assert result.description == "Watching carefully"

    @patch("simulation.agent_runtime._call_llm")
    def test_run_agent_step_handles_empty_facts(self, mock_llm):
        from simulation.agent_runtime import run_agent_step

        mock_llm.return_value = json.dumps({
            "action_type": "observe",
            "description": "No info available",
            "new_facts": [],
            "confidence": 0.5,
            "impact_score": 0.0,
        })

        agent = _make_agent()
        result = run_agent_step(
            agent=agent,
            facts=[],
            pending_reactions=[],
            scene_type="finance",
            sim_time=None,
            goal="",
        )

        assert result.action_type in ["observe", "hold"]

    @patch("simulation.agent_runtime._call_llm")
    def test_run_agent_step_with_pending_reactions(self, mock_llm):
        from simulation.agent_runtime import run_agent_step

        mock_llm.return_value = json.dumps({
            "action_type": "diplomatic_statement",
            "description": "Responding to escalation",
            "new_facts": [],
            "confidence": 0.9,
            "impact_score": 0.7,
        })

        agent = _make_agent()
        pending = [
            {"action_type": "escalation", "description": "Military buildup detected", "impact_score": 0.8}
        ]
        result = run_agent_step(
            agent=agent,
            facts=["Tension rising"],
            pending_reactions=pending,
            scene_type="geopolitics",
            sim_time=datetime.now(timezone.utc),
            goal="Maintain stability",
        )

        assert result.impact_score == 0.7
        # Verify LLM was called with pending reactions included
        call_args = mock_llm.call_args
        user_msg = call_args[0][1]
        assert "escalation" in user_msg.lower() or "Military buildup" in user_msg
