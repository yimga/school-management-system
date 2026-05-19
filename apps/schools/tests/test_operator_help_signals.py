"""Operator help signal bundle — no PII aggregates."""

from django.test import SimpleTestCase

from apps.schools.operator_help_signals import operator_help_signal_bundle


class OperatorHelpSignalsTests(SimpleTestCase):
    def test_bundle_shape(self):
        bundle = operator_help_signal_bundle()
        self.assertIn("friction", bundle)
        self.assertIn("feedback", bundle)
        self.assertIn("ai", bundle)
        self.assertIn("kb", bundle)
        self.assertIn("total_signal_7d", bundle)
        self.assertIsInstance(bundle["kb"].get("article_count", 0), int)
