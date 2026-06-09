"""Phase 6 — provisioning crash / retry resiliency."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.platform_runtime.models import WorkflowRun
from apps.schools.models import School, SchoolProvisioningEvent
from apps.schools.provisioning_progress import resolve_provisioning_progress
from apps.schools.tasks import ensure_admin_user_for_school, provision_school_sync


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ProvisioningCrashResiliencyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Crash Resiliency Academy",
            slug="crash-resiliency",
            subdomain="crash-resiliency",
            is_active=False,
        )

    @patch("apps.schools.tasks._do_provision_tracked")
    def test_failure_leaves_school_inactive_and_records_failed_event(self, mock_tracked):
        mock_tracked.side_effect = RuntimeError("simulated tenant_schema failure")

        with self.assertRaises(RuntimeError):
            provision_school_sync(
                str(self.school.id), contact_email="owner@crash-resiliency.test"
            )

        self.school.refresh_from_db()
        self.assertFalse(self.school.is_active)
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="FAILED"
            ).exists()
        )

    @patch("apps.schools.tasks._do_provision_tracked")
    def test_failure_finalizes_workflow_run_as_failed(self, mock_tracked):
        mock_tracked.side_effect = ValueError("simulated seed_data failure")

        with self.assertRaises(ValueError):
            provision_school_sync(str(self.school.id), contact_email="owner@crash.test")

        run = WorkflowRun.objects.filter(
            workflow_key="tenant_school_provision",
            school_id=str(self.school.pk),
        ).first()
        self.assertIsNotNone(run, "WorkflowRun must exist after begin_run (visible to polls)")
        self.assertEqual((run.status or "").lower(), "failed")

        progress = resolve_provisioning_progress(self.school)
        self.assertEqual(progress.get("status"), "failed")
        self.assertIsNotNone(progress.get("workflow_run_id"))

    @patch("apps.schools.tasks._do_provision_tracked")
    def test_retry_after_failure_can_activate_school(self, mock_tracked):
        attempts = {"n": 0}

        def flaky_tracked(school, school_id, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("first attempt failed")
            School.objects.filter(pk=school.pk).update(is_active=True)

        mock_tracked.side_effect = flaky_tracked

        with self.assertRaises(RuntimeError):
            provision_school_sync(
                str(self.school.id), contact_email="owner@crash-resiliency.test"
            )

        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="FAILED"
            ).exists()
        )

        provision_school_sync(
            str(self.school.id), contact_email="owner@crash-resiliency.test"
        )

        self.school.refresh_from_db()
        self.assertTrue(self.school.is_active)

    def test_ensure_admin_user_is_idempotent_on_retry(self):
        ensure_admin_user_for_school(self.school, "owner@crash-resiliency.test")
        ensure_admin_user_for_school(self.school, "owner@crash-resiliency.test")
        User = get_user_model()
        self.assertEqual(
            User.objects.filter(email__iexact="owner@crash-resiliency.test").count(), 1
        )
