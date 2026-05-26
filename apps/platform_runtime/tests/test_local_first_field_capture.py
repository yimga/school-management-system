"""Local-first field_capture offline enqueue → notes_report apply."""

from __future__ import annotations

import json
import uuid

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.people.models import StudentNote
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import enqueue_offline_action, process_offline_queue
from apps.schools.models import School, SchoolMembership


def _host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class LocalFirstFieldCaptureTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name=f"LF {uid}",
            slug=f"lf-{uid}",
            subdomain=f"lf{uid}",
            is_active=True,
        )
        self.operator = User.objects.create_user(
            username=f"lf_a_{uid}",
            password="pw",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.operator,
            school=self.school,
            defaults={"role": self.operator.role, "is_primary": True},
        )

    def test_field_capture_payload_creates_student_note(self):
        from django.utils import timezone

        start = timezone.now()
        end = start + timezone.timedelta(days=1)
        body = json.dumps(
            {
                "workflow": "substitute_handover",
                "fields": {
                    "teacher_id": "t-1",
                    "substitute_id": "s-2",
                    "absence_start": start.strftime("%Y-%m-%dT%H:%M"),
                    "absence_end": end.strftime("%Y-%m-%dT%H:%M"),
                    "lesson_outline_json": "[]",
                    "grace_minutes": "30",
                },
            }
        )
        action = enqueue_offline_action(
            user_id=self.operator.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": body, "title": "substitute handover", "kind": "note"},
            idempotency_key=f"lf-handover-{uuid.uuid4().hex[:12]}",
        )
        self.assertEqual(action.status, OfflineAction.Status.QUEUED)
        summary = process_offline_queue(school_id=self.school.pk, user_id=self.operator.pk)
        self.assertGreaterEqual(summary.get("synced", 0), 1)
        note = StudentNote.objects.filter(school_id=self.school.pk).order_by("-id").first()
        self.assertIsNotNone(note)
        parsed = json.loads(note.body)
        self.assertEqual(parsed.get("workflow"), "substitute_handover")
        self.assertTrue(parsed.get("packet_id"))

    def test_api_offline_enqueue_accepts_field_capture_shape(self):
        from django.test import RequestFactory

        from apps.portal.views_offline_sync import api_offline_enqueue

        factory = RequestFactory()
        payload = {
            "action_type": "notes_report",
            "payload": {
                "body": json.dumps({"workflow": "ops_pos_sale", "fields": {"item_label": "Pen"}}),
                "title": "ops pos sale",
            },
            "idempotency_key": f"lf-pos-{uuid.uuid4().hex[:12]}",
        }
        request = factory.post(
            "/portal/api/offline/enqueue/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = self.operator
        request.school = self.school
        resp = api_offline_enqueue(request)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body.get("ok"))
