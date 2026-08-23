"""Entity-API writes must be admin-only, on every verb.

Three viewsets in ``apps/api/entity_api.py`` define ``_require_admin`` under a
comment that says "Writes restricted to admin-like users". Only one of the four
write verbs was actually wired to it.

  ClassroomViewSet         defines the helper and NEVER calls it. get_queryset
                           returns every classroom in the school to any
                           authenticated caller (open read, by design), so
                           get_object() resolves any of them -- a parent could
                           PATCH or DELETE a classroom.

  StudentProfileViewSet    guards `update` (and `partial_update`, which
                           delegates to it) and guards its three bulk actions --
                           but has NO `create` and NO `destroy` override, so
                           both ran ungated. get_queryset scopes reads to a
                           teacher's assigned classrooms and a parent's own
                           children, and that scoping is exactly what makes the
                           write reachable: get_object() resolves the row, and
                           DELETE removes the student record. A parent could
                           delete their own child; a teacher, any student in a
                           classroom they teach.

  TeacherProfileViewSet    fixed separately -- see
                           test_teacher_profile_write_is_admin_only_2026_08_22.

These are not hypothetical: `_is_admin_like` is the only thing standing between
an authenticated tenant member and these rows, and it was never consulted.

HTTP_HOST is load-bearing here. request.school is resolved from the subdomain
and every get_queryset returns .none() without it, so a test that omits it 404s
on every route and passes against vulnerable code. The `*_can_still_read_*`
tests are the guard that proves these requests reach the view.
"""

import uuid

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School


class _EntityWriteGateBase(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Gate High",
            slug=f"gate-{tag}",
            subdomain=f"gate-{tag}",
            is_active=True,
        )
        today = timezone.now().date()
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"AY-{tag}",
            start_date=today,
            end_date=today.replace(year=today.year + 1),
        )
        self.department = Department.objects.create(
            school=self.school, name=f"Dept {tag}"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Form 1A",
            code=f"F1A-{tag}",
        )
        self.parent_user = User.objects.create_user(
            username=f"par_{tag}", password="pass", role=User.Role.PARENT
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Nkeng",
            classroom=self.classroom,
            academic_year=self.year,
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent_user,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            can_view_results=True,
        )
        self.client = APIClient(HTTP_HOST=f"{self.school.subdomain}.runmycampus.com")

    def _login(self, user):
        self.client.force_authenticate(user=user)
        session = self.client.session
        session["school_id"] = str(self.school.pk)
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key


class ClassroomWriteGateTests(_EntityWriteGateBase):
    def test_a_parent_can_read_classrooms(self):
        # Open read is the documented behaviour; a fix must not break it, and
        # this proves the requests below actually reach the view.
        self._login(self.parent_user)
        resp = self.client.get(f"/api/entities/classrooms/{self.classroom.pk}/")
        self.assertEqual(resp.status_code, 200, resp.content[:300])

    def test_a_parent_cannot_rename_a_classroom(self):
        self._login(self.parent_user)
        resp = self.client.patch(
            f"/api/entities/classrooms/{self.classroom.pk}/",
            {"name": "Renamed By A Parent"},
            format="json",
        )
        self.assertNotEqual(resp.status_code, 200, resp.content[:300])
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, "Form 1A")

    def test_a_parent_cannot_delete_a_classroom(self):
        # An EMPTY classroom, deliberately. self.classroom holds a student and
        # StudentProfile.classroom is on_delete=PROTECT, so deleting it raises
        # ProtectedError -- the request still reaches destroy(), and a test that
        # leaned on that would be measuring a database constraint rather than
        # the permission gate.
        empty = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Empty Room",
            code=f"EMP-{uuid.uuid4().hex[:6]}",
        )
        self._login(self.parent_user)
        resp = self.client.delete(f"/api/entities/classrooms/{empty.pk}/")
        self.assertNotEqual(resp.status_code, 204, resp.content[:300])
        self.assertTrue(Classroom.objects.filter(pk=empty.pk).exists())

    def test_a_parent_cannot_create_a_classroom(self):
        self._login(self.parent_user)
        before = Classroom.objects.count()
        resp = self.client.post(
            "/api/entities/classrooms/",
            {
                "academic_year": self.year.pk,
                "department": self.department.pk,
                "name": "Ghost Class",
                "code": f"GH-{uuid.uuid4().hex[:6]}",
            },
            format="json",
        )
        self.assertNotIn(resp.status_code, (200, 201), resp.content[:300])
        self.assertEqual(Classroom.objects.count(), before)


class StudentProfileWriteGateTests(_EntityWriteGateBase):
    def test_a_parent_can_read_their_own_child(self):
        self._login(self.parent_user)
        resp = self.client.get(f"/api/entities/students/{self.student.pk}/")
        self.assertEqual(resp.status_code, 200, resp.content[:300])

    def test_a_parent_cannot_delete_their_child_record(self):
        # get_queryset scopes a parent to their own children -- which is what
        # makes DELETE reachable, not what prevents it.
        self._login(self.parent_user)
        resp = self.client.delete(f"/api/entities/students/{self.student.pk}/")
        self.assertNotEqual(resp.status_code, 204, resp.content[:300])
        self.student.refresh_from_db()
        self.assertIsNone(
            self.student.deleted_at,
            "StudentProfile.delete() is a SOFT delete (it stamps deleted_at), so "
            "the row surviving proves nothing -- the stamp is what hides the "
            "student from every reader. A guardian must not be able to set it.",
        )

    def test_a_parent_cannot_create_a_student(self):
        self._login(self.parent_user)
        before = StudentProfile.objects.count()
        resp = self.client.post(
            "/api/entities/students/",
            {"first_name": "Ghost", "last_name": "Pupil"},
            format="json",
        )
        self.assertNotIn(resp.status_code, (200, 201), resp.content[:300])
        self.assertEqual(StudentProfile.objects.count(), before)

    def test_the_existing_update_gate_still_holds(self):
        # Regression seal on the one verb that WAS guarded.
        self._login(self.parent_user)
        resp = self.client.patch(
            f"/api/entities/students/{self.student.pk}/",
            {"first_name": "Rewritten"},
            format="json",
        )
        self.assertNotEqual(resp.status_code, 200, resp.content[:300])
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Ada")


class AdminCanStillWriteTests(_EntityWriteGateBase):
    """The gate must admit admins, or it has simply broken the feature."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username=f"adm_{uuid.uuid4().hex[:8]}",
            password="pass",
            role=User.Role.ADMIN,
            is_staff=True,
        )

    def test_admin_can_rename_a_classroom(self):
        self._login(self.admin)
        resp = self.client.patch(
            f"/api/entities/classrooms/{self.classroom.pk}/",
            {"name": "Form 1 Alpha"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, "Form 1 Alpha")

    def test_admin_can_delete_a_student(self):
        self._login(self.admin)
        resp = self.client.delete(f"/api/entities/students/{self.student.pk}/")
        self.assertEqual(resp.status_code, 204, resp.content[:300])
        self.student.refresh_from_db()
        self.assertIsNotNone(
            self.student.deleted_at, "the delete is soft; deleted_at is the effect"
        )
