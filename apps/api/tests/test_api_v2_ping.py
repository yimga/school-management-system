"""Smoke tests for /api/v2/ developer-platform surface."""

from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class ApiV2PingTests(TestCase):
    def test_ping_returns_contract_envelope(self):
        r = self.client.get("/api/v2/ping/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("contract_version", data)
        self.assertEqual(data["data"]["api_version"], "2")

    def test_v2_manifest_has_oauth_and_links(self):
        r = self.client.get("/api/v2/manifest.json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("api_version"), "2.0")
        self.assertIn("oauth", data)
        self.assertIn("token_url", data["oauth"])
        self.assertIn("/api/v1/oauth/token/", data["oauth"]["token_url"])
        self.assertIn("links", data)
        self.assertIn("developer_hub", data["links"])
