"""HTTP tests for offline sync queue dashboard + conflict UX (tenant-scoped)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
)
from apps.people.models import StudentProfile
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import enqueue_offline_action, process_offline_queue
from apps.schools.models import School, SchoolMembership
from apps.schools.provision_email_urls import build_public_site_url


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


class OfflineSyncDashboardHttpTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.client = Client(enforce_csrf_checks=False)
        self.school_a = School.objects.create(
            name=f"OS A {uid}",
            slug=f"os-a-{uid}",
            subdomain=f"osoa{uid}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name=f"OS B {uid}",
            slug=f"os-b-{uid}",
            subdomain=f"osob{uid}",
            is_active=True,
        )
        self.teacher_a = User.objects.create_user(
            username=f"tea_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        self.teacher_b = User.objects.create_user(
            username=f"teb_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        self.principal = User.objects.create_user(
            username=f"pri_{uid}",
            password="pass-test",
            role=User.Role.PRINCIPAL,
            is_staff=True,
        )
        for u in (self.teacher_a, self.teacher_b, self.principal):
            SchoolMembership.objects.get_or_create(
                user=u,
                school=self.school_a,
                defaults={"role": u.role, "is_primary": True},
            )

        year = AcademicYear.objects.create(
            name="Y",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school_a,
        )
        dept = Department.objects.create(
            name="Core",
            code=f"C{uid}",
            school=self.school_a,
        )
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="F1",
            code=f"F{uid}",
            school=self.school_a,
        )
        self.student = StudentProfile.objects.create(
            first_name="Kid",
            last_name="One",
            date_of_birth="2012-03-03",
            student_code=f"K{uid}",
            school=self.school_a,
            classroom=self.classroom,
        )

    def test_queue_sections_show_distinct_states(self):
        enqueue_offline_action(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-08-01",
                "status": Attendance.Status.PRESENT,
            },
            idempotency_key=f"qd-q-{uuid.uuid4().hex[:8]}",
        )
        OfflineAction.objects.create(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={"x": 1},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
        )
        OfflineAction.objects.create(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={"body": "note"},
            status=OfflineAction.Status.CONFLICT,
            retry_count=0,
            conflict_reason="stub conflict",
        )
        OfflineAction.objects.create(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.PAYMENT_RECEIPT,
            payload={"invoice_id": 1},
            status=OfflineAction.Status.SYNCED,
            retry_count=0,
        )
        url = reverse("portal:offline_sync_queue")
        self.client.force_login(self.principal)
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Queued", body)
        self.assertIn("Failed", body)
        self.assertIn("Conflicts", body)
        self.assertIn("Recently synced", body)
        self.assertIn(self.teacher_a.username, body)

    def test_teacher_sees_only_own_rows_not_other_submitters(self):
        marker_a = f"MARK-A-{uuid.uuid4().hex[:8]}"
        marker_b = f"MARK-B-{uuid.uuid4().hex[:8]}"
        OfflineAction.objects.create(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
            conflict_reason=marker_a,
        )
        OfflineAction.objects.create(
            user_id=self.teacher_b.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
            conflict_reason=marker_b,
        )
        url = reverse("portal:offline_sync_queue")
        self.client.force_login(self.teacher_a)
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, marker_a)
        self.assertNotContains(resp, marker_b)

    def test_cross_tenant_host_does_not_surface_other_school_actions(self):
        tenant_marker = f"TENANT-A-{uuid.uuid4().hex[:10]}"
        action = OfflineAction.objects.create(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
            conflict_reason=tenant_marker,
        )
        url = reverse("portal:offline_sync_queue")
        self.client.force_login(self.teacher_a)
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school_b))
        # Tenant-host isolation rejects the session before a cross-school page can
        # render.  The former 200 expectation pre-dated the host-membership gate.
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp["Location"],
            build_public_site_url(reverse("accounts:login")),
        )
        self.assertNotIn(tenant_marker, resp.content.decode())
        # Bare str(pk) is unsafe (e.g. "1" appears in unrelated HTML); assert row hook absent.
        self.assertNotIn(f'data-rmc-offline-row="{action.pk}"', resp.content.decode())

    def test_operator_can_resolve_other_users_conflict(self):
        Attendance.objects.create(
            school_id=self.school_a.pk,
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-09-01",
            status=Attendance.Status.ABSENT,
        )
        action = enqueue_offline_action(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-09-01",
                "status": Attendance.Status.PRESENT,
            },
        )
        process_offline_queue(school_id=self.school_a.pk, user_id=self.teacher_a.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.CONFLICT)

        conflicts_url = reverse("portal:offline_sync_conflicts")
        self.client.force_login(self.principal)
        page = self.client.get(conflicts_url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Keep mine")
        self.assertContains(page, "Server")
        self.assertContains(page, "Local / offline snapshot")

        post = self.client.post(
            conflicts_url,
            {"action_id": str(action.pk), "resolution": "keep_mine"},
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(post.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        audits = (action.sync_metadata or {}).get("resolution_audits") or []
        self.assertTrue(audits)
        self.assertEqual(audits[-1].get("original_submitter_user_id"), self.teacher_a.pk)
        self.assertEqual(audits[-1].get("resolver_user_id"), self.principal.pk)

        cleared = self.client.get(conflicts_url, HTTP_HOST=_tenant_host(self.school_a))
        self.assertEqual(cleared.status_code, 200)
        self.assertContains(cleared, "No sync conflicts")

    def test_retry_failed_post_requeues_for_teacher(self):
        failed = OfflineAction.objects.create(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.GRADING,
            payload={},
            status=OfflineAction.Status.FAILED,
            retry_count=0,
        )
        queue_url = reverse("portal:offline_sync_queue")
        self.client.force_login(self.teacher_a)
        resp = self.client.post(
            queue_url,
            {"action": "retry_failed"},
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(resp.status_code, 200)
        failed.refresh_from_db()
        self.assertEqual(failed.status, OfflineAction.Status.QUEUED)
        self.assertEqual(failed.retry_count, 1)

    def test_process_queue_post_invokes_processor(self):
        enqueue_offline_action(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.NOTES_REPORT,
            payload={
                "body": "queued via dashboard test",
                "title": "t",
                "student_id": self.student.pk,
            },
            idempotency_key=f"qd-proc-{uuid.uuid4().hex[:8]}",
        )
        queue_url = reverse("portal:offline_sync_queue")
        self.client.force_login(self.teacher_a)
        resp = self.client.post(
            queue_url,
            {"action": "process_queue"},
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Processed")

    def test_review_manual_records_audit_conflict_stays_open(self):
        Attendance.objects.create(
            school_id=self.school_a.pk,
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-09-05",
            status=Attendance.Status.ABSENT,
        )
        action = enqueue_offline_action(
            user_id=self.teacher_a.pk,
            school_id=self.school_a.pk,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={
                "student_id": self.student.pk,
                "classroom_id": self.classroom.pk,
                "date": "2025-09-05",
                "status": Attendance.Status.PRESENT,
            },
        )
        process_offline_queue(school_id=self.school_a.pk, user_id=self.teacher_a.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.CONFLICT)

        conflicts_url = reverse("portal:offline_sync_conflicts")
        self.client.force_login(self.teacher_a)
        post = self.client.post(
            conflicts_url,
            {"action_id": str(action.pk), "resolution": "review_manual"},
            HTTP_HOST=_tenant_host(self.school_a),
        )
        self.assertEqual(post.status_code, 302)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.CONFLICT)
        audits = (action.sync_metadata or {}).get("resolution_audits") or []
        self.assertTrue(audits)
        self.assertEqual(audits[-1].get("choice"), OfflineAction.Resolution.REVIEW_MANUAL)
