"""Process-gap closure proofs: MFA wizard gate, zombie cancel, MC off-HTTP, Flight Deck async."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.platform_runtime.models import WorkflowRun
from apps.schools.models import School, SchoolMembership
from apps.schools.provision_watchdog import (
    cancel_unfinished_provision_runs_for_school,
    resume_provision_if_stuck,
)


User = get_user_model()


class OwnerOnboardingMfaWizardGateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            "mfa_wiz", "mfa_wiz@example.com", "pw", role=User.Role.ADMIN
        )
        self.school = School.objects.create(
            name="MFA Wizard School",
            slug="mfa-wizard-school",
            subdomain="mfa-wizard-school",
            is_active=True,
            settings={"owner_onboarding": {"step": "mfa"}},
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
            is_school_owner=True,
        )
        self.client.force_login(self.user)

    def test_done_redirects_to_mfa_when_unenrolled(self):
        resp = self.client.get(reverse("accounts:owner_onboarding_done"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/onboarding/mfa/", resp["Location"])

    def test_mfa_step_renders_onboarding_wizard_chrome(self):
        resp = self.client.get(reverse("accounts:owner_onboarding_mfa"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Protect your account", body)
        self.assertIn("Step 3 of 4", body)
        self.assertIn("enable_mfa", body)

    def test_done_allowed_when_enrolled(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.user, name="phone", confirmed=True)
        resp = self.client.get(reverse("accounts:owner_onboarding_done"))
        # May 200 the launchpad or 302 to tenant host — must NOT bounce to MFA.
        if resp.status_code == 302:
            self.assertNotIn("/onboarding/mfa/", resp["Location"])
            self.assertNotIn("/mfa/setup/", resp["Location"])
        else:
            self.assertEqual(resp.status_code, 200)


class DualZombieCancelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Zombie School",
            slug="zombie-school",
            subdomain="zombie-school",
            is_active=False,
        )

    def test_cancel_unfinished_clears_stuck_and_running(self):
        now = timezone.now()
        stuck = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision",
            school_id=str(self.school.pk),
            status="stuck",
            total_steps=5,
            expected_duration_seconds=600,
            last_heartbeat_at=now,
        )
        n = cancel_unfinished_provision_runs_for_school(str(self.school.pk))
        self.assertEqual(n, 1)
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, "cancelled")
        # After cancel, a fresh running row is allowed (one-active invariant).
        running = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision",
            school_id=str(self.school.pk),
            status="running",
            total_steps=5,
            expected_duration_seconds=600,
            last_heartbeat_at=now,
        )
        n2 = cancel_unfinished_provision_runs_for_school(str(self.school.pk))
        self.assertEqual(n2, 1)
        running.refresh_from_db()
        self.assertEqual(running.status, "cancelled")

    def test_resume_cancels_stuck_before_kick(self):
        now = timezone.now()
        WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision",
            school_id=str(self.school.pk),
            status="stuck",
            total_steps=5,
            expected_duration_seconds=600,
            last_heartbeat_at=now - timezone.timedelta(hours=2),
            current_step_name="tenant_schema",
        )
        with patch(
            "apps.schools.tasks.kick_complete_provisioning_background"
        ) as kick:
            result = resume_provision_if_stuck(self.school, reason="test")
        self.assertEqual(result.get("action"), "resumed")
        kick.assert_called_once()
        self.assertFalse(
            WorkflowRun.objects.filter(
                school_id=str(self.school.pk),
                workflow_key="tenant_school_provision",
                status__in=("running", "stuck"),
            ).exists()
        )


class MigrationCloudEnqueueOffHttpTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_enqueue_advance_eager_uses_durable_outbox(self):
        from apps.migration_cloud import celery_tasks as ct

        fake = type("R", (), {"id": "oid", "outbox_id": "oid", "durable_outbox": True})()
        with patch.object(ct, "_kick_advance_off_request", return_value=fake) as kick:
            result = ct.enqueue_advance(42, use_accelerator=True)
        kick.assert_called_once()
        self.assertTrue(getattr(result, "durable_outbox", False))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_enqueue_advance_broker_path_still_outbox(self):
        from apps.migration_cloud import celery_tasks as ct

        fake = type("R", (), {"id": "oid2", "outbox_id": "oid2", "durable_outbox": True})()
        with patch.object(ct, "_kick_advance_off_request", return_value=fake):
            result = ct.enqueue_advance(7, use_accelerator=True)
        self.assertTrue(getattr(result, "durable_outbox", False))

    def test_run_bundle_pipeline_off_http_enqueues_apply_after(self):
        from apps.migration_cloud.services.connector_bundle_bridge import (
            run_bundle_pipeline,
        )

        fake = type("R", (), {"id": "pipe1", "outbox_id": "pipe1", "durable_outbox": True})()
        bundle = MagicMock()
        bundle.status = "ingested"
        bundle.source_hint = ""
        with patch(
            "apps.migration_cloud.services.connector_bundle_bridge.MigrationBundle.objects.get",
            return_value=bundle,
        ), patch(
            "apps.migration_cloud.celery_tasks.enqueue_advance", return_value=fake
        ) as enq, patch(
            "apps.migration_cloud.services.connector_bundle_bridge.advance_bundle"
        ) as adv:
            out = run_bundle_pipeline(bundle_id=99, off_http=True, dry_run_apply=False)
        adv.assert_not_called()
        enq.assert_called_once_with(
            99, use_accelerator=True, apply_after=True, dry_run_apply=False
        )
        self.assertTrue(out.get("queued"))
        self.assertEqual(out.get("outbox_id"), "pipe1")

    def test_repair_bundle_off_http_enqueues_apply(self):
        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.repair import RepairReadiness, repair_bundle

        bundle = MagicMock()
        bundle.pk = 7
        bundle.status = BundleStatus.FAILED
        fake = type("R", (), {"id": "rep1", "outbox_id": "rep1", "durable_outbox": True})()
        readiness = RepairReadiness(
            repairable=True, reason="ok", issue_count=1, status=BundleStatus.FAILED
        )
        with patch(
            "apps.migration_cloud.repair.MigrationBundle.objects.get",
            return_value=bundle,
        ), patch(
            "apps.migration_cloud.repair.repair_readiness", return_value=readiness
        ), patch(
            "apps.migration_cloud.celery_tasks.enqueue_apply", return_value=fake
        ) as enq:
            result = repair_bundle(bundle_id=7, off_http=True)
        enq.assert_called_once_with(7, dry_run=False, reconcile_after=True)
        self.assertTrue(result.queued)
        self.assertEqual(result.outbox_id, "rep1")
        self.assertFalse(result.ran)


class RetryFailedStepStrengthTests(TestCase):
    def test_migration_advance_retry_enqueues_outbox(self):
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

        run = WorkflowRun.objects.create(
            workflow_key="migration_bundle_advance",
            workflow_label="Advance",
            school_id="1",
            status="stuck",
            total_steps=3,
            expected_duration_seconds=600,
            last_heartbeat_at=timezone.now(),
            payload_summary={"bundle_id": 42},
        )
        fake = type("R", (), {"id": "mc1", "outbox_id": "mc1", "durable_outbox": True})()
        with patch(
            "apps.migration_cloud.celery_tasks.enqueue_advance", return_value=fake
        ) as enq:
            result = apply_auto_fix_kind(run=run, kind="retry_failed_step")
        enq.assert_called_once_with(42, use_accelerator=True)
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("durable_outbox"))
        self.assertEqual(result.get("outbox_id"), "mc1")

    def test_generic_retry_requeues_registered_celery_task(self):
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

        run = WorkflowRun.objects.create(
            workflow_key="evals_bulk_grades",
            workflow_label="Bulk grades",
            school_id="school-evals-1",
            status="stuck",
            total_steps=2,
            expected_duration_seconds=300,
            last_heartbeat_at=timezone.now(),
            payload_summary={},
        )
        with patch("celery.current_app.send_task") as send:
            result = apply_auto_fix_kind(run=run, kind="retry_failed_step")
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("queued_async"))
        self.assertEqual(result.get("celery_task_name"), "evals.process_bulk_grades")
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "evals.process_bulk_grades")
        self.assertEqual(
            send.call_args.kwargs.get("kwargs", {}).get("school_id"),
            "school-evals-1",
        )
        run.refresh_from_db()
        self.assertEqual(run.status, "running")

    def test_unregistered_workflow_stamp_retries_without_send_task(self):
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

        run = WorkflowRun.objects.create(
            workflow_key="tenant_school_purge",
            workflow_label="Manual purge",
            school_id="school-purge-1",
            status="stuck",
            total_steps=2,
            expected_duration_seconds=300,
            last_heartbeat_at=timezone.now(),
            payload_summary={},
        )
        with patch("celery.current_app.send_task") as send:
            result = apply_auto_fix_kind(run=run, kind="retry_failed_step")
        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("queued_async"))
        send.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, "running")


class FlightDeckAsyncHealTests(TestCase):
    def test_repair_tenant_schema_drift_queues_outbox(self):
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind

        run = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision",
            school_id="1",
            tenant_schema="tenant_x",
            status="stuck",
            total_steps=5,
            expected_duration_seconds=600,
            last_heartbeat_at=timezone.now(),
            current_step_name="tenant_schema",
        )
        fake = MagicMock()
        fake.pk = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        with patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_heavy_work",
            return_value=fake,
        ) as enq:
            with patch(
                "apps.platform_runtime.workflow_fix_handlers.call_command"
            ) as cc:
                result = apply_auto_fix_kind(
                    run=run, kind="repair_tenant_schema_drift"
                )
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("queued_async"))
        self.assertTrue(result.get("durable_outbox"))
        self.assertEqual(result.get("outbox_id"), str(fake.pk))
        enq.assert_called_once()
        cc.assert_not_called()


class HeavyWorkOutboxDurableTests(TestCase):
    def test_enqueue_and_drain_provision_row(self):
        from apps.platform_runtime.heavy_work_outbox import (
            drain_heavy_work_outbox,
            enqueue_provision_school,
        )
        from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

        school = School.objects.create(
            name="Outbox School",
            slug="outbox-school",
            subdomain="outbox-school",
            is_active=False,
        )
        with patch(
            "apps.platform_runtime.heavy_work_outbox.kick_heavy_work_drain"
        ):
            row = enqueue_provision_school(str(school.pk), contact_email="a@b.c")
        self.assertEqual(row.status, HeavyWorkOutbox.Status.PENDING)
        with patch("apps.schools.tasks.provision_school_sync") as sync:
            out = drain_heavy_work_outbox(limit=5)
        sync.assert_called_once()
        self.assertEqual(out["processed"], 1)
        row.refresh_from_db()
        self.assertEqual(row.status, HeavyWorkOutbox.Status.SUCCEEDED)

    def test_one_active_provision_run_constraint(self):
        school = School.objects.create(
            name="Unique Run School",
            slug="unique-run-school",
            subdomain="unique-run-school",
            is_active=False,
        )
        now = timezone.now()
        WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision",
            school_id=str(school.pk),
            status="running",
            total_steps=5,
            expected_duration_seconds=600,
            last_heartbeat_at=now,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            WorkflowRun.objects.create(
                workflow_key="tenant_school_provision",
                workflow_label="Provision",
                school_id=str(school.pk),
                status="stuck",
                total_steps=5,
                expected_duration_seconds=600,
                last_heartbeat_at=now,
            )
