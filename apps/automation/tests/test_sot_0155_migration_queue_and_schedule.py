"""§0.1.5 Wave 5: exception queue UI + scheduled migration parity tick."""

from django.test import TestCase, override_settings
from django.urls import reverse

from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.migration_services import run_migration_finish, run_migration_start
from apps.automation.models import (
    AutomationExecutionLog,
    MigrationQuarantineRecord,
    MigrationRun,
)
from apps.schools.models import School


def _sign_in_operator(client, user):
    """force_login + the MFA state a real operator login would have established."""
    TOTPDevice.objects.get_or_create(user=user, name="default", defaults={"confirmed": True})
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()


class MigrationExceptionQueueSot0155Tests(TestCase):
    @override_settings(ALLOWED_HOSTS=["*"])
    def setUp(self):
        self.school = School.objects.create(
            name="Q School",
            slug="q-school",
            subdomain="q-school",
            is_active=True,
        )
        self.superuser = User.objects.create_user(
            username="sot_super",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        # RequireMFAMiddleware gates privileged users twice: no confirmed device
        # redirects to /mfa/setup/, and a device without a verified session
        # redirects to /mfa/verify/. force_login() skips the real login flow, so
        # neither is satisfied unless the fixture does it.
        _sign_in_operator(self.client, self.superuser)
        self.host = "manager.runmycampus.com"

    def test_run_migration_finish_opens_exception_queue(self):
        run = run_migration_start(self.school, "students", 10, user=self.superuser)
        run_migration_finish(
            run,
            {
                "created": 5,
                "updated": 0,
                "error_count": 5,
                "errors": ["row 2 bad"],
            },
        )
        run.refresh_from_db()
        self.assertEqual(run.exception_ack_status, MigrationRun.ExceptionAck.OPEN)

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_exception_ack_post_closes_queue(self):
        run = run_migration_start(self.school, "grades", 3, user=self.superuser)
        run_migration_finish(
            run,
            {"created": 0, "updated": 1, "error_count": 2, "errors": ["e1", "e2"]},
        )
        run.refresh_from_db()
        url = reverse("super:migration_exception_ack", args=[run.pk])
        r = self.client.post(
            url,
            {"note": "reviewed — source file fixed"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(r.status_code, 302)
        run.refresh_from_db()
        self.assertEqual(run.exception_ack_status, MigrationRun.ExceptionAck.CLOSED)
        self.assertIn("reviewed", run.exception_ack_note)

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_quarantine_waive_post(self):
        run = run_migration_start(self.school, "students", 1, user=self.superuser)
        run_migration_finish(run, {"created": 1, "updated": 0, "error_count": 0})
        rec = MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=run,
            domain="students",
            row_index=1,
            payload={},
            issue_class="duplicate",
            status=MigrationQuarantineRecord.Status.PENDING,
        )
        url = reverse("super:migration_quarantine_waive", args=[rec.pk])
        r = self.client.post(url, {"note": "dup acceptable"}, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.status, MigrationQuarantineRecord.Status.REPAIRED)
        self.assertTrue(rec.resolution_payload.get("operator_waive"))

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_migration_cloud_shows_exception_section(self):
        run = run_migration_start(self.school, "students", 2, user=self.superuser)
        run_migration_finish(
            run, {"created": 0, "updated": 0, "error_count": 2, "errors": ["a", "b"]}
        )
        url = reverse("super:migration_cloud")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Exception queue")
        self.assertContains(r, "Acknowledge")


class MigrationScheduledParityTickTests(TestCase):
    def test_tick_writes_automation_execution_log(self):
        from apps.automation.tasks import migration_scheduled_parity_tick

        before = AutomationExecutionLog.objects.count()
        out = migration_scheduled_parity_tick()
        self.assertEqual(AutomationExecutionLog.objects.count(), before + 1)
        log = AutomationExecutionLog.objects.order_by("-id").first()
        self.assertEqual(log.task_name, "migration.scheduled_parity_tick")
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        self.assertIn("open_exception_runs", log.execution_summary)
        self.assertIn("open_exception_runs", out)
