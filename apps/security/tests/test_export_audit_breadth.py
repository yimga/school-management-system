"""Compliance AuditLog EXPORT rows surface on the enterprise security hub."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MGR],
)
class ExportAuditBreadthTests(TestCase):
    databases = {"default"}

    def test_export_audit_row_visible_on_security_hub(self):
        school = School.objects.create(
            name="Export Audit School",
            slug="export-audit-school",
            subdomain="export-audit-school",
            is_active=True,
        )
        actor = User.objects.create_user(
            username=f"ex_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=True,
        )
        AuditLog.objects.create(
            action=AuditLog.Action.EXPORT,
            user=actor,
            model_name="ComplianceExport",
            object_id=str(school.id),
            object_repr="Regional compliance CSV bundle",
            app_label="siteconfig",
            sensitivity=AuditLog.Sensitivity.HIGH,
        )
        c = Client(HTTP_HOST=_MGR)
        c.force_login(actor)
        r = c.get(reverse("super:security_hub"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Regional compliance CSV bundle", html=False)
        self.assertContains(r, "Export timeline", html=False)
        self.assertContains(r, "hmac-bound", html=False)
        self.assertRegex(r.content.decode(), r"data-rmc-export-integrity=\"[a-f0-9]{32}\"")
