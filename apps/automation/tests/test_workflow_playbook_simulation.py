"""
§11.4 workflow simulation slice: one scripted migration-playbook dry-run through
``execute_playbook`` (outcomes / automation audit path).
"""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.automation.models import (
    AutomationExecutionLog,
    MigrationPlaybook,
    MigrationProfile,
    MigrationRun,
)
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

    def test_two_step_playbook_failed_second_step_stops_audit_records_failed(self):
        """§11.4 depth: second step FAILURE → overall FAILED, both runs listed, execution log FAILED."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim fail step2 school",
            slug="workflow-sim-fail-step2",
            subdomain="workflow-sim-fail-step2",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_fail_step2",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_fail_on_step_two",
            name="SOT workflow simulation (fail step 2)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        run_ok = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.SUCCESS,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 0,
                "profile_slug": "students_from_powerschool",
            },
        )
        run_fail = MigrationRun.objects.create(
            school=school,
            migration_type="grades",
            dry_run=True,
            status=MigrationRun.Status.FAILED,
            triggered_by=user,
            error_message="simulated step 2 failure",
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 1,
                "profile_slug": "grades_from_powerschool",
            },
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step",
            side_effect=[run_ok, run_fail],
        ):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(result.get("runs") or []), 2)
        self.assertEqual(result["runs"][0].pk, run_ok.pk)
        self.assertEqual(result["runs"][1].pk, run_fail.pk)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "FAILED")
        self.assertEqual(summary.get("failed_steps"), 1)
        self.assertEqual(summary.get("partial_steps"), 0)
        self.assertEqual(summary.get("playbook_slug"), playbook.slug)

    def test_two_step_playbook_partial_then_success_yields_partial_audit(self):
        """§11.4 depth: step 1 PARTIAL + step 2 SUCCESS → overall PARTIAL; both runs; partial_steps=1."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim partial first school",
            slug="workflow-sim-partial-first",
            subdomain="workflow-sim-partial-first",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_partial_first",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_partial_then_ok",
            name="SOT workflow simulation (partial then ok)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        run_partial = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.PARTIAL,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 0,
                "profile_slug": "students_from_powerschool",
            },
        )
        run_ok = MigrationRun.objects.create(
            school=school,
            migration_type="grades",
            dry_run=True,
            status=MigrationRun.Status.SUCCESS,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 1,
                "profile_slug": "grades_from_powerschool",
            },
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step",
            side_effect=[run_partial, run_ok],
        ):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(len(result.get("runs") or []), 2)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.PARTIAL)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "PARTIAL")
        self.assertEqual(summary.get("failed_steps"), 0)
        self.assertEqual(summary.get("partial_steps"), 1)

    def test_two_step_playbook_success_then_partial_yields_partial_audit(self):
        """§11.4 depth: step 1 SUCCESS + step 2 PARTIAL → overall PARTIAL; partial_steps=1."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim partial second school",
            slug="workflow-sim-partial-second",
            subdomain="workflow-sim-partial-second",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_partial_second",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_ok_then_partial",
            name="SOT workflow simulation (ok then partial)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        run_ok = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.SUCCESS,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 0,
                "profile_slug": "students_from_powerschool",
            },
        )
        run_partial = MigrationRun.objects.create(
            school=school,
            migration_type="grades",
            dry_run=True,
            status=MigrationRun.Status.PARTIAL,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 1,
                "profile_slug": "grades_from_powerschool",
            },
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step",
            side_effect=[run_ok, run_partial],
        ):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(len(result.get("runs") or []), 2)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.PARTIAL)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "PARTIAL")
        self.assertEqual(summary.get("failed_steps"), 0)
        self.assertEqual(summary.get("partial_steps"), 1)

    def test_two_step_playbook_both_steps_partial_yields_partial_two_partial_steps(self):
        """§11.4 depth: two PARTIAL steps → overall PARTIAL; partial_steps=2."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim both partial school",
            slug="workflow-sim-both-partial",
            subdomain="workflow-sim-both-partial",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_both_partial",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_both_partial",
            name="SOT workflow simulation (both partial)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        run_p0 = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.PARTIAL,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 0,
                "profile_slug": "students_from_powerschool",
            },
        )
        run_p1 = MigrationRun.objects.create(
            school=school,
            migration_type="grades",
            dry_run=True,
            status=MigrationRun.Status.PARTIAL,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 1,
                "profile_slug": "grades_from_powerschool",
            },
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step",
            side_effect=[run_p0, run_p1],
        ):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        self.assertEqual(result["status"], "PARTIAL")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "PARTIAL")
        self.assertEqual(summary.get("failed_steps"), 0)
        self.assertEqual(summary.get("partial_steps"), 2)

    def test_two_step_playbook_partial_then_failed_yields_failed_mixed_steps(self):
        """§11.4 depth: PARTIAL then FAILED → FAILED; partial_steps=1 and failed_steps=1."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim partial then failed school",
            slug="workflow-sim-partial-fail",
            subdomain="workflow-sim-partial-fail",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_partial_fail",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_partial_then_fail",
            name="SOT workflow simulation (partial then fail)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        run_partial = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.PARTIAL,
            triggered_by=user,
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 0,
                "profile_slug": "students_from_powerschool",
            },
        )
        run_fail = MigrationRun.objects.create(
            school=school,
            migration_type="grades",
            dry_run=True,
            status=MigrationRun.Status.FAILED,
            triggered_by=user,
            error_message="simulated failure after partial",
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 1,
                "profile_slug": "grades_from_powerschool",
            },
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step",
            side_effect=[run_partial, run_fail],
        ):
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(result.get("runs") or []), 2)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "FAILED")
        self.assertEqual(summary.get("failed_steps"), 1)
        self.assertEqual(summary.get("partial_steps"), 1)

    def test_two_step_playbook_failed_first_step_does_not_invoke_second(self):
        """§11.4 depth: step 1 FAILED → stop; only one _run_one_step call; second profile never runs."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim fail first school",
            slug="workflow-sim-fail-first",
            subdomain="workflow-sim-fail-first",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_fail_first",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_fail_on_step_one",
            name="SOT workflow simulation (fail step 1)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        run_fail = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.FAILED,
            triggered_by=user,
            error_message="simulated step 1 failure",
            execution_summary={
                "playbook_slug": playbook.slug,
                "step_index": 0,
                "profile_slug": "students_from_powerschool",
            },
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step",
            side_effect=[run_fail],
        ) as mock_step:
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        self.assertEqual(mock_step.call_count, 1)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(result.get("runs") or []), 1)
        self.assertEqual(result["runs"][0].pk, run_fail.pk)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("failed_steps"), 1)
        self.assertEqual(summary.get("partial_steps"), 0)

    def test_playbook_empty_profile_slugs_fails_without_steps_and_records_log(self):
        """§11.4 depth: empty profile_slugs → no steps; FAILED + audit; _run_one_step never called."""
        school = School.objects.create(
            name="Workflow sim empty slugs school",
            slug="workflow-sim-empty-slugs",
            subdomain="workflow-sim-empty-slugs",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_empty_slugs",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_empty_profile_slugs",
            name="SOT workflow simulation (empty profile_slugs)",
            profile_slugs=[],
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step"
        ) as mock_step:
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        mock_step.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result.get("message"), "Playbook has no valid profiles.")
        self.assertEqual(len(result.get("runs") or []), 0)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertIn("Playbook has no valid profiles", log.error_message or "")
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "FAILED")
        self.assertEqual(summary.get("failed_steps"), 0)
        self.assertEqual(summary.get("partial_steps"), 0)
        self.assertEqual(summary.get("steps"), [])

    def test_playbook_unknown_profile_slugs_fails_without_steps_and_records_log(self):
        """§11.4 depth: slugs not matching active MigrationProfile rows → same early FAILED path."""
        school = School.objects.create(
            name="Workflow sim unknown slugs school",
            slug="workflow-sim-unknown-slugs",
            subdomain="workflow-sim-unknown-slugs",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_unknown_slugs",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_unknown_profile_slugs",
            name="SOT workflow simulation (unknown profile slugs)",
            profile_slugs=["zzz_no_such_migration_profile_slug_sot156"],
        )
        with patch(
            "apps.automation.playbook_executor._run_one_step"
        ) as mock_step:
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        mock_step.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result.get("message"), "Playbook has no valid profiles.")
        self.assertEqual(len(result.get("runs") or []), 0)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        self.assertIn("Playbook has no valid profiles", log.error_message or "")
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "FAILED")
        self.assertEqual(summary.get("failed_steps"), 0)
        self.assertEqual(summary.get("partial_steps"), 0)
        self.assertEqual(summary.get("steps"), [])

    def test_playbook_inactive_profile_slug_skipped_active_remaining_runs_one_step(self):
        """§11.4 depth: first slug inactive → skipped; second active profile still executes (one run)."""
        call_command("seed_migration_profiles")
        students = MigrationProfile.objects.get(slug="students_from_powerschool")
        students.is_active = False
        students.save(update_fields=["is_active"])
        school = School.objects.create(
            name="Workflow sim skip inactive school",
            slug="workflow-sim-skip-inactive",
            subdomain="workflow-sim-skip-inactive",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_skip_inactive",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_skip_inactive_students",
            name="SOT workflow simulation (skip inactive students)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        result = execute_playbook(
            playbook,
            school=school,
            user=user,
            dry_run=True,
            steps_payload=None,
        )
        self.assertIn(result["status"], ("SUCCESS", "PARTIAL"))
        runs = result.get("runs") or []
        self.assertEqual(len(runs), 1)
        es = runs[0].execution_summary or {}
        self.assertEqual(es.get("profile_slug"), "grades_from_powerschool")
        self.assertEqual(es.get("step_index"), 0)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIn(
            log.status,
            (
                AutomationExecutionLog.Status.SUCCESS,
                AutomationExecutionLog.Status.PARTIAL,
            ),
        )
        summary = log.execution_summary or {}
        steps = summary.get("steps") or []
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].get("profile_slug"), "grades_from_powerschool")

    def test_playbook_all_listed_profiles_inactive_fails_without_steps(self):
        """§11.4 depth: every listed slug maps only to inactive profiles → same FAILED path as empty."""
        call_command("seed_migration_profiles")
        MigrationProfile.objects.filter(
            slug__in=["students_from_powerschool", "grades_from_powerschool"]
        ).update(is_active=False)
        school = School.objects.create(
            name="Workflow sim all inactive school",
            slug="workflow-sim-all-inactive",
            subdomain="workflow-sim-all-inactive",
            is_active=True,
        )
        user = User.objects.create_user(
            username="workflow_sim_all_inactive",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_all_profiles_inactive",
            name="SOT workflow simulation (all profiles inactive)",
            profile_slugs=["students_from_powerschool", "grades_from_powerschool"],
        )
        with patch("apps.automation.playbook_executor._run_one_step") as mock_step:
            result = execute_playbook(
                playbook,
                school=school,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        mock_step.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result.get("message"), "Playbook has no valid profiles.")
        self.assertEqual(len(result.get("runs") or []), 0)

    def test_single_step_playbook_dry_run_user_none_records_success_log_without_triggered_by(
        self,
    ):
        """§11.4 depth: scheduled/system-style call with user=None still completes audit path."""
        call_command("seed_migration_profiles")
        school = School.objects.create(
            name="Workflow sim user none school",
            slug="workflow-sim-user-none",
            subdomain="workflow-sim-user-none",
            is_active=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_user_none_one_step",
            name="SOT workflow simulation (user=None one step)",
            profile_slugs=["students_from_powerschool"],
        )
        result = execute_playbook(
            playbook,
            school=school,
            user=None,
            dry_run=True,
            steps_payload=None,
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(result.get("runs") or []), 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIsNone(log.triggered_by_id)
        self.assertEqual(log.execution_type, AutomationExecutionLog.ExecutionType.DRY_RUN)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "SUCCESS")
        run = result["runs"][0]
        self.assertIsNone(run.triggered_by_id)

    def test_playbook_no_valid_profiles_user_none_records_failed_log_without_triggered_by(
        self,
    ):
        """§11.4 depth: early FAILED path with user=None leaves triggered_by unset."""
        school = School.objects.create(
            name="Workflow sim user none empty school",
            slug="workflow-sim-user-none-empty",
            subdomain="workflow-sim-user-none-empty",
            is_active=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_user_none_empty_slugs",
            name="SOT workflow simulation (user=None empty slugs)",
            profile_slugs=[],
        )
        with patch("apps.automation.playbook_executor._run_one_step") as mock_step:
            result = execute_playbook(
                playbook,
                school=school,
                user=None,
                dry_run=True,
                steps_payload=None,
            )
        mock_step.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIsNone(log.triggered_by_id)
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        summary = log.execution_summary or {}
        self.assertEqual(summary.get("final_status"), "FAILED")

    def test_single_step_playbook_dry_run_school_none_records_success_and_null_school_on_log(
        self,
    ):
        """§11.4 depth: school=None → log + run carry NULL school (platform / unscoped path)."""
        call_command("seed_migration_profiles")
        user = User.objects.create_user(
            username="workflow_sim_school_none_ok",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_school_none_one_step",
            name="SOT workflow simulation (school=None one step)",
            profile_slugs=["students_from_powerschool"],
        )
        result = execute_playbook(
            playbook,
            school=None,
            user=user,
            dry_run=True,
            steps_payload=None,
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(result.get("runs") or []), 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIsNone(log.school_id)
        summary = log.execution_summary or {}
        self.assertIsNone(summary.get("school_id"))
        self.assertEqual(summary.get("final_status"), "SUCCESS")
        run = result["runs"][0]
        self.assertIsNone(run.school_id)

    def test_playbook_no_valid_profiles_school_none_records_failed_log_with_null_school(
        self,
    ):
        """§11.4 depth: early FAILED with school=None leaves school unset on audit log."""
        user = User.objects.create_user(
            username="workflow_sim_school_none_empty",
            password="pass",
            is_staff=True,
        )
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_school_none_empty_slugs",
            name="SOT workflow simulation (school=None empty slugs)",
            profile_slugs=[],
        )
        with patch("apps.automation.playbook_executor._run_one_step") as mock_step:
            result = execute_playbook(
                playbook,
                school=None,
                user=user,
                dry_run=True,
                steps_payload=None,
            )
        mock_step.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIsNone(log.school_id)
        summary = log.execution_summary or {}
        self.assertIsNone(summary.get("school_id"))
        self.assertEqual(summary.get("final_status"), "FAILED")

    def test_single_step_playbook_dry_run_school_and_user_none_records_success(self):
        """§11.4 depth: fully unscoped call (school=None, user=None) still audits SUCCESS."""
        call_command("seed_migration_profiles")
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_unscoped_one_step",
            name="SOT workflow simulation (school+user None)",
            profile_slugs=["students_from_powerschool"],
        )
        result = execute_playbook(
            playbook,
            school=None,
            user=None,
            dry_run=True,
            steps_payload=None,
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(result.get("runs") or []), 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIsNone(log.school_id)
        self.assertIsNone(log.triggered_by_id)
        self.assertEqual(log.execution_type, AutomationExecutionLog.ExecutionType.DRY_RUN)
        summary = log.execution_summary or {}
        self.assertIsNone(summary.get("school_id"))
        self.assertEqual(summary.get("final_status"), "SUCCESS")
        run = result["runs"][0]
        self.assertIsNone(run.school_id)
        self.assertIsNone(run.triggered_by_id)

    def test_playbook_no_valid_profiles_school_and_user_none_records_failed(self):
        """§11.4 depth: early FAILED with both school and user unset on audit log."""
        playbook = MigrationPlaybook.objects.create(
            slug="sot_workflow_sim_unscoped_empty_slugs",
            name="SOT workflow simulation (unscoped empty slugs)",
            profile_slugs=[],
        )
        with patch("apps.automation.playbook_executor._run_one_step") as mock_step:
            result = execute_playbook(
                playbook,
                school=None,
                user=None,
                dry_run=True,
                steps_payload=None,
            )
        mock_step.assert_not_called()
        self.assertEqual(result["status"], "FAILED")
        log = AutomationExecutionLog.objects.filter(
            task_name="automation.playbook.execute"
        ).latest("started_at")
        self.assertIsNone(log.school_id)
        self.assertIsNone(log.triggered_by_id)
        self.assertEqual(log.status, AutomationExecutionLog.Status.FAILED)
        summary = log.execution_summary or {}
        self.assertIsNone(summary.get("school_id"))
        self.assertEqual(summary.get("final_status"), "FAILED")
