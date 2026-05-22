"""Extended tenant offboarding: self-service, scheduler, admin guard, S3."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import Permission
from apps.schools.admin import SchoolAdmin
from apps.schools.models import School, SchoolMembership
from apps.schools.tenant_offboarding import (
    cancel_self_service_closure,
    request_self_service_closure,
    run_scheduled_purges,
    schools_scheduled_for_purge,
)
from apps.schools.views_tenant_self_offboarding import api_tenant_offboarding_request_closure
from apps.siteconfig.models import RegionConfig
from config.admin import platform_admin_site

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*"],
    TENANT_SELF_SERVICE_OFFBOARDING_ENABLED="1",
    TENANT_AUTO_PURGE_ENABLED="1",
    TENANT_AUTO_PURGE_GRACE_DAYS="14",
)
class TenantOffboardingExtendedTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Extended Offboard",
            slug="extended-offboard-school",
            subdomain="extended-offboard-school",
            is_active=True,
            default_region=self.region,
        )
        self.admin_user = User.objects.create_user(
            username="school_admin_off",
            password="testpass123",
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin_user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.admin_user.feature_permissions.add(manage_perm)
        self.factory = RequestFactory()

    def test_self_service_request_schedules_purge(self):
        result = request_self_service_closure(
            self.school,
            actor=self.admin_user,
            acknowledge=True,
        )
        self.assertIn("scheduled_purge_at", result)
        self.school.refresh_from_db()
        off = (self.school.settings or {}).get("offboarding") or {}
        self.assertEqual(off.get("self_service_status"), "scheduled")
        self.assertFalse(self.school.is_active)

    def test_cancel_self_service(self):
        request_self_service_closure(
            self.school, actor=self.admin_user, acknowledge=True
        )
        cancel_self_service_closure(self.school, actor=self.admin_user)
        off = (self.school.settings or {}).get("offboarding") or {}
        self.assertEqual(off.get("self_service_status"), "cancelled")

    def test_schools_scheduled_for_purge_query(self):
        purge_day = (date.today() - timedelta(days=1)).isoformat()
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "scheduled",
            "scheduled_purge_at": purge_day,
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        due = schools_scheduled_for_purge()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].slug, self.school.slug)

    @patch("apps.schools.tenant_offboarding.drop_tenant_schema_for_school", return_value=None)
    def test_run_scheduled_purges_dry_run(self, _mock):
        purge_day = date.today().isoformat()
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "scheduled",
            "scheduled_purge_at": purge_day,
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        result = run_scheduled_purges(dry_run=True, limit=5)
        self.assertTrue(result.get("ok"))
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    def test_tenant_api_request_closure(self):
        request = self.factory.post(
            "/api/school/offboarding/request-closure/",
            data=json.dumps({"acknowledge": True}),
            content_type="application/json",
        )
        request.user = self.admin_user
        request.school = self.school
        response = api_tenant_offboarding_request_closure(request)
        self.assertEqual(response.status_code, 200)

    def test_school_admin_has_no_delete_permission(self):
        superuser = User.objects.create_superuser("su", "su@x.com", "x")
        request = self.factory.get("/admin/schools/school/")
        request.user = superuser
        admin = SchoolAdmin(School, platform_admin_site)
        self.assertFalse(admin.has_delete_permission(request, self.school))

    def test_s3_lifecycle_policy_document_shape(self):
        from apps.compliance.tenant_offboarding_storage import lifecycle_policy_document

        doc = lifecycle_policy_document(bucket="test-bucket")
        self.assertIn("Rules", doc)
        self.assertGreaterEqual(len(doc["Rules"]), 2)
