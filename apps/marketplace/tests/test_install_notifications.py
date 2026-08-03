"""Installing an app must drop a header-bell notification for tenant admins.

Before this, ``install_app`` published events + workflow triggers but created no
``finance.Notification`` — so nothing appeared in the notification bell/inbox when
an app was installed, and (worse) when an install left a SENSITIVE scope PENDING
the admin got no nudge telling them WHERE to approve it. These must-fire tests
assert the real effect:

  * an INFO "App installed" notification for every owner/admin;
  * a WARNING "Approve permissions" notification, linking to the Scope Consent
    page, WHEN (and only when) a sensitive scope is left pending;
  * recipients are the school's owners + admins, not other members;
  * a GET to the POST-only ``/settings/approve-scope/`` action URL redirects to
    Scope Consent instead of dead-ending on the tenant "Page not found" page.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.finance.models import Notification
from apps.marketplace.models import (
    AppScope,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
    ScopeGrant,
)
from apps.marketplace.services import install_app
from apps.schools.models import School, SchoolMembership

_HOST = "notify-school.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _HOST],
    DEBUG=False,
    SECURE_SSL_REDIRECT=False,
)
class MarketplaceInstallNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.env = patch.dict(
            os.environ,
            {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com", "MULTI_TENANT_LEGACY_BASE_DOMAINS": ""},
            clear=False,
        )
        cls.env.start()
        cls.school = School.objects.create(
            name="Notify School", slug="notify-school", subdomain="notify-school", is_active=True
        )
        cls.perm_manage, _ = Permission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )
        # admin: role=ADMIN membership
        cls.admin = User.objects.create_user(
            username="notify_admin", password="test-harness-1", role=User.Role.ADMIN
        )
        cls.admin.feature_permissions.add(cls.perm_manage)
        SchoolMembership.objects.get_or_create(
            user=cls.admin, school=cls.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        # owner: not ADMIN role, but is_school_owner=True (must still be notified)
        cls.owner = User.objects.create_user(
            username="notify_owner", password="x", role=User.Role.TEACHER
        )
        SchoolMembership.objects.get_or_create(
            user=cls.owner, school=cls.school,
            defaults={"role": User.Role.TEACHER, "is_school_owner": True},
        )
        # plain member: neither admin nor owner (must NOT be notified)
        cls.member = User.objects.create_user(
            username="notify_member", password="x", role=User.Role.TEACHER
        )
        SchoolMembership.objects.get_or_create(
            user=cls.member, school=cls.school,
            defaults={"role": User.Role.TEACHER},
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="notify-pub", name="Notify Pub",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
            country_code="US", payout_ref="notify-pub",
        )
        cls.app = MarketplaceApp.objects.create(
            publisher=cls.publisher, slug="notify-app", name="Notify App",
            kind=MarketplaceApp.AppKind.THIRD_PARTY, version="1.0.0",
            manifest={"scopes": ["migration_import", "roster:read"], "widgets": {}},
            is_active=True, is_intentionally_free=True,
        )
        cls.sensitive_scope = AppScope.objects.create(
            app=cls.app, scope_code="migration_import", description="Import records",
            sensitive=True,
        )
        cls.normal_scope = AppScope.objects.create(
            app=cls.app, scope_code="roster:read", description="Read roster",
        )
        MarketplaceListing.objects.create(
            app=cls.app, publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        super().tearDownClass()

    def _install(self, *scope_codes):
        return install_app(
            self.school, self.app, installed_by=self.admin,
            grant_scope_codes=list(scope_codes),
            skip_compatibility=True, run_schema_patches=False,
        )

    def _notes(self, user):
        return Notification.objects.filter(recipient=user, school=self.school)

    def test_install_with_sensitive_scope_notifies_owner_and_admin(self):
        inst = self._install("migration_import")
        # the install genuinely left a pending sensitive grant
        self.assertTrue(
            ScopeGrant.objects.filter(
                installation=inst, scope=self.sensitive_scope,
                status=ScopeGrant.GrantStatus.PENDING,
            ).exists()
        )
        for user in (self.admin, self.owner):
            notes = self._notes(user)
            self.assertTrue(
                notes.filter(title__icontains="installed").exists(),
                f"{user.username} got no install notification",
            )
            warn = notes.filter(severity=Notification.Severity.WARNING).first()
            self.assertIsNotNone(warn, f"{user.username} got no approval nudge")
            self.assertIn("scope-consent", warn.link)
            self.assertIn("migration_import", warn.message)
        # a plain member is NOT an approver -> gets nothing
        self.assertEqual(self._notes(self.member).count(), 0)

    def test_install_without_sensitive_scope_emits_info_only(self):
        self._install("roster:read")
        notes = self._notes(self.admin)
        self.assertTrue(notes.filter(title__icontains="installed").exists())
        self.assertFalse(
            notes.filter(severity=Notification.Severity.WARNING).exists(),
            "a non-sensitive install must not raise an approval nudge",
        )

    def test_get_approve_scope_redirects_to_consent_not_404(self):
        client = Client(HTTP_HOST=_HOST, raise_request_exception=False)
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.get_or_create(
            user=self.admin, name="notify-device", defaults={"confirmed": True}
        )
        client.login(username="notify_admin", password="test-harness-1")
        session = client.session
        session["mfa_verified"] = True
        session.save()
        url = reverse("tenant_approve_scope", urlconf="config.tenant_urls")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 302, "GET must redirect, not 404/405")
        self.assertIn("scope-consent", resp["Location"])
