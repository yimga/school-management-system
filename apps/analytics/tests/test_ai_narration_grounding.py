"""Tests for ``apps.analytics.ai_narration_grounding``.

12-pillar audit P8 follow-up. Verifies the entity-grounding guardrail
correctly rejects narratives that mention names absent from the input
context, and accepts narratives that stay within the allowlist.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.analytics.ai_narration_grounding import (
    UngroundedNarrativeError,
    assert_grounded,
    extract_proper_nouns,
    is_grounded,
)


class ExtractProperNounsTests(SimpleTestCase):
    def test_empty_text_returns_empty_list(self):
        self.assertEqual(extract_proper_nouns(""), [])
        self.assertEqual(extract_proper_nouns(None), [])  # type: ignore[arg-type]

    def test_single_name_extracted(self):
        text = "Aisha needs early outreach this week."
        self.assertEqual(extract_proper_nouns(text), ["Aisha"])

    def test_two_word_name_extracted_as_one_token(self):
        text = "Aisha Mohammed is in the red band."
        self.assertEqual(extract_proper_nouns(text), ["Aisha Mohammed"])

    def test_multiple_names(self):
        text = "Schedule a check-in for Aisha Mohammed and Daniel Park."
        result = extract_proper_nouns(text)
        self.assertIn("Aisha Mohammed", result)
        self.assertIn("Daniel Park", result)

    def test_safe_stopwords_excluded(self):
        text = (
            "The student is struggling. Today Aisha will meet with the "
            "Math teacher."
        )
        # "The", "Today", and "Math" are in _SAFE_CAPITALIZED_TOKENS;
        # only "Aisha" is a real entity.
        self.assertEqual(extract_proper_nouns(text), ["Aisha"])

    def test_dedup_preserves_first_occurrence(self):
        text = "Aisha is struggling. Aisha needs help. Aisha can recover."
        self.assertEqual(extract_proper_nouns(text), ["Aisha"])


class AssertGroundedTests(SimpleTestCase):
    def test_grounded_narrative_does_not_raise(self):
        narrative = (
            "Aisha Mohammed and Daniel Park are in the red band today. "
            "Reach out to their teachers this afternoon."
        )
        allowed = ["Aisha Mohammed", "Daniel Park"]
        # Should not raise.
        assert_grounded(narrative, allowed)

    def test_first_name_only_in_narrative_is_grounded(self):
        # _expand_allowed admits "Aisha" when "Aisha Mohammed" is allowed.
        narrative = "Aisha needs an early check-in this week."
        allowed = ["Aisha Mohammed"]
        assert_grounded(narrative, allowed)

    def test_hallucinated_name_raises(self):
        narrative = (
            "Aisha Mohammed is high-risk. Also, James Wong should be "
            "called immediately."  # James Wong is not in the input.
        )
        allowed = ["Aisha Mohammed"]
        with self.assertRaises(UngroundedNarrativeError) as ctx:
            assert_grounded(narrative, allowed)
        self.assertIn("James Wong", ctx.exception.unknown_entities)

    def test_hallucinated_single_name_raises(self):
        narrative = "Reach out to Cassandra today."
        allowed = ["Aisha Mohammed", "Daniel Park"]
        with self.assertRaises(UngroundedNarrativeError) as ctx:
            assert_grounded(narrative, allowed)
        self.assertIn("Cassandra", ctx.exception.unknown_entities)

    def test_empty_narrative_is_grounded(self):
        # Fallback path (gateway off) emits empty string; that's grounded
        # by definition (no entities to verify).
        assert_grounded("", ["Aisha Mohammed"])

    def test_school_domain_words_not_treated_as_entities(self):
        # Words like Math, Reading, Attendance are common in school
        # narratives and should not trigger false positives.
        narrative = "Math and Attendance are the top drivers for the cohort."
        assert_grounded(narrative, [])  # no allowed entities; should still pass.

    def test_is_grounded_returns_bool(self):
        self.assertTrue(is_grounded("Aisha needs outreach.", ["Aisha"]))
        self.assertFalse(is_grounded("Aisha and James need outreach.", ["Aisha"]))


class ErrorReportingTests(SimpleTestCase):
    def test_error_carries_narrative_and_unknown_list(self):
        narrative = "Call Aisha and James about the Phoenix initiative."
        try:
            assert_grounded(narrative, ["Aisha"])
        except UngroundedNarrativeError as exc:
            self.assertEqual(exc.narrative, narrative)
            self.assertGreater(len(exc.unknown_entities), 0)
            # "James" or "Phoenix" must be flagged.
            joined = " ".join(exc.unknown_entities)
            self.assertTrue("James" in joined or "Phoenix" in joined)
        else:
            self.fail("expected UngroundedNarrativeError")
