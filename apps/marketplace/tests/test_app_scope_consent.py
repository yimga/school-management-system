"""
Pillar 4: Sandboxed marketplace security — install-time scope consent.

Two layers of test coverage:
- ``AppScopeConsentTests`` (SimpleTestCase): the contract that drives the UI
  payload (build_scope_consent in app_catalog_governance).
- ``MarketplaceInstallScopeConsentTests`` (TestCase): the end-to-end POST
  contract — the install endpoint refuses install when any manifest scope is
  not explicitly confirmed, succeeds when all are, persists per-scope grants,
  writes a ``compliance.AuditLog.PERMISSION_GRANT`` row capturing the exact
  consented scope list, and stays tenant-scoped (school A's consent does NOT
  install for school B).
"""

import os
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.compliance.models_audit import AuditLog as ComplianceAuditLog
from apps.marketplace.models import (
    AppInstallation,
    AppScope,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
    ScopeGrant,
)
from apps.platform_runtime.app_catalog_governance import build_scope_consent
from apps.schools.models import School, SchoolMembership


class AppScopeConsentTests(SimpleTestCase):
    def test_scope_consent_exposes_data_billing_webhook_and_uninstall_impact(self):
        consent = build_scope_consent(
            {
                "app_key": "attendance-recovery",
                "scopes": ["attendance:read", "students:write"],
                "billing_model": "usage",
                "webhooks": ["attendance.absent"],
            }
        )

        self.assertTrue(consent["consent_required"])
        self.assertEqual(consent["data_access"], ["attendance", "students"])
        self.assertEqual(consent["billing_impact"], "usage")
        self.assertIn("attendance.absent", consent["webhook_impact"])
        self.assertEqual(consent["uninstall_posture"], "revoke_scopes_disable_webhooks_preserve_audit")


