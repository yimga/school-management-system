"""Help-center tier batches 1339–1345 — unit tests."""

from django.test import SimpleTestCase

from apps.portal.kb_synonyms import expand_query_synonyms
from apps.portal.help_search_intelligence import zero_result_fingerprints, deflection_rate_summary
from apps.portal.help_governance import ai_help_enabled_for_request, help_telemetry_retention_days
from apps.portal.kb_embeddings import effective_deflection_threshold, filter_kb_queryset_by_locale


class HelpCenterTiersTests(SimpleTestCase):
    def test_synonym_expansion(self):
        out = expand_query_synonyms("enrolment fees")
        self.assertIn("enrollment", out.lower())

    def test_deflection_threshold_in_range(self):
        t = effective_deflection_threshold(school=None)
        self.assertGreaterEqual(t, 0.88)
        self.assertLessEqual(t, 0.95)

    def test_zero_result_summary_shape(self):
        rows = zero_result_fingerprints(days=7, limit=3)
        self.assertIsInstance(rows, list)

    def test_deflection_metrics_shape(self):
        m = deflection_rate_summary(days=7)
        self.assertIn("available", m)

    def test_governance_defaults(self):
        self.assertGreaterEqual(help_telemetry_retention_days(), 30)

    def test_hitl_model_has_note_field(self):
        from apps.feedback.models import SupportAIInteractionReview

        self.assertIsNotNone(SupportAIInteractionReview._meta.get_field("note"))

    def test_locale_filter_no_crash(self):
        from apps.portal.kb_context import published_kb_queryset

        qs = filter_kb_queryset_by_locale(published_kb_queryset())
        self.assertTrue(hasattr(qs, "count"))
