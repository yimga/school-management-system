"""Stable status codes for unauthenticated /api/v1/* (contract smoke)."""

from django.test import TestCase


class ApiV1ContractSmokeTests(TestCase):
    def test_manifest_public(self):
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"].split(";")[0].strip(), "application/json")

    def test_developer_api_docs_public(self):
        r = self.client.get("/developers/api-docs/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "manifest")

    def test_protected_v1_returns_401_without_auth(self):
        for path in (
            "/api/v1/me/schools",
            "/api/v1/super/pulse",
            "/api/v1/finance/disputes",
        ):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertIn(
                    r.status_code,
                    (401, 403, 302),
                    msg=f"{path} -> {r.status_code}",
                )
