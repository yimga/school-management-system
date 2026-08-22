"""OAuth2 token endpoint (client_credentials, refresh_token)."""

from urllib.parse import parse_qsl, urlencode, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.apicenter.models import (
    DeveloperApplication,
    OAuthAuthorizationCode,
    _hash_secret,
)

User = get_user_model()


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


@override_settings(ALLOWED_HOSTS=["*", "testserver"])
class OAuthAuthorizeScopeTests(TestCase):
    """The authorization server must not hand out scopes a client never registered.

    ``oauth_authorize`` read ``scope`` straight off the query string and stored it
    verbatim on the authorization code, and thus on ``OAuthTokenPair.scope``. On
    the read side ``apps.marketplace.permissions_runtime.effective_scopes_for_oauth_pair``
    UNIONS that self-declared string with the installation's GRANTED ScopeGrant
    rows, so the token's own claim was trusted: a client registered for "read"
    could send a user through authorize with ``scope=finance:write`` and get a
    token that ``app_has_scopes()`` accepts for finance writes.

    RFC 6749 sec. 3.3 makes constraining the requested scope the authorization
    server's job and names ``invalid_scope`` for the refusal.
    """

    def setUp(self):
        self.app = DeveloperApplication.objects.create(
            name="Scoped App",
            app_key="rmcapp_scopetest123456",
            client_id="rmc_scopetest_client_id",
            client_secret_hash=_hash_secret("cs_scope_secret_for_unit_tests"),
            redirect_uris=["http://127.0.0.1:9999/callback"],
            scopes=["read"],
        )
        # is_superuser purely to clear the module-access gate: /api/v1/oauth/authorize/
        # is additionally guarded by can_access_module(user, "oauth", "read"), which
        # 403s a plain user before the view runs. That gate is a separate concern
        # with its own coverage; what is under test here is what the authorization
        # server does with the scope parameter once a caller is admitted.
        self.user = User.objects.create_user(
            username="oauth_scope_user",
            email="oauth_scope@example.com",
            password="testpass123",
            is_superuser=True,
        )
        self.client.force_login(self.user)

    def _authorize(self, scope):
        return self.client.get(
            "/api/v1/oauth/authorize/",
            {
                "client_id": self.app.client_id,
                "redirect_uri": "http://127.0.0.1:9999/callback",
                "response_type": "code",
                "state": "xyz",
                "scope": scope,
            },
        )

    def _issued_scope(self, response):
        """Scope actually persisted on the authorization code behind the redirect.

        Only the HASH is stored (the raw code is returned once), so look the row
        up the same way consume_authorization_code does.
        """
        location = response.headers.get("Location", "")
        code = dict(parse_qsl(urlparse(location).query)).get("code")
        self.assertTrue(code, f"no code in redirect: {location!r}")
        return OAuthAuthorizationCode.objects.get(code_hash=_hash_secret(code)).scope

    def test_unregistered_scope_is_refused(self):
        r = self._authorize("finance:write")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(r.json().get("error"), "invalid_scope")

    def test_mixed_request_keeps_only_the_registered_scope(self):
        r = self._authorize("read finance:write")
        self.assertEqual(r.status_code, 302, r.content)
        self.assertEqual(self._issued_scope(r), "read")

    def test_empty_scope_falls_back_to_the_registered_default(self):
        r = self._authorize("")
        self.assertEqual(r.status_code, 302, r.content)
        self.assertEqual(self._issued_scope(r), "read")

    def test_registered_scope_still_works(self):
        r = self._authorize("read")
        self.assertEqual(r.status_code, 302, r.content)
        self.assertEqual(self._issued_scope(r), "read")
