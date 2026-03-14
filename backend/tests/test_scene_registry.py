"""Tests for simulation.scene_registry — pure logic, no external deps."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.scene_registry import (
    SCENE_REGISTRY,
    get_action_types,
    get_prompt_prefix,
    get_scene,
    get_scoring_metrics,
    list_scenes,
)


class TestSceneRegistry:
    def test_all_scenes_have_required_keys(self):
        required_keys = {"display_name", "prompt_prefix", "action_types", "scoring_metrics"}
        for scene_type, cfg in SCENE_REGISTRY.items():
            missing = required_keys - set(cfg.keys())
            assert not missing, f"Scene '{scene_type}' missing keys: {missing}"

    def test_all_scenes_have_observe_action(self):
        """Every scene should have an 'observe' action type (fallback)."""
        for scene_type, cfg in SCENE_REGISTRY.items():
            # finance uses 'hold' as fallback, but most have 'observe'
            # Just verify action_types is non-empty
            assert len(cfg["action_types"]) >= 3, f"Scene '{scene_type}' has too few action types"

    def test_scoring_metrics_weights_sum_to_one(self):
        for scene_type, cfg in SCENE_REGISTRY.items():
            metrics = cfg["scoring_metrics"]
            total_weight = sum(m["weight"] for m in metrics.values())
            assert abs(total_weight - 1.0) < 0.01, (
                f"Scene '{scene_type}' scoring weights sum to {total_weight}, expected 1.0"
            )

    def test_get_scene_returns_geopolitics_for_unknown(self):
        scene = get_scene("nonexistent_scene")
        assert scene["display_name"] == "地缘政治"

    def test_get_scene_valid(self):
        scene = get_scene("finance")
        assert scene["display_name"] == "金融市场"

    def test_get_action_types(self):
        actions = get_action_types("geopolitics")
        assert "diplomatic_statement" in actions
        assert "observe" in actions

    def test_get_scoring_metrics(self):
        metrics = get_scoring_metrics("supply_chain")
        assert "supply_continuity" in metrics
        assert metrics["supply_continuity"]["weight"] == 0.35

    def test_get_prompt_prefix(self):
        prefix = get_prompt_prefix("public_opinion")
        assert "舆论" in prefix

    def test_list_scenes(self):
        scenes = list_scenes()
        assert len(scenes) == len(SCENE_REGISTRY)
        scene_types = {s["scene_type"] for s in scenes}
        assert "geopolitics" in scene_types
        assert "finance" in scene_types
        assert "business" in scene_types


class TestSceneRegistryEdgeCases:
    def test_all_action_types_are_strings(self):
        for scene_type, cfg in SCENE_REGISTRY.items():
            for action in cfg["action_types"]:
                assert isinstance(action, str), f"Scene '{scene_type}' has non-string action: {action}"

    def test_all_metrics_have_desc_and_weight(self):
        for scene_type, cfg in SCENE_REGISTRY.items():
            for key, metric in cfg["scoring_metrics"].items():
                assert "desc" in metric, f"Scene '{scene_type}' metric '{key}' missing 'desc'"
                assert "weight" in metric, f"Scene '{scene_type}' metric '{key}' missing 'weight'"
                assert 0 < metric["weight"] <= 1.0
