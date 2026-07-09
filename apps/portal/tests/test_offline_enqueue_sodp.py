"""SODP security invariants for api_offline_enqueue."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.platform_runtime.offline_action_types import OfflineActionType
from apps.portal.views_offline_sync import api_offline_enqueue
from apps.schools.models import School, SchoolMembership


class OfflineEnqueueSodpTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name=f"SODP {uid}",
            slug=f"sodp-{uid}",
            subdomain=f"sodp{uid}",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username=f"sodp_t_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.get_or_create(
            user=self.teacher,
            school=self.school,
            defaults={"role": self.teacher.role, "is_primary": True},
        )
        self.second_teacher = User.objects.create_user(
            username=f"sodp_t2_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.get_or_create(
            user=self.second_teacher,
            school=self.school,
            defaults={"role": self.second_teacher.role, "is_primary": False},
        )

    def _post(self, payload: dict, *, user=None, school=None):
        request = self.factory.post(
            "/portal/api/offline/enqueue/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = user if user is not None else self.teacher
        request.school = school if school is not None else self.school
        return api_offline_enqueue(request)

    def test_rejects_body_tenant_id(self):
        resp = self._post(
            {
                "action_type": OfflineActionType.ATTENDANCE_MARK,
                "payload": {},
                "tenant_id": 99,
            }
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content).get("error"), "tenant_from_session_only")

    def test_rejects_body_school_id(self):
        resp = self._post(
            {
                "action_type": OfflineActionType.ATTENDANCE_MARK,
                "payload": {},
                "school_id": str(self.school.pk),
            }
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content).get("error"), "tenant_from_session_only")

    def test_rejects_unauthenticated(self):
        resp = self._post(
            {"action_type": OfflineActionType.ATTENDANCE_MARK, "payload": {}},
            user=AnonymousUser(),
        )
        self.assertEqual(resp.status_code, 302)

    def test_accepts_attendance_mark_without_tenant_in_body(self):
        resp = self._post(
            {
                "action_type": OfflineActionType.ATTENDANCE_MARK,
                "payload": {
                    "student_id": 1,
                    "classroom_id": 1,
                    "date": "2026-05-23",
                    "status": "present",
                },
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content).get("ok"))

    def test_accepts_provision_signup(self):
        resp = self._post(
            {
                "action_type": OfflineActionType.PROVISIONAL_SIGNUP,
                "payload": {"device_id": "field-tablet-abc12345"},
                "idempotency_key": "provision-field-tablet-abc12345",
            }
        )
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body.get("ok"))

    def test_duplicate_idempotency_returns_existing_school_row(self):
        payload = {
            "action_type": OfflineActionType.PROVISIONAL_SIGNUP,
            "payload": {"device_id": "field-tablet-shared"},
            "idempotency_key": "provision-field-tablet-shared",
        }
        first = self._post(payload, user=self.teacher)
        second = self._post(payload, user=self.second_teacher)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_body = json.loads(first.content)
        second_body = json.loads(second.content)
        self.assertTrue(first_body.get("ok"))
        self.assertTrue(second_body.get("ok"))
        self.assertEqual(first_body.get("id"), second_body.get("id"))
