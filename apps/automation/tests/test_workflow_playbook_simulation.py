"""
§11.4 workflow simulation slice: one scripted migration-playbook dry-run through
``execute_playbook`` (outcomes / automation audit path).
"""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.automation.models import AutomationExecutionLog, MigrationPlaybook
from apps.automation.playbook_executor import execute_playbook
from apps.schools.models import School

User = get_user_model()


class WorkflowPlaybookSimulationTests(TestCase):
    def test_single_step_playbook_dry_run_records_execution_log(self):
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim school",
            slug="workflow-sim-school",
            subdomain="workflow-sim-school",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_user",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_one_step",
            name="SOT workflow simulation",
            profile_slugs=["students_from_powerschool"],
        )
        result = execute_playbook(
            playbook,
            school=school,
            user=user,
            dry_run=True,
            steps_payload=None,
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(result.get("runs") or []), 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("playbook_slug"), playbook.slug)
        self.assertEqual(summary.get("final_status"), "SUCCESS")
        self.assertIn("preflight_confidence_score", summary)

    def test_two_step_playbook_dry_run_with_school_records_two_runs(self):
        """Multi-step: students → grades profiles in one playbook (tenant-scoped audit path)."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim two-step school",
            slug="workflow-sim-two-step",
            subdomain="workflow-sim-two-step",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_two_step",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_two_step",
            name="SOT workflow simulation (two steps)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        result = execute_playbook(
            playbook,
            school=school,
            user=user,
            dry_run=True,
            steps_payload=None,
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(result.get("runs") or []), 2)
        step_indices = {
            r.execution_summary.get("step_index")
            for r in result["runs"]
            if r.execution_summary
        }
        self.assertEqual(step_indices, {0, 1})
        profiles = {r.execution_summary.get("profile_slug") for r in result["runs"]}
        self.assertIn("students_from_powerschool", profiles)
        self.assertIn("grades_from_powerschool", profiles)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("playbook_slug"), playbook.slug)
        self.assertEqual(summary.get("final_status"), "SUCCESS")
        self.assertIn("preflight_confidence_score", summary)

    def test_playbook_dry_run_with_steps_payload_preflight_sees_rows(self):
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim school payload",
            slug="workflow-sim-payload",
            subdomain="workflow-sim-payload",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_payload_user",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_payload_step",
            name="SOT workflow simulation (payload)",
            profile_slugs=["students_from_powerschool"],
        )
        # Canonical column names so migration dry-run validation can succeed end-to-end.
        steps_payload = [
            {
                "mapping": {},
                "rows": [
                    {
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "admission_number": "ADM-SIM-001",
                    },
                ],
            }
        ]
        result = execute_playbook(
            playbook,
            school=school,
            user=user,
            dry_run=True,
            steps_payload=steps_payload,
        )
        self.assertEqual(result["status"], "SUCCESS")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        summary = log.execution_summary or {}
        signals = summary.get("preflight_signals") or {}
        self.assertGreaterEqual(summary.get("preflight_confidence_score", 0), 0)
        self.assertGreater(signals.get("rows_evaluated", 0), 0)

    def test_playbook_preflight_blocked_below_threshold_without_override(self):
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim school gate",
            slug="workflow-sim-gate",
            subdomain="workflow-sim-gate",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_gate_user",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_low_confidence",
            name="SOT low-confidence gate",
            profile_slugs=["students_from_powerschool"],
        )
        # Rows present but no column mapping → required-field coverage collapses; score stays
        # below a high threshold so the gate blocks without override_reason.
        bad_payload = [{"rows": [{"fn": "x", "ln": "y", "adm": "1"}], "mapping": {}}]
        with patch.dict(os.environ, {"MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE": "95"}):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=bad_payload,
            )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result.get("runs"), [])
        self.assertIn("confidence", (result.get("message") or "").lower())

    def test_playbook_preflight_override_allows_execution_below_threshold(self):
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim school override",
            slug="workflow-sim-override",
            subdomain="workflow-sim-override",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_override_user",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_override",
            name="SOT override path",
            profile_slugs=["students_from_powerschool"],
        )
        bad_payload = [{"rows": [{"fn": "x", "ln": "y", "adm": "1"}], "mapping": {}}]
        with patch.dict(os.environ, {"MIGRATION_PLAYBOOK_MIN_CONFIDENCE_SCORE": "95"}):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=bad_payload,
                override_reason="SOT simulation — operator acknowledged low mapping coverage.",
            )
        # Preflight override allows the step to run; row validation may still yield PARTIAL.
        self.assertIn(result["status"], ("SUCCESS", "PARTIAL"))
        self.assertEqual(len(result.get("runs") or []), 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        summary = log.execution_summary or {}
        self.assertTrue(summary.get("override_applied"))
