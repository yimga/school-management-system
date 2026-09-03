"""Year rollover reads its academic years from the requesting school, not by bare id.

This module already contains the fix for exactly this hole -- and applied it to the
gentler of the two paths. ``_clone_year_queryset(request)`` scopes the year picker for
``clone_year_setup``, and its docstring states the reasoning outright:

    Previously ``AcademicYear.objects.all()``. A tenant SCHEMA can hold several
    Schools (multi-campus), and RLS deployments share one schema outright, so an
    unfiltered read let one campus see - and clone into - another's years. Scoping
    here also turns the ``get_object_or_404`` below into an ownership check rather
    than a bare id lookup, closing the matching POST-side IDOR.

``rollover_year`` and ``rollover_prepare`` kept both halves of that hole. Cloning a
year copies structure; rollover MOVES students between years and graduates them, so the
path left open is the one that writes.

Three sites, all in ``apps/accounts/views_rollover.py``:

1. ``rollover_year`` -- ``years = list(AcademicYear.objects.all()...)`` builds the
   picker, so the form offers every co-located school's years by name.
2. ``rollover_year`` POST and ``rollover_prepare`` -- ``get_object_or_404(AcademicYear,
   id=source_id)`` on ids taken straight from ``request.POST``. A bare id lookup, which
   is the POST-side IDOR the helper above was written to close. NOTE the two differ
   downstream: ``rollover_year`` POST reaches ``evaluate_year_close_blockers``, which
   DOES raise a ``tenant_mismatch`` blocker -- but only for ``source_year``, and only
   when a school is bound. ``rollover_prepare`` reaches no such check; that helper has
   exactly one production call site, and it is not this one.
3. ``rollover_year`` GET -- ``AcademicYear.objects.filter(id=source_id).first()`` on
   ``request.GET`` ids, which renders the cross-school preview rows.

``rollover_prepare`` is the sharpest of the three because of what it hands on. It
passes the REQUESTING school's id alongside years that were never checked against it::

    prepare_rollover_proposal.apply(args=[school_id, source_year.id, target_year.id])

and ``_prepare_rollover_proposal_impl`` then selects the cohort by year alone::

    students = StudentProfile.objects.filter(academic_year=source_year, is_active=True)
    target_classrooms = Classroom.objects.filter(academic_year=target_year)

So a ``RolloverProposal`` is filed under school A whose items point at school B's
students and B's classrooms. ``RolloverProposal.school`` is NOT NULL and A's own
``rollover_queue`` filters on it, so A's operator is shown B's student names on a page
that offers Approve and Apply -- while B's queue, correctly scoped, never lists it.

Why the existing suite could not see this. The four rollover test modules
(``test_rollover_backup_gate``, ``_freezes_transcripts``, ``_graduation_gate``,
``_async_notify_parity``) all run on the default ``testserver`` host, where
``request.school`` is None and only one school exists. With no second school there is
nothing to leak from, and with no bound school a scoped query and an unscoped one
return the same rows. These tests bind a real tenant host and build two schools.

On what these tests prove. They exercise the APPLICATION-level bound. On the cloud each
tenant holds its own schema, which hides all three sites; on a sovereign box every
school shares one schema and they are live. Postgres RLS is a second lane and not the
subject here -- policies do not bind on Django's own connection, and 198 tables carry a
policy without FORCE, so the app-level bound is the one actually load-bearing.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import RolloverProposal, RolloverProposalItem, User
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.test_utils.http_clients import login_tenant_admin_client
from apps.test_utils.tenant_hosts import (
    HOST_ROUTED_SETTINGS,
    TENANT_URLCONF,
    assert_resolved_urlconf,
    tenant_host,
)


class _TwoSchoolRolloverFixture(TestCase):
    """Two schools, each with a full source year: classroom, department, students."""

    def setUp(self):
        self.ours, self.our_year, self.our_target, self.our_student = self._school(
            "ours"
        )
        self.theirs, self.their_year, self.their_target, self.their_student = (
            self._school("theirs")
        )
        self.admin = User.objects.create_user(
            username="rollover_admin",
            email="rollover_admin@example.test",
            password="pass1234",
            role=User.Role.ADMIN,
        )
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])
        self.client = login_tenant_admin_client(
            self.admin,
            password="pass1234",
            host=tenant_host(self.ours),
            school=self.ours,
            role=User.Role.ADMIN,
        )

    def _school(self, tag):
        school = School.objects.create(
            name=f"School {tag}",
            slug=f"rollover-scope-{tag}",
            subdomain=f"rollover-scope-{tag}",
            is_active=True,
        )
        # The two schools' years are named distinctly so an assertion on the rendered
        # picker cannot pass by accident on a shared label.
        source = AcademicYear.objects.create(
            school=school,
            name=f"{tag.capitalize()} 2024/2025",
            start_date=timezone.localdate() - timedelta(days=400),
            end_date=timezone.localdate() - timedelta(days=40),
            is_active=False,
        )
        target = AcademicYear.objects.create(
            school=school,
            name=f"{tag.capitalize()} 2025/2026",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        # Department.code and Classroom.code are per-school unique, so the second
        # school must not reuse the first's.
        department = Department.objects.create(
            school=school, name=f"{tag} dept", code=f"{school.subdomain}-d1"
        )
        source_room = Classroom.objects.create(
            school=school,
            academic_year=source,
            department=department,
            name="Form 1",
            code=f"{school.subdomain}-src",
        )
        Classroom.objects.create(
            school=school,
            academic_year=target,
            department=department,
            name="Form 2",
            code=f"{school.subdomain}-tgt",
        )
        student = StudentProfile.objects.create(
            school=school,
            academic_year=source,
            classroom=source_room,
            first_name=tag.capitalize(),
            last_name="Roller",
            student_code=f"RS-{tag.upper()}",
            is_active=True,
        )
        return school, source, target, student


@override_settings(**HOST_ROUTED_SETTINGS)
class RolloverYearPickerIsSchoolScopedTests(_TwoSchoolRolloverFixture):
    """The GET form: which years an operator is even offered."""

    def test_the_picker_offers_only_this_school_s_years(self):
        response = self.client.get(reverse("accounts:rollover_year"))
        assert_resolved_urlconf(response, TENANT_URLCONF)
        self.assertEqual(response.status_code, 200)
        offered = {y.pk for y in response.context["years"]}
        self.assertIn(self.our_year.pk, offered)
        self.assertNotIn(
            self.their_year.pk,
            offered,
            "another school's academic year was offered on the rollover form -- "
            "AcademicYear.objects.all() bounds by nothing",
        )

    def test_another_school_s_year_name_is_not_rendered(self):
        """Independent of context: the operator must not read B's year names."""
        response = self.client.get(reverse("accounts:rollover_year"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.their_year.name)


@override_settings(**HOST_ROUTED_SETTINGS)
class RolloverPreviewIsSchoolScopedTests(_TwoSchoolRolloverFixture):
    """The GET preview: ?source_year=&target_year= taken from the query string."""

    def test_the_preview_refuses_another_school_s_years(self):
        response = self.client.get(
            reverse("accounts:rollover_year"),
            {
                "source_year": str(self.their_year.pk),
                "target_year": str(self.their_target.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            response.context["source_year"],
            "the preview resolved another school's year from a query-string id",
        )
        self.assertEqual(response.context["rows"], [])
        self.assertNotContains(response, self.their_student.last_name)

    def test_the_preview_still_works_for_this_school(self):
        """The fix must not break the legitimate preview it is guarding."""
        response = self.client.get(
            reverse("accounts:rollover_year"),
            {
                "source_year": str(self.our_year.pk),
                "target_year": str(self.our_target.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(
            response.context["source_year"],
            "scoping the lookup broke this school's own preview",
        )
        self.assertEqual(response.context["source_year"].pk, self.our_year.pk)


@override_settings(**HOST_ROUTED_SETTINGS)
class RolloverPrepareIsSchoolScopedTests(_TwoSchoolRolloverFixture):
    """The write path: a proposal filed under A must never contain B's students."""

    def test_preparing_from_another_school_s_year_creates_no_proposal(self):
        self.client.post(
            reverse("accounts:rollover_prepare"),
            {
                "source_year": str(self.their_year.pk),
                "target_year": str(self.their_target.pk),
            },
        )
        self.assertFalse(
            RolloverProposal.objects.filter(source_year=self.their_year).exists(),
            "a rollover proposal was built from another school's academic year",
        )

    def test_no_proposal_item_ever_points_at_another_school_s_student(self):
        """The assertion that survives a change of refusal shape.

        Whether the view 404s, redirects, or files an empty proposal, the invariant
        is the same: nothing filed under our school may reference their student.
        """
        self.client.post(
            reverse("accounts:rollover_prepare"),
            {
                "source_year": str(self.their_year.pk),
                "target_year": str(self.their_target.pk),
            },
        )
        leaked = RolloverProposalItem.objects.filter(student=self.their_student)
        self.assertFalse(
            leaked.exists(),
            "a proposal item points at another school's student; "
            f"proposals now on record: "
            f"{list(RolloverProposal.objects.values_list('pk', 'school_id', 'source_year_id'))}",
        )

    def test_preparing_from_this_school_s_year_still_works(self):
        """The positive case, so the fix is a bound and not a blanket refusal."""
        self.client.post(
            reverse("accounts:rollover_prepare"),
            {
                "source_year": str(self.our_year.pk),
                "target_year": str(self.our_target.pk),
            },
        )
        proposal = RolloverProposal.objects.filter(source_year=self.our_year).first()
        self.assertIsNotNone(
            proposal,
            "scoping the year lookup broke this school's own rollover preparation",
        )
        self.assertEqual(proposal.school_id, self.ours.pk)
        self.assertTrue(
            RolloverProposalItem.objects.filter(
                proposal=proposal, student=self.our_student
            ).exists(),
            "the proposal was created but did not pick up this school's own student",
        )


class RolloverCohortCarriesTheSchoolTermTests(TestCase):
    """Defence in depth inside the task: which students a proposal may contain.

    The view now refuses a foreign year, so this asserts the layer BEHIND that.
    Two properties, and they pull in opposite directions -- which is the whole
    reason the term is NULL-inclusive rather than strict:

    1. a student whose school is a DIFFERENT school must be excluded, even when
       their academic_year is the year being rolled over (a corrupt cross-link,
       and the shape a legacy shared year produces at scale -- AcademicYear.school
       is itself nullable, so several schools can reference one year);
    2. a student whose school is NULL must be RETAINED. StudentProfile.school is
       nullable, and a rollover MOVES and graduates people, so an unattributed
       student silently left behind is worse than one listed for review.

    A strict `school=school` would satisfy (1) and break (2).
    """

    def setUp(self):
        self.ours = School.objects.create(
            name="Cohort ours", slug="cohort-ours",
            subdomain="cohort-ours", is_active=True,
        )
        self.theirs = School.objects.create(
            name="Cohort theirs", slug="cohort-theirs",
            subdomain="cohort-theirs", is_active=True,
        )
        self.source = AcademicYear.objects.create(
            school=self.ours, name="Cohort 2024/2025",
            start_date=timezone.localdate() - timedelta(days=400),
            end_date=timezone.localdate() - timedelta(days=40),
            is_active=False,
        )
        self.target = AcademicYear.objects.create(
            school=self.ours, name="Cohort 2025/2026",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        self.mine = self._student(self.ours, "MINE")
        self.foreign = self._student(self.theirs, "FOREIGN")
        self.orphan = self._student(None, "ORPHAN")

    def _student(self, school, tag):
        # Every one of the three sits in OUR source year on purpose: the year
        # filter is not what separates them, the school term is.
        return StudentProfile.objects.create(
            school=school,
            academic_year=self.source,
            first_name=tag.capitalize(),
            last_name="Cohort",
            student_code=f"CO-{tag}",
            is_active=True,
        )

    def _run(self):
        from apps.accounts.tasks import _prepare_rollover_proposal_impl

        result = _prepare_rollover_proposal_impl(
            self.ours.pk, self.source.pk, self.target.pk
        )
        self.assertTrue(result.get("ok"), result)
        proposal = RolloverProposal.objects.get(pk=result["proposal_id"])
        return set(
            RolloverProposalItem.objects.filter(proposal=proposal).values_list(
                "student_id", flat=True
            )
        )

    def test_a_different_school_s_student_is_excluded(self):
        picked = self._run()
        self.assertNotIn(
            self.foreign.pk,
            picked,
            "a student belonging to another school was selected for this "
            "school's rollover -- they would be moved and possibly graduated",
        )

    def test_a_school_less_student_is_retained(self):
        picked = self._run()
        self.assertIn(
            self.orphan.pk,
            picked,
            "an unattributed (school=NULL) student was dropped from the "
            "rollover; a strict school= term causes exactly this, and the "
            "student is silently left behind in a closed year",
        )

    def test_the_cohort_is_exactly_ours_plus_the_orphan(self):
        self.assertEqual(self._run(), {self.mine.pk, self.orphan.pk})


class TeacherOrgTreeUsesItsOwnSchoolYearTests(TestCase):
    """`_teacher_org_tree` takes a user, and User has no school column.

    `get_active_year_and_term` resolves `years.order_by("id").first()`, so the
    EARLIEST-created active year wins when no school is passed. The other school
    is therefore created first here: that is what makes the wrong answer the
    default rather than a coincidence.

    The failure mode is silence, not a leak -- every assignment in the tree is
    filtered by this year, so a foreign year yields an empty tree and no error.
    """

    def setUp(self):
        # created FIRST -> lower id -> an unscoped read returns THIS one
        self.theirs = School.objects.create(
            name="Org theirs", slug="org-theirs",
            subdomain="org-theirs", is_active=True,
        )
        self.their_year = AcademicYear.objects.create(
            school=self.theirs, name="Org theirs 2025/2026",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        self.ours = School.objects.create(
            name="Org ours", slug="org-ours",
            subdomain="org-ours", is_active=True,
        )
        self.our_year = AcademicYear.objects.create(
            school=self.ours, name="Org ours 2025/2026",
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() + timedelta(days=300),
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="org_teacher", password="pass1234", role=User.Role.TEACHER
        )

    def test_the_year_comes_from_the_teacher_profile_school(self):
        from apps.people.models import TeacherProfile

        from apps.accounts.views import _teacher_org_tree

        TeacherProfile.objects.create(user=self.user, school=self.ours)
        tree = _teacher_org_tree(self.user)
        self.assertIsNotNone(tree)
        self.assertEqual(
            tree["academic_year"].pk,
            self.our_year.pk,
            "the org tree resolved another school's active year; every "
            "assignment it renders is filtered by this year, so the teacher "
            "would see an empty tree with nothing logged",
        )

    def test_a_school_less_profile_falls_back_to_the_primary_membership(self):
        from apps.people.models import TeacherProfile

        from apps.accounts.views import _teacher_org_tree

        TeacherProfile.objects.create(user=self.user, school=None)
        SchoolMembership.objects.create(
            user=self.user, school=self.ours,
            role=User.Role.TEACHER, is_primary=True,
        )
        tree = _teacher_org_tree(self.user)
        self.assertIsNotNone(tree)
        self.assertEqual(tree["academic_year"].pk, self.our_year.pk)
