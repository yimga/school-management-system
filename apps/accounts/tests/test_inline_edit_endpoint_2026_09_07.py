"""The inline-edit save endpoint: who it lets through, and what it refuses.

WHAT THIS FILE COVERS AND WHAT IT DOES NOT. The views are exercised directly
through a ``RequestFactory`` with ``request.school`` and ``request.user`` set,
rather than through ``self.client.post`` on the real URL. That is a deliberate
narrowing, not a shortcut: a tenant-host request has to satisfy school
membership and MFA before it reaches any view here, so a client test that 302s
tells you which wall it hit and nothing about the endpoint's own decisions --
and those decisions are the entire security surface. The routing half is checked
separately: both names reverse and resolve under ``config.tenant_urls`` (the
urlconf a real school host uses), which is the half a view test cannot see.

THE SEEDING TRAP HAS ITS OWN TEST. The gate is Django's
``people.change_teacherprofile``. An unseeded permission code denies everyone,
permanently, with no error anywhere -- the control simply never appears and the
endpoint 403s a user who plainly should have access.
``test_the_permission_code_this_gate_needs_actually_exists`` fails loudly in that
case instead of leaving somebody to debug a working system.
"""

from __future__ import annotations

import json
import uuid

from django.apps import apps
from django.contrib.auth.models import Permission
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.views_inline_edit import (
    inline_edit_options,
    inline_edit_save,
    resolve_editable_model,
)

School = apps.get_model("schools", "School")
User = apps.get_model("accounts", "User")
Department = apps.get_model("academics", "Department")
TeacherProfile = apps.get_model("people", "TeacherProfile")


class InlineEditEndpointTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        other = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Ours {uid}", slug=f"ours-{uid}", subdomain=f"ours{uid}", is_active=True
        )
        self.other_school = School.objects.create(
            name=f"Theirs {other}", slug=f"theirs-{other}", subdomain=f"theirs{other}",
            is_active=True,
        )
        self.ours = Department.objects.create(
            school=self.school, name="Sciences", code=f"SCI{uid}"
        )
        self.theirs = Department.objects.create(
            school=self.other_school, name="Sciences", code=f"SCI{other}"
        )
        self.user = User.objects.create_user(
            username=f"admin{uid}", email=f"admin{uid}@example.test", password="x"
        )
        self.teacher_user = User.objects.create_user(
            username=f"teach{uid}", email=f"teach{uid}@example.test", password="x"
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school, user=self.teacher_user, staff_id=f"ST{uid}"
        )

    # -- helpers ---------------------------------------------------------
    def _grant(self, codename="change_teacherprofile", app_label="people"):
        perm = Permission.objects.filter(
            codename=codename, content_type__app_label=app_label
        ).first()
        self.assertIsNotNone(perm, f"{app_label}.{codename} is not seeded")
        self.user.user_permissions.add(perm)
        self.user = User.objects.get(pk=self.user.pk)  # drop the perm cache

    def _post(self, data, *, pk=None, app_label="people", model_name="teacherprofile"):
        request = self.factory.post("/authentication/backend/inline-edit/", data)
        request.user = self.user
        request.school = self.school
        return inline_edit_save(
            request, app_label=app_label, model_name=model_name,
            pk=pk if pk is not None else self.teacher.pk,
        )

    # -- the seeding trap ------------------------------------------------
    def test_the_permission_code_this_gate_needs_actually_exists(self):
        """An unseeded code denies everyone silently and forever."""
        self.assertTrue(
            Permission.objects.filter(
                codename="change_teacherprofile", content_type__app_label="people"
            ).exists(),
            "people.change_teacherprofile is missing; every user would be denied "
            "with no error to explain it",
        )

    # -- authority -------------------------------------------------------
    def test_without_the_change_permission_the_save_is_refused(self):
        response = self._post({"field": "position_title", "value": "Head of Science"})
        self.assertEqual(response.status_code, 403)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.position_title, "")

    def test_the_refusal_names_the_permission_it_wanted(self):
        """So a missing code is diagnosable from the response, not from a hunt."""
        payload = json.loads(self._post({"field": "position_title", "value": "x"}).content)
        self.assertEqual(payload["permission"], "people.change_teacherprofile")

    def test_with_the_permission_the_field_is_saved(self):
        """Guard against a gate so tight nothing passes it."""
        self._grant()
        response = self._post({"field": "position_title", "value": "Head of Science"})
        self.assertEqual(response.status_code, 200)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.position_title, "Head of Science")

    # -- tenancy ---------------------------------------------------------
    def test_another_schools_record_is_not_found(self):
        self._grant()
        theirs = TeacherProfile.objects.create(
            school=self.other_school,
            user=User.objects.create_user(
                username=f"t{uuid.uuid4().hex[:8]}", email="t@example.test", password="x"
            ),
            staff_id="X1",
        )
        with self.assertRaises(Http404):
            self._post({"field": "position_title", "value": "x"}, pk=theirs.pk)

    def test_another_schools_department_is_refused_as_a_value(self):
        """A valid pk that belongs to somebody else. The core refusal."""
        self._grant()
        response = self._post({"field": "department", "value": self.theirs.pk})
        self.assertEqual(response.status_code, 400)
        self.teacher.refresh_from_db()
        self.assertIsNone(self.teacher.department_id)

    def test_this_schools_department_is_accepted(self):
        self._grant()
        response = self._post({"field": "department", "value": self.ours.pk})
        self.assertEqual(response.status_code, 200)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.department_id, self.ours.pk)

    # -- what may never be edited ---------------------------------------
    def test_the_tenant_key_is_refused_at_the_endpoint(self):
        """Locking must not live only in the renderer.

        Nothing stops somebody POSTing a field the page never offered, so the
        refusal has to be in the endpoint rather than in the markup.
        """
        self._grant()
        response = self._post({"field": "school", "value": self.other_school.pk})
        self.assertEqual(response.status_code, 400)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.school_id, self.school.pk)

    def test_the_identity_binding_is_refused(self):
        """``user`` says which login this person IS."""
        self._grant()
        response = self._post({"field": "user", "value": self.user.pk})
        self.assertEqual(response.status_code, 400)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.user_id, self.teacher_user.pk)

    def test_an_unknown_field_is_not_found(self):
        self._grant()
        with self.assertRaises(Http404):
            self._post({"field": "no_such_field", "value": "x"})

    # -- which models are in scope at all --------------------------------
    def test_a_model_with_no_school_column_is_out_of_scope(self):
        """This is what keeps platform tables out without naming them.

        ``School`` has no ``school`` FK -- it IS the tenant -- so there is no
        school to scope an edit to and the endpoint refuses the whole model.
        """
        with self.assertRaises(Http404):
            resolve_editable_model("schools", "school")

    def test_an_append_only_log_is_out_of_scope(self):
        """An audit row that can be edited is not an audit row."""
        with self.assertRaises(Http404):
            resolve_editable_model("compliance", "auditlog")

    def test_a_school_owned_model_is_in_scope(self):
        """Guard against a scope rule that excludes everything."""
        self.assertIs(resolve_editable_model("people", "teacherprofile"), TeacherProfile)

    # -- the cascade, reported rather than silent ------------------------
    def test_a_cascade_is_named_in_the_response(self):
        """A second control changing unannounced is a change somebody undoes.

        ``StudentProfile.classroom`` implies ``academic_year`` by the derived
        rule; the response has to say so.
        """
        StudentProfile = apps.get_model("people", "StudentProfile")
        Classroom = apps.get_model("academics", "Classroom")
        AcademicYear = apps.get_model("academics", "AcademicYear")
        uid = uuid.uuid4().hex[:6]
        year = AcademicYear.objects.create(
            school=self.school, name=f"20{uid[:2]}/20{uid[2:4]}",
            start_date="2026-09-01", end_date="2027-07-31",
        )
        classroom = Classroom.objects.create(
            school=self.school, name=f"Form 1 {uid}", code=f"F1{uid}",
            academic_year=year, department=self.ours,
        )
        student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Lovelace"
        )
        perm = Permission.objects.filter(
            codename="change_studentprofile", content_type__app_label="people"
        ).first()
        self.assertIsNotNone(perm, "people.change_studentprofile is not seeded")
        self.user.user_permissions.add(perm)
        self.user = User.objects.get(pk=self.user.pk)

        response = self._post(
            {"field": "classroom", "value": classroom.pk},
            pk=student.pk,
            model_name="studentprofile",
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = json.loads(response.content)
        self.assertIn("academic_year", payload["also_set"])
        student.refresh_from_db()
        self.assertEqual(student.academic_year_id, year.pk)


class InlineEditOptionsTests(TestCase):
    """The dropdown source. Must be the same set the save accepts."""

    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        other = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Ours {uid}", slug=f"o-{uid}", subdomain=f"o{uid}", is_active=True
        )
        self.other_school = School.objects.create(
            name=f"Theirs {other}", slug=f"t-{other}", subdomain=f"t{other}", is_active=True
        )
        self.ours = Department.objects.create(
            school=self.school, name="Sciences", code=f"S{uid}"
        )
        self.theirs = Department.objects.create(
            school=self.other_school, name="Arts", code=f"A{other}"
        )
        self.user = User.objects.create_user(
            username=f"u{uid}", email=f"u{uid}@example.test", password="x"
        )
        perm = Permission.objects.filter(
            codename="change_teacherprofile", content_type__app_label="people"
        ).first()
        self.user.user_permissions.add(perm)
        self.user = User.objects.get(pk=self.user.pk)

    def test_the_list_holds_this_schools_rows_only(self):
        request = self.factory.get("/x/", {"field": "department"})
        request.user = self.user
        request.school = self.school
        response = inline_edit_options(
            request, app_label="people", model_name="teacherprofile", pk=1
        )
        labels = {row["value"] for row in json.loads(response.content)["choices"]}
        self.assertIn(self.ours.pk, labels)
        self.assertNotIn(self.theirs.pk, labels)


