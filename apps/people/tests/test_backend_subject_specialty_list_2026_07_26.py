"""Tenant browse lists for Subjects + Specialties (Migration Cloud import->visible).

Imported courses/specialties land school-scoped but had no browsable page — you
could not "visit Subjects and see them." These read-only backend lists close
that. The tests drive the views on the CSV-export path (no template render, so
no middleware/context-processor coupling) to lock the three things that matter:

  * permission-gated (a member without ``academics.view_*`` is denied),
  * school-scoped (only the acting school's rows — never another tenant's),
  * the imported rows are actually returned (visible).

Full-page HTML render validity is covered separately by verify_template_compiles.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from apps.academics.models import Department, Specialty, Subject
from apps.people.views_backend import backend_specialty_list, backend_subject_list
from apps.schools.models import School

User = get_user_model()


class BackendSubjectSpecialtyListTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Browse School", slug="browse-school", subdomain="browse-school",
            is_active=True, country_code="CM",
        )
        self.other = School.objects.create(
            name="Other School", slug="other-school", subdomain="other-school",
            is_active=True, country_code="CM",
        )
        self.admin = User.objects.create_superuser(
            username="browse-admin", email="browse-admin@example.com", password="x"
        )
        self.member = User.objects.create_user(
            username="browse-member", email="browse-member@example.com", password="x"
        )

    def _csv(self, view, user):
        req = self.rf.get("/backend/list/?format=csv")
        req.user = user
        req.school = self.school
        return view(req)

    # --- Subjects ---------------------------------------------------------
    def test_subject_list_returns_imported_subjects_scoped_to_school(self):
        Subject.objects.create(school=self.school, name="Mathematics")
        Subject.objects.create(school=self.school, name="English")
        Subject.objects.create(school=self.other, name="SecretOtherSubject")
        resp = self._csv(backend_subject_list, self.admin)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = resp.content.decode()
        self.assertIn("Mathematics", body)
        self.assertIn("English", body)
        self.assertNotIn("SecretOtherSubject", body)  # tenant isolation

    def test_subject_list_denies_member_without_permission(self):
        with self.assertRaises(PermissionDenied):
            self._csv(backend_subject_list, self.member)

    # --- Specialties ------------------------------------------------------
    def test_specialty_list_returns_imported_specialties_scoped_to_school(self):
        dept = Department.objects.create(
            school=self.school, name="Science", code="DPT-SCI-T"
        )
        other_dept = Department.objects.create(
            school=self.other, name="Arts", code="DPT-ART-T"
        )
        Specialty.objects.create(
            school=self.school, department=dept, name="Pure Sciences", code="SPC-PS-T"
        )
        Specialty.objects.create(
            school=self.other, department=other_dept, name="SecretOtherStream", code="SPC-X-T"
        )
        resp = self._csv(backend_specialty_list, self.admin)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Pure Sciences", body)
        self.assertNotIn("SecretOtherStream", body)  # tenant isolation

    def test_specialty_list_denies_member_without_permission(self):
        with self.assertRaises(PermissionDenied):
            self._csv(backend_specialty_list, self.member)
