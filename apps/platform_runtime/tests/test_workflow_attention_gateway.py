"""Flight Deck attention gateway: fail isolate, success archive, simulation."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.platform_runtime.models import WorkflowRun, WorkflowStep
from apps.platform_runtime.views_workflow_flight_deck import (
    flight_deck_json_view,
    simulate_scenario_view,
)
from apps.platform_runtime.workflow_attention_gateway import (
    SIMULATION_FAIL_STEP,
    SIMULATION_WORKFLOW_KEY,
    bucket_for_run,
    compute_health,
    pipeline_stages_for_run,
    remediator_for_run,
)
from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind
from apps.platform_runtime.workflow_simulation import (
    begin_simulation_run,
    resume_simulation_from_failure,
    run_simulation_worker,
)
from apps.platform_runtime.workflow_tracker import serialize_workflow_run

User = get_user_model()


class AttentionGatewayUnitTests(TestCase):
    def test_failed_run_is_action_required_and_pins_failed_step(self):
        run = WorkflowRun.objects.create(
            workflow_key=SIMULATION_WORKFLOW_KEY,
            workflow_label="Flight Deck scenario simulation",
            status="failed",
            current_step_name=SIMULATION_FAIL_STEP,
            current_step_ordinal=3,
            total_steps=4,
        )
        WorkflowStep.objects.create(run=run, ordinal=1, name="lint_verify", status="done")
        WorkflowStep.objects.create(run=run, ordinal=2, name="build_package", status="done")
        WorkflowStep.objects.create(
            run=run, ordinal=3, name="integration_test", status="failed"
        )
        WorkflowStep.objects.create(
            run=run, ordinal=4, name="cloud_deploy", status="pending"
        )
        self.assertEqual(bucket_for_run(run), "action_required")
        visuals = [row["visual"] for row in pipeline_stages_for_run(run)]
        self.assertEqual(visuals, ["done", "done", "failed", "pending"])
        rem = remediator_for_run(run)
        self.assertEqual(rem["failed_step"], SIMULATION_FAIL_STEP)
        self.assertTrue(rem["runbook_steps"])

    def test_succeeded_run_archives_out_of_action_required(self):
        run = WorkflowRun.objects.create(
            workflow_key=SIMULATION_WORKFLOW_KEY,
            status="succeeded",
        )
        self.assertEqual(bucket_for_run(run), "success_logs")
        health = compute_health(
            action_required=[],
            success_logs=[{"progress_percent": 100}],
        )
        self.assertEqual(health["workflow_state"], "Healthy")
        self.assertEqual(health["health_index"], 100)


class FlightDeckSimulationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.staff = User.objects.create_user(
            username="fd_sim_staff",
            email="fd_sim_staff@example.com",
            password="Test1234!long",
            is_staff=True,
            is_superuser=True,
        )

    def test_failure_path_isolates_integration_test_and_loads_runbook(self):
        run = begin_simulation_run(path="failure")
        self.assertIsNotNone(run)
        run_simulation_worker(run, path="failure", delay_seconds=0.0)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.current_step_name, SIMULATION_FAIL_STEP)
        self.assertEqual(
            run.suggested_remediation.get("auto_fix_kind"),
            "resume_from_checkpoint",
        )
        self.assertIn("AuthCheckSync", run.error_summary.get("message", ""))
        failed_step = run.steps.get(name=SIMULATION_FAIL_STEP)
        self.assertEqual(failed_step.status, "failed")

    def test_resume_from_failure_archives_to_success_logs(self):
        run = begin_simulation_run(path="failure")
        run_simulation_worker(run, path="failure", delay_seconds=0.0)
        run.refresh_from_db()
        result = resume_simulation_from_failure(run, delay_seconds=0.0)
        self.assertTrue(result.get("ok"))
        run.refresh_from_db()
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(bucket_for_run(run), "success_logs")
        self.assertEqual(run.steps.get(name="cloud_deploy").status, "done")

    def test_apply_fix_kind_resumes_simulation(self):
        run = begin_simulation_run(path="failure")
        run_simulation_worker(run, path="failure", delay_seconds=0.0)
        run.refresh_from_db()
        result = apply_auto_fix_kind(run=run, kind="resume_from_checkpoint")
        self.assertTrue(result.get("ok"))
        run.refresh_from_db()
        self.assertEqual(run.status, "succeeded")

    def test_success_path_never_lands_in_action_required(self):
        run = begin_simulation_run(path="success")
        run_simulation_worker(run, path="success", delay_seconds=0.0)
        run.refresh_from_db()
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(bucket_for_run(run), "success_logs")

    @override_settings(DEBUG=True)
    def test_flight_deck_json_splits_action_required_and_success_logs(self):
        failed = begin_simulation_run(path="failure")
        run_simulation_worker(failed, path="failure", delay_seconds=0.0)
        succeeded = begin_simulation_run(path="success")
        run_simulation_worker(succeeded, path="success", delay_seconds=0.0)
        req = self.factory.get("/platform-runtime/workflow-progress/flight-deck.json")
        req.user = self.staff
        resp = flight_deck_json_view(req)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        action_ids = {row["id"] for row in payload.get("action_required") or []}
        success_ids = {row["id"] for row in payload.get("success_logs") or []}
        failed.refresh_from_db()
        succeeded.refresh_from_db()
        self.assertIn(failed.pk, action_ids)
        self.assertNotIn(succeeded.pk, action_ids)
        self.assertIn(succeeded.pk, success_ids)
        featured = payload.get("featured_failure") or {}
        self.assertEqual(featured.get("id"), failed.pk)
        self.assertEqual(
            featured.get("remediator", {}).get("failed_step"),
            SIMULATION_FAIL_STEP,
        )
        self.assertEqual(payload.get("health", {}).get("workflow_state"), "Blocked")
        self.assertIn("simulate", payload.get("endpoints") or {})

    @override_settings(DEBUG=True)
    def test_simulate_view_sync_failure(self):
        req = self.factory.post(
            "/platform-runtime/workflow-progress/simulate/",
            {"path": "failure", "sync": "1"},
        )
        req.user = self.staff
        resp = simulate_scenario_view(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body.get("ok"))
        run = WorkflowRun.objects.get(pk=body["run_id"])
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.workflow_key, SIMULATION_WORKFLOW_KEY)

    def test_serialize_includes_progress_for_pipeline(self):
        run = WorkflowRun.objects.create(
            workflow_key=SIMULATION_WORKFLOW_KEY,
            status="running",
            current_step_name="build_package",
            current_step_ordinal=2,
            total_steps=4,
        )
        data = serialize_workflow_run(run)
        self.assertGreaterEqual(int(data.get("progress_percent") or 0), 0)
        self.assertEqual(data["workflow_key"], SIMULATION_WORKFLOW_KEY)

    def test_simulate_url_reverses(self):
        self.assertTrue(reverse("platform_runtime:workflow_progress_simulate"))
