"""Tests for simulation.profile_generator — agent profile generation."""

import json
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.profile_generator import _clamp


class TestProfileClamp:
    def test_normal_value(self):
        assert _clamp(0.5) == 0.5

    def test_out_of_range(self):
        assert _clamp(-1) == 0.0
        assert _clamp(2) == 1.0

    def test_invalid(self):
        assert _clamp("bad") == 0.5
        assert _clamp(None) == 0.5


class TestGenerateProfiles:
    @patch("simulation.profile_generator._call_llm_for_profiles")
    def test_generate_profiles_from_entities(self, mock_llm):
        from simulation.profile_generator import generate_profiles

        mock_llm.return_value = [
            {
                "entity_name": "usa",
                "role": "Superpower",
                "background": "World's largest economy",
                "personality": "Assertive",
                "ideology": "Liberal democracy",
                "influence_weight": 0.9,
                "risk_tolerance": 0.6,
                "change_resistance": 0.4,
                "information_access": "full",
                "scene_metadata": {"military": "strong"},
            },
            {
                "entity_name": "china",
                "role": "Rising power",
                "background": "Second largest economy",
                "personality": "Strategic",
                "ideology": "State capitalism",
                "influence_weight": 0.85,
                "risk_tolerance": 0.5,
                "change_resistance": 0.5,
                "information_access": "partial",
                "scene_metadata": {},
            },
        ]

        session = MagicMock()

        # Mock entity query
        ent1 = MagicMock()
        ent1.name = "usa"
        ent1.id = uuid.uuid4()
        ent1.entity_type = "organization"
        ent1.summary = "The United States"

        ent2 = MagicMock()
        ent2.name = "china"
        ent2.id = uuid.uuid4()
        ent2.entity_type = "organization"
        ent2.summary = "China"

        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = [ent1, ent2]
        session.execute.return_value = entities_result

        task = MagicMock()
        task.id = uuid.uuid4()
        task.scene_type = "geopolitics"
        task.goal = "Analyze US-China relations"

        result = generate_profiles(session, task, "base_ns")

        assert len(result) == 2
        assert session.add.call_count == 2
        assert session.flush.called

    @patch("simulation.profile_generator._call_llm_for_profiles")
    def test_generate_profiles_no_entities(self, mock_llm):
        from simulation.profile_generator import generate_profiles

        session = MagicMock()
        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = []
        session.execute.return_value = entities_result

        task = MagicMock()
        task.id = uuid.uuid4()
        task.scene_type = "finance"
        task.goal = "Test"

        result = generate_profiles(session, task, "base_ns")
        assert result == []
        mock_llm.assert_not_called()

    @patch("simulation.profile_generator._call_llm_for_profiles")
    def test_generate_profiles_deduplicates(self, mock_llm):
        from simulation.profile_generator import generate_profiles

        mock_llm.return_value = [
            {"entity_name": "usa", "role": "A", "influence_weight": 0.9},
            {"entity_name": "usa", "role": "B", "influence_weight": 0.8},  # duplicate
        ]

        session = MagicMock()
        ent1 = MagicMock()
        ent1.name = "usa"
        ent1.id = uuid.uuid4()
        ent1.entity_type = "org"
        ent1.summary = None

        entities_result = MagicMock()
        entities_result.scalars.return_value.all.return_value = [ent1]
        session.execute.return_value = entities_result

        task = MagicMock()
        task.id = uuid.uuid4()
        task.scene_type = "geopolitics"
        task.goal = "Test"

        result = generate_profiles(session, task, "base_ns")
        assert len(result) == 1  # Deduplicated