class PrivilegeFieldTests(TestCase):
    """Roles and access flags: a second gate, and one refusal that needs no ladder.

    Editing a phone number and editing a role are not the same act. The second is
    the only edit where the person performing it can profit from it, so the
    endpoint asks two further questions: does this person hold identity-management
    authority at this school, and are they pointing it at themselves.

    WHAT IS DELIBERATELY ABSENT, so nobody later mistakes it for an oversight:
    there is no "you may not grant a role above your own" rule. ``User.Role`` is
    declared SUPERADMIN, ADMIN, LEADERSHIP, PRINCIPAL ... TEACHER, IT_ADMIN, DPO --
    IT_ADMIN sits AFTER TEACHER. Enum order is not a privilege ladder, and reading
    one out of it would be a guess that silently decides who may promote whom.
    Authority is asked of ``_can_manage_tenant_identity``, which is where this
    platform already answers it.
    """

    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        other = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"P {uid}", slug=f"p-{uid}", subdomain=f"p{uid}", is_active=True
        )
        self.other_school = School.objects.create(
            name=f"Q {other}", slug=f"q-{other}", subdomain=f"q{other}", is_active=True
        )
        self.admin = User.objects.create_user(
            username=f"adm{uid}", email=f"adm{uid}@example.test", password="x"
        )
        self.plain = User.objects.create_user(
            username=f"pln{uid}", email=f"pln{uid}@example.test", password="x"
        )
        self.subject = User.objects.create_user(
            username=f"sub{uid}", email=f"sub{uid}@example.test", password="x"
        )
        perm = Permission.objects.filter(
            codename="change_schoolmembership", content_type__app_label="schools"
        ).first()
        self.assertIsNotNone(perm, "schools.change_schoolmembership is not seeded")
        for who in (self.admin, self.plain):
            who.user_permissions.add(perm)

        from apps.schools.models import SchoolMembership

        self.SchoolMembership = SchoolMembership
        # ADMIN is one of _IDENTITY_HUB_MANAGE_ROLES; TEACHER is not.
        self.admin_membership = SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN"
        )
        self.plain_membership = SchoolMembership.objects.create(
            user=self.plain, school=self.school, role="TEACHER"
        )
        self.subject_membership = SchoolMembership.objects.create(
            user=self.subject, school=self.school, role="TEACHER"
        )
        self.admin = User.objects.get(pk=self.admin.pk)
        self.plain = User.objects.get(pk=self.plain.pk)

    def _post(self, actor, pk, data, *, app_label="schools", model_name="schoolmembership"):
        request = self.factory.post("/authentication/backend/inline-edit/", data)
        request.user = actor
        request.school = self.school
        return inline_edit_save(
            request, app_label=app_label, model_name=model_name, pk=pk
        )

    def test_a_teacher_cannot_change_anyones_role(self):
        """Django's change permission alone is not enough for a role."""
        response = self._post(
            self.plain, self.subject_membership.pk, {"field": "role", "value": "ADMIN"}
        )
        self.assertEqual(response.status_code, 403)
        self.subject_membership.refresh_from_db()
        self.assertEqual(self.subject_membership.role, "TEACHER")

    def test_an_administrator_can_change_someone_elses_role(self):
        """Guard against a gate so tight the feature does not exist."""
        response = self._post(
            self.admin, self.subject_membership.pk, {"field": "role", "value": "BURSAR"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.subject_membership.refresh_from_db()
        self.assertEqual(self.subject_membership.role, "BURSAR")

    def test_nobody_may_change_their_own_role(self):
        """Self-escalation, refused without needing to rank the roles.

        The admin here HAS identity-management authority and still cannot point it
        at their own membership -- raising your own authority is the move whatever
        the roles are called.
        """
        response = self._post(
            self.admin, self.admin_membership.pk, {"field": "role", "value": "SUPERADMIN"}
        )
        self.assertEqual(response.status_code, 403)
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, "ADMIN")

    def test_an_ordinary_field_is_not_caught_by_the_privilege_gate(self):
        """A teacher editing a phone number must not need identity rights."""
        perm = Permission.objects.filter(
            codename="change_teacherprofile", content_type__app_label="people"
        ).first()
        self.plain.user_permissions.add(perm)
        actor = User.objects.get(pk=self.plain.pk)
        teacher = TeacherProfile.objects.create(
            school=self.school, user=self.subject, staff_id=f"S{uuid.uuid4().hex[:6]}"
        )
        request = self.factory.post("/x/", {"field": "phone", "value": "670000000"})
        request.user = actor
        request.school = self.school
        response = inline_edit_save(
            request, app_label="people", model_name="teacherprofile", pk=teacher.pk
        )
        self.assertEqual(response.status_code, 200, response.content)
        teacher.refresh_from_db()
        self.assertEqual(teacher.phone, "670000000")


class UserThroughMembershipTests(TestCase):
    """accounts.User carries no school column and must still be reachable."""

    def setUp(self):
        self.factory = RequestFactory()
        uid = uuid.uuid4().hex[:8]
        other = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"M {uid}", slug=f"m-{uid}", subdomain=f"m{uid}", is_active=True
        )
        self.other_school = School.objects.create(
            name=f"N {other}", slug=f"n-{other}", subdomain=f"n{other}", is_active=True
        )
        self.actor = User.objects.create_user(
            username=f"act{uid}", email=f"act{uid}@example.test", password="x"
        )
        self.member = User.objects.create_user(
            username=f"mem{uid}", email=f"mem{uid}@example.test", password="x",
            first_name="Wrong",
        )
        self.stranger = User.objects.create_user(
            username=f"str{other}", email=f"str{other}@example.test", password="x"
        )
        perm = Permission.objects.filter(
            codename="change_user", content_type__app_label="accounts"
        ).first()
        self.assertIsNotNone(perm, "accounts.change_user is not seeded")
        self.actor.user_permissions.add(perm)

        from apps.schools.models import SchoolMembership

        SchoolMembership.objects.create(user=self.actor, school=self.school, role="ADMIN")
        SchoolMembership.objects.create(user=self.member, school=self.school, role="TEACHER")
        SchoolMembership.objects.create(
            user=self.stranger, school=self.other_school, role="TEACHER"
        )
        self.actor = User.objects.get(pk=self.actor.pk)

    def _post(self, pk, data):
        request = self.factory.post("/x/", data)
        request.user = self.actor
        request.school = self.school
        return inline_edit_save(request, app_label="accounts", model_name="user", pk=pk)

    def test_a_member_of_this_school_can_be_corrected(self):
        response = self._post(self.member.pk, {"field": "first_name", "value": "Fonong"})
        self.assertEqual(response.status_code, 200, response.content)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Fonong")

    def test_a_member_of_another_school_is_not_found(self):
        """The whole reason the membership path has to be scoped."""
        with self.assertRaises(Http404):
            self._post(self.stranger.pk, {"field": "first_name", "value": "Nope"})

    def test_the_password_field_is_never_reachable(self):
        """400 with a reason, not 404: the field exists, it is simply forbidden.

        ``structural_lock`` classifies it as credential material and the endpoint
        says so, which is more useful than pretending the field is absent. What
        matters is the stored hash: assert THAT, not only the status code, so this
        still fails if a future refactor returns 400 while writing the value.
        """
        before = User.objects.get(pk=self.member.pk).password
        response = self._post(self.member.pk, {"field": "password", "value": "hunter2"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("credential material", response.content.decode())
        self.assertEqual(User.objects.get(pk=self.member.pk).password, before)

    def test_a_superuser_flag_needs_identity_rights_and_is_not_self_settable(self):
        """is_superuser is a privilege field like any role."""
        response = self._post(self.actor.pk, {"field": "is_superuser", "value": "1"})
        self.assertEqual(response.status_code, 403)
        self.actor.refresh_from_db()
        self.assertFalse(self.actor.is_superuser)
