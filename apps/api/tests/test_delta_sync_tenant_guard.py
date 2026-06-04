"""Delta sync requires resolved tenant context."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.api.sync_delta_api import DeltaSyncAPI
from apps.api.sync_services import apply_changes
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class DeltaSyncTenantGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name=f"Delta {uid}",
            slug=f"delta-{uid}",
            subdomain=f"delta{uid}",
            is_active=True,
        )
        cls.user = User.objects.create_user(
            username=f"delta_user_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=cls.user,
            school=cls.school,
            role="ADMIN",
            is_primary=True,
        )

    @mock.patch("apps.api.sync_delta_api.get_effective_offline_runtime_settings")
    def test_missing_request_school_returns_403(self, mock_offline):
        mock_offline.return_value = {"enable_offline_mode": True}
        rf = RequestFactory()
        request = rf.post(
            "/api/v1/sync/delta/",
            data={"items": []},
            content_type="application/json",
        )
        request.user = self.user
        response = DeltaSyncAPI.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_apply_changes_without_school_id_fail_closed(self):
        out = apply_changes(None, self.user, [{"entity_type": "student", "id": 1, "changes": {}}])
        self.assertEqual(out["success_count"], 0)
        self.assertTrue(all(r["status"] == 403 for r in out["results"]))
