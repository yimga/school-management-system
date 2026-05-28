"""Admin index surface preview context — live NPS metric and school rows."""


from django.test import TestCase

from apps.feedback.models import SurveyResponse
from apps.siteconfig.admin_index_surface import (
    build_admin_index_surface_context,
    build_admin_preview_nps_metric,
    empty_admin_index_surface,
)


class AdminIndexSurfaceTests(TestCase):
    def test_empty_surface_has_nps_metric_shape(self):
        surface = empty_admin_index_surface()
        nps = surface["nps_metric"]
        self.assertIn("score_display", nps)
        self.assertIn("eyebrow", nps)
        self.assertEqual(nps["response_count"], 0)

    def test_nps_metric_with_responses(self):
        for score in (10, 9, 8, 4, 10):
            SurveyResponse.objects.create(
                survey_type=SurveyResponse.SurveyType.NPS,
                score=score,
                role="parent",
            )
        metric = build_admin_preview_nps_metric()
        self.assertGreater(metric["response_count"], 0)
        self.assertNotEqual(metric["score_display"], "—")
        self.assertGreaterEqual(len(metric["breakdown"]), 1)

    def test_build_admin_index_surface_context_smoke(self):
        ctx = build_admin_index_surface_context()
        self.assertIn("school_rows", ctx)
        self.assertIn("nps_metric", ctx)
        self.assertIn("audit_rows", ctx)
