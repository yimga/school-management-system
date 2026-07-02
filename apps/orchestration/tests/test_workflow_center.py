"""T13: orchestration Workflow Center — browse definitions, launch runs, timeline.

Promotes the old operator_workbench stub into a usable center: an operator can
see what process definitions exist, launch a run, and inspect a run's step
timeline — over the existing engine (models + JSON API + Celery).
"""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.orchestration import event_log
from apps.orchestration.models import (
    OrchestrationRun,
    OrchestrationStepEvent,
    ProcessDefinition,
    ProcessDefinitionVersion,
)


@override_settings(ALLOWED_HOSTS=["*"])
class WorkflowCenterTests(TestCase):
    # The Workflow Center is reached at the /super/ path, which
    # require_super_access_with_host accepts on any host (its _is_super_surface
    # check passes on a /super/ path), so the default testserver client + a
    # superuser is sufficient — no manager-host cookie juggling needed.
    def setUp(self):
        self.user = User.objects.create_user(
            username="wf_center_op",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        cache.clear()
        self.defn = ProcessDefinition.objects.create(
            code="admissions_flow",
            name="Admissions Flow",
            description="Multi-step admissions review.",
            current_version=1,
        )
        ProcessDefinitionVersion.objects.create(
            definition=self.defn,
            version_number=1,
            is_current=True,
        )

    def test_workbench_lists_definitions_with_start_button(self):
        url = reverse("super:orchestration_workbench")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Admissions Flow", body)
        self.assertIn("Process definitions", body)
        self.assertIn(
            reverse("super:orchestration_start_run", args=[self.defn.code]), body
        )

    def test_start_run_creates_pending_run_and_event(self):
        url = reverse("super:orchestration_start_run", args=[self.defn.code])
        resp = self.client.post(url)
        self.assertIn(resp.status_code, (302, 303), resp.content)
        run = OrchestrationRun.objects.filter(definition=self.defn).first()
        self.assertIsNotNone(run)
        self.assertEqual(run.status, OrchestrationRun.Status.PENDING)
        self.assertEqual(run.triggered_by_id, self.user.pk)
        self.assertTrue(
            OrchestrationStepEvent.objects.filter(
                run=run, event_type=OrchestrationStepEvent.EventType.RUN_CREATED
            ).exists()
        )
        # The redirect points at this run's detail page.
        self.assertIn(str(run.pk), resp["Location"])

    def test_run_detail_shows_timeline(self):
        run = OrchestrationRun.objects.create(
            definition=self.defn,
            status=OrchestrationRun.Status.PENDING,
        )
        event_log.emit(
            run,
            event_type=OrchestrationStepEvent.EventType.RUN_CREATED,
            payload={},
        )
        url = reverse("super:orchestration_run_detail", args=[run.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Step timeline", body)
        self.assertIn("Admissions Flow", body)
