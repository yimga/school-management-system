"""POST /api/v1/runtime/structural-options/initialize."""

from __future__ import annotations

import json
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.academics.academic_structure import AcademicStructureNode
from apps.academics.models import AcademicYear
from apps.api.runtime_endpoints import structural_options_initialize_runtime
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class StructuralOptionsInitializeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Init Structure School",
            slug="init-structure-school",
            subdomain="init-structure-school",
            country_code="CM",
            is_active=True,
            settings={"school_type": "primaire"},
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="structure_init_admin",
            password="unused",
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )

    def _post(self, body=None):
        request = self.factory.post(
            "/api/v1/runtime/structural-options/initialize",
            data=json.dumps(body or {}),
            content_type="application/json",
        )
        request.user = self.user
        request.school = self.school
        request.session = {"school_id": str(self.school.id)}
        with mock.patch(
            "apps.schools.tenant_switch_security.user_may_access_school_api",
            return_value=True,
        ):
            return structural_options_initialize_runtime(request)

    def test_initialize_creates_structure_nodes(self):
        response = self._post({"school_type_codes": ["primaire"]})
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload.get("status"), "ok")
        self.assertGreaterEqual(
            payload.get("structure", {}).get("created_nodes", 0), 1
        )
        self.assertTrue(
            AcademicStructureNode.objects.filter(school=self.school).exists()
        )

    def test_initialize_requires_auth(self):
        request = self.factory.post("/api/v1/runtime/structural-options/initialize")
        request.user = mock.Mock(is_authenticated=False)
        request.school = self.school
        response = structural_options_initialize_runtime(request)
        self.assertEqual(response.status_code, 401)
