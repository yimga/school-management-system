"""
End-to-end platform loop (mission checklist):

1. **Event** — `attendance_saved` via `publish_event` with tenant, school, student, classroom,
   `recorded_at`, optional `actor_user_id`, and canonical `event_id` (injected into payload before fan-out).
2. **Workflow** — Visual workflow trigger `attendance_saved`, condition `status in (absent, late)`,
   action `delay` (non-destructive); present → `WorkflowRunLog` SKIPPED.
3. **Webhook** — `EventWebhookSubscription` + signed POST + `EventWebhookDelivery`; analytics row
   `platform_loop_webhook_outcome` with status and `latency_ms`.
4. **Trace** — `platform_loop_attendance_trace` after workflow dispatch (skipped on replay for workflows).
5. **Replay** — `replay_event`: no extra workflow runs, no duplicate webhook deliveries or webhook outcome rows.

Run (set ``DJANGO_TEST_DB_FILE`` if the default test DB file is locked)::

    DJANGO_TEST_DB_FILE=".django_test_dbs/full_e2e.sqlite3" python manage.py test
      apps.platform_runtime.tests.test_platform_loop_attendance_workflow_webhook
      apps.events.tests apps.automation.tests apps.apicenter.tests
      --settings=config.settings --noinput --keepdb
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
)
from apps.automation.models import Workflow, WorkflowEdge, WorkflowNode, WorkflowRunLog
from apps.people.models import StudentProfile
from apps.platform_runtime import event_bus
from apps.platform_runtime.models import (
    EventWebhookDelivery,
    EventWebhookSubscription,
    PlatformEventLog,
)
from apps.platform_runtime.tasks import deliver_event_webhook_task
from apps.schools.models import School


class PlatformLoopAttendanceWorkflowWebhookTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Loop School",
            slug=f"loop-{uuid.uuid4().hex[:8]}",
            subdomain=f"loop-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school,
            name="Core",
            code=f"D-{uuid.uuid4().hex[:6]}",
        )
        cls.spec = Specialty.objects.create(
            department=cls.dept, name="Gen", code=f"G-{uuid.uuid4().hex[:4]}"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 1A",
            code=f"C-{uuid.uuid4().hex[:8]}",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Loop",
            last_name="Student",
            student_code=f"ST-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-LP",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=cls.spec,
            date_of_birth=date(2010, 3, 1),
            is_active=True,
        )

        cls.workflow = Workflow.objects.create(
            school=cls.school,
            name="Absent/Late loop",
            trigger_event=Workflow.Trigger.ATTENDANCE_SAVED,
            status=Workflow.Status.PUBLISHED,
            is_active=True,
        )
        t = WorkflowNode.objects.create(
            workflow=cls.workflow,
            external_id="t1",
            kind=WorkflowNode.Kind.TRIGGER,
            config={},
            position={},
        )
        c = WorkflowNode.objects.create(
            workflow=cls.workflow,
            external_id="c1",
            kind=WorkflowNode.Kind.CONDITION,
            config={
                "conditions": [
                    {
                        "field": "status",
                        "op": "in",
                        "value": ["absent", "late"],
                    }
                ]
            },
            position={},
        )
        a = WorkflowNode.objects.create(
            workflow=cls.workflow,
            external_id="a1",
            kind=WorkflowNode.Kind.ACTION,
            config={"action": {"type": "delay", "params": {"seconds": 0}}},
            position={},
        )
        WorkflowEdge.objects.create(workflow=cls.workflow, source=t, target=c)
        WorkflowEdge.objects.create(workflow=cls.workflow, source=c, target=a)

        cls.webhook_secret = "loop-test-secret"
        EventWebhookSubscription.objects.create(
            target_url="https://example.invalid/platform-loop",
            event_types=["attendance_saved"],
            is_active=True,
            tenant_id=str(cls.school.pk),
            secret=cls.webhook_secret,
        )

    def setUp(self):
        super().setUp()
        self._delay_patch = patch.object(
            deliver_event_webhook_task,
            "delay",
            side_effect=self._sync_deliver,
        )
        self._delay_patch.start()

    def tearDown(self):
        self._delay_patch.stop()
        super().tearDown()

    @staticmethod
    def _sync_deliver(delivery_id: int):
        return event_bus.deliver_webhook_attempt(int(delivery_id))

    @patch("requests.post")
    def test_platform_loop_absent_attendance_full_chain(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="ok")

        wf_logs_before = WorkflowRunLog.objects.filter(workflow=self.workflow).count()

        att = Attendance.objects.create(
            school=self.school,
            student=self.student,
            classroom=self.classroom,
            date=date(2025, 11, 12),
            status=Attendance.Status.ABSENT,
            remarks="",
        )

        ev = PlatformEventLog.objects.filter(event_type="attendance_saved").order_by("-pk").first()
        self.assertIsNotNone(ev)
        payload = ev.payload
        self.assertEqual(payload.get("event_id"), str(ev.pk))
        self.assertEqual(payload.get("attendance_id"), str(att.pk))
        self.assertEqual(payload.get("school_id"), str(self.school.pk))
        self.assertEqual(payload.get("tenant_id"), str(self.school.pk))
        self.assertEqual(payload.get("student_id"), str(self.student.pk))
        self.assertEqual(payload.get("classroom_id"), str(self.classroom.pk))
        self.assertIn("recorded_at", payload)

        self.assertTrue(mock_post.called)
        _args, kwargs = mock_post.call_args
        body_bytes = kwargs.get("data")
        headers = kwargs.get("headers") or {}
        self.assertIsNotNone(body_bytes)
        sig = headers.get("X-RMC-Signature")
        self.assertIsNotNone(sig)
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(sig, expected)

        d = EventWebhookDelivery.objects.filter(platform_event=ev).first()
        self.assertIsNotNone(d)
        self.assertEqual(d.status, EventWebhookDelivery.Status.DELIVERED)
        if d.delivered_at and d.created_at:
            latency = (d.delivered_at - d.created_at).total_seconds()
            self.assertGreaterEqual(latency, 0.0)

        wf_logs = WorkflowRunLog.objects.filter(workflow=self.workflow)
        self.assertEqual(wf_logs.count(), wf_logs_before + 1)
        log = wf_logs.order_by("-pk").first()
        self.assertEqual(log.status, WorkflowRunLog.Status.SUCCESS)

        trace = PlatformEventLog.objects.filter(
            event_type="platform_loop_attendance_trace"
        ).order_by("-pk").first()
        self.assertIsNotNone(trace)
        self.assertEqual(trace.payload.get("source_event_id"), str(ev.pk))
        self.assertFalse(trace.payload.get("is_replay"))
        self.assertTrue(trace.payload.get("workflow_dispatch_ran"))
        self.assertGreaterEqual(trace.payload.get("visual_workflow_results") or 0, 1)

        wh_out = PlatformEventLog.objects.filter(
            event_type="platform_loop_webhook_outcome"
        ).order_by("-pk").first()
        self.assertIsNotNone(wh_out)
        self.assertEqual(wh_out.payload.get("platform_event_id"), str(ev.pk))
        self.assertEqual(wh_out.payload.get("status"), "delivered")
        self.assertIsNotNone(wh_out.payload.get("latency_ms"))

        wh_out_before = PlatformEventLog.objects.filter(
            event_type="platform_loop_webhook_outcome"
        ).count()

        deliveries_before = EventWebhookDelivery.objects.count()
        out = event_bus.replay_event(ev.pk, dispatch_webhooks=True)
        self.assertTrue(out.get("ok"))

        self.assertEqual(
            WorkflowRunLog.objects.filter(workflow=self.workflow).count(),
            wf_logs_before + 1,
        )
        self.assertEqual(EventWebhookDelivery.objects.count(), deliveries_before)
        self.assertEqual(
            PlatformEventLog.objects.filter(
                event_type="platform_loop_webhook_outcome"
            ).count(),
            wh_out_before,
        )

        trace_after = PlatformEventLog.objects.filter(
            event_type="platform_loop_attendance_trace"
        ).order_by("-pk").first()
        self.assertIsNotNone(trace_after)
        self.assertTrue(trace_after.payload.get("is_replay"))

    @patch("requests.post")
    def test_present_skips_workflow_condition(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        wf_logs_before = WorkflowRunLog.objects.filter(workflow=self.workflow).count()

        Attendance.objects.create(
            school=self.school,
            student=self.student,
            classroom=self.classroom,
            date=date(2025, 11, 13),
            status=Attendance.Status.PRESENT,
            remarks="",
        )

        self.assertEqual(
            WorkflowRunLog.objects.filter(workflow=self.workflow).count(),
            wf_logs_before + 1,
        )
        skip_log = (
            WorkflowRunLog.objects.filter(workflow=self.workflow).order_by("-pk").first()
        )
        self.assertIsNotNone(skip_log)
        self.assertEqual(skip_log.status, WorkflowRunLog.Status.SKIPPED)
