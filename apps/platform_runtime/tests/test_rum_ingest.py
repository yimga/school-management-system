import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.platform_runtime.models import PlatformEventLog


@override_settings(ALLOWED_HOSTS=["testserver", "example.com"])
class RumIngestTests(TestCase):
    def test_disabled_without_key_returns_404(self):
        c = Client()
        r = c.post(
            reverse("rum_ingest"),
            data=json.dumps({"token": "x", "path": "/", "metrics": {}}),
            content_type="application/json",
            HTTP_HOST="testserver",
        )
        self.assertEqual(r.status_code, 404)

    @override_settings(RUM_INGEST_KEY="rum-test-key-16chars")
    def test_wrong_token_403(self):
        c = Client()
        r = c.post(
            reverse("rum_ingest"),
            data=json.dumps({"token": "wrong", "path": "/a", "metrics": {"lcp": 1.2}}),
            content_type="application/json",
            HTTP_HOST="testserver",
        )
        self.assertEqual(r.status_code, 403)

    @override_settings(RUM_INGEST_KEY="rum-test-key-16chars")
    def test_valid_beacon_emits_platform_event(self):
        c = Client()
        r = c.post(
            reverse("rum_ingest"),
            data=json.dumps(
                {
                    "token": "rum-test-key-16chars",
                    "path": "/portal/parent/",
                    "metrics": {"lcp": 1234.5, "cls": 0.01, "evil": 9},
                    "layout": {
                        "version": 1,
                        "observed_count": 5,
                        "overflow_count": 2,
                        "inline_overflow_count": 2,
                        "block_overflow_count": 0,
                        "max_inline_overflow_px": 72,
                        "viewport_class": "B",
                        "direction": "ltr",
                        "text": "must not persist",
                    },
                    "navigation_type": "0",
                }
            ),
            content_type="application/json",
            HTTP_HOST="testserver",
        )
        self.assertEqual(r.status_code, 204)
        row = PlatformEventLog.objects.filter(event_type="rum_web_vitals").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.payload.get("path"), "/portal/parent/")
        self.assertIn("lcp", row.payload.get("metrics", {}))
        self.assertNotIn("evil", row.payload.get("metrics", {}))
        self.assertEqual(row.payload["layout"]["overflow_count"], 2)
        self.assertNotIn("text", row.payload["layout"])

    @override_settings(RUM_INGEST_KEY="rum-test-key-16chars")
    def test_invalid_layout_version_is_discarded(self):
        c = Client()
        r = c.post(
            reverse("rum_ingest"),
            data=json.dumps(
                {
                    "token": "rum-test-key-16chars",
                    "path": "/",
                    "metrics": {},
                    "layout": {"version": 999, "text": "private"},
                }
            ),
            content_type="application/json",
            HTTP_HOST="testserver",
        )
        self.assertEqual(r.status_code, 204)
        row = PlatformEventLog.objects.filter(event_type="rum_web_vitals").first()
        self.assertEqual(row.payload["layout"], {})
