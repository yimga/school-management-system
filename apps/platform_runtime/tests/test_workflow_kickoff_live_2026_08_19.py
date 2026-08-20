"""Cross-engine kickoff live attention — current issues only, no false positives."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.orchestration.models import OrchestrationRun, ProcessDefinition
from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_attention_gateway import SIMULATION_WORKFLOW_KEY
from apps.platform_runtime.workflow_kickoff_live import (
    compose_engine_attention,
    compose_from_automation_log,
    compose_from_orchestration_run,
    compose_from_progress_run,
    compose_kickoff_live,
    mark_orchestration_open_failures,
    open_automation_failure_count,
    open_orchestration_failure_count,
)
from apps.schools.models import School
from apps.siteconfig.models_workflow import (
    SchoolAutomationWorkflow,
    SchoolWorkflowExecutionLog,
)
from apps.studio_os.services import get_automation_workflow_health_summary


class KickoffLiveHonestyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Kickoff Live School",
            slug="kickoff-live-1810",
            subdomain="kickoff-live-1810",
            is_active=True,
        )
        self.defn = ProcessDefinition.objects.create(
            code="admissions",
            name="Admissions",
        )

    def test_succeeded_progress_run_has_no_remediator(self):
        run = WorkflowRun.objects.create(
            workflow_key="evals_bulk_grades",
            status="succeeded",
            school_id=str(self.school.pk),
        )
        live = compose_from_progress_run(run)
        self.assertEqual(live["issues_open"], 0)
        self.assertIsNone(live["remediator"])
        self.assertEqual(live["attention_bucket"], "success_logs")
        self.assertEqual(live["percent"], 100)

    def test_failed_progress_run_is_action_required(self):
        run = WorkflowRun.objects.create(
            workflow_key="evals_bulk_grades",
            status="failed",
            school_id=str(self.school.pk),
            current_step_name="write",
            error_summary={"type": "ValueError", "message": "row rejected"},
        )
        live = compose_from_progress_run(run)
        self.assertEqual(live["issues_open"], 1)
        self.assertIsNotNone(live["remediator"])
        self.assertEqual(live["attention_bucket"], "action_required")

    def test_later_orchestration_success_clears_open_failure(self):
        OrchestrationRun.objects.create(
            definition=self.defn,
            school=self.school,
            status=OrchestrationRun.Status.FAILED,
            error_message="timeout",
        )
        self.assertEqual(open_orchestration_failure_count(school=self.school), 1)
        request = type("R", (), {"school": self.school})()
        self.assertEqual(get_automation_workflow_health_summary(request)["failing_count"], 1)
        live_failed = compose_from_orchestration_run(
            OrchestrationRun.objects.filter(school=self.school).order_by("pk").first()
        )
        self.assertEqual(live_failed["issues_open"], 1)
        self.assertIsNotNone(live_failed["remediator"])

        OrchestrationRun.objects.create(
            definition=self.defn,
            school=self.school,
            status=OrchestrationRun.Status.COMPLETED,
        )
        self.assertEqual(open_orchestration_failure_count(school=self.school), 0)
        latest = (
            OrchestrationRun.objects.filter(school=self.school)
            .order_by("-created_at")
            .first()
        )
        live = compose_from_orchestration_run(latest)
        self.assertEqual(live["issues_open"], 0)
        self.assertIsNone(live["remediator"])
        attention = compose_engine_attention(self.school)
        self.assertEqual(attention["orchestration_open"], 0)
        self.assertFalse(attention["needs_attention"])

    def test_studio_failing_count_uses_open_not_all_time(self):
        OrchestrationRun.objects.create(
            definition=self.defn,
            school=self.school,
            status=OrchestrationRun.Status.FAILED,
        )
        OrchestrationRun.objects.create(
            definition=self.defn,
            school=self.school,
            status=OrchestrationRun.Status.COMPLETED,
        )
        request = type("R", (), {"school": self.school})()
        summary = get_automation_workflow_health_summary(request)
        self.assertEqual(summary["failing_count"], 0)

    def test_simulation_run_hidden_from_tenant_attention(self):
        WorkflowRun.objects.create(
            workflow_key=SIMULATION_WORKFLOW_KEY,
            status="failed",
            school_id=str(self.school.pk),
            error_summary={"type": "AuthError", "message": "token expired"},
        )
        tenant_attention = compose_engine_attention(
            self.school,
            school_id=str(self.school.pk),
            control_plane=False,
        )
        self.assertEqual(tenant_attention["progress_bus_open"], 0)
        self.assertFalse(tenant_attention["needs_attention"])
        manager_attention = compose_engine_attention(
            self.school,
            school_id=str(self.school.pk),
            control_plane=True,
        )
        self.assertGreaterEqual(manager_attention["progress_bus_open"], 1)

    def test_later_automation_success_clears_open_failure(self):
        wf = SchoolAutomationWorkflow.objects.create(
            school=self.school,
            name="Attendance reminder",
            trigger="attendance_saved",
            status=SchoolAutomationWorkflow.Status.PUBLISHED,
        )
        SchoolWorkflowExecutionLog.objects.create(
            workflow=wf,
            run_status=SchoolWorkflowExecutionLog.RunStatus.FAILED,
            error_message="notify failed",
        )
        self.assertEqual(open_automation_failure_count(school=self.school), 1)
        SchoolWorkflowExecutionLog.objects.create(
            workflow=wf,
            run_status=SchoolWorkflowExecutionLog.RunStatus.SUCCESS,
        )
        self.assertEqual(open_automation_failure_count(school=self.school), 0)
        latest = (
            SchoolWorkflowExecutionLog.objects.filter(workflow=wf)
            .order_by("-created_at")
            .first()
        )
        live = compose_from_automation_log(latest)
        self.assertEqual(live["issues_open"], 0)
        self.assertIsNone(live["remediator"])

    def test_workbench_retry_only_on_open_failure(self):
        old = OrchestrationRun.objects.create(
            definition=self.defn,
            school=self.school,
            status=OrchestrationRun.Status.FAILED,
        )
        new = OrchestrationRun.objects.create(
            definition=self.defn,
            school=self.school,
            status=OrchestrationRun.Status.COMPLETED,
        )
        rows = list(
            OrchestrationRun.objects.filter(school=self.school).order_by("-created_at")
        )
        mark_orchestration_open_failures(rows, school=self.school)
        by_id = {row.pk: row for row in rows}
        self.assertTrue(by_id[old.pk].superseded_failure)
        self.assertFalse(by_id[old.pk].open_failure)
        self.assertFalse(by_id[new.pk].open_failure)

    def test_compose_kickoff_prefers_progress_bus_then_idle(self):
        idle = compose_kickoff_live(
            workflow_key="academics-timetable-generate",
            school=self.school,
        )
        self.assertEqual(idle["issues_open"], 0)
        self.assertIsNone(idle["remediator"])
        WorkflowRun.objects.create(
            workflow_key="academics-timetable-generate",
            status="failed",
            school_id=str(self.school.pk),
        )
        live = compose_kickoff_live(
            workflow_key="academics-timetable-generate",
            school=self.school,
            school_id=str(self.school.pk),
        )
        self.assertEqual(live["issues_open"], 1)
        self.assertEqual(live["engine"], "progress_bus")


class KickoffLiveHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kickoff-live-staff",
            email="kickoff-live@example.com",
            password="Test1234!long",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_kickoff_json_hides_remediator_when_clean(self):
        url = reverse("platform_runtime:workflow_progress_kickoff_live")
        resp = self.client.get(url, {"workflow_key": "evals_bulk_grades"})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload.get("issues_open"), 0)
        self.assertIsNone(payload.get("remediator"))
        self.assertIn("needs_attention", payload)

    def test_anonymous_is_rejected(self):
        self.client.logout()
        url = reverse("platform_runtime:workflow_progress_kickoff_live")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (401, 302, 403))
