"""Workflow-aware offline apply (batch 1509)."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import enqueue_offline_action, process_offline_queue
from apps.schools.models import School, SchoolMembership


class OfflineWorkflowApplyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"WF {uid}",
            slug=f"wf-{uid}",
            subdomain=f"wf{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"wf_a_{uid}",
            password="pw",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.admin,
            school=self.school,
            defaults={"role": self.admin.role, "is_primary": True},
        )

    def test_substitute_handover_workflow_apply_returns_packet_id(self):
        start = timezone.now()
        end = start + timedelta(days=1)
        body = json.dumps(
            {
                "workflow": "substitute_handover",
                "fields": {
                    "teacher_id": "t-42",
                    "substitute_id": "s-99",
                    "absence_start": start.strftime("%Y-%m-%dT%H:%M"),
                    "absence_end": end.strftime("%Y-%m-%dT%H:%M"),
                    "grace_minutes": "30",
                    "reason_code": "sick",
                    "grace_minutes": "30",
                    "lesson_outline_json": "[]",
                },
            }
        )
        action = enqueue_offline_action(
            user_id=self.admin.pk,
            school_id=self.school.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": body, "title": "handover"},
            idempotency_key=f"wf-sh-{uuid.uuid4().hex[:10]}",
        )
        summary = process_offline_queue(school_id=self.school.pk, user_id=self.admin.pk)
        self.assertGreaterEqual(summary.get("synced", 0), 1)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        result = action.payload.get("_apply_result") or {}
        if not result:
            # apply metadata may live on conflict_details depending on processor version
            result = (action.conflict_details or {}).get("apply") or {}
        # Processor stores result on row metadata in process path — assert note body encodes packet
        from apps.people.models import StudentNote
        from apps.schoolops.models_micro_friction import SubstituteHandoverPacketRecord

        self.assertEqual(
            SubstituteHandoverPacketRecord.objects.filter(school_id=self.school.pk).count(),
            1,
        )
        note = StudentNote.objects.filter(school_id=self.school.pk).order_by("-id").first()
        self.assertIsNotNone(note)
        parsed = json.loads(note.body)
        self.assertEqual(parsed.get("workflow"), "substitute_handover")
        self.assertTrue(parsed.get("packet_id"))
