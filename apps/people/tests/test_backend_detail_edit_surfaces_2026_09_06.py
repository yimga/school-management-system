"""Guardian / Subject / Specialty rows must open a record you can correct.

All three entities had a create surface and a list surface and nothing else:
their list ``<tbody>`` contained zero hrefs, so a row created with the wrong
name, code, phone or finance access could be *seen* forever and never *opened*.
Django Admin was the only fix, and a school admin does not reach it.

These tests fail on the shape of that gap rather than on its symptoms:

  * the rendered list page must contain a link to each row's detail page --
    asserted against the real template output, not the view's context, because
    the context was always fine; it was the ``<td>`` that had no ``<a>``;
  * the detail page must GET 200 with the record's own values in the HTML;
  * a POST must CHANGE THE ROW IN THE DATABASE -- re-read after the response,
    because a detail view that renders a bound form and quietly re-displays it
    also returns 200 and saves nothing;
  * another school's row must 404 (a detail view keyed on a pk alone is a
    tenant-isolation defect); and
  * a member without ``change_<model>`` must be denied.

Each render assertion is paired with an anti-vacuity check on the record's own
text, so an empty page (or a swallowed exception) cannot pass the href check.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.academics.models import Department, Specialty, Subject
from apps.people.models import StudentGuardian, StudentProfile
from apps.people.views_backend import (
    backend_guardian_detail,
    backend_guardian_list,
    backend_specialty_detail,
    backend_specialty_list,
    backend_subject_detail,
    backend_subject_list,
)
from apps.schools.models import School

User = get_user_model()


class _BackendRecordMixin:
    """Two schools, an admin and a permissionless member, plus request plumbing."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Record Surface High",
            slug="record-surface-high",
            subdomain="record-surface-high",
            is_active=True,
            country_code="CM",
        )
        self.other = School.objects.create(
            name="Foreign Tenant High",
            slug="foreign-tenant-high",
            subdomain="foreign-tenant-high",
            is_active=True,
            country_code="CM",
        )
        self.admin = User.objects.create_superuser(
            username="rec_admin", email="rec_admin@example.com", password="pw"
        )
        self.member = User.objects.create_user(
            username="rec_member", email="rec_member@example.com", password="pw"
        )

    def _prep(self, req, user=None):
        req.user = user or self.admin
        # Tenant middleware is what normally stamps this; RequestFactory skips
        # the middleware chain, so without it every view here would bounce to
        # the dashboard and the assertions would pass for the wrong reason.
        req.school = self.school
        req.session = SessionStore()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def _get(self, view, path, user=None, **kwargs):
        return view(self._prep(self.factory.get(path), user=user), **kwargs)

    def _post(self, view, path, data, user=None, **kwargs):
        return view(self._prep(self.factory.post(path, data), user=user), **kwargs)

    def _html(self, response):
        if hasattr(response, "render") and not response.is_rendered:
            response.render()
        return response.content.decode("utf-8", "replace")


