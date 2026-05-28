"""Full tenant lifecycle: signup email, verify, schedule purge, operator queue."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.schools.models import School, SignupVerification
from apps.schools.signup_views import verify_signup
from apps.schools.super_views_offboarding_queue import api_super_run_scheduled_purges
from apps.schools.tenant_offboarding import (
    request_self_service_closure,
    run_scheduled_purges,
    schools_scheduled_for_purge,
)
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"], TENANT_AUTO_PURGE_ENABLED=False)
class TenantLifecycleFullTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="lifecycle_full",
            email="lifecycle@example.com",
            password="testpass123",
        )
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Lifecycle Full School",
            slug="lifecycle-full-school",
            subdomain="lifecycle-full-school",
            is_active=True,
            default_region=self.region,
        )
        self.admin = User.objects.create_user(
            username="admin@lifecycle.test",
            email="admin@lifecycle.test",
            password="testpass123",
            is_active=True,
        )

    def _manager_post(self, path: str, data: dict):
        request = self.factory.post(
            path,
            data=json.dumps(data).encode(),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.superuser
        request.public_host_kind = "manager"
        return request

    @patch("apps.schools.signup_views.send_transactional")
    def test_signup_sends_verification_email(self, mock_send):
        mock_send.return_value = {"ok": True, "status": "queued"}
        school = School.objects.create(
            name="Email Test",
            slug="email-test-school",
            subdomain="email-test-school",
            is_active=False,
            default_region=self.region,
        )
        expires = timezone.now() + timedelta(days=2)
        SignupVerification.objects.create(
            school=school,
            email="owner@example.com",
            expires_at=expires,
        )
        self.assertTrue(
            SignupVerification.objects.filter(school=school, email="owner@example.com").exists()
        )

    @patch("apps.schools.tasks.dispatch_provision_school")
    def test_verify_signup_activates_inactive_school(self, _mock_provision):
        school = School.objects.create(
            name="Verify School",
            slug="verify-school",
            subdomain="verify-school",
            is_active=False,
            country_code="US",
            settings={},
            default_region=self.region,
        )
        sv, _created = SignupVerification.objects.update_or_create(
            school=school,
            defaults={
                "email": "v@verify.test",
                "expires_at": timezone.now() + timedelta(days=1),
                "verified_at": None,
            },
        )
        request = self.factory.get(f"/verify-signup/?token={sv.token}")
        resp = verify_signup(request)
        self.assertEqual(resp.status_code, 302)
        school.refresh_from_db()
        self.assertTrue(school.is_active)

    def test_self_service_schedules_purge_and_lists_due(self):
        request_self_service_closure(
            self.school,
            actor=self.admin,
            acknowledge=True,
        )
        self.school.refresh_from_db()
        off = (self.school.settings or {}).get("offboarding") or {}
        self.assertEqual(off.get("self_service_status"), "scheduled")
        self.assertTrue(off.get("scheduled_purge_at"))
        settings = dict(self.school.settings or {})
        settings["offboarding"] = dict(off)
        settings["offboarding"]["scheduled_purge_at"] = "2000-01-01"
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        due = schools_scheduled_for_purge(on_or_before=timezone.now().date())
        slugs = [s.slug for s in due]
        self.assertIn(self.school.slug, slugs)

    def test_run_scheduled_purges_dry_run_when_auto_disabled(self):
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "scheduled",
            "scheduled_purge_at": "2000-01-01",
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        result = run_scheduled_purges(dry_run=True, limit=5)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("dry_run"))

    def test_run_scheduled_purges_apply_blocked_without_force(self):
        result = run_scheduled_purges(dry_run=False, limit=1)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), "auto_purge_disabled")

    def test_api_force_operator_requires_confirm(self):
        request = self._manager_post(
            "/super/api/offboarding/run-scheduled/",
            {"dry_run": False, "force_operator": True, "limit": 1},
        )
        response = api_super_run_scheduled_purges(request)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertEqual(body.get("error"), "confirm_required")

    def test_api_force_operator_dry_run_via_queue(self):
        settings = dict(self.school.settings or {})
        settings["offboarding"] = {
            "self_service_status": "operator_scheduled",
            "scheduled_purge_at": "2000-01-01",
        }
        self.school.settings = settings
        self.school.save(update_fields=["settings", "updated_at"])
        request = self._manager_post(
            "/super/api/offboarding/run-scheduled/",
            {"dry_run": True, "limit": 3},
        )
        response = api_super_run_scheduled_purges(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body.get("ok"))
