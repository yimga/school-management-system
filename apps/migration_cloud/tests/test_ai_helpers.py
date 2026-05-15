"""Smoke tests for `services.ai_helpers` (platform-wide AI wrapper).

The gateway itself is exercised by `services/tests/` (concurrent-agent
territory). These tests check only the wrapper behaviour: graceful
degradation when AI is disabled, PII heuristics, JSON extraction.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_helpers import (
    _extract_json,
    invoke_json_task,
    invoke_task,
    is_ai_available,
    looks_like_pii,
)


class IsAvailableTests(SimpleTestCase):
    def test_returns_false_for_none_school(self) -> None:
        self.assertFalse(is_ai_available(None))


class InvokeReturnsNoneWhenDisabled(SimpleTestCase):
    def test_invoke_task_returns_none_without_school(self) -> None:
        self.assertIsNone(
            invoke_task(
                school=None,
                task_type_name="NARRATIVE",
                prompt="anything",
                prompt_type="test.smoke",
            )
        )

    def test_invoke_json_task_returns_none_without_school(self) -> None:
        self.assertIsNone(
            invoke_json_task(
                school=None,
                task_type_name="NARRATIVE",
                prompt="anything",
                prompt_type="test.smoke",
            )
        )


class PiiHeuristicTests(SimpleTestCase):
    def test_obvious_pii_field_name_triggers(self) -> None:
        self.assertTrue(looks_like_pii("ssn"))

    def test_email_pattern_triggers(self) -> None:
        self.assertTrue(looks_like_pii("Hi from ada@example.com"))

    def test_us_ssn_pattern_triggers(self) -> None:
        self.assertTrue(looks_like_pii("123-45-6789"))

    def test_innocuous_string_doesnt_trigger(self) -> None:
        self.assertFalse(looks_like_pii("Math grade total"))


class JsonExtractionTests(SimpleTestCase):
    def test_extract_simple_json_object(self) -> None:
        self.assertEqual(_extract_json('Result: {"a": 1, "b": "x"}'), {"a": 1, "b": "x"})

    def test_extract_returns_none_on_garbage(self) -> None:
        self.assertIsNone(_extract_json("no braces at all"))

    def test_extract_handles_multiline_block(self) -> None:
        text = 'before\n{\n "k": 2\n}\nafter'
        self.assertEqual(_extract_json(text), {"k": 2})
