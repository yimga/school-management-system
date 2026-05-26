"""IAM intents may use the unified portal offline enqueue API (batch 1509)."""

from __future__ import annotations

import json
import uuid

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.models_rebac import OfflineAccessIntent
from apps.portal.views_offline_sync import api_offline_enqueue
from apps.schools.models import School, SchoolMembership


class OfflineEnqueueIamUnifiedTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"IAM {uid}",
            slug=f"iam-{uid}",
            subdomain=f"iam{uid}",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=f"iam_u_{uid}",
            password="pw",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.get_or_create(
            user=self.user,
            school=self.school,
            defaults={"role": self.user.role, "is_primary": True},
        )
        self.factory = RequestFactory()

    def test_iam_request_access_via_enqueue(self):
        payload = {
            "action_type": "iam.request_access",
            "payload": {
                "permission_code": "grade.submit",
                "reason": "offline capture test",
            },
            "idempotency_key": f"iam-{uuid.uuid4().hex[:12]}",
        }
        request = self.factory.post(
            "/portal/api/offline/enqueue/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        resp = api_offline_enqueue(request)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("applied_via"), "iam_intent")
        intent = OfflineAccessIntent.objects.filter(
            school=self.school,
            user=self.user,
        ).first()
        self.assertIsNotNone(intent)
