"""analytics_viz_context enables mounts on marketing (no request.site)."""

from django.test import RequestFactory, TestCase

from apps.siteconfig.context_processors import analytics_viz_context


class AnalyticsVizContextTests(TestCase):
    def test_marketing_request_uses_code_defaults(self):
        request = RequestFactory().get("/marketing/")
        request.site = None
        ctx = analytics_viz_context(request)
        self.assertTrue(ctx["ENABLE_UNIFIED_ANALYTICS_VIZ"])
        self.assertIn("analytics-viz", ctx["ANALYTICS_VIZ_API_URL"])
