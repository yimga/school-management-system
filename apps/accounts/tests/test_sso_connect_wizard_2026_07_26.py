"""F5b — self-serve SSO connect wizard + UserTenantBinding at JIT (2026-07-26).

RequestFactory unit tests (per the accounts test-harness pattern): the SSO admin
views are @login_required @require_school, so we set request.user + request.school
directly and attach a session + message store. Discovery HTTP is mocked.
"""

import json
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.models_sso import UserTenantBinding
from apps.accounts.sso_binding import bind_user_to_tenant
from apps.accounts.views_sso_admin import (
    sso_connection_delete,
    sso_connection_toggle,
    sso_connections,
    sso_discovery_probe,
)
from apps.integrations_marketplace.models import ServiceIntegration
from apps.schools.models import School, SchoolMembership

_OAUTH = ServiceIntegration.ServiceType.OAUTH
_GOOGLE_ENDPOINTS = {
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
    "issuer": "https://accounts.google.com",
}


class SsoConnectWizardTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="SSO Wizard School", slug="sso-wizard", subdomain="sso-wizard",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="sso.admin", email="sso.admin@example.com", password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.admin, role=User.Role.ADMIN, is_primary=True
        )
        self.parent = User.objects.create_user(
            username="sso.parent", email="sso.parent@example.com", password="x",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            school=self.school, user=self.parent, role=User.Role.PARENT
        )

    def _prep(self, request, user):
        request.user = user
        request.school = self.school
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def _post(self, data, user=None):
        req = self.factory.post("/accounts/sso/connections/", data)
        return self._prep(req, user or self.admin)

    # ---- permission gate --------------------------------------------------

    def test_non_manager_forbidden(self):
        req = self.factory.get("/accounts/sso/connections/")
        self._prep(req, self.parent)
        resp = sso_connections(req)
        self.assertEqual(resp.status_code, 403)

    # ---- create OIDC ------------------------------------------------------

    @patch("apps.accounts.views_sso_admin.fetch_oidc_discovery")
    def test_create_google_oidc_activates_and_lights_login(self, mock_fetch):
        mock_fetch.return_value = {"ok": True, "endpoints": dict(_GOOGLE_ENDPOINTS)}
        resp = sso_connections(
            self._post(
                {
                    "provider": "google",
                    "client_id": "cid-123",
                    "client_secret": "sekret",
                    "default_role": "TEACHER",
                    "scope": "openid email profile",
                    "is_active": "on",
                }
            )
        )
        self.assertEqual(resp.status_code, 302)
        si = ServiceIntegration.objects.get(school=self.school, service_type=_OAUTH)
        self.assertEqual(si.config["idp_type"], "oidc")
        self.assertEqual(si.config["display_name"], "Google")
        self.assertEqual(si.config["default_role"], "TEACHER")
        self.assertEqual(
            si.config["authorization_endpoint"], _GOOGLE_ENDPOINTS["authorization_endpoint"]
        )
        self.assertEqual(si.config["token_endpoint"], _GOOGLE_ENDPOINTS["token_endpoint"])
        self.assertEqual(si.client_id, "cid-123")
        self.assertTrue(si.is_active)

        # The login page button now lights up for this school.
        from apps.accounts.views import _get_login_sso_integrations

        fake = self.factory.get("/")
        fake.school = self.school
        labels = [b["label"] for b in _get_login_sso_integrations(fake)]
        self.assertIn("Google", labels)

    @patch("apps.accounts.views_sso_admin.fetch_oidc_discovery")
    def test_discovery_unreachable_saves_draft(self, mock_fetch):
        mock_fetch.return_value = {"ok": False, "error": "Could not reach the IdP discovery URL (URLError)."}
        resp = sso_connections(
            self._post(
                {"provider": "google", "client_id": "cid", "client_secret": "s", "is_active": "on"}
            )
        )
        self.assertEqual(resp.status_code, 302)
        si = ServiceIntegration.objects.get(school=self.school, service_type=_OAUTH)
        self.assertFalse(si.is_active)  # forced to draft — cannot activate a broken IdP

    @patch("apps.accounts.views_sso_admin.fetch_oidc_discovery")
    def test_missing_client_id_rerenders_no_row(self, mock_fetch):
        mock_fetch.return_value = {"ok": True, "endpoints": dict(_GOOGLE_ENDPOINTS)}
        resp = sso_connections(self._post({"provider": "google", "is_active": "on"}))
        self.assertEqual(resp.status_code, 200)  # re-rendered form with error
        self.assertFalse(
            ServiceIntegration.objects.filter(school=self.school, service_type=_OAUTH).exists()
        )

    @patch("apps.accounts.views_sso_admin.fetch_oidc_discovery")
    def test_invalid_role_map_rerenders_no_row(self, mock_fetch):
        mock_fetch.return_value = {"ok": True, "endpoints": dict(_GOOGLE_ENDPOINTS)}
        resp = sso_connections(
            self._post(
                {"provider": "google", "client_id": "c", "client_secret": "s", "role_map": "{not json"}
            )
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            ServiceIntegration.objects.filter(school=self.school, service_type=_OAUTH).exists()
        )

    @patch("apps.accounts.views_sso_admin.fetch_oidc_discovery")
    def test_role_map_drops_non_provisionable_targets(self, mock_fetch):
        mock_fetch.return_value = {"ok": True, "endpoints": dict(_GOOGLE_ENDPOINTS)}
        sso_connections(
            self._post(
                {
                    "provider": "google", "client_id": "c", "client_secret": "s",
                    "role_map": json.dumps({"Teachers": "TEACHER", "Admins": "SUPERADMIN"}),
                    "is_active": "on",
                }
            )
        )
        si = ServiceIntegration.objects.get(school=self.school, service_type=_OAUTH)
        self.assertEqual(si.config.get("role_map"), {"Teachers": "TEACHER"})  # SUPERADMIN dropped

    # ---- SAML -------------------------------------------------------------

    def test_saml_without_cert_saves_draft(self):
        resp = sso_connections(
            self._post(
                {"provider": "saml", "saml_sso_url": "https://idp.example.com/sso", "is_active": "on"}
            )
        )
        self.assertEqual(resp.status_code, 302)
        si = ServiceIntegration.objects.get(school=self.school, service_type=_OAUTH)
        self.assertEqual(si.config["idp_type"], "saml")
        self.assertFalse(si.is_active)

    # ---- discovery probe --------------------------------------------------

    @patch("apps.accounts.views_sso_admin.fetch_oidc_discovery")
    def test_discovery_probe_returns_endpoints(self, mock_fetch):
        mock_fetch.return_value = {"ok": True, "endpoints": dict(_GOOGLE_ENDPOINTS)}
        req = self.factory.post("/accounts/sso/connections/discovery-probe/", {"provider": "google"})
        self._prep(req, self.admin)
        resp = sso_discovery_probe(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["endpoints"]["issuer"], "https://accounts.google.com")

    def test_discovery_probe_forbidden_for_non_manager(self):
        req = self.factory.post("/accounts/sso/connections/discovery-probe/", {"provider": "google"})
        self._prep(req, self.parent)
        resp = sso_discovery_probe(req)
        self.assertEqual(resp.status_code, 403)

    # ---- toggle + delete --------------------------------------------------

    def _make_connection(self):
        return ServiceIntegration.objects.create(
            school=self.school, service_name="google", service_type=_OAUTH,
            client_id="c", config={"idp_type": "oidc", "display_name": "Google"},
            is_active=True,
        )

    def test_toggle_flips_active(self):
        si = self._make_connection()
        req = self.factory.post(f"/accounts/sso/connections/{si.pk}/toggle/")
        self._prep(req, self.admin)
        resp = sso_connection_toggle(req, si.pk)
        self.assertEqual(resp.status_code, 302)
        si.refresh_from_db()
        self.assertFalse(si.is_active)

    def test_delete_removes_connection(self):
        si = self._make_connection()
        req = self.factory.post(f"/accounts/sso/connections/{si.pk}/delete/")
        self._prep(req, self.admin)
        resp = sso_connection_delete(req, si.pk)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ServiceIntegration.objects.filter(pk=si.pk).exists())


class SsoBindingTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="Bind A", slug="bind-a", subdomain="bind-a", is_active=True
        )
        self.school_b = School.objects.create(
            name="Bind B", slug="bind-b", subdomain="bind-b", is_active=True
        )
        self.user = User.objects.create_user(
            username="bind.user", email="bind@example.com", password="x"
        )

    def test_first_binding_is_primary(self):
        binding = bind_user_to_tenant(
            user=self.user, school=self.school_a,
            source=UserTenantBinding.Source.OIDC, subject="sub-1", issuer="https://idp",
        )
        self.assertIsNotNone(binding)
        self.assertTrue(binding.is_primary)
        self.assertEqual(binding.source, UserTenantBinding.Source.OIDC)
        self.assertEqual(binding.subject, "sub-1")

    def test_second_school_binding_not_primary(self):
        bind_user_to_tenant(user=self.user, school=self.school_a, source=UserTenantBinding.Source.OIDC)
        b2 = bind_user_to_tenant(user=self.user, school=self.school_b, source=UserTenantBinding.Source.SAML)
        self.assertFalse(b2.is_primary)
        # Constraint holds: exactly one primary binding for the user.
        self.assertEqual(
            UserTenantBinding.objects.filter(user=self.user, is_primary=True).count(), 1
        )

    def test_idempotent_refreshes_audit_fields(self):
        bind_user_to_tenant(user=self.user, school=self.school_a, source=UserTenantBinding.Source.OIDC, subject="old")
        bind_user_to_tenant(user=self.user, school=self.school_a, source=UserTenantBinding.Source.OIDC, subject="new")
        self.assertEqual(
            UserTenantBinding.objects.filter(user=self.user, school=self.school_a).count(), 1
        )
        binding = UserTenantBinding.objects.get(user=self.user, school=self.school_a)
        self.assertEqual(binding.subject, "new")
