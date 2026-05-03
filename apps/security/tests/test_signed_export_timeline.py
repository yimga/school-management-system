"""Export timeline rows expose deterministic HMAC integrity tokens (audit row binding)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School
from apps.schools.super_views_enterprise_security import (
    _build_export_timeline_rows,
    _export_audit_integrity_token,
)

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MGR],
)
class SignedExportTimelineTests(TestCase):
    databases = {"default"}

    def test_timeline_row_matches_hmac_helper(self):
        school = School.objects.create(
            name="Integrity School",
            slug="integrity-school",
            subdomain="integrity-school",
            is_active=True,
        )
        actor = User.objects.create_user(
            username=f"hmac_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=True,
        )
        log = AuditLog.objects.create(
            action=AuditLog.Action.EXPORT,
            user=actor,
            model_name="AttendanceExport",
            object_id="export-1",
            object_repr="attendance term=1",
            app_label="portal",
            sensitivity=AuditLog.Sensitivity.HIGH,
        )
        token = _export_audit_integrity_token(log)
        self.assertEqual(len(token), 32)
        rows = _build_export_timeline_rows([log])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["integrity_token"], token)
        self.assertEqual(rows[0]["verification_state"], "hmac-bound")
        self.assertIn("AttendanceExport", rows[0]["export_type"])

    def test_security_hub_renders_integrity_in_export_timeline(self):
        school = School.objects.create(
            name="Render School",
            slug="render-school",
            subdomain="render-school",
            is_active=True,
        )
        actor = User.objects.create_user(
            username=f"ren_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=True,
        )
        log = AuditLog.objects.create(
            action=AuditLog.Action.EXPORT,
            user=actor,
            model_name="School",
            object_id=str(school.id),
            object_repr="student roster",
            app_label="people",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
        )
        expect = _export_audit_integrity_token(log)
        c = Client(HTTP_HOST=_MGR)
        c.force_login(actor)
        r = c.get(reverse("super:enterprise_security_command_center"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(expect, r.content.decode())
        self.assertContains(r, "data-rmc-export-timeline", html=False)
