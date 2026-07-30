"""TenantReportSchedule persistence, API list, and send_scheduled_reports command."""

import json
from datetime import timedelta, time
from io import StringIO
from smtplib import SMTPException
from unittest.mock import patch

from apps.reports.admin import (
    TenantReportScheduleActiveEmptyRecipientsFilter,
    TenantReportScheduleAdmin,
)
from config.admin import tenant_admin_site
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.http import HttpResponse, QueryDict
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.api.views_v1 import ScheduledReportDetailView, ScheduledReportsListView
from apps.reports.models import TenantReportSchedule
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import Plan

User = get_user_model()


class TenantReportScheduleAdminRegistrationTests(TestCase):
    def test_registered_on_tenant_admin_site(self):
        self.assertIn(TenantReportSchedule, tenant_admin_site._registry)


class TenantReportScheduleAdminRecipientDisplayTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pa",
            slug="p-adm-rc",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Sa",
            slug="s-adm-rc",
            subdomain="s-adm-rc",
            is_active=True,
            plan=self.plan,
        )
        self.user = User.objects.create_user(
            username="u_adm_rc",
            email="u_adm_rc@example.com",
            password="x",
            role="ADMIN",
        )
        self.schedule = TenantReportSchedule.objects.create(
            school=self.school,
            name="RC",
            report_key="rc",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["one@example.com", "two@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=timezone.now() + timedelta(days=1),
            created_by=self.user,
        )

    def test_recipient_count_display_matches_list_length(self):
        ma = TenantReportScheduleAdmin(TenantReportSchedule, tenant_admin_site)
        self.assertEqual(ma.recipient_count_display(self.schedule), 2)
        TenantReportSchedule.objects.filter(pk=self.schedule.pk).update(recipients=[])
        self.schedule.refresh_from_db()
        self.assertEqual(ma.recipient_count_display(self.schedule), 0)

    def test_active_empty_recipients_filter_queryset(self):
        TenantReportSchedule.objects.filter(pk=self.schedule.pk).update(
            recipients=[],
        )
        self.schedule.refresh_from_db()
        ma = TenantReportScheduleAdmin(TenantReportSchedule, tenant_admin_site)
        params = QueryDict(mutable=True)
        params["trs_recipient_gap"] = "active_empty"
        request = RequestFactory().get("/admin/reports/tenantreportschedule/")
        flt = TenantReportScheduleActiveEmptyRecipientsFilter(
            request,
            params,
            TenantReportSchedule,
            ma,
        )
        qs = flt.queryset(request, TenantReportSchedule.objects.all())
        self.assertEqual(list(qs.values_list("pk", flat=True)), [self.schedule.pk])


class TenantReportScheduleModelValidationTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pv",
            slug="p-val",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Sv",
            slug="s-val",
            subdomain="s-val",
            is_active=True,
            plan=self.plan,
        )
        self.user = User.objects.create_user(
            username="u_val",
            email="u_val@example.com",
            password="x",
            role="ADMIN",
        )

    def test_active_schedule_requires_recipients(self):
        sch = TenantReportSchedule(
            school=self.school,
            name="No emails",
            report_key="x",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(7, 0),
            recipients=[],
            is_active=True,
            next_run=timezone.now(),
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            sch.full_clean()

    def test_inactive_schedule_allows_empty_recipients(self):
        sch = TenantReportSchedule(
            school=self.school,
            name="Paused",
            report_key="y",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(7, 0),
            recipients=[],
            is_active=False,
            next_run=timezone.now(),
            created_by=self.user,
        )
        sch.full_clean()


class TenantReportScheduleApiTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.plan = Plan.objects.create(
            name="P",
            slug="p-sched",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Sched School",
            slug="sched-school",
            subdomain="sched-school",
            is_active=True,
            plan=self.plan,
        )
        self.user = User.objects.create_user(
            username="admin_sched",
            email="admin@example.com",
            password="x",
            role="ADMIN",
        )
        # The scheduled-reports API gate (_require_super_or_school) admits a
        # tenant admin only when they hold a SchoolMembership on request.school
        # (role alone is insufficient), so bind the admin to the tenant.
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=self.user.role, is_primary=True
        )
        now = timezone.now()
        self.schedule = TenantReportSchedule.objects.create(
            school=self.school,
            name="Morning digest",
            report_key="digest",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["ops@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now + timedelta(days=1),
            created_by=self.user,
        )

    def test_scheduled_reports_list_returns_tenant_rows(self):
        request = self.factory.get("/api/v1/reports/scheduled")
        request.user = self.user
        request.school = self.school
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data.get("schema"), "reports_scheduled_delivery_v2")
        self.assertEqual(len(data["schedules"]), 1)
        row = data["schedules"][0]
        self.assertEqual(row["name"], "Morning digest")
        self.assertEqual(row["report_key"], "digest")
        self.assertEqual(row["recipient_count"], 1)
        self.assertTrue(row["has_recipients"])
        self.assertTrue(row["delivery_ready"])
        self.assertNotIn("recipients", row)

    def test_scheduled_reports_list_filter_is_active(self):
        TenantReportSchedule.objects.filter(pk=self.schedule.pk).update(is_active=False)
        req_true = self.factory.get("/api/v1/reports/scheduled?is_active=true")
        req_true.user = self.user
        req_true.school = self.school
        resp_true = ScheduledReportsListView.as_view()(req_true)
        self.assertEqual(resp_true.status_code, 200)
        self.assertEqual(json.loads(resp_true.content)["schedules"], [])

        req_false = self.factory.get("/api/v1/reports/scheduled?is_active=false")
        req_false.user = self.user
        req_false.school = self.school
        resp_false = ScheduledReportsListView.as_view()(req_false)
        self.assertEqual(resp_false.status_code, 200)
        names = [r["name"] for r in json.loads(resp_false.content)["schedules"]]
        self.assertEqual(names, ["Morning digest"])

    def test_scheduled_reports_list_filter_delivery_ready(self):
        TenantReportSchedule.objects.create(
            school=self.school,
            name="Paused empty",
            report_key="pe",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(8, 0),
            recipients=[],
            parameters={},
            is_active=False,
            last_run=None,
            next_run=timezone.now() + timedelta(days=2),
            created_by=self.user,
        )
        req_ready = self.factory.get("/api/v1/reports/scheduled?delivery_ready=true")
        req_ready.user = self.user
        req_ready.school = self.school
        resp_ready = ScheduledReportsListView.as_view()(req_ready)
        self.assertEqual(resp_ready.status_code, 200)
        names_ok = [r["name"] for r in json.loads(resp_ready.content)["schedules"]]
        self.assertEqual(names_ok, ["Morning digest"])

        req_not = self.factory.get("/api/v1/reports/scheduled?delivery_ready=false")
        req_not.user = self.user
        req_not.school = self.school
        resp_not = ScheduledReportsListView.as_view()(req_not)
        self.assertEqual(resp_not.status_code, 200)
        names_bad = {r["name"] for r in json.loads(resp_not.content)["schedules"]}
        # Active rows with recipients are delivery-ready and are excluded here.
        self.assertEqual(names_bad, {"Paused empty"})

    def test_scheduled_reports_list_invalid_is_active_query_returns_400(self):
        request = self.factory.get("/api/v1/reports/scheduled?is_active=maybe")
        request.user = self.user
        request.school = self.school
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_scheduled_reports_list_delivery_ready_false_when_inactive_empty(self):
        TenantReportSchedule.objects.create(
            school=self.school,
            name="Paused empty",
            report_key="pe",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(8, 0),
            recipients=[],
            parameters={},
            is_active=False,
            last_run=None,
            next_run=timezone.now() + timedelta(days=2),
            created_by=self.user,
        )
        request = self.factory.get("/api/v1/reports/scheduled")
        request.user = self.user
        request.school = self.school
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        by_name = {r["name"]: r for r in data["schedules"]}
        self.assertFalse(by_name["Paused empty"]["has_recipients"])
        self.assertFalse(by_name["Paused empty"]["delivery_ready"])
        self.assertTrue(by_name["Morning digest"]["delivery_ready"])

    def test_scheduled_reports_list_other_school_empty(self):
        other = School.objects.create(
            name="Other",
            slug="other-sched",
            subdomain="other-sched",
            is_active=True,
            plan=self.plan,
        )
        # The user must be a member of ``other`` to reach its endpoint (the gate
        # requires membership); the isolation being proven here is that ``other``
        # has none of ``self.school``'s schedules — the list filters by tenant.
        SchoolMembership.objects.create(
            user=self.user, school=other, role=self.user.role
        )
        request = self.factory.get("/api/v1/reports/scheduled")
        request.user = self.user
        request.school = other
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["schedules"], [])

    def test_scheduled_reports_post_create_returns_201(self):
        body = json.dumps(
            {
                "name": "Weekly rollup",
                "schedule_frequency": "WEEKLY",
                "schedule_time": "09:30:00",
                "recipients": ["weekly@example.com"],
                "report_key": "rollup",
            }
        )
        request = self.factory.post(
            "/api/v1/reports/scheduled",
            data=body,
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.content)
        self.assertTrue(data.get("ok"))
        new_id = data["id"]
        obj = TenantReportSchedule.objects.get(pk=new_id)
        self.assertEqual(obj.name, "Weekly rollup")
        self.assertEqual(obj.report_key, "rollup")
        self.assertEqual(obj.recipients, ["weekly@example.com"])
        self.assertTrue(data.get("delivery_ready"))

    def test_scheduled_reports_post_inactive_allows_empty_recipients(self):
        body = json.dumps(
            {
                "name": "Draft only",
                "schedule_frequency": "DAILY",
                "schedule_time": "08:15:00",
                "is_active": False,
                "recipients": [],
            }
        )
        request = self.factory.post(
            "/api/v1/reports/scheduled",
            data=body,
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.content)
        self.assertFalse(data["has_recipients"])
        self.assertFalse(data["delivery_ready"])

    def test_scheduled_reports_post_active_rejects_empty_recipients(self):
        body = json.dumps(
            {
                "name": "Bad",
                "schedule_frequency": "DAILY",
                "schedule_time": "08:20:00",
                "is_active": True,
                "recipients": [],
            }
        )
        request = self.factory.post(
            "/api/v1/reports/scheduled",
            data=body,
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        response = ScheduledReportsListView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_scheduled_report_detail_get_patch_delete(self):
        request = self.factory.get(f"/api/v1/reports/scheduled/{self.schedule.pk}")
        request.user = self.user
        request.school = self.school
        response = ScheduledReportDetailView.as_view()(request, id=self.schedule.pk)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["name"], "Morning digest")
        self.assertEqual(data["recipients"], ["ops@example.com"])

        patch_body = json.dumps({"name": "Evening digest", "is_active": False})
        patch_req = self.factory.patch(
            f"/api/v1/reports/scheduled/{self.schedule.pk}",
            data=patch_body,
            content_type="application/json",
        )
        patch_req.user = self.user
        patch_req.school = self.school
        patch_resp = ScheduledReportDetailView.as_view()(
            patch_req, id=self.schedule.pk
        )
        self.assertEqual(patch_resp.status_code, 200)
        patch_out = json.loads(patch_resp.content)
        self.assertFalse(patch_out["delivery_ready"])
        self.assertTrue(patch_out["has_recipients"])
        self.assertEqual(patch_out["name"], "Evening digest")
        self.assertEqual(patch_out["report_key"], "digest")
        self.assertFalse(patch_out["is_active"])
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.name, "Evening digest")
        self.assertFalse(self.schedule.is_active)

        del_req = self.factory.delete(f"/api/v1/reports/scheduled/{self.schedule.pk}")
        del_req.user = self.user
        del_req.school = self.school
        del_resp = ScheduledReportDetailView.as_view()(del_req, id=self.schedule.pk)
        self.assertEqual(del_resp.status_code, 200)
        del_out = json.loads(del_resp.content)
        self.assertEqual(del_out.get("schema"), "reports_scheduled_delivery_v2")
        self.assertTrue(del_out.get("ok"))
        self.assertFalse(
            TenantReportSchedule.objects.filter(pk=self.schedule.pk).exists()
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SendScheduledReportsCommandTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="P2",
            slug="p2-sched",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Cmd School",
            slug="cmd-school",
            subdomain="cmd-school",
            is_active=True,
            plan=self.plan,
        )
        self.user = User.objects.create_user(
            username="u_cmd",
            email="u@example.com",
            password="x",
            role="ADMIN",
        )
        now = timezone.now()
        TenantReportSchedule.objects.create(
            school=self.school,
            name="Due now",
            report_key="due",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["dst@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now - timedelta(minutes=5),
            created_by=self.user,
        )

    def test_send_scheduled_reports_sends_email_and_advances_next_run(self):
        mail.outbox.clear()
        out = StringIO()
        call_command("send_scheduled_reports", stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Due now", mail.outbox[0].subject)
        self.assertIn("emailed=1", out.getvalue())
        self.assertIn("skipped_no_recipients=0", out.getvalue())
        sr = TenantReportSchedule.objects.get(name="Due now")
        self.assertIsNotNone(sr.last_run)
        self.assertGreater(sr.next_run, sr.last_run)

    def test_send_scheduled_reports_dry_run_no_mail(self):
        mail.outbox.clear()
        out = StringIO()
        call_command("send_scheduled_reports", dry_run=True, stdout=out)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("Dry-run summary", out.getvalue())

    def test_send_scheduled_reports_filters_by_school_id(self):
        other = School.objects.create(
            name="Other Cmd",
            slug="other-cmd",
            subdomain="other-cmd",
            is_active=True,
            plan=self.plan,
        )
        now = timezone.now()
        TenantReportSchedule.objects.create(
            school=other,
            name="Other due",
            report_key="other",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(7, 0),
            recipients=["other@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now - timedelta(minutes=1),
            created_by=self.user,
        )
        mail.outbox.clear()
        call_command("send_scheduled_reports", school_id=self.school.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Due now", mail.outbox[0].subject)
        other_sr = TenantReportSchedule.objects.get(name="Other due")
        self.assertIsNone(other_sr.last_run)

    def test_send_scheduled_reports_limit_caps_batch(self):
        now = timezone.now()
        for i in range(2):
            TenantReportSchedule.objects.create(
                school=self.school,
                name=f"Extra {i}",
                report_key=f"x{i}",
                schedule_frequency=TenantReportSchedule.Frequency.DAILY,
                schedule_time=time(8, 0),
                recipients=[f"e{i}@example.com"],
                parameters={},
                is_active=True,
                last_run=None,
                next_run=now - timedelta(minutes=10 - i),
                created_by=self.user,
            )
        mail.outbox.clear()
        call_command("send_scheduled_reports", limit=2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(TenantReportSchedule.objects.filter(last_run__isnull=True).count(), 1)

    def test_send_scheduled_reports_limit_must_be_positive(self):
        with self.assertRaises(CommandError):
            call_command("send_scheduled_reports", limit=0)

    def test_send_scheduled_reports_no_due_global_message(self):
        TenantReportSchedule.objects.all().delete()
        out = StringIO()
        call_command("send_scheduled_reports", stdout=out)
        self.assertIn("No scheduled reports due.", out.getvalue())

    def test_send_scheduled_reports_no_due_for_school_message(self):
        out = StringIO()
        call_command("send_scheduled_reports", school_id=9_999_999, stdout=out)
        self.assertIn("No due schedules for school_id=9999999", out.getvalue())

    def test_send_scheduled_reports_stderr_when_active_no_recipients(self):
        iso_school = School.objects.create(
            name="Iso stderr",
            slug="iso-stderr",
            subdomain="iso-stderr",
            is_active=True,
            plan=self.plan,
        )
        now = timezone.now()
        sr = TenantReportSchedule.objects.create(
            school=iso_school,
            name="No rcpt stderr",
            report_key="nrstderr",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["placeholder@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now - timedelta(minutes=2),
            created_by=self.user,
        )
        TenantReportSchedule.objects.filter(pk=sr.pk).update(recipients=[])
        err = StringIO()
        mail.outbox.clear()
        call_command("send_scheduled_reports", school_id=iso_school.pk, stderr=err)
        self.assertIn("no recipient", err.getvalue().lower())
        self.assertEqual(len(mail.outbox), 0)
        sr.refresh_from_db()
        self.assertIsNotNone(sr.last_run)

    def test_send_scheduled_reports_dry_run_stdout_warns_no_recipients(self):
        iso_school = School.objects.create(
            name="Iso dry",
            slug="iso-dry",
            subdomain="iso-dry",
            is_active=True,
            plan=self.plan,
        )
        now = timezone.now()
        sr = TenantReportSchedule.objects.create(
            school=iso_school,
            name="No rcpt dry",
            report_key="nrdry",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["placeholder@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now - timedelta(minutes=3),
            created_by=self.user,
        )
        TenantReportSchedule.objects.filter(pk=sr.pk).update(recipients=[])
        out = StringIO()
        call_command(
            "send_scheduled_reports",
            dry_run=True,
            school_id=iso_school.pk,
            stdout=out,
        )
        self.assertIn("WARNING", out.getvalue())
        self.assertIn("Dry-run summary", out.getvalue())

    def test_send_scheduled_reports_logs_warning_when_skipping_no_recipients(self):
        iso_school = School.objects.create(
            name="Iso log",
            slug="iso-log",
            subdomain="iso-log",
            is_active=True,
            plan=self.plan,
        )
        now = timezone.now()
        sr = TenantReportSchedule.objects.create(
            school=iso_school,
            name="No rcpt log",
            report_key="nrlog",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["p@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now - timedelta(minutes=1),
            created_by=self.user,
        )
        TenantReportSchedule.objects.filter(pk=sr.pk).update(recipients=[])
        mail.outbox.clear()
        log_name = "apps.reports.management.commands.send_scheduled_reports"
        with self.assertLogs(log_name, level="WARNING") as captured:
            call_command("send_scheduled_reports", school_id=iso_school.pk)
        self.assertTrue(
            any("skipped_no_recipients" in entry for entry in captured.output),
            captured.output,
        )

    def test_send_scheduled_reports_json_summary_line(self):
        out = StringIO()
        call_command("send_scheduled_reports", stdout=out, json_summary=True)
        lines = [ln for ln in out.getvalue().strip().split("\n") if ln.strip()]
        summary = json.loads(lines[-1])
        self.assertEqual(summary["command"], "send_scheduled_reports")
        self.assertIn("emailed", summary)
        self.assertEqual(summary["failed"], 0)

    def test_send_scheduled_reports_strict_no_skip_raises_on_empty_recipients(self):
        iso_school = School.objects.create(
            name="Iso strict",
            slug="iso-strict",
            subdomain="iso-strict",
            is_active=True,
            plan=self.plan,
        )
        now = timezone.now()
        sr = TenantReportSchedule.objects.create(
            school=iso_school,
            name="Strict skip",
            report_key="strict",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["p@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now - timedelta(minutes=1),
            created_by=self.user,
        )
        TenantReportSchedule.objects.filter(pk=sr.pk).update(recipients=[])
        with self.assertRaises(CommandError):
            call_command(
                "send_scheduled_reports",
                school_id=iso_school.pk,
                strict_no_skip=True,
            )

    @patch("django.core.mail.EmailMessage.send", side_effect=SMTPException("fail"))
    def test_send_scheduled_reports_raises_when_email_fails(self, _mock_send):
        with self.assertRaises(CommandError):
            call_command("send_scheduled_reports", school_id=self.school.pk)


class ScheduledReportRunnerDelegationTests(TestCase):
    @patch("django.core.management.call_command")
    def test_run_due_reports_delegates_to_send_scheduled_reports(self, mock_cmd):
        from apps.reports.bi_services import ScheduledReportRunner

        ScheduledReportRunner.run_due_reports()
        mock_cmd.assert_called_once_with("send_scheduled_reports")

    @patch("django.core.management.call_command")
    def test_run_due_reports_forwards_school_limit_dry_run(self, mock_cmd):
        from apps.reports.bi_services import ScheduledReportRunner

        ScheduledReportRunner.run_due_reports(school_id=42, limit=3, dry_run=True)
        mock_cmd.assert_called_once_with(
            "send_scheduled_reports",
            school_id=42,
            limit=3,
            dry_run=True,
        )

    @patch("django.core.management.call_command")
    def test_run_due_reports_forwards_strict_no_skip_and_json_summary(self, mock_cmd):
        from apps.reports.bi_services import ScheduledReportRunner

        ScheduledReportRunner.run_due_reports(strict_no_skip=True, json_summary=True)
        mock_cmd.assert_called_once_with(
            "send_scheduled_reports",
            strict_no_skip=True,
            json_summary=True,
        )


class TenantReportScheduleRlsPolicyArtifactTests(TestCase):
    """PostgreSQL single-schema RLS lives in reports.0019; django-tenants and SQLite skip it."""

    def test_should_apply_rls_false_when_sqlite(self):
        from django.db import connection

        from apps.schools.rls import should_apply_rls

        if connection.vendor != "sqlite":
            self.skipTest("SQLite dev DB assertion")
        self.assertFalse(should_apply_rls(connection))

    def test_rls_migration_targets_schedule_table(self):
        import importlib

        mod = importlib.import_module(
            "apps.reports.migrations.0019_tenant_report_schedule_rls_postgresql"
        )
        self.assertEqual(mod.TABLE, "reports_tenantreportschedule")
        self.assertEqual(
            mod.POLICY_NAME, "reports_tenantreportschedule_tenant_isolation"
        )


def _request_with_messages(user):
    factory = RequestFactory()
    request = factory.post("/admin/reports/tenantreportschedule/")
    request.user = user

    def get_response(req):
        return HttpResponse()

    SessionMiddleware(get_response).process_request(request)
    request.session.save()
    MessageMiddleware(get_response).process_request(request)
    return request


class TenantReportScheduleAdminOperationsTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Padm",
            slug="p-adm-op",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Sadm",
            slug="s-adm-op",
            subdomain="s-adm-op",
            is_active=True,
            plan=self.plan,
        )
        self.user = User.objects.create_user(
            username="u_adm_op",
            email="u_adm_op@example.com",
            password="x",
            role="ADMIN",
        )
        self.schedule = TenantReportSchedule.objects.create(
            school=self.school,
            name="Gap",
            report_key="gap",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["keep@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=timezone.now() + timedelta(days=1),
            created_by=self.user,
        )
        TenantReportSchedule.objects.filter(pk=self.schedule.pk).update(recipients=[])

    def test_list_display_includes_last_run(self):
        ma = TenantReportScheduleAdmin(TenantReportSchedule, tenant_admin_site)
        self.assertIn("last_run", ma.list_display)

    def test_deactivate_active_empty_recipients_bulk_action(self):
        from django.contrib.messages import get_messages

        ma = TenantReportScheduleAdmin(TenantReportSchedule, tenant_admin_site)
        request = _request_with_messages(self.user)
        ma.deactivate_active_empty_recipients(
            request, TenantReportSchedule.objects.filter(pk=self.schedule.pk)
        )
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_active)
        msgs = [m.message for m in get_messages(request)]
        self.assertTrue(any("Deactivated" in m for m in msgs), msgs)
