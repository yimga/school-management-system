"""Playbook operator hub: super-only migration playbook audit surface."""

import codecs
from urllib.parse import quote

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.automation.models import (
    AutomationExecutionLog,
    MigrationPlaybook,
    MigrationRun,
)
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class PlaybookOperatorHubTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="playbook_hub_tester",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.host = "manager.runmycampus.com"
        # Manager host reads MANAGER_SESSION_COOKIE_NAME and operators carry
        # baseline strict MFA; a bare force_login 302s to mfa/setup. Arm the
        # manager client (confirmed device + manager session + mfa_verified).
        self.client = login_manager_client(
            self.user, password="testpass123", host=self.host
        )
        cache.clear()
        AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute",
        ).delete()

    def test_playbook_operator_hub_renders_200(self):
        url = reverse("super:playbook_operator_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Playbook operator hub", html=False)
        self.assertContains(response, "automation.playbook.execute", html=False)

    def test_playbook_operator_hub_phase_h_skip_link_targets_main(self):
        url = reverse("super:playbook_operator_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#playbook-operator-hub-main"', body)
        self.assertIn('id="playbook-operator-hub-main"', body)

    def test_playbook_operator_hub_filters_logs_by_status(self):
        task = "automation.playbook.execute"
        row_ok = "pb_hub_filter_row_success"
        row_fail = "pb_hub_filter_row_failed"
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name=row_ok,
        )
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.FAILED,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name=row_fail,
        )
        base = reverse("super:playbook_operator_hub")
        r_all = self.client.get(base, HTTP_HOST=self.host)
        self.assertEqual(r_all.status_code, 200)
        self.assertContains(r_all, row_ok, html=False)
        self.assertContains(r_all, row_fail, html=False)

        r_ok = self.client.get(f"{base}?status=SUCCESS", HTTP_HOST=self.host)
        self.assertEqual(r_ok.status_code, 200)
        self.assertContains(r_ok, row_ok, html=False)
        self.assertNotContains(r_ok, row_fail, html=False)

        r_et = self.client.get(
            f"{base}?status=SUCCESS&execution_type=SCHEDULED", HTTP_HOST=self.host
        )
        self.assertEqual(r_et.status_code, 200)
        self.assertContains(r_et, "No playbook execution logs yet", html=False)
        self.assertNotContains(r_et, row_ok, html=False)
        self.assertNotContains(r_et, row_fail, html=False)

    def test_playbook_operator_hub_csv_export_starts_with_utf8_bom(self):
        base = reverse("super:playbook_operator_hub")
        r = self.client.get(f"{base}?export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            r.content.startswith(codecs.BOM_UTF8),
            msg=f"expected UTF-8 BOM prefix, got {r.content[:8]!r}",
        )

    def test_playbook_operator_hub_csv_content_disposition_static_filename(self):
        from urllib.parse import quote as url_quote

        from apps.schools.super_views_runtime_ops import PLAYBOOK_OPERATOR_HUB_CSV_FILENAME

        base = reverse("super:playbook_operator_hub")
        poison = "evil.csv"
        url = (
            f"{base}?export=csv&playbook_slug={quote(poison)}"
            f"&status=SUCCESS&execution_type=DRY_RUN"
        )
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        cd = r.get("Content-Disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn(PLAYBOOK_OPERATOR_HUB_CSV_FILENAME, cd)
        self.assertNotIn(poison, cd)
        star = url_quote(PLAYBOOK_OPERATOR_HUB_CSV_FILENAME, safe="")
        self.assertIn("filename*=UTF-8''", cd)
        self.assertIn(star, cd)

    def test_playbook_operator_hub_csv_filename_star_encodes_non_ascii_basename(self):
        from unittest.mock import patch
        from urllib.parse import quote as url_quote

        import apps.schools.super_views_runtime_ops as ops

        unicode_name = "journal_exécution_日志.csv"
        base = reverse("super:playbook_operator_hub")
        with patch.object(ops, "PLAYBOOK_OPERATOR_HUB_CSV_FILENAME", unicode_name):
            r = self.client.get(f"{base}?export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        cd = r.get("Content-Disposition", "")
        self.assertIn("filename*=UTF-8''", cd)
        self.assertIn(url_quote(unicode_name, safe=""), cd)
        self.assertIn(
            f'filename="{ops.PLAYBOOK_OPERATOR_HUB_CSV_FILENAME_ASCII_FALLBACK}"',
            cd,
        )

    def test_playbook_operator_hub_csv_export_includes_rows(self):
        task = "automation.playbook.execute"
        log = AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name="pb_hub_csv_schema_marker",
            execution_summary={
                "playbook_slug": "pb_export_slug",
                "steps": [{"run_id": 9001, "migration_type": "step_a", "status": "SUCCESS"}],
            },
        )
        base = reverse("super:playbook_operator_hub")
        r = self.client.get(f"{base}?export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.get("Content-Type", ""))
        body = r.content.decode()
        self.assertIn("log_id", body)
        self.assertIn("pb_hub_csv_schema_marker", body)
        self.assertIn("pb_export_slug", body)
        self.assertIn("9001", body)
        self.assertIn(str(log.pk), body)

    def test_playbook_operator_hub_csv_export_respects_status_filter(self):
        task = "automation.playbook.execute"
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name="csv_only_success",
        )
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.FAILED,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name="csv_only_failed",
        )
        base = reverse("super:playbook_operator_hub")
        r = self.client.get(f"{base}?status=SUCCESS&export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn("csv_only_success", body)
        self.assertNotIn("csv_only_failed", body)

    def test_playbook_operator_hub_csv_export_header_only_when_no_rows(self):
        base = reverse("super:playbook_operator_hub")
        r = self.client.get(f"{base}?export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        lines = [ln for ln in body.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, msg=body[:500])
        self.assertIn("log_id", lines[0])

    def test_playbook_operator_hub_csv_export_header_only_when_filter_empty(self):
        task = "automation.playbook.execute"
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.FAILED,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name="csv_filter_only_failed",
        )
        base = reverse("super:playbook_operator_hub")
        r = self.client.get(f"{base}?status=SUCCESS&export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        lines = [ln for ln in body.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1)
        self.assertNotIn("csv_filter_only_failed", body)

    def test_playbook_operator_hub_csv_export_caps_row_count(self):
        from apps.schools.super_views_runtime_ops import PLAYBOOK_OPERATOR_HUB_CSV_MAX_ROWS

        task = "automation.playbook.execute"
        batch = PLAYBOOK_OPERATOR_HUB_CSV_MAX_ROWS + 2
        AutomationExecutionLog.objects.bulk_create(
            [
                AutomationExecutionLog(
                    task_name=task,
                    status=AutomationExecutionLog.Status.SUCCESS,
                    execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
                    schema_name=f"csv_cap_{i:05d}",
                )
                for i in range(batch)
            ],
            batch_size=100,
        )
        base = reverse("super:playbook_operator_hub")
        r = self.client.get(f"{base}?export=csv", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        lines = [ln for ln in body.splitlines() if ln.strip()]
        self.assertEqual(len(lines), PLAYBOOK_OPERATOR_HUB_CSV_MAX_ROWS + 1)

    def test_playbook_operator_hub_shows_migration_run_admin_links(self):
        task = "automation.playbook.execute"
        run = MigrationRun.objects.create(
            migration_type="students_import",
            dry_run=True,
            status=MigrationRun.Status.SUCCESS,
        )
        run_pk = run.pk
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            execution_summary={
                "playbook_slug": "link_demo_pb",
                "steps": [
                    {
                        "run_id": run_pk,
                        "migration_type": "students_import",
                        "status": "SUCCESS",
                    },
                ],
            },
        )
        url = reverse("super:playbook_operator_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        # admin/ is host-split to platform_admin_site on the manager urlconf; the
        # hub view (rendered under the manager request) reverses it there, so the
        # test must reverse against the same urlconf (the default resolver has no
        # 'admin' namespace).
        run_change = reverse(
            "admin:automation_migrationrun_change",
            args=[run_pk],
            urlconf="config.manager_urls",
        )
        self.assertContains(response, run_change, html=False)
        self.assertContains(response, "link_demo_pb", html=False)

    def test_playbook_operator_hub_stale_migration_run_id_has_no_admin_link(self):
        task = "automation.playbook.execute"
        stale_id = 90_010_090_010
        self.assertFalse(MigrationRun.objects.filter(pk=stale_id).exists())
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            execution_summary={
                "playbook_slug": "stale_run_pb",
                "steps": [
                    {
                        "run_id": stale_id,
                        "migration_type": "orphan_step",
                        "status": "SUCCESS",
                    },
                ],
            },
        )
        url = reverse("super:playbook_operator_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        bad = reverse(
            "admin:automation_migrationrun_change",
            args=[stale_id],
            urlconf="config.manager_urls",
        )
        self.assertNotContains(response, bad, html=False)
        self.assertContains(response, "record removed or unavailable", html=False)

    def test_playbook_operator_hub_filters_by_playbook_slug(self):
        task = "automation.playbook.execute"
        MigrationPlaybook.objects.create(
            slug="pb-hub-alpha",
            name="Alpha",
            profile_slugs=[],
        )
        MigrationPlaybook.objects.create(
            slug="pb-hub-beta",
            name="Beta",
            profile_slugs=[],
        )
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name="sch_alpha",
            execution_summary={"playbook_slug": "pb-hub-alpha"},
        )
        AutomationExecutionLog.objects.create(
            task_name=task,
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_type=AutomationExecutionLog.ExecutionType.DRY_RUN,
            schema_name="sch_beta",
            execution_summary={"playbook_slug": "pb-hub-beta"},
        )
        base = reverse("super:playbook_operator_hub")
        r_all = self.client.get(base, HTTP_HOST=self.host)
        self.assertEqual(r_all.status_code, 200)
        self.assertContains(r_all, "sch_alpha", html=False)
        self.assertContains(r_all, "sch_beta", html=False)

        r_a = self.client.get(f"{base}?playbook_slug=pb-hub-alpha", HTTP_HOST=self.host)
        self.assertEqual(r_a.status_code, 200)
        self.assertContains(r_a, "sch_alpha", html=False)
        self.assertNotContains(r_a, "sch_beta", html=False)