class SubjectDetailSurfaceTests(_BackendRecordMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.subject = Subject.objects.create(
            school=self.school, name="Mathematics", code="MTH"
        )

    def test_list_row_links_to_the_subject_detail_page(self):
        response = self._get(backend_subject_list, "/backend/subjects/")
        self.assertEqual(response.status_code, 200)
        html = self._html(response)
        # Anti-vacuity: the row is on the page at all.
        self.assertIn("Mathematics", html)
        self.assertIn(
            reverse("accounts:backend_subject_detail", args=[self.subject.pk]), html
        )

    def test_detail_get_renders_the_record(self):
        url = reverse("accounts:backend_subject_detail", args=[self.subject.pk])
        response = self._get(backend_subject_detail, url, subject_id=self.subject.pk)
        self.assertEqual(response.status_code, 200)
        html = self._html(response)
        self.assertIn("Mathematics", html)
        self.assertIn("MTH", html)

    def test_detail_post_persists_the_edit(self):
        url = reverse("accounts:backend_subject_detail", args=[self.subject.pk])
        response = self._post(
            backend_subject_detail,
            url,
            {
                "name": "Further Mathematics",
                "code": "FMTH",
                "category": Subject.Category.GENERAL,
                "credits": "4.00",
            },
            subject_id=self.subject.pk,
        )
        self.assertEqual(
            response.status_code, 302, msg=self._html(response)[-2000:]
        )
        fresh = Subject.objects.get(pk=self.subject.pk)
        self.assertEqual(fresh.name, "Further Mathematics")
        self.assertEqual(fresh.code, "FMTH")
        self.assertEqual(fresh.school_id, self.school.id)

    def test_detail_refuses_another_schools_subject(self):
        foreign = Subject.objects.create(school=self.other, name="Foreign Subject")
        url = f"/backend/subjects/{foreign.pk}/"
        with self.assertRaises(Http404):
            self._get(backend_subject_detail, url, subject_id=foreign.pk)

    def test_detail_denies_a_member_without_change_permission(self):
        url = reverse("accounts:backend_subject_detail", args=[self.subject.pk])
        with self.assertRaises(PermissionDenied):
            self._get(
                backend_subject_detail,
                url,
                user=self.member,
                subject_id=self.subject.pk,
            )


class SpecialtyDetailSurfaceTests(_BackendRecordMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.department = Department.objects.create(
            school=self.school, name="Sciences", code="DPT-SCI-R"
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.department,
            name="Pure Sciences",
            code="SPC-PS-R",
        )

    def test_list_row_links_to_the_specialty_detail_page(self):
        response = self._get(backend_specialty_list, "/backend/specialties/")
        self.assertEqual(response.status_code, 200)
        html = self._html(response)
        self.assertIn("Pure Sciences", html)
        self.assertIn(
            reverse("accounts:backend_specialty_detail", args=[self.specialty.pk]), html
        )

    def test_detail_get_renders_the_record(self):
        url = reverse("accounts:backend_specialty_detail", args=[self.specialty.pk])
        response = self._get(
            backend_specialty_detail, url, specialty_id=self.specialty.pk
        )
        self.assertEqual(response.status_code, 200)
        html = self._html(response)
        self.assertIn("Pure Sciences", html)
        self.assertIn("SPC-PS-R", html)

    def test_detail_post_persists_the_edit(self):
        url = reverse("accounts:backend_specialty_detail", args=[self.specialty.pk])
        response = self._post(
            backend_specialty_detail,
            url,
            {
                "name": "Pure Sciences (Upper)",
                "code": "SPC-PSU-R",
                "department": str(self.department.pk),
            },
            specialty_id=self.specialty.pk,
        )
        self.assertEqual(
            response.status_code, 302, msg=self._html(response)[-2000:]
        )
        fresh = Specialty.objects.get(pk=self.specialty.pk)
        self.assertEqual(fresh.name, "Pure Sciences (Upper)")
        self.assertEqual(fresh.code, "SPC-PSU-R")
        self.assertEqual(fresh.school_id, self.school.id)

    def test_detail_refuses_another_schools_specialty(self):
        foreign_dept = Department.objects.create(
            school=self.other, name="Arts", code="DPT-ART-R"
        )
        foreign = Specialty.objects.create(
            school=self.other,
            department=foreign_dept,
            name="Foreign Stream",
            code="SPC-FX-R",
        )
        with self.assertRaises(Http404):
            self._get(
                backend_specialty_detail,
                f"/backend/specialties/{foreign.pk}/",
                specialty_id=foreign.pk,
            )

    def test_detail_denies_a_member_without_change_permission(self):
        url = reverse("accounts:backend_specialty_detail", args=[self.specialty.pk])
        with self.assertRaises(PermissionDenied):
            self._get(
                backend_specialty_detail,
                url,
                user=self.member,
                specialty_id=self.specialty.pk,
            )


class GuardianDetailSurfaceTests(_BackendRecordMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Nkemi"
        )
        self.parent = User.objects.create_user(
            username="rec_parent@example.com",
            email="rec_parent@example.com",
            password="pw",
            first_name="Beatrice",
            last_name="Nkemi",
            role=User.Role.PARENT,
        )
        self.link = StudentGuardian.objects.create(
            student=self.student,
            guardian_user=self.parent,
            email="rec_parent@example.com",
            phone="670000001",
            can_view_finance=False,
        )

    def test_list_row_links_to_the_guardian_detail_page(self):
        response = self._get(backend_guardian_list, "/backend/guardians/")
        self.assertEqual(response.status_code, 200)
        html = self._html(response)
        self.assertIn("Beatrice Nkemi", html)
        self.assertIn(
            reverse("accounts:backend_guardian_detail", args=[self.link.pk]), html
        )

    def test_detail_get_renders_the_record(self):
        url = reverse("accounts:backend_guardian_detail", args=[self.link.pk])
        response = self._get(backend_guardian_detail, url, guardian_id=self.link.pk)
        self.assertEqual(response.status_code, 200)
        html = self._html(response)
        self.assertIn("Beatrice Nkemi", html)
        self.assertIn("670000001", html)

    def test_detail_post_persists_the_edit(self):
        url = reverse("accounts:backend_guardian_detail", args=[self.link.pk])
        response = self._post(
            backend_guardian_detail,
            url,
            {
                "relationship": StudentGuardian.Relationship.MOTHER,
                "phone": "670999888",
                "whatsapp_number": "",
                "address": "Molyko, Buea",
                "preferred_contact": StudentGuardian.PreferredContact.SMS,
                "receives_email": "on",
                "can_view_results": "on",
                "can_view_finance": "on",
            },
            guardian_id=self.link.pk,
        )
        self.assertEqual(
            response.status_code, 302, msg=self._html(response)[-2000:]
        )
        fresh = StudentGuardian.objects.get(pk=self.link.pk)
        self.assertEqual(fresh.phone, "670999888")
        self.assertEqual(fresh.address, "Molyko, Buea")
        self.assertEqual(fresh.relationship, StudentGuardian.Relationship.MOTHER)
        # The access flag is the one an admin most needs to correct after the
        # fact, and it is a checkbox -- an unchecked-to-checked transition is
        # exactly what a form the view never binds would silently drop.
        self.assertTrue(fresh.can_view_finance)
        # Identity is not editable here, so it must survive the edit intact.
        self.assertEqual(fresh.student_id, self.student.pk)
        self.assertEqual(fresh.guardian_user_id, self.parent.pk)

    def test_detail_refuses_another_schools_guardian_link(self):
        foreign_student = StudentProfile.objects.create(
            school=self.other, first_name="Foreign", last_name="Child"
        )
        foreign_parent = User.objects.create_user(
            username="foreign_parent@example.com",
            email="foreign_parent@example.com",
            password="pw",
            role=User.Role.PARENT,
        )
        foreign = StudentGuardian.objects.create(
            student=foreign_student,
            guardian_user=foreign_parent,
            email="foreign_parent@example.com",
        )
        with self.assertRaises(Http404):
            self._get(
                backend_guardian_detail,
                f"/backend/guardians/{foreign.pk}/",
                guardian_id=foreign.pk,
            )

    def test_detail_denies_a_member_without_change_permission(self):
        url = reverse("accounts:backend_guardian_detail", args=[self.link.pk])
        with self.assertRaises(PermissionDenied):
            self._get(
                backend_guardian_detail,
                url,
                user=self.member,
                guardian_id=self.link.pk,
            )
