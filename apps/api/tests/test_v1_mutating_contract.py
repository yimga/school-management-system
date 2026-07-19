"""#20 API Quality — Wave 16 mutating response-shape contracts.

Locks stable top-level keys on high-traffic authenticated write paths so
integrators do not silently break. Additive keys are allowed; required keys
must not disappear.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Term
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.schools.session_school_bind import sign_session_school_bind


def _tenant_django_client(school: School, user) -> Client:
    client = Client(HTTP_HOST=f"{school.subdomain}.runmycampus.com")
    client.force_login(user)
    sign_session_school_bind(
        client.session, school_id=str(school.pk), user_id=user.pk
    )
    client.session.save()
    return client


def _tenant_api_client(school: School, user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    api.defaults["HTTP_HOST"] = f"{school.subdomain}.runmycampus.com"
    # Bind session school the same way browser/session clients do.
    session = api.session
    sign_session_school_bind(session, school_id=str(school.pk), user_id=user.pk)
    session.save()
    return api


class V1MutatingContractTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Contract School {uid}",
            slug=f"contract-{uid}",
            subdomain=f"c{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"contract_admin_{uid}",
            email=f"contract_{uid}@example.com",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="FIRST",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(
            school=self.school, name="General", code=f"GEN-{uid}"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 1A",
            code=f"F1A-{uid}",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Lovelace",
            student_code=f"STU-{uid}",
            academic_year=self.year,
            classroom=self.classroom,
            is_active=True,
        )

    def test_me_switch_school_success_keys(self):
        client = _tenant_django_client(self.school, self.admin)
        url = reverse("api_v1:me-switch-school")
        resp = client.post(
            url,
            data=json.dumps({"school_id": str(self.school.pk)}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        for key in ("ok", "school_id", "redirect_url"):
            self.assertIn(key, body, msg=f"switch-school dropped key {key!r}")
        self.assertIs(body["ok"], True)
        self.assertEqual(body["school_id"], str(self.school.pk))
        self.assertIsInstance(body["redirect_url"], str)

    def test_attendance_bulk_update_success_keys(self):
        client = _tenant_django_client(self.school, self.admin)
        url = reverse("api_v1:attendance-bulk-update")
        today = date.today().isoformat()
        resp = client.patch(
            url,
            data=json.dumps(
                {
                    "records": [
                        {
                            "student": self.student.pk,
                            "classroom": self.classroom.pk,
                            "date": today,
                            "status": "present",
                        }
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        for key in ("ok", "updated"):
            self.assertIn(key, body, msg=f"attendance bulk-update dropped key {key!r}")
        self.assertIs(body["ok"], True)
        self.assertIsInstance(body["updated"], int)
        self.assertGreaterEqual(body["updated"], 1)

    def test_students_create_success_keys(self):
        api = _tenant_api_client(self.school, self.admin)
        url = reverse("api_v1:students-list")
        resp = api.post(
            url,
            {
                "first_name": "Grace",
                "last_name": "Hopper",
                "academic_year": self.year.pk,
                "classroom": self.classroom.pk,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        for key in ("id", "first_name", "last_name", "student_code", "is_active"):
            self.assertIn(key, body, msg=f"students create dropped key {key!r}")
        self.assertEqual(body["first_name"], "Grace")
        self.assertEqual(body["last_name"], "Hopper")

    def test_wallet_top_up_success_keys(self):
        """Re-assert the existing wallet top-up contract from the mutating suite."""
        client = _tenant_django_client(self.school, self.admin)
        url = reverse("api_v1:finance-wallet-top-up")
        resp = client.post(
            url,
            data=json.dumps({"amount": "10.00", "reference": "mutating-contract"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        for key in (
            "ok",
            "wallet_balance",
            "currency_code",
            "transaction_id",
            "reference",
        ):
            self.assertIn(key, body, msg=f"wallet top-up dropped key {key!r}")
        self.assertIs(body["ok"], True)
