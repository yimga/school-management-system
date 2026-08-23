"""A classroom write must not point at another tenant's academic year or department.

``ClassroomViewSet.get_queryset`` scopes the ROW being written to
``request.school``. Nothing scoped the rows it points AT: ``academic_year`` and
``department`` are plain pks on the wire, and a ModelSerializer's default related
queryset is the whole table.

The admin-only write gate (test_entity_write_gates_2026_08_22) narrows WHO can
reach this; it does not stop the write itself from crossing tenants, and the
resulting classroom then renders another school's term dates and department name
on this school's roster and timetable.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.schools.models import School


class ClassroomForeignKeysAreTenantScopedTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        today = timezone.now().date()
        self.school = School.objects.create(
            name="FK Home",
            slug=f"fkh-{tag}",
            subdomain=f"fkh-{tag}",
            is_active=True,
        )
        self.other = School.objects.create(
            name="FK Away",
            slug=f"fka-{tag}",
            subdomain=f"fka-{tag}",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"AY-{tag}",
            start_date=today,
            end_date=today.replace(year=today.year + 1),
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other,
            name=f"AY-other-{tag}",
            start_date=today,
            end_date=today.replace(year=today.year + 1),
        )
        self.department = Department.objects.create(
            school=self.school, name=f"Dept {tag}"
        )
        self.other_department = Department.objects.create(
            school=self.other, name=f"Dept other {tag}"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Form 1A",
            code=f"F1A-{tag}",
        )
        self.admin = User.objects.create_user(
            username=f"adm_{tag}", password="pass", role=User.Role.ADMIN, is_staff=True
        )
        self.client = APIClient(HTTP_HOST=f"{self.school.subdomain}.runmycampus.com")
        self.client.force_authenticate(user=self.admin)
        session = self.client.session
        session["school_id"] = str(self.school.pk)
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def _patch(self, payload):
        return self.client.patch(
            f"/api/entities/classrooms/{self.classroom.pk}/", payload, format="json"
        )

    def test_an_admin_can_still_repoint_within_their_own_school(self):
        """Guard: without this, a 400 on everything would look like a passing fix.

        This proves the request reaches the serializer and a same-tenant FK is
        accepted, so the refusals below are about the tenant, not about the route,
        the gate, or a broken payload.
        """
        resp = self._patch({"academic_year": self.year.pk, "name": "Form 1 Alpha"})
        self.assertEqual(resp.status_code, 200, resp.content[:400])
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, "Form 1 Alpha")

    def test_another_schools_academic_year_is_refused(self):
        resp = self._patch({"academic_year": self.other_year.pk})
        self.assertEqual(resp.status_code, 400, resp.content[:400])
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.academic_year_id, self.year.pk)

    def test_another_schools_department_is_refused(self):
        resp = self._patch({"department": self.other_department.pk})
        self.assertEqual(resp.status_code, 400, resp.content[:400])
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.department_id, self.department.pk)
