from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.platform_runtime.context_processors import rum_ingest_context


class LayoutObservabilityContextTests(SimpleTestCase):
    @override_settings(
        RUM_INGEST_KEY="",
        RMC_LAYOUT_OBSERVABILITY_ENABLED=False,
    )
    def test_kill_switch_is_exposed_without_rum_key(self):
        context = rum_ingest_context(RequestFactory().get("/"))
        self.assertFalse(context["rmc_layout_observability_enabled"])
        self.assertIsNone(context["rum_ingest_url"])
