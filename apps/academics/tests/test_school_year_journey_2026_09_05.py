"""Drive the first half of a real school year, on the host a real school gets.

Every other academic test in this tree asserts one hand-off in isolation. This
module asserts the SEAM between them -- that the thing step N produces is the
thing step N+1 goes looking for -- because that is where this journey actually
breaks, and it breaks silently: each step reports success and the next one
returns an empty list.

The worked example is ``write_academic_year_setup`` (the ``academic_year_setup``
wizard's writer). It creates the ``AcademicYear`` and its ``Term`` rows, reports
the step complete, and the wizard says done. But it writes the terms WITHOUT
``school``, WITHOUT ``position`` and WITHOUT ``is_active`` -- while
``ensure_terms`` (``apps/academics/structure_provisioning.py``), the other
producer of the same rows, sets all three and self-heals the active one. Every
downstream consumer reads at least one of those three columns:

* ``get_active_year_and_term`` filters ``Term.is_active=True`` -> returns
  ``(year, None)``, so ``teacher_marks_entry`` answers 403 "No active academic
  year/term set by admin yet." and ``timetable_generate`` bounces with an error.
* ``provision_teaching_grid_for_school`` filters ``Term.objects.filter(
  school=school, ...)`` -> matches nothing, so no ``SubjectAssignment`` is built.
* No ``SubjectAssignment`` means no ``TeacherAssignment``, and
  ``_attendance_visible_classrooms`` locks an unassigned teacher down to ``[]``.

So one writer omitting three columns takes out marks entry, the timetable, the
teaching grid and roll call at once, and the only symptom anybody sees is empty
dropdowns. The tests below pin each of those hand-offs separately, so a
regression names the seam it broke instead of failing as "attendance is empty".

Host fidelity matters here and is not incidental: ``UrlConfSwitcherMiddleware``
hands ``testserver`` the DEVELOPER urlconf, which mounts a superset of every
host's routes. A journey test on the default host would keep passing against a
URL surface no school is ever served, so these drive a real tenant host and
assert the resolved urlconf (see ``apps/test_utils/tenant_hosts.py``).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.services import get_active_year_and_term
from apps.accounts.models import User
from apps.evals.models import TeacherAssignment
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.test_utils.tenant_hosts import (
    TENANT_URLCONF,
    assert_resolved_urlconf,
    host_routed,
    tenant_host,
)

PASSWORD = "JourneyTest1234!"

# A Cameroon secondary school: bilingual, francophone /20 marking, three terms.
CM_COUNTRY = "CM"


def _cm_school(*, slug: str, name: str = "Lycée Bilingue de Buea") -> School:
    """A Cameroon tenant with a distinct slug AND subdomain.

    Both are unique; a second school created without an explicit subdomain
    collides on the blank one (see ``scan_blank_unique_text_fields``), and a
    tenant host cannot be built from a blank subdomain at all.
    """
    return School.objects.create(
        name=name,
        slug=slug,
        subdomain=slug,
        country_code=CM_COUNTRY,
        is_active=True,
    )


class YearSetupWriterHandoffTests(TestCase):
    """What the year-setup wizard writes vs what the next step reads.

    No HTTP: this is the writer's contract with the rest of the platform, and
    calling it directly is what lets the failure be attributed to the writer
    rather than to the wizard engine that dispatches it by dotted string.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = _cm_school(slug="zzt-journey-wizard")

    def _run_writer(self, *, term_count: int = 3):
        from apps.setup_studio.wizard_resolvers_operator import (
            write_academic_year_setup,
        )

        write_academic_year_setup(
            school=self.school,
            wizard_key="academic_year_setup",
            step_key="year_dates",
            payload={
                "name": "2026/2027",
                "start_date": "2026-09-07",
                "end_date": "2027-07-16",
                "term_count": term_count,
            },
            actor_user_id=None,
        )

    def test_writer_creates_the_year_it_reports(self):
        """Positive control: the year itself really does land, and is active.

        Paired with the negative assertions below so a future change that makes
        the writer a no-op cannot turn those green by writing nothing at all.
        """
        self._run_writer()
        year = AcademicYear.objects.get(school=self.school, name="2026/2027")
        self.assertTrue(year.is_active)
        self.assertEqual(year.start_date, date(2026, 9, 7))
        self.assertEqual(Term.objects.filter(academic_year=year).count(), 3)

    def test_wizard_terms_are_stamped_with_the_school(self):
        """A term with ``school_id`` NULL is invisible to every school-scoped read.

        ``provision_teaching_grid_for_school`` filters ``Term.objects.filter(
        school=school, academic_year=year)``. An unstamped term matches nothing,
        so the teaching grid comes back empty from a year that visibly has terms.
        """
        self._run_writer()
        year = AcademicYear.objects.get(school=self.school, name="2026/2027")
        unstamped = Term.objects.filter(academic_year=year, school__isnull=True)
        self.assertEqual(
            list(unstamped.values_list("name", flat=True)),
            [],
            "wizard-created terms must carry school_id; an unstamped term is "
            "invisible to Term.objects.filter(school=...), which is how the "
            "teaching-grid provisioner looks them up",
        )
        self.assertEqual(
            Term.objects.filter(academic_year=year, school=self.school).count(),
            3,
        )

    def test_wizard_terms_carry_a_position(self):
        """Order is read from ``position``; all-NULL positions order arbitrarily.

        ``provision_teaching_grid_for_school`` and ``provision_per_specialty_grid``
        both ``.order_by("position")``, and ``SubjectAssignment.clean`` gates the
        third term on ``term.position == 3``. With every position NULL the
        third-term guard can never fire.
        """
        self._run_writer()
        year = AcademicYear.objects.get(school=self.school, name="2026/2027")
        positions = sorted(
            p
            for p in Term.objects.filter(academic_year=year).values_list(
                "position", flat=True
            )
            if p is not None
        )
        self.assertEqual(
            positions,
            [1, 2, 3],
            "wizard-created terms must be positioned 1..n; the teaching-grid "
            "provisioners order by position and the third-term guard compares "
            "position == 3",
        )

    def test_wizard_year_leaves_exactly_one_active_term(self):
        """The headline hand-off: marks entry and the timetable both need a term.

        ``get_active_year_and_term`` returns ``(year, None)`` when no term is
        active. ``teacher_marks_entry`` turns that into a 403 whose text blames
        the admin for not setting a year -- when the admin did exactly that,
        through the wizard the product offered them.
        """
        self._run_writer()
        year, term = get_active_year_and_term(school=self.school)
        self.assertIsNotNone(year, "the year itself landed")
        self.assertIsNotNone(
            term,
            "completing the academic-year wizard must leave an ACTIVE term; "
            "without one get_active_year_and_term returns (year, None) and "
            "teacher_marks_entry answers 403 'No active academic year/term set "
            "by admin yet.'",
        )
        self.assertEqual(
            Term.objects.filter(academic_year=year, is_active=True).count(),
            1,
            "exactly one term may be active",
        )

    def test_rerunning_the_wizard_repairs_a_year_with_no_active_term(self):
        """Idempotent re-run heals, rather than silently leaving the year broken.

        ``get_or_create`` ignores its ``defaults`` when the row already exists,
        so a year seeded by a partial earlier run would keep its inactive terms
        forever unless the writer heals explicitly -- the same reason
        ``ensure_terms`` carries a self-heal after its loop.
        """
        self._run_writer()
        year = AcademicYear.objects.get(school=self.school, name="2026/2027")
        Term.objects.filter(academic_year=year).update(is_active=False)

        self._run_writer()

        _year, term = get_active_year_and_term(school=self.school)
        self.assertIsNotNone(
            term, "a re-run must re-activate a term rather than leave the year dead"
        )

    def test_teaching_grid_provisioner_sees_wizard_terms(self):
        """End-to-end seam: wizard year -> teaching grid.

        This is the assertion that would have caught the defect on its own. It
        exercises the real provisioner rather than re-implementing its query, so
        it stays true if that lookup changes.
        """
        from apps.academics.structure_provisioning import (
            ensure_general_department,
            ensure_general_specialty,
        )
        from apps.academics.structure_provisioning import (
            provision_teaching_grid_for_school,
        )

        self._run_writer()
        year = AcademicYear.objects.get(school=self.school, name="2026/2027")
        ensure_general_department(self.school)
        dept = Department.objects.filter(school=self.school).first()
        ensure_general_specialty(self.school)
        Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=dept,
            name="Form 1A",
            code="F1A",
        )
        Subject.objects.create(school=self.school, name="Mathematics", code="MATH")

        result = provision_teaching_grid_for_school(self.school, academic_year=year)

        self.assertTrue(
            SubjectAssignment.objects.filter(academic_year=year).exists(),
            "the teaching grid must be buildable from a wizard-created year; "
            f"provisioner returned {result!r} and wrote nothing, which is what "
            "an unstamped Term looks like from the far side of the seam",
        )


