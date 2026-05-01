"""
Governed query layer: tenant isolation, permissions, ORM-only / no-SQL responses.
"""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import Permission
from apps.analytics.governed_query.executor import GovernedQueryError, execute_governed_query
from apps.analytics.insight_registry import SURFACE_REVENUE, filter_insights_by_surface
from apps.analytics.models import GovernedSavedReport
from apps.analytics.views_governed import (
    governed_query_export_csv,
    governed_query_export_json,
    governed_query_preview,
    governed_saved_report_run,
)
from apps.people.models import StudentProfile
from apps.schools.models import School

User = get_user_model()


class GovernedQueryLayerTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Gov A",
            slug="gov-a",
            subdomain="gov-a",
            is_active=True,
            settings={},
        )
        cls.school_b = School.objects.create(
            name="Gov B",
            slug="gov-b",
            subdomain="gov-b",
            is_active=True,
            settings={},
        )
        cls.code_a = "gov-" + uuid.uuid4().hex[:10]
        cls.code_b = "gov-" + uuid.uuid4().hex[:10]
        StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Ann",
            last_name="A",
            student_code=cls.code_a,
            is_active=True,
        )
        StudentProfile.objects.create(
            school=cls.school_b,
            first_name="Bob",
            last_name="B",
            student_code=cls.code_b,
            is_active=True,
        )
        cls.perm_reports, _ = Permission.objects.get_or_create(
            code="reports.manage",
            defaults={"name": "Reports manage"},
        )

    def _user_with_reports(self):
        u = User.objects.create_user(
            username="rep_" + uuid.uuid4().hex[:8],
            email=f"rep_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
        )
        u.feature_permissions.add(self.perm_reports)
        return u

    def _user_without_reports(self):
        # Default role PARENT maps to AccessRole PARENT which includes reports.manage (accounts signals).
        # EMPLOYER has no ROLE_TEMPLATES entry — no AccessRole is applied; truly lacks report perms.
        return User.objects.create_user(
            username="nor_" + uuid.uuid4().hex[:8],
            email=f"nor_{uuid.uuid4().hex[:8]}@example.com",
            password="testpass123",
            role=User.Role.EMPLOYER,
        )

    def test_tenant_isolation_students(self):
        user = self._user_with_reports()
        rows, _meta = execute_governed_query(
            user=user,
            school_id=str(self.school_a.pk),
            dataset_id="students",
            fields=["student_code"],
            limit=50,
        )
        codes = {r["student_code"] for r in rows}
        self.assertIn(self.code_a, codes)
        self.assertNotIn(self.code_b, codes)

    def test_permission_denied_without_feature(self):
        user = self._user_without_reports()
        with self.assertRaises(GovernedQueryError) as ctx:
            execute_governed_query(
                user=user,
                school_id=str(self.school_a.pk),
                dataset_id="students",
                fields=["id"],
            )
        self.assertIn("permission", str(ctx.exception).lower())

    def test_disallowed_field_rejected(self):
        user = self._user_with_reports()
        with self.assertRaises(GovernedQueryError):
            execute_governed_query(
                user=user,
                school_id=str(self.school_a.pk),
                dataset_id="students",
                fields=["malicious_field_xyz"],
            )

    def test_aggregation_count_group_by(self):
        user = self._user_with_reports()
        rows, meta = execute_governed_query(
            user=user,
            school_id=str(self.school_a.pk),
            dataset_id="students",
            fields=["id"],
            group_by=["is_active"],
            aggregate={"fn": "count", "field": "id"},
            limit=20,
        )
        self.assertTrue(meta.get("aggregated"))
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(any("count_id" in r for r in rows))

    def test_preview_json_has_no_sql_leakage(self):
        factory = RequestFactory()
        user = self._user_with_reports()
        body = {
            "dataset_id": "students",
            "fields": ["student_code"],
            "limit": 10,
        }
        request = factory.post(
            "/analytics/governed/query/preview/",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_query_preview(request)
        payload = json.loads(response.content.decode("utf-8"))
        text = json.dumps(payload).lower()
        self.assertNotIn("select ", text)
        self.assertNotIn(" from ", text)
        self.assertNotIn("raw_sql", text)
        self.assertIn("rows", payload)

    def test_export_csv_permissions_and_shape(self):
        factory = RequestFactory()
        user = self._user_with_reports()
        body = {
            "dataset_id": "students",
            "fields": ["student_code"],
            "limit": 10,
        }
        request = factory.post(
            "/analytics/governed/export.csv",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_query_export_csv(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        content = response.content.decode("utf-8")
        self.assertIn("student_code", content.lower())

    def test_repeatable_governed_execution_stable_shape(self):
        user = self._user_with_reports()
        kwargs = {
            "user": user,
            "school_id": str(self.school_a.pk),
            "dataset_id": "students",
            "fields": ["student_code"],
            "limit": 5,
        }
        r1, _ = execute_governed_query(**kwargs)
        r2, _ = execute_governed_query(**kwargs)
        self.assertEqual(len(r1), len(r2))

    def test_saved_report_run_executes(self):
        user = self._user_with_reports()
        rep = GovernedSavedReport.objects.create(
            school=self.school_a,
            created_by=user,
            name="Unit test report",
            definition={
                "dataset_id": "students",
                "fields": ["student_code"],
                "limit": 20,
            },
        )
        factory = RequestFactory()
        request = factory.post(
            f"/analytics/governed/saved/{rep.pk}/run/",
            data=b"{}",
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_saved_report_run(request, rep.pk)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertIn("rows", payload)
        self.assertEqual(payload.get("saved_report_id"), rep.pk)

    def test_saved_report_cross_tenant_blocked(self):
        user = self._user_with_reports()
        rep = GovernedSavedReport.objects.create(
            school=self.school_b,
            created_by=user,
            name="Other tenant report",
            definition={
                "dataset_id": "students",
                "fields": ["student_code"],
                "limit": 5,
            },
        )
        factory = RequestFactory()
        request = factory.post(
            f"/analytics/governed/saved/{rep.pk}/run/",
            data=b"{}",
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_saved_report_run(request, rep.pk)
        self.assertEqual(response.status_code, 404)

    def test_export_json_returns_rows(self):
        factory = RequestFactory()
        user = self._user_with_reports()
        body = {
            "dataset_id": "students",
            "fields": ["student_code"],
            "limit": 10,
        }
        request = factory.post(
            "/analytics/governed/export.json",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = user
        request.school = self.school_a
        response = governed_query_export_json(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertIn("rows", payload)

    def test_insight_surface_filter(self):
        insights = [
            {"id": "a", "surfaces": [SURFACE_REVENUE]},
            {"id": "b", "surfaces": ["school_health"]},
        ]
        got = filter_insights_by_surface(insights, SURFACE_REVENUE)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["id"], "a")
