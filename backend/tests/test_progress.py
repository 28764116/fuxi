"""Tests for simulation.progress — Redis publish logic."""

import json
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPublishProgress:
    @patch("simulation.progress._get_redis")
    def test_publish_basic(self, mock_get_redis):
        from simulation.progress import publish_progress

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        publish_progress("task-123", "extracting", 15, "Extracting entities...")

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        payload = json.loads(call_args[0][1])

        assert channel == "sim:progress:task-123"
        assert payload["status"] == "extracting"
        assert payload["progress"] == 15
        assert payload["message"] == "Extracting entities..."
        assert payload["error"] is None

    @patch("simulation.progress._get_redis")
    def test_publish_with_error(self, mock_get_redis):
        from simulation.progress import publish_progress

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        publish_progress("task-456", "failed", 50, error="Something broke")

        payload = json.loads(mock_redis.publish.call_args[0][1])
        assert payload["status"] == "failed"
        assert payload["error"] == "Something broke"

    @patch("simulation.progress._get_redis")
    def test_publish_with_worldline_and_event(self, mock_get_redis):
        from simulation.progress import publish_progress

        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        publish_progress(
            "task-789", "simulating", 60, "Running worldline 2/3",
            worldline_id="wl-001",
            latest_event={"action_type": "escalation", "description": "Major event"},
        )

        payload = json.loads(mock_redis.publish.call_args[0][1])
        assert payload["worldline_id"] == "wl-001"
        assert payload["latest_event"]["action_type"] == "escalation"

    @patch("simulation.progress._get_redis")
    def test_publish_handles_redis_error(self, mock_get_redis):
        from simulation.progress import publish_progress

        mock_redis = MagicMock()
        mock_redis.publish.side_effect = Exception("Redis down")
        mock_get_redis.return_value = mock_redis

        # Should not raise, just log
        publish_progress("task-err", "extracting", 5, "Test")