@host_routed
class BackendClassroomCreateTenancyTests(TestCase):
    """The only classroom-create page in the product, driven on a tenant host.

    A classroom is the spine of the year: attendance, the timetable and the
    teaching grid all hang off it. A classroom that lands without a school is
    not merely untidy -- ``uniq_classroom_school_code`` is
    ``(school, code)``, and NULLs compare distinct, so the constraint that is
    supposed to stop two "F1A"s silently stops enforcing.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = _cm_school(slug="zzt-journey-rooms")
        cls.other = _cm_school(slug="zzt-journey-other", name="Other School")

        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2026/2027",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 7, 16),
            is_active=True,
        )
        cls.other_year = AcademicYear.objects.create(
            school=cls.other,
            name="2026/2027",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 7, 16),
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="General Education", code="GEN"
        )
        cls.other_dept = Department.objects.create(
            school=cls.other, name="General Education", code="GEN"
        )

        cls.admin = User.objects.create_user(
            username="journey_admin",
            email="admin@zzt-journey-rooms.test",
            password=PASSWORD,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.get_or_create(
            user=cls.admin,
            school=cls.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

    def setUp(self):
        from django.contrib.auth.models import Permission as DjangoPermission

        # The view is gated on the Django model permission, not the RBAC code.
        perm = DjangoPermission.objects.filter(codename="add_classroom").first()
        if perm is not None:
            self.admin.user_permissions.add(perm)
        self.admin.refresh_from_db()

        from apps.test_utils.http_clients import login_tenant_admin_client

        self.client = login_tenant_admin_client(
            self.admin,
            password=PASSWORD,
            host=tenant_host(self.school),
            school=self.school,
        )

    def test_created_classroom_belongs_to_the_school_that_created_it(self):
        url = reverse("accounts:backend_classroom_create")
        response = self.client.post(
            url,
            {
                "name": "Form 1A",
                "code": "F1A",
                "academic_year": self.year.pk,
                "department": self.dept.pk,
                "allows_third_term": "on",
            },
            follow=False,
        )
        self.assertIn(response.status_code, (200, 302))

        classroom = Classroom.objects.filter(code="F1A").first()
        self.assertIsNotNone(
            classroom,
            "the classroom-create page must actually create the classroom",
        )
        self.assertEqual(
            classroom.school_id,
            self.school.pk,
            "a classroom created on a tenant host must be stamped with that "
            "school; a NULL school_id disables uniq_classroom_school_code and "
            "hides the row from every school-scoped read",
        )

    def test_form_does_not_offer_another_tenants_year_or_department(self):
        """The dropdowns are the leak: they are built from unscoped querysets.

        Asserted through the form rather than the rendered HTML so the failure
        names the queryset, and so the test does not depend on widget markup.
        """
        from apps.people.forms_backend import ClassroomCreateForm

        form = ClassroomCreateForm(school=self.school)

        year_ids = set(form.fields["academic_year"].queryset.values_list("pk", flat=True))
        dept_ids = set(form.fields["department"].queryset.values_list("pk", flat=True))

        self.assertIn(self.year.pk, year_ids, "positive control: own year offered")
        self.assertIn(self.dept.pk, dept_ids, "positive control: own department offered")
        self.assertNotIn(
            self.other_year.pk,
            year_ids,
            "the academic-year dropdown must not list another school's year",
        )
        self.assertNotIn(
            self.other_dept.pk,
            dept_ids,
            "the department dropdown must not list another school's department",
        )

    def test_form_rejects_a_posted_foreign_year(self):
        """Scoping a dropdown is presentation; the POST is the security boundary.

        A hand-crafted POST does not go through the widget, so the queryset must
        reject the id rather than merely not offering it.
        """
        url = reverse("accounts:backend_classroom_create")
        self.client.post(
            url,
            {
                "name": "Smuggled",
                "code": "SMUG",
                "academic_year": self.other_year.pk,
                "department": self.other_dept.pk,
                "allows_third_term": "on",
            },
        )
        self.assertFalse(
            Classroom.objects.filter(code="SMUG").exists(),
            "a POST naming another school's academic year must not create a "
            "classroom",
        )


@host_routed
class TeacherDailyOpsHandoffTests(TestCase):
    """Roll call and marks entry, driven as the teacher, on the tenant host.

    Builds the full chain an admin has to assemble -- year, term, department,
    specialty, classroom, subject, subject assignment, teacher assignment,
    enrolled students -- and then asserts the teacher can actually reach the two
    things they do every day.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = _cm_school(slug="zzt-journey-teach")
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2026/2027",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 7, 16),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name="Term 1",
            position=1,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 12, 18),
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="General Education", code="GEN"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school, department=cls.dept, name="General", code="GEN"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 1A",
            code="F1A",
        )
        cls.subject = Subject.objects.create(
            school=cls.school, name="Mathematics", code="MATH"
        )
        cls.subject_assignment = SubjectAssignment.objects.create(
            school=cls.school,
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=cls.subject,
        )

        cls.teacher_user = User.objects.create_user(
            username="journey_teacher",
            email="teacher@zzt-journey-teach.test",
            password=PASSWORD,
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.get_or_create(
            user=cls.teacher_user,
            school=cls.school,
            defaults={"role": User.Role.TEACHER, "is_primary": True},
        )
        cls.teacher = TeacherProfile.objects.create(
            user=cls.teacher_user, school=cls.school, staff_id="T001"
        )

        # Cameroonian names, deliberately: slugify() returns "" for many of them,
        # which is how a blank+unique slug field collides on the SECOND row.
        cls.students = [
            StudentProfile.objects.create(
                school=cls.school,
                first_name=first,
                last_name=last,
                classroom=cls.classroom,
                academic_year=cls.year,
                status=StudentProfile.Status.NEW,
            )
            for first, last in (("Ndi", "Enow"), ("Manyi", "Tambe"), ("Tabi", "Ayuk"))
        ]

    def _login_teacher(self):
        from apps.test_utils.http_clients import login_tenant_client

        return login_tenant_client(
            self.teacher_user, password=PASSWORD, host=tenant_host(self.school)
        )

    def _grant(self, *codes):
        """Seed the catalog AND attach the role, because those are two steps.

        ``rbac_seed.grant`` creates the ``AccessRole`` and its permissions; it
        does not put the role on a user. ``has_feature_permission`` reads
        ``self.roles`` (an M2M), so seeding alone leaves the teacher holding
        nothing -- and an unseeded permission code denies everyone silently,
        which is exactly the shape that makes a negative assertion pass for the
        wrong reason.
        """
        from apps.test_utils.rbac_seed import grant

        role = grant(User.Role.TEACHER, *codes)
        self.teacher_user.roles.add(role)
        # Positive control: prove the grant actually took before relying on it.
        assert self.teacher_user.has_feature_permission(codes[0]), (
            f"RBAC seed did not take for {codes[0]!r}; every assertion that "
            "follows would pass or fail for the wrong reason"
        )
        return role

    def test_journey_runs_on_the_tenant_urlconf(self):
        """Guard the guard: if this fails every other assertion here is vacuous."""
        client = self._login_teacher()
        response = client.get(reverse("portal:take_student_attendance"))
        assert_resolved_urlconf(response, TENANT_URLCONF)

    def test_assigned_teacher_can_save_roll_call(self):
        """The happy path, written first so the empty-state test has a control."""
        self._grant("attendance.manage")
        TeacherAssignment.objects.create(
            school=self.school,
            teacher=self.teacher,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
        )
        client = self._login_teacher()
        att_date = date(2026, 9, 14)

        payload = {"date": att_date.isoformat(), "classroom": self.classroom.pk}
        for student in self.students:
            payload[f"status_{student.pk}"] = Attendance.Status.PRESENT
        payload[f"status_{self.students[1].pk}"] = Attendance.Status.ABSENT

        client.post(reverse("portal:take_student_attendance"), payload)

        rows = Attendance.objects.filter(classroom=self.classroom, date=att_date)
        self.assertEqual(
            rows.count(),
            len(self.students),
            "roll call must write one row per student in the class",
        )
        self.assertEqual(
            rows.get(student=self.students[1]).status,
            Attendance.Status.ABSENT,
            "the marked absence must survive the save",
        )
        self.assertEqual(
            set(rows.values_list("school_id", flat=True)),
            {self.school.pk},
            "every attendance row must be stamped with the school",
        )

    def test_unassigned_teacher_is_told_why_the_class_list_is_empty(self):
        """A locked-down teacher must get a reason, not a blank dropdown.

        ``_attendance_visible_classrooms`` returns ``[]`` for a teacher with no
        ``TeacherAssignment``. That is the correct SECURITY answer and a
        terrible product answer: the page renders with an empty class selector
        and nothing on it explains that an administrator has to assign the
        teacher to a class first, so the teacher has no next action.
        """
        self._grant("attendance.manage")
        client = self._login_teacher()

        response = client.get(reverse("portal:take_student_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["classrooms"]),
            [],
            "positive control: an unassigned teacher really does see no classes",
        )
        body = response.content.decode("utf-8", "replace").lower()
        self.assertTrue(
            any(
                phrase in body
                for phrase in (
                    "not been assigned",
                    "no classes assigned",
                    "ask an administrator",
                    "administrator has not",
                )
            ),
            "the empty class list must explain that the teacher has no class "
            "assignment yet and who can fix it; rendering an empty <select> "
            "with no message leaves the teacher with no next action",
        )


class AcademicsHubDestinationTests(TestCase):
    """The hub is the admin's map of the year; a card must go where it says.

    No HTTP and no host binding: the card table is a module-level constant
    reachable through the view's own action list, and asserting on it directly
    keeps the failure pointed at the wrong destination rather than at whatever
    permission or membership the page happens to need that week.
    """

    def test_teaching_assignments_card_does_not_point_at_a_read_only_list(self):
        import inspect

        from apps.academics import views_hub

        # Read the MODULE, not the function. `academics_hub` is wrapped by the
        # school-context guard, which is hand-rolled without functools.wraps --
        # so it exposes no `__wrapped__` to unwrap, and `getsource` on the bare
        # name returns the WRAPPER: four lines of `if getattr(request, "school",
        # None) is None`. The positive control then fails while the card is
        # present and correct, which is a test that lies in the safe direction
        # but lies all the same.
        #
        # The card table is a module-level constant (see this class's docstring),
        # so the module source is both the honest subject and immune to however
        # the view is decorated next.
        source = inspect.getsource(views_hub)
        self.assertIn(
            "Teaching assignments",
            source,
            "positive control: the card still exists",
        )
        # The read-only subject list may still be linked -- by a card that says
        # it lists subjects. What it must not be is the destination of the card
        # that promises to connect teachers to classes.
        teaching_line = next(
            line
            for line in source.splitlines()
            if '"Teaching assignments"' in line or "'Teaching assignments'" in line
        )
        self.assertNotIn(
            "backend_subject_list",
            teaching_line,
            "the 'Teaching assignments' card must not open the subject list, "
            "which documents itself as a read-only browse surface; without a "
            "reachable teaching-grid surface no teacher can be assigned, and "
            "an unassigned teacher gets an empty roll call and a 403 on marks",
        )


class YearOpsPreflightCommandTests(TestCase):
    """The preflight must FIND a broken year, not just run clean on a good one.

    A checker that has never been shown failing is not evidence of anything, so
    each state is asserted in both directions on the same school.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = _cm_school(slug="zzt-journey-preflight")

    def _run(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        try:
            call_command(
                "year_ops_preflight", school=self.school.slug, json=True, stdout=out
            )
        except SystemExit:
            # Exit 1 is the documented signal that a BLOCKER was found; the
            # report has already been written to stdout.
            pass
        import json as _json

        return _json.loads(out.getvalue())[0]["checks"]

    def _status(self, checks, key):
        for c in checks:
            if c["check"] == key:
                return c["status"]
        return None

    def test_reports_a_blocker_when_there_is_no_academic_year(self):
        checks = self._run()
        self.assertEqual(self._status(checks, "academic_year"), "BLOCKER")
        self.assertTrue(
            any(c["next_action"] for c in checks),
            "a blocker must carry the next action, not just a status",
        )

    def test_reports_a_blocker_when_the_year_has_no_active_term(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 7, 16),
            is_active=True,
        )
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 12, 18),
            is_active=False,
        )
        checks = self._run()
        self.assertEqual(
            self._status(checks, "academic_year"),
            "OK",
            "positive control: the year itself is fine",
        )
        self.assertEqual(
            self._status(checks, "active_term"),
            "BLOCKER",
            "a year whose terms are all inactive is the silent dead end this "
            "command exists to name",
        )

    def test_reports_a_blocker_for_a_term_with_no_school(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 7, 16),
            is_active=True,
        )
        Term.objects.create(
            school=None,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 12, 18),
            is_active=True,
        )
        checks = self._run()
        self.assertEqual(
            self._status(checks, "term_tenancy"),
            "BLOCKER",
            "an unstamped term is invisible to the teaching-grid provisioner "
            "even though the admin can see it on screen",
        )

    def test_a_fully_set_up_year_clears_the_structural_checks(self):
        """The control that makes every BLOCKER above meaningful."""
        year = AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 7),
            end_date=date(2027, 7, 16),
            is_active=True,
        )
        Term.objects.create(
            school=self.school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=date(2026, 9, 7),
            end_date=date(2026, 12, 18),
            is_active=True,
        )
        checks = self._run()
        self.assertEqual(self._status(checks, "academic_year"), "OK")
        self.assertEqual(self._status(checks, "active_term"), "OK")
        self.assertEqual(self._status(checks, "term_tenancy"), "OK")
