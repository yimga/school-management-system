"""Authenticated offline enqueue → process API replay (metric 8/25 server proof)."""

from __future__ import annotations

import json
import uuid

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.lesson_homework_kernel import (
    PUBLISHED,
    advance_homework_stage,
    create_homework,
    store_homework,
)
from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.platform_runtime.models import OfflineAction
from apps.schools.models import School, SchoolMembership


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


class OfflineAuthenticatedApiReplayTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name=f"Offline Auth {uid}",
            slug=f"off-auth-{uid}",
            subdomain=f"offauth{uid}",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username=f"teacher_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        self.student_user = User.objects.create_user(
            username=f"student_{uid}",
            password="pass-test",
            role=User.Role.STUDENT,
        )
        SchoolMembership.objects.create(
            user=self.teacher,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        SchoolMembership.objects.create(
            user=self.student_user,
            school=self.school,
            role=User.Role.STUDENT,
            is_primary=True,
        )
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025-2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )
        dept = Department.objects.create(
            school=self.school,
            name="Core",
            code=f"C{uid}",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=dept,
            name="1A",
            code=f"1A{uid}",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            first_name="Offline",
            last_name="Learner",
            student_code=f"ST{uid}",
            academic_year=year,
            classroom=self.classroom,
            is_active=True,
        )
        self.host = _tenant_host(self.school)

    def _seed_published_homework(self):
        hw = create_homework(
            school_id=self.school.pk,
            teacher_user_id=self.teacher.pk,
            classroom_id=self.classroom.pk,
            subject="Science",
            title="Offline lab report",
            instructions="Submit observations from the field trip.",
            assigned_student_ids=[self.student.pk],
            due_date=None,
        )
        hw = advance_homework_stage(
            homework=hw, target_stage=PUBLISHED, actor_user_id=self.teacher.pk
        )
        self.school.settings = store_homework(
            school_settings=dict(self.school.settings or {}),
            homework=hw,
        )
        self.school.save(update_fields=["settings", "updated_at"])
        return hw.homework_id

    def test_teacher_enqueue_then_process_syncs_support_ticket(self):
        idem = f"auth-sync-{uuid.uuid4().hex[:12]}"
        self.client.force_login(self.teacher)
        enqueue_resp = self.client.post(
            reverse("portal:api_offline_enqueue"),
            data=json.dumps(
                {
                    "action_type": "support.ticket",
                    "payload": {
                        "subject": "Authenticated offline replay",
                        "message": "Integration test — safe to ignore.",
                    },
                    "idempotency_key": idem,
                }
            ),
            content_type="application/json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(enqueue_resp.status_code, 200)
        body = enqueue_resp.json()
        self.assertTrue(body.get("ok"))
        action_id = body.get("id")
        self.assertTrue(action_id)

        row = OfflineAction.objects.get(pk=action_id)
        self.assertEqual(row.status, OfflineAction.Status.QUEUED)
        self.assertEqual(row.idempotency_key, idem)

        process_resp = self.client.post(
            reverse("portal:api_offline_process"),
            data="{}",
            content_type="application/json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(process_resp.status_code, 200)
        summary = process_resp.json()
        self.assertTrue(summary.get("ok"))
        self.assertGreaterEqual(summary.get("synced", 0), 1)

        row.refresh_from_db()
        self.assertEqual(row.status, OfflineAction.Status.SYNCED)

    def test_student_enqueue_then_process_syncs_homework_submission(self):
        homework_id = self._seed_published_homework()
        idem = f"hw-auth-{uuid.uuid4().hex[:12]}"
        # Teacher session: portal offline API is role-gated; payload carries student_id.
        self.client.force_login(self.teacher)
        enqueue_resp = self.client.post(
            reverse("portal:api_offline_enqueue"),
            data=json.dumps(
                {
                    "action_type": "homework_submission",
                    "payload": {
                        "homework_id": homework_id,
                        "student_id": self.student.pk,
                        "submission_text": "Submitted offline via authenticated API replay.",
                    },
                    "idempotency_key": idem,
                }
            ),
            content_type="application/json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(enqueue_resp.status_code, 200)
        body = enqueue_resp.json()
        self.assertTrue(body.get("ok"))

        process_resp = self.client.post(
            reverse("portal:api_offline_process"),
            data="{}",
            content_type="application/json",
            HTTP_HOST=self.host,
        )
        self.assertEqual(process_resp.status_code, 200)
        summary = process_resp.json()
        self.assertTrue(summary.get("ok"))
        self.assertGreaterEqual(summary.get("synced", 0), 1)

        self.school.refresh_from_db()
        subs = (
            (self.school.settings or {})
            .get("academics", {})
            .get("homework_submissions", {})
            .get(homework_id, {})
        )
        self.assertIn(str(self.student.pk), subs)
        self.assertIn("Submitted offline", subs[str(self.student.pk)]["submission_text"])
