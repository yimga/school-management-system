"""HTTP contract: tenant connector quarantine resolve accepts clear_queue JSON POST."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
)
from apps.schools.models import School, SchoolMembership


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.tenant_urls",
    SECURITY_ENFORCE_MINIMUM_STRENGTH=True,
)
class TenantQuarantineClearQueueHttpTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.school = School.objects.create(
            name="Gilead Tech High",
            slug=f"gilead-{uuid.uuid4().hex[:6]}",
            subdomain="gilead-tech",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:6]}",
            email="admin@gilead.test",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="held-import",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"held-{uuid.uuid4().hex[:8]}",
            status=BundleStatus.MAPPED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )
        MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain="students",
            row_index=1,
            issue_class="missing_required",
            payload={"error": "held", "source_row": {"name": "Test Row"}},
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def _tenant_client(self) -> Client:
        client = Client(HTTP_HOST="gilead-tech.runmycampus.com")
        client.force_login(self.admin)
        session = client.session
        session["school_id"] = str(self.school.pk)
        session["mfa_verified"] = True
        session.save()
        return client

    def test_clear_queue_post_returns_json_not_profile_redirect(self):
        url = reverse(
            "migration_cloud_connector:bundle-quarantine-resolve",
            kwargs={"bundle_id": self.bundle.pk},
        )
        response = self._tenant_client().post(
            url,
            data=json.dumps({"action": "clear_queue", "auto_retry": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, getattr(response, "url", ""))
        self.assertEqual(response["Content-Type"], "application/json")
        payload = response.json()
        self.assertTrue(payload.get("ok"))
