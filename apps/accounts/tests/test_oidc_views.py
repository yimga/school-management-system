import base64
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.models_sso import UserTenantBinding
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import ServiceIntegration


class OidcViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="OIDC School",
            slug="oidc-school",
            subdomain="oidc-school",
            is_active=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="District OIDC",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            endpoint_url="https://idp.example.com/authorize",
            client_id="oidc-client",
            client_secret="oidc-secret",
            config={
                "default_role": "TEACHER",
                "post_login_redirect": "/portal/",
                "token_endpoint": "https://idp.example.com/token",
            },
            is_active=True,
        )

    @staticmethod
    def _b64(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    def _id_token(self, *, nonce: str, email: str = "teacher.oidc@example.com"):
        header = {"alg": "none", "typ": "JWT"}
        payload = {
            "sub": "oidc-subject-1",
            "nonce": nonce,
            "email": email,
            "given_name": "Teacher",
            "family_name": "Oidc",
        }
        return f"{self._b64(header)}.{self._b64(payload)}."

    def test_oidc_start_redirects_to_authorization_endpoint(self):
        response = self.client.get(
            reverse("accounts:oidc_start", args=[self.integration.pk])
            + f"?school_slug={self.school.slug}"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("https://idp.example.com/authorize", response["Location"])
        self.assertIn("client_id=oidc-client", response["Location"])
        self.assertIn("response_type=code", response["Location"])

    def _start_and_state(self, *, next_url=""):
        suffix = f"&next={next_url}" if next_url else ""
        start = self.client.get(
            reverse("accounts:oidc_start", args=[self.integration.pk])
            + f"?school_slug={self.school.slug}{suffix}"
        )
        state = parse_qs(urlparse(start["Location"]).query)["state"][0]
        nonce = self.client.session[f"oidc:{self.integration.pk}:{state}"]["nonce"]
        return start, state, nonce

    def test_oidc_callback_provisions_user_and_membership(self):
        # SECURITY: the callback only trusts an id_token obtained via the
        # server-to-server code exchange (2026-06-17 auth-bypass seal) — never a
        # front-channel ?id_token=. Send a code and mock the exchange.
        _, state, nonce = self._start_and_state(next_url="/portal/")
        with patch(
            "apps.accounts.views_oidc._exchange_code_for_tokens",
            return_value={"id_token": self._id_token(nonce=nonce)},
        ):
            callback = self.client.get(
                reverse("accounts:oidc_callback", args=[self.integration.pk])
                + f"?state={state}&code=auth-code-abc"
            )
        self.assertEqual(callback.status_code, 302)
        self.assertIn("/portal/", callback["Location"])

        user = User.objects.get(email="teacher.oidc@example.com")
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertTrue(
            SchoolMembership.objects.filter(school=self.school, user=user).exists()
        )
        # F5b: the SSO login records a UserTenantBinding audit row.
        binding = UserTenantBinding.objects.get(user=user, school=self.school)
        self.assertEqual(binding.source, UserTenantBinding.Source.OIDC)
        self.assertEqual(binding.subject, "oidc-subject-1")

    def test_oidc_callback_rejects_bad_nonce(self):
        _, state, _ = self._start_and_state()
        with patch(
            "apps.accounts.views_oidc._exchange_code_for_tokens",
            return_value={"id_token": self._id_token(nonce="bad")},
        ):
            callback = self.client.get(
                reverse("accounts:oidc_callback", args=[self.integration.pk])
                + f"?state={state}&code=auth-code-abc"
            )
        self.assertEqual(callback.status_code, 403)

    def test_oidc_callback_stores_id_token_hint_for_logout(self):
        _, state, nonce = self._start_and_state()
        tok = self._id_token(nonce=nonce)
        with patch(
            "apps.accounts.views_oidc._exchange_code_for_tokens",
            return_value={"id_token": tok},
        ):
            self.client.get(
                reverse("accounts:oidc_callback", args=[self.integration.pk])
                + f"?state={state}&code=auth-code-abc"
            )
        self.assertEqual(
            self.client.session.get(f"oidc_id_token_hint:{self.integration.pk}"), tok
        )

    def test_oidc_logout_clears_session_and_redirects_end_session(self):
        self.integration.config = {
            **(self.integration.config or {}),
            "end_session_endpoint": "https://idp.example.com/logout",
            "post_logout_redirect_uri": "https://app.example.com/",
        }
        self.integration.save()
        session = self.client.session
        session[f"oidc_id_token_hint:{self.integration.pk}"] = "hint.token.value"
        session.save()
        self.client.force_login(
            User.objects.create_user("u1", password="x", role=User.Role.TEACHER)
        )
        r = self.client.get(reverse("accounts:oidc_logout", args=[self.integration.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("idp.example.com/logout", r["Location"])
        self.assertIn("post_logout_redirect_uri", r["Location"])
