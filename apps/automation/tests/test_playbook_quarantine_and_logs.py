"""Playbook audit logs, quarantine ↔ run traceability, stop-on-fail semantics."""

import uuid
from unittest.mock import patch

from django.db import connection
from django.core.management import call_command
from django.test import TestCase

from apps.automation.models import (
    AutomationExecutionLog,
    MigrationPlaybook,
    MigrationRun,
)
from apps.automation.quarantine_services import add_to_quarantine
from apps.schools.models import School


class MigrationRunQuarantineLinkTests(TestCase):
    def test_quarantine_records_reverse_relation_from_run(self):
        u = uuid.uuid4().hex[:8]
        school = School.objects.create(
            name="Q School",
            slug=f"q-school-{u}",
            subdomain=f"q-school-{u}",
            is_active=True,
        )
        run = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.SUCCESS,
            row_count=0,
        )
        rec = add_to_quarantine(
            school=school,
            migration_run=run,
            domain="students",
            row_index=1,
            payload={"a": 1},
            issue_class="missing_required",
        )
        self.assertEqual(rec.migration_run_id, run.pk)
        self.assertEqual(run.quarantine_records.count(), 1)
        self.assertIn(rec, run.quarantine_records.all())


class PlaybookExecutionLogTests(TestCase):
    def test_execution_log_records_current_connection_schema_name_when_present(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"schema_name_log_{u}",
            name="Schema name log",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        with patch.object(connection, "schema_name", "tenant_a", create=True):
            result = execute_playbook(
                playbook, school=None, user=None, dry_run=True, steps_payload=None
            )
        self.assertEqual(result["status"], "SUCCESS")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.schema_name, "tenant_a")

    def test_execution_log_schema_name_ignored_when_non_string(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"schema_name_non_str_{u}",
            name="Schema name non-string",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        with patch.object(connection, "schema_name", {"x": "tenant_a"}, create=True):
            result = execute_playbook(
                playbook, school=None, user=None, dry_run=True, steps_payload=None
            )
        self.assertEqual(result["status"], "SUCCESS")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.schema_name, "")

    def test_execution_log_schema_name_ignored_when_whitespace_only(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"schema_name_ws_{u}",
            name="Schema name whitespace",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        with patch.object(connection, "schema_name", "   \n\t  ", create=True):
            result = execute_playbook(
                playbook, school=None, user=None, dry_run=True, steps_payload=None
            )
        self.assertEqual(result["status"], "SUCCESS")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.schema_name, "")

    def test_execution_log_schema_name_truncates_oversized(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"schema_name_long_{u}",
            name="Schema name long",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        with patch.object(connection, "schema_name", "t" * 200, create=True):
            result = execute_playbook(
                playbook, school=None, user=None, dry_run=True, steps_payload=None
            )
        self.assertEqual(result["status"], "SUCCESS")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(len(log.schema_name), 63)

    def test_empty_playbook_writes_failed_log(self):
        playbook = MigrationPlaybook.objects.create(
            slug="empty_pb",
            name="Empty",
            profile_slugs=[],
        )
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook, school=None, user=None, dry_run=True, steps_payload=None
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("preflight_confidence_score", result)
        self.assertIn("preflight_signals", result)
        self.assertFalse(result.get("override_applied"))
        log = AutomationExecutionLog.objects.get(
            task_name="automation.playbook.execute"
        )
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertEqual(log.execution_summary.get("final_status"), "FAILED")
        self.assertEqual(log.execution_summary.get("failed_steps"), 0)
        self.assertEqual(log.execution_summary.get("partial_steps"), 0)

    @patch("apps.automation.playbook_executor._run_one_step")
    def test_playbook_stops_after_first_failed_step(self, mock_step):
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="PB School",
            slug="pb-school",
            subdomain="pb-school",
            is_active=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="two_step_fail",
            name="Two step",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )

        def _one_fail(*args, **kwargs):
            return MigrationRun.objects.create(
                school=school,
                migration_type="students",
                dry_run=True,
                status=MigrationRun.Status.FAILED,
                row_count=0,
                execution_summary={"playbook_slug": playbook.slug, "step_index": 0},
            )

        mock_step.side_effect = _one_fail
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook, school=school, user=None, dry_run=True, steps_payload=None
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(mock_step.call_count, 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertEqual(len(log.execution_summary.get("steps") or []), 1)
        self.assertEqual(log.execution_summary.get("failed_steps"), 1)

    @patch("apps.automation.playbook_executor._run_one_step")
    def test_playbook_partial_status_preserved_across_steps(self, mock_step):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        school = School.objects.create(
            name="PB2 School",
            slug=f"pb2-school-{u}",
            subdomain=f"pb2-school-{u}",
            is_active=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug=f"two_step_partial_{u}",
            name="Two step partial",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        profiles = playbook.get_profiles()
        self.assertEqual(len(profiles), 2)

        def _step(pb, profile, step_index, sch, user, dry_run, payload):
            st = (
                MigrationRun.Status.PARTIAL
                if step_index == 1
                else MigrationRun.Status.SUCCESS
            )
            return MigrationRun.objects.create(
                school=sch,
                migration_type=profile.domain,
                dry_run=True,
                status=st,
                row_count=0,
                execution_summary={
                    "playbook_slug": pb.slug,
                    "step_index": step_index,
                    "profile_slug": profile.slug,
                },
            )

        mock_step.side_effect = _step
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook, school=school, user=None, dry_run=True, steps_payload=None
        )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(mock_step.call_count, 2)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.PARTIAL)
        self.assertEqual(len(log.execution_summary.get("steps") or []), 2)
        self.assertEqual(log.execution_summary.get("partial_steps"), 1)

    def test_preflight_low_confidence_blocks_without_override(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"low_conf_block_{u}",
            name="Low conf block",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=False,
            steps_payload=[{"rows": [{"first_name": "A"}], "mapping": {}}],
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("preflight_confidence_score", result)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertFalse(log.execution_summary.get("override_applied"))
        self.assertIn("preflight_confidence_score", log.execution_summary)

    def test_preflight_whitespace_only_override_reason_still_blocks(self):
        """Override must be non-empty after strip; whitespace is not a valid operator attestation."""
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"low_conf_ws_override_{u}",
            name="Low conf whitespace override",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=False,
            steps_payload=[{"rows": [{"first_name": "A"}], "mapping": {}}],
            override_reason="   \n\t  ",
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("preflight_confidence_score", result)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertFalse(log.execution_summary.get("override_applied"))

    def test_preflight_invisible_only_override_reason_still_blocks(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"low_conf_invisible_override_{u}",
            name="Low conf invisible override",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=False,
            steps_payload=[{"rows": [{"first_name": "A"}], "mapping": {}}],
            override_reason="\u200b\u200c\u200d\ufeff",
        )
        self.assertEqual(result["status"], "FAILED")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertFalse(log.execution_summary.get("override_applied"))

    @patch("apps.automation.models.AutomationExecutionLog.objects.filter")
    def test_execute_playbook_does_not_use_latest_log_lookup(self, mock_filter):
        # Guard against race-prone "latest started_at" lookups; executor should update
        # the exact log instance it creates.
        mock_filter.side_effect = AssertionError("execute_playbook must not call .filter(...).latest(...)")
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"no_latest_lookup_{u}",
            name="No latest lookup",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=True,
            steps_payload=None,
        )
        self.assertEqual(result["status"], "SUCCESS")

    @patch("apps.automation.playbook_executor._run_one_step")
    def test_preflight_override_allows_execution(self, mock_step):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"low_conf_override_{u}",
            name="Low conf override",
            profile_slugs=["students_from_powerschool"],
        )

        def _ok(*args, **kwargs):
            return MigrationRun.objects.create(
                school=None,
                migration_type="students",
                dry_run=False,
                status=MigrationRun.Status.SUCCESS,
                row_count=1,
                execution_summary={"playbook_slug": playbook.slug, "step_index": 0},
            )

        mock_step.side_effect = _ok
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=False,
            steps_payload=[{"rows": [{"first_name": "A"}], "mapping": {}}],
            override_reason="Operator validated source quality manually.",
        )
        self.assertEqual(result["status"], "SUCCESS")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertTrue(log.execution_summary.get("override_applied"))
        self.assertIn("Operator validated", log.execution_summary.get("override_reason", ""))

    def test_preflight_high_confidence_runs_without_override(self):
        call_command("seed_migration_profiles")
        u = uuid.uuid4().hex[:8]
        playbook = MigrationPlaybook.objects.create(
            slug=f"high_conf_ok_{u}",
            name="High conf",
            profile_slugs=["students_from_powerschool"],
        )
        from apps.automation.playbook_executor import execute_playbook

        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=True,
            steps_payload=[
                {
                    "rows": [
                        {"first_name": "A", "last_name": "B", "admission_number": "S1"},
                        {"first_name": "C", "last_name": "D", "admission_number": "S2"},
                    ],
                    "mapping": {
                        "first_name": "first_name",
                        "last_name": "last_name",
                        "admission_number": "admission_number",
                    },
                }
            ],
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("preflight_confidence_score", result)
        self.assertIn("preflight_signals", result)
        self.assertFalse(result.get("override_applied"))
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertGreaterEqual(log.execution_summary.get("preflight_confidence_score", 0), 70)
