"""OAuth2 token endpoint (client_credentials, refresh_token)."""

from urllib.parse import urlencode

from django.test import TestCase, override_settings

from apps.apicenter.models import DeveloperApplication, _hash_secret


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class OAuthTokenTests(TestCase):
    def setUp(self):
        raw_secret = "cs_test_secret_value_for_unit_tests_only"
        self.app = DeveloperApplication.objects.create(
            name="Test OAuth App",
            app_key="rmcapp_testunit123456",
            client_id="rmc_testunit_client_id_xx",
            client_secret_hash=_hash_secret(raw_secret),
            redirect_uris=["http://127.0.0.1:9999/callback"],
            scopes=["read"],
        )
        self.raw_secret = raw_secret

    def test_client_credentials_returns_tokens(self):
        r = self.client.post(
            "/api/v1/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.app.client_id,
                    "client_secret": self.raw_secret,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertEqual(body.get("token_type"), "Bearer")
        self.assertGreater(body.get("expires_in", 0), 0)

    def test_client_credentials_invalid_secret(self):
        r = self.client.post(
            "/api/v1/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.app.client_id,
                    "client_secret": "wrong",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(r.status_code, 401)

    def test_refresh_token_rotates(self):
        first = self.client.post(
            "/api/v1/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self.app.client_id,
                    "client_secret": self.raw_secret,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        refresh = first.json()["refresh_token"]
        second = self.client.post(
            "/api/v1/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": self.app.client_id,
                    "client_secret": self.raw_secret,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(second.status_code, 200, second.content)
        body = second.json()
        self.assertNotEqual(body["access_token"], first.json()["access_token"])
