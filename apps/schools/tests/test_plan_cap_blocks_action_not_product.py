"""A plan limit must block the excess enrolment, never the whole school.

Found while wiring the approved pricing model (2026-07-17).

``UsageLimitMiddleware`` is wired into the tenants MIDDLEWARE branch
(``config/settings.py:4081``) -- the branch that actually loads in production --
and ``DISABLE_USAGE_LIMIT_MIDDLEWARE`` is set nowhere. Its check lived in
``process_request``::

    count = StudentProfile.objects.filter(school=school).count()
    if count >= plan.max_students:
        return HttpResponseForbidden("Student limit reached for your plan.")

``process_request`` runs on EVERY request, so one school over its cap got 403
on every page: teachers could not take attendance, parents could not open a
report card, the bursar could not collect a franc. The school was not nudged to
upgrade -- it was bricked. Nobody has been burned only because of a second bug,
``if not plan: return None``: a plan-less school skips all caps, so the MISSING
plan was the thing protecting live tenants.

That also blocked our own revenue: the approved model takes a percentage of the
fees a school collects through our checkout, and a bricked school cannot reach
checkout. The lockout stops the school AND the take-rate.

So the cap moves to the action it is actually about -- creating the student that
would exceed it. Everything the school already depends on keeps working. This is
what Slack (hides history, keeps the workspace) and Shopify (stops new actions,
keeps the storefront) do.

SCOPE, honestly: the guard sits on ``StudentProfile.save()``/``TeacherProfile.save()``,
which is the only chokepoint all four enrolment paths share (portal onboarding,
bulk CSV import, admissions kernel, geos lane-2). ``bulk_create`` bypasses
``save()`` and is therefore NOT capped -- an operator bulk-importing is a
deliberate act, and failing an 800-row migration halfway is worse than letting
it land. Documented rather than silently missing.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import Plan


class _CappedSchoolFixture(TestCase):
    def _seed(self, slug: str, *, max_students=None):
        self.plan = Plan.objects.create(
            name=f"Capped {slug}",
            slug=f"capped-{slug}",
            max_students=max_students,
            included_features=[],
        )
        self.school = School.objects.create(
            name=f"{slug} High", slug=slug, subdomain=slug, plan=self.plan,
        )

    def _enrol(self, code: str):
        return StudentProfile.objects.create(
            school=self.school, first_name="S", last_name=code, student_code=code,
        )


class PlanCapBlocksTheEnrolmentTests(_CappedSchoolFixture):
    """The cap must refuse the student that exceeds it."""

    def setUp(self):
        self._seed("cap-two", max_students=2)

    def test_enrolling_within_the_cap_is_allowed(self):
        self._enrol("A-1")
        self._enrol("A-2")
        self.assertEqual(
            StudentProfile.objects.filter(school=self.school).count(), 2
        )

    def test_the_student_over_the_cap_is_refused(self):
        self._enrol("B-1")
        self._enrol("B-2")
        with self.assertRaises(ValidationError) as ctx:
            self._enrol("B-3")
        self.assertIn("limit", str(ctx.exception).lower())

    def test_the_refusal_does_not_lose_the_students_already_enrolled(self):
        self._enrol("C-1")
        self._enrol("C-2")
        with self.assertRaises(ValidationError):
            self._enrol("C-3")
        self.assertEqual(
            StudentProfile.objects.filter(school=self.school).count(), 2,
            "refusing the 3rd enrolment must not disturb the first 2",
        )

    def test_an_existing_student_can_still_be_edited_at_the_cap(self):
        """Being AT the cap must not freeze the records already there."""
        first = self._enrol("D-1")
        self._enrol("D-2")
        first.first_name = "Renamed"
        first.save()  # an UPDATE, not a new enrolment -- must not be capped
        first.refresh_from_db()
        self.assertEqual(first.first_name, "Renamed")


class AnUncappedPlanNeverBlocksTests(_CappedSchoolFixture):
    """Free core at any size -- the approved model."""

    def setUp(self):
        self._seed("uncapped", max_students=None)

    def test_a_school_larger_than_any_tier_still_enrols(self):
        for i in range(5):
            self._enrol(f"U-{i}")
        self.assertEqual(
            StudentProfile.objects.filter(school=self.school).count(), 5
        )


class APlanLessSchoolIsNeverBlockedTests(TestCase):
    """The current protection for live tenants must survive."""

    def test_plan_less_school_enrols_freely(self):
        school = School.objects.create(
            name="No Plan High", slug="no-plan", subdomain="no-plan"
        )
        self.assertIsNone(school.plan_id)
        for i in range(3):
            StudentProfile.objects.create(
                school=school, first_name="N", last_name=str(i),
                student_code=f"NP-{i}",
            )
        self.assertEqual(StudentProfile.objects.filter(school=school).count(), 3)


class TheDefaultPlanIsNotAFuseTests(TestCase):
    """The plan every new tenant binds to must not cap on school size.

    A school's size is fixed by its building -- it cannot grow into a plan the
    way a store grows sales, so a student cap either blocks it at signup or
    never binds. The approved model monetises the fees collected through the
    platform, not the school's size.

    This seeds the catalog rather than skipping when it is absent: the catalog
    is real production data (``scripts/release/render_predeploy.sh`` runs
    ``seed_subscription_catalog`` on EVERY deploy, and the seed OVERWRITES
    max_students from the spec), so the spec is the source of truth and a
    skipped assertion here would leave it unpinned.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_subscription_catalog")

    def test_a_default_plan_exists_at_all(self):
        self.assertIsNotNone(
            Plan.get_default_plan(),
            "no plan is marked is_default -- new tenants would bind to nothing",
        )

    def test_the_default_plan_does_not_cap_students(self):
        default = Plan.get_default_plan()
        self.assertIsNone(
            default.max_students,
            f"the default plan {default.slug!r} caps students at "
            f"{default.max_students} -- every school binding to it gets a fuse, "
            "and free core is meant to work at any size",
        )

    def test_the_default_plan_does_not_cap_staff(self):
        default = Plan.get_default_plan()
        self.assertIsNone(default.max_staff, "same reasoning as max_students")
