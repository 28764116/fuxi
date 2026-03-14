"""Tests for memory.extractor — triplet extraction parsing and LLM integration."""

import json
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.extractor import Triplet, _clean_llm_output, extract_triplets


class TestCleanLLMOutput:
    def test_remove_think_blocks(self):
        text = "<think>some reasoning</think>actual output"
        assert _clean_llm_output(text) == "actual output"

    def test_remove_code_fences(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        assert _clean_llm_output(text) == '{"key": "value"}'

    def test_remove_multiline_think(self):
        text = "<think>\nlong\nreasoning\nblock\n</think>[{\"subject\": \"A\"}]"
        result = _clean_llm_output(text)
        assert result.startswith("[")

    def test_plain_text_unchanged(self):
        text = '[{"subject": "test"}]'
        assert _clean_llm_output(text) == text


class TestTriplet:
    def test_create_triplet(self):
        t = Triplet(
            subject="Alice",
            subject_type="person",
            predicate="works_at",
            object="Google",
            object_type="organization",
            fact="Alice works at Google",
            confidence=0.95,
        )
        assert t.subject == "Alice"
        assert t.confidence == 0.95

    def test_default_confidence(self):
        t = Triplet(
            subject="A", subject_type="person",
            predicate="rel", object="B", object_type="person",
            fact="A is related to B",
        )
        assert t.confidence == 1.0


class TestExtractTriplets:
    @patch("memory.extractor.OpenAI")
    def test_successful_extraction(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([
            {
                "subject": "美国",
                "subject_type": "organization",
                "predicate": "sanctions",
                "object": "华为",
                "object_type": "organization",
                "fact": "美国对华为实施制裁",
                "confidence": 0.9,
            }
        ])
        mock_client.chat.completions.create.return_value = mock_response

        result = extract_triplets("美国对华为实施了出口管制")
        assert len(result) == 1
        assert result[0].subject == "美国"
        assert result[0].object == "华为"

    @patch("memory.extractor.OpenAI")
    def test_extraction_with_think_block(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        raw = '<think>Analyzing...</think>```json\n' + json.dumps([
            {
                "subject": "张三",
                "subject_type": "person",
                "predicate": "lives_in",
                "object": "北京",
                "object_type": "location",
                "fact": "张三住在北京",
                "confidence": 0.8,
            }
        ]) + "\n```"
        mock_response = MagicMock()
        mock_response.choices[0].message.content = raw
        mock_client.chat.completions.create.return_value = mock_response

        result = extract_triplets("张三搬到了北京")
        assert len(result) == 1
        assert result[0].predicate == "lives_in"

    @patch("memory.extractor.OpenAI")
    def test_extraction_with_goal(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"
        mock_client.chat.completions.create.return_value = mock_response

        result = extract_triplets("Some text", goal="Analyze trade impacts")
        assert result == []
        # Verify goal was injected into prompt
        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args[1]["messages"][0]["content"]
        assert "GOAL-DIRECTED" in system_msg

    @patch("memory.extractor.OpenAI")
    def test_extraction_with_context(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"
        mock_client.chat.completions.create.return_value = mock_response

        extract_triplets("He works there", context="Previous: Alice went to Google")
        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "Previous context" in user_msg

    @patch("memory.extractor.OpenAI")
    def test_extraction_handles_llm_error(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        result = extract_triplets("Some text")
        assert result == []

    @patch("memory.extractor.OpenAI")
    def test_extraction_handles_malformed_item(self, mock_openai_class):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([
            {"subject": "A"},  # missing required fields
            {
                "subject": "B", "subject_type": "person",
                "predicate": "rel", "object": "C", "object_type": "org",
                "fact": "B relates to C", "confidence": 0.8,
            },
        ])
        mock_client.chat.completions.create.return_value = mock_response

        result = extract_triplets("test")
        assert len(result) == 1  # Only the valid one
        assert result[0].subject == "B"

    @patch("memory.extractor.OpenAI")
    def test_extraction_handles_dict_wrapper(self, mock_openai_class):
        """Some LLMs wrap results in a dict like {"triplets": [...]}."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "triplets": [
                {
                    "subject": "X", "subject_type": "concept",
                    "predicate": "causes", "object": "Y", "object_type": "concept",
                    "fact": "X causes Y",
                }
            ]
        })
        mock_client.chat.completions.create.return_value = mock_response

        result = extract_triplets("test")
        assert len(result) == 1
