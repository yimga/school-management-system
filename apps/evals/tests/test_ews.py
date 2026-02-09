"""Tests for EWS (early warning system) dashboard helper."""
from django.test import TestCase

from apps.evals.services import ews_students_needing_attention


class EWSHelperTests(TestCase):
    """ews_students_needing_attention returns empty when inputs are empty/None."""

    def test_returns_empty_when_no_teacher_profile(self):
        result = ews_students_needing_attention(None, None, None, [])
        self.assertEqual(result, [])

    def test_returns_empty_when_assignments_empty(self):
        result = ews_students_needing_attention(
            object(),  # any teacher stub
            object(),
            object(),
            [],
        )
        self.assertEqual(result, [])
