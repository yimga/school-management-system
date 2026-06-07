from __future__ import annotations

from unittest.mock import patch

from django.test import Client, TestCase, override_settings


@override_settings(
    ALLOWED_HOSTS=[
        "*",
        "manager.runmycampus.com",
        "school-management-system-2kzk.onrender.com",
    ],
    ROOT_URLCONF="config.urls",
)
class LiveVersionEndpointTests(TestCase):
    def test_version_endpoint_returns_safe_metadata_from_env(self):
        with patch.dict(
            "os.environ",
            {
                "RENDER_GIT_COMMIT": "e194771fd270a475e18cf7c85e3b6e2cffc85ebc",
                "BUILD_TIME": "2026-05-05T20:00:00Z",
                "RENDER_SERVICE_NAME": "school-management-system",
                "DATABASE_URL": "postgres://user:secret@example.test/db",
                "SECRET_KEY": "not-for-output",
            },
            clear=False,
        ):
            response = Client().get("/-/version/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        payload = response.json()
        self.assertEqual(
            payload["commit_sha"], "e194771fd270a475e18cf7c85e3b6e2cffc85ebc"
        )
        self.assertEqual(payload["build_time"], "2026-05-05T20:00:00Z")
        self.assertEqual(payload["environment"], "school-management-system")
        self.assertIn("app_version", payload)
        body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn("DATABASE_URL", body)
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("not-for-output", body)
        self.assertNotIn("postgres://", body)

    def test_missing_or_invalid_commit_reports_unknown(self):
        with patch.dict(
            "os.environ",
            {"RENDER_GIT_COMMIT": "not a sha", "GIT_COMMIT": ""},
            clear=True,
        ):
            response = Client().get("/-/version/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertEqual(response.json()["commit_sha"], "unknown")

    def test_version_endpoint_resolves_on_manager_urlconf(self):
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            response = Client(HTTP_HOST="manager.runmycampus.com").get("/-/version/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertIn("commit_sha", response.json())

    def test_version_endpoint_resolves_on_public_urlconf(self):
        with self.settings(ROOT_URLCONF="config.public_urls"):
            response = Client(
                HTTP_HOST="school-management-system-2kzk.onrender.com"
            ).get("/-/version/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertIn("commit_sha", response.json())

    def test_public_urlconf_version_aliases_return_json(self):
        with self.settings(ROOT_URLCONF="config.public_urls"):
            client = Client(HTTP_HOST="runmycampus.com")
            for path in (
                "/api/system/version/",
                "/version.json",
            ):
                with self.subTest(path=path):
                    response = client.get(path, HTTP_ACCEPT="application/json")
                    self.assertEqual(response.status_code, 200, msg=response.content[:200])
                    self.assertIn("application/json", response["Content-Type"])
                    self.assertIn("commit_sha", response.json())

    def test_manager_urlconf_version_aliases_return_json(self):
        with self.settings(ROOT_URLCONF="config.manager_urls"):
            client = Client(HTTP_HOST="manager.runmycampus.com")
            for path in ("/api/system/version/", "/version.json"):
                with self.subTest(path=path):
                    response = client.get(path, HTTP_ACCEPT="application/json")
                    self.assertEqual(response.status_code, 200, msg=response.content[:200])
                    self.assertIn("commit_sha", response.json())

    def test_version_endpoint_resolves_on_tenant_urlconf(self):
        with self.settings(ROOT_URLCONF="config.tenant_urls"):
            response = Client(HTTP_HOST="demo.runmycampus.com").get("/-/version/")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        payload = response.json()
        self.assertIn("commit_sha", payload)
        self.assertIn("app_version", payload)
