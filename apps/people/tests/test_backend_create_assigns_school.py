"""A backend-created student/teacher must belong to the creating school.

``backend_student_create`` did ``form.save(commit=False)``, set ``created_by``
and ``is_active``, and saved. ``StudentCreateForm.Meta.fields`` has no ``school``
and ``StudentProfile.school`` is ``null=True``, so the row landed with
``school_id = NULL`` — orphaned from every school-scoped surface. The sibling
``backend_applicant_create`` sets ``applicant.school = school`` and the offline
applier sets ``student.school_id``; these two views were the odd ones out.
``backend_teacher_create`` had the identical omission.

The visible damage: the row shows up in the (unfiltered) list but
``backend_student_detail`` filters ``school_id=school.id`` and 404s on it, the
status strip counts it as nothing, ``bulk_set_student_status`` reports "Student
not found.", the per-school partial unique constraints on ``student_code`` /
``admission_number`` do not apply to a NULL-school row, and both
``roster_webhook_on_student_save`` and ``dispatch_student_automation_workflows``
return early on ``if not school``.
"""

from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class _BackendCreateMixin:
    def setUp(self):
        self.school = School.objects.create(
            name="Backend Create High",
            slug="bkc-high",
            subdomain="bkc-high",
        )
        self.admin = User.objects.create_superuser(
            username="bkc_admin", email="bkc_admin@example.com", password="pw"
        )
        self.factory = RequestFactory()

    def _post(self, view, path, data):
        req = self.factory.post(path, data)
        req.user = self.admin
        # Tenant middleware is what normally stamps this; RequestFactory skips
        # the middleware chain, so set it here or resolve_request_school falls
        # through to the membership lookup and returns None — which would make
        # every assertion below pass for the wrong reason.
        req.school = self.school
        req.session = SessionStore()
        setattr(req, "_messages", FallbackStorage(req))
        return view(req)


class BackendStudentCreateAssignsSchoolTests(_BackendCreateMixin, TestCase):
    def test_created_student_is_owned_by_the_request_school(self):
        from apps.people.views_backend import backend_student_create

        resp = self._post(
            backend_student_create,
            "/backend/students/create/",
            {"first_name": "Ada", "last_name": "Nkemi", "status": "NEW"},
        )

        # Anti-vacuous: the POST really got past the form and wrote a row. A
        # rejected form re-renders 200 and creates nothing, which would leave
        # the school assertion untested.
        self.assertEqual(resp.status_code, 302, msg=getattr(resp, "content", b"")[:400])
        student = StudentProfile.objects.get(first_name="Ada", last_name="Nkemi")
        self.assertEqual(student.school_id, self.school.id)

    def test_the_new_student_is_reachable_from_the_school_scoped_detail_view(self):
        from apps.people.views_backend import (
            backend_student_create,
            backend_student_detail,
        )

        self._post(
            backend_student_create,
            "/backend/students/create/",
            {"first_name": "Ada", "last_name": "Nkemi", "status": "NEW"},
        )
        student = StudentProfile.objects.get(first_name="Ada", last_name="Nkemi")

        req = self.factory.get(f"/backend/students/{student.pk}/")
        req.user = self.admin
        req.school = self.school
        req.session = SessionStore()
        setattr(req, "_messages", FallbackStorage(req))
        resp = backend_student_detail(req, student.pk)

        # Http404 here is the bug's headline symptom: listed but un-openable.
        self.assertEqual(resp.status_code, 200)


class BackendTeacherCreateAssignsSchoolTests(_BackendCreateMixin, TestCase):
    def test_created_teacher_is_owned_by_the_request_school(self):
        from apps.people.views_backend import backend_teacher_create

        resp = self._post(
            backend_teacher_create,
            "/backend/teachers/create/",
            {
                "email": "teacher@bkc.example.com",
                "password": "Temp12345!",
                "staff_id": "BKC-T1",
                "position_title": "Mathematics Teacher",
            },
        )

        self.assertEqual(resp.status_code, 302, msg=getattr(resp, "content", b"")[:400])
        teacher = TeacherProfile.objects.get(staff_id="BKC-T1")
        self.assertEqual(teacher.school_id, self.school.id)
