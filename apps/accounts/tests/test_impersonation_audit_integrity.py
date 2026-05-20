"""Impersonation audit integrity: reason, operator context, no PII leakage."""

from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase, override_settings
from apps.accounts.models import User
from apps.schools.models import School
from apps.schools.super_views_impersonation import switch_to_tenant
from apps.siteconfig.models import ImpersonationLog, RegionConfig

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", _MGR, "testserver"],
    IMPERSONATION_REQUIRE_JUSTIFICATION=True,
    JIT_IMPERSONATION_REQUIRE_CONSENT=False,
)
class ImpersonationAuditIntegrityTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CM",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )
        self.school = School.objects.create(
            name="Audit Integrity School",
            slug="audit-integrity-school",
            subdomain="audit-integrity-school",
            is_active=True,
            default_region=self.region,
        )
        self.actor = User.objects.create_user(
            username="audit_integrity_actor",
            email="audit.actor@example.com",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
        )
        self.factory = RequestFactory()

    def _switch_request(self, *, reason: str):
        request = self.factory.post(
            "/super/switch-to-tenant/",
            data={
                "school_id": str(self.school.id),
                "impersonation_reason": reason,
            },
        )
        request.user = self.actor
        request.public_host_kind = "manager"
        request.META["HTTP_HOST"] = _MGR
        request.META["REMOTE_ADDR"] = "203.0.113.10"
        request.META["HTTP_USER_AGENT"] = "stage2-penetration-test"
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))
        return switch_to_tenant(request)

    def test_impersonation_switch_logs_reason_ip_and_school(self):
        response = self._switch_request(
            reason="Audit integrity penetration test — operator access."
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("impersonate=", response.url or "")
        log = (
            ImpersonationLog.objects.filter(
                school=self.school, action=ImpersonationLog.Action.SWITCH
            )
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(log)
        self.assertGreaterEqual(len((log.reason or "").strip()), 3)
        self.assertEqual(str(log.ip_address), "203.0.113.10")
        self.assertEqual(log.actor_id, self.actor.id)

    def test_impersonation_log_str_does_not_embed_raw_email(self):
        response = self._switch_request(reason="Verify repr hides operator email in logs.")
        self.assertEqual(response.status_code, 302)
        log = ImpersonationLog.objects.filter(school=self.school).latest("created_at")
        rendered = str(log)
        self.assertNotIn("audit.actor@example.com", rendered)
        self.assertNotIn("pass12345", rendered)

    def test_impersonation_without_reason_blocked(self):
        request = self.factory.post(
            "/super/switch-to-tenant/",
            data={"school_id": str(self.school.id), "impersonation_reason": "  "},
        )
        request.user = self.actor
        request.public_host_kind = "manager"
        request.META["HTTP_HOST"] = _MGR
        request.session = SessionStore()
        setattr(request, "_messages", FallbackStorage(request))
        response = switch_to_tenant(request)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("impersonate=", response.url or "")
        self.assertFalse(
            ImpersonationLog.objects.filter(
                school=self.school, action=ImpersonationLog.Action.SWITCH
            ).exists()
        )

    def test_parse_impersonation_token_rejects_tampered_payload(self):
        from apps.accounts.views_impersonation import _parse_impersonation_token

        self.assertIsNone(_parse_impersonation_token("not-a-valid-token"))