_TENANT_HOST_A = "scope-consent-a.runmycampus.com"
_TENANT_HOST_B = "scope-consent-b.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _TENANT_HOST_A, _TENANT_HOST_B],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
)
class MarketplaceInstallScopeConsentTests(TestCase):
    """End-to-end install-time consent gate (Pillar 4)."""

    @classmethod
    def setUpTestData(cls):
        cls.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        cls.env.start()
        cls.school_a = School.objects.create(
            name="Scope Consent School A",
            slug="scope-consent-a",
            subdomain="scope-consent-a",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Scope Consent School B",
            slug="scope-consent-b",
            subdomain="scope-consent-b",
            is_active=True,
        )
        cls.perm_manage, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.admin_a = User.objects.create_user(
            username="scope_admin_a",
            password="test-harness-1",
            role=User.Role.ADMIN,
        )
        cls.admin_a.feature_permissions.add(cls.perm_manage)
        SchoolMembership.objects.get_or_create(
            user=cls.admin_a,
            school=cls.school_a,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="scope-consent-publisher",
            name="Scope Consent Publisher",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
            country_code="US",
            payout_ref="scope-consent-publisher",
        )
        cls.app = MarketplaceApp.objects.create(
            publisher=cls.publisher,
            slug="scope-consent-app",
            name="Scope Consent App",
            kind=MarketplaceApp.AppKind.THIRD_PARTY,
            version="1.0.0",
            manifest={
                "scopes": ["attendance:read", "students:write", "grades:read"],
                "widgets": {},
            },
            is_active=True,
            is_intentionally_free=True,
        )
        AppScope.objects.create(
            app=cls.app, scope_code="attendance:read", description="Read attendance",
        )
        AppScope.objects.create(
            app=cls.app, scope_code="students:write", description="Update students",
            sensitive=True,
        )
        AppScope.objects.create(
            app=cls.app, scope_code="grades:read", description="Read grades",
        )
        MarketplaceListing.objects.create(
            app=cls.app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        super().tearDownClass()

    def setUp(self):
        from django.test import Client
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self.client = Client(HTTP_HOST=_TENANT_HOST_A, raise_request_exception=False)
        # Bypass MFA gate (the marketplace install routes go through it).
        TOTPDevice.objects.get_or_create(
            user=self.admin_a, name="test-device", defaults={"confirmed": True}
        )

    def _login_admin_a(self):
        self.client.login(username="scope_admin_a", password="test-harness-1")
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def _install_url(self):
        return reverse("tenant_install_app", urlconf="config.tenant_urls")

    def _catalog_url(self):
        return reverse("tenant_app_catalog", urlconf="config.tenant_urls")

    # ----- Test 1: consent screen renders all manifest scopes -----
    def test_install_shows_consent_screen_for_all_manifest_scopes(self):
        """The catalog page must render the install-impact modal partial AND
        the consent fieldset; the impact preview JSON must include every
        scope the manifest declares so the JS can build a checkbox per scope."""
        from apps.marketplace.install_impact import build_tenant_install_impact

        impact = build_tenant_install_impact(self.school_a, self.app)
        codes = sorted(s["scope_code"] for s in impact["scopes"])
        self.assertEqual(
            codes, ["attendance:read", "grades:read", "students:write"],
            "build_tenant_install_impact must surface every AppScope so the "
            "consent UI can render a checkbox per scope.",
        )
        # Modal partial must contain the consent fieldset that the JS populates.
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        partial = repo_root / "templates/marketplace/partials/install_impact_modal.html"
        text = partial.read_text(encoding="utf-8")
        self.assertIn("rmcInstallImpactConsentList", text)
        self.assertIn("rmc-scope-consent", text)
        # Submit must be disabled by default until JS verifies consent.
        self.assertIn("disabled", text)
        # JS file injects a checkbox per scope under name="consented_scopes".
        js_path = repo_root / (
            "static/js/_pages/marketplace__partials__install_impact_modal-1.js"
        )
        js_text = js_path.read_text(encoding="utf-8")
        self.assertIn('"consented_scopes"', js_text)
        self.assertIn("renderConsent", js_text)
        self.assertIn("refreshConsentGate", js_text)

    # ----- Test 2: install REFUSED when any scope is unconfirmed -----
    def test_install_refuses_when_scope_not_confirmed(self):
        self._login_admin_a()
        # Confirm only 2 of 3 scopes — install must be refused.
        resp = self.client.post(
            self._install_url(),
            {
                "app_id": self.app.pk,
                "install_after_impact_preview": "1",
                "consented_scopes": ["attendance:read", "students:write"],
                # missing "grades:read"
            },
            HTTP_HOST=_TENANT_HOST_A,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            AppInstallation.objects.filter(
                school=self.school_a, app=self.app
            ).exists(),
            "Install must NOT be persisted when consent is incomplete.",
        )
        # And no PERMISSION_GRANT audit row should exist.
        self.assertFalse(
            ComplianceAuditLog.objects.filter(
                action=ComplianceAuditLog.Action.PERMISSION_GRANT,
                model_name="AppInstallation",
            ).exists()
        )

    def test_install_refuses_when_no_scopes_confirmed(self):
        self._login_admin_a()
        resp = self.client.post(
            self._install_url(),
            {
                "app_id": self.app.pk,
                "install_after_impact_preview": "1",
                # consented_scopes entirely absent
            },
            HTTP_HOST=_TENANT_HOST_A,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            AppInstallation.objects.filter(
                school=self.school_a, app=self.app
            ).exists()
        )

    # ----- Test 3: install SUCCEEDS when all scopes confirmed -----
    def test_install_succeeds_when_all_scopes_confirmed(self):
        self._login_admin_a()
        resp = self.client.post(
            self._install_url(),
            {
                "app_id": self.app.pk,
                "install_after_impact_preview": "1",
                "consented_scopes": [
                    "attendance:read",
                    "students:write",
                    "grades:read",
                ],
            },
            HTTP_HOST=_TENANT_HOST_A,
        )
        self.assertEqual(resp.status_code, 302)
        # Pull flash messages without rendering the redirect target.
        from django.contrib.messages import get_messages
        msgs = "; ".join(str(m) for m in get_messages(resp.wsgi_request))
        installation = AppInstallation.objects.filter(
            school=self.school_a, app=self.app
        ).first()
        self.assertIsNotNone(
            installation,
            f"Install must succeed when all scopes consented. Redirect → {resp.url}; messages: {msgs!r}",
        )
        # Sandbox-first.
        self.assertEqual(
            installation.install_phase, AppInstallation.InstallPhase.SANDBOX
        )
        # ScopeGrant rows should exist for each consented scope.
        granted_codes = sorted(
            ScopeGrant.objects.filter(installation=installation)
            .values_list("scope__scope_code", flat=True)
        )
        self.assertEqual(
            granted_codes, ["attendance:read", "grades:read", "students:write"]
        )
        # Sensitive scope must be PENDING; non-sensitive must be GRANTED.
        sensitive_grant = ScopeGrant.objects.get(
            installation=installation, scope__scope_code="students:write"
        )
        self.assertEqual(sensitive_grant.status, ScopeGrant.GrantStatus.PENDING)
        non_sensitive = ScopeGrant.objects.get(
            installation=installation, scope__scope_code="attendance:read"
        )
        self.assertEqual(non_sensitive.status, ScopeGrant.GrantStatus.GRANTED)

    # ----- Test 4: AuditLog records the EXACT consented-scope list -----
    def test_audit_log_records_consented_scopes(self):
        self._login_admin_a()
        consented = ["attendance:read", "students:write", "grades:read"]
        self.client.post(
            self._install_url(),
            {
                "app_id": self.app.pk,
                "install_after_impact_preview": "1",
                "consented_scopes": consented,
            },
            HTTP_HOST=_TENANT_HOST_A,
        )
        log = ComplianceAuditLog.objects.filter(
            action=ComplianceAuditLog.Action.PERMISSION_GRANT,
            model_name="AppInstallation",
        ).order_by("-timestamp").first()
        self.assertIsNotNone(
            log, "PERMISSION_GRANT audit row must be written on install."
        )
        self.assertEqual(log.sensitivity, ComplianceAuditLog.Sensitivity.HIGH)
        self.assertEqual(log.user_id, self.admin_a.pk)
        new_values = log.new_values or {}
        self.assertEqual(new_values.get("app_id"), self.app.pk)
        self.assertEqual(new_values.get("app_slug"), self.app.slug)
        self.assertEqual(new_values.get("school_id"), str(self.school_a.pk))
        self.assertEqual(
            sorted(new_values.get("scopes_consented") or []), sorted(consented),
            "Audit row must capture the exact scopes the admin acknowledged.",
        )

    # ----- Test 5: tenant isolation — A's consent does NOT install for B -----
    def test_consent_is_tenant_scoped(self):
        """Admin A confirms install for school A. School B must not be touched."""
        self._login_admin_a()
        self.client.post(
            self._install_url(),
            {
                "app_id": self.app.pk,
                "install_after_impact_preview": "1",
                "consented_scopes": [
                    "attendance:read",
                    "students:write",
                    "grades:read",
                ],
            },
            HTTP_HOST=_TENANT_HOST_A,
        )
        self.assertTrue(
            AppInstallation.objects.filter(
                school=self.school_a, app=self.app
            ).exists()
        )
        self.assertFalse(
            AppInstallation.objects.filter(
                school=self.school_b, app=self.app
            ).exists(),
            "Consent confirmed under school A's host MUST NOT install the app "
            "for any other tenant.",
        )
        # The PERMISSION_GRANT audit row's school_id must match school A only.
        for log in ComplianceAuditLog.objects.filter(
            action=ComplianceAuditLog.Action.PERMISSION_GRANT,
            model_name="AppInstallation",
        ):
            self.assertEqual(
                (log.new_values or {}).get("school_id"), str(self.school_a.pk)
            )
