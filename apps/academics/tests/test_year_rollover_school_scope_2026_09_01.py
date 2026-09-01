"""Year rollover must scope classroom codes to the school that owns the year.

Two defects, both in ``apps.academics.services_year_setup.clone_academic_year``,
and both reachable only on a SHARED-SCHEMA deployment. A sovereign edge box runs
RLS in one schema, so every tenant's rows sit in the same table; the cloud runs
schema-per-tenant, where the search_path already fences every query. The edge is
the deployment these tests are about.

1. The "is this code taken?" probe ran GLOBALLY. ``Classroom.code`` is unique per
   SCHOOL (``uniq_classroom_school_code``, academics migration 0085), never
   globally, so on a shared schema the probe answered a question about a
   STRANGER's row and pushed this school's classroom onto a different code.

2. The ``get_or_create`` below it passed no ``school`` at all -- not in the
   lookup, not in ``defaults`` -- so every classroom a rollover created was an
   ORPHAN (``school_id IS NULL``). ``Classroom.school`` is ``null=True``, so
   nothing in the schema refused it. The cloned ``Term`` and ``SubjectAssignment``
   rows carry the same nullable ``school`` and had the same hole.

What an orphan row actually does here, established rather than assumed:

* App layer -- 39 call sites read classrooms as
  ``Classroom.objects.filter(school=<school>, ...)``. ``school_id = X`` is FALSE
  for a NULL, so an orphan is invisible to all of them: the hub class count, the
  OneRoster export, the comms group picker, the teaching-grid provisioner. The
  rollover reports "N classrooms created" and the school sees none of them.
  ``test_cloned_classrooms_are_visible_to_school_scoped_reads`` pins this.
* DB layer, on a forced-RLS Postgres edge -- the academics policy
  (``academics/0038_rls_policy_default_deny``) is
  ``school_id::text = current_setting('app.current_school_id')``, which is NULL,
  not TRUE, for a NULL ``school_id`` -- in ``USING`` and in ``WITH CHECK`` alike.
  An orphan would be invisible to every tenant AND the INSERT that made it would
  be refused. NOT asserted here: this suite runs on SQLite, and
  ``academics_classroom`` appears in no ``FORCE ROW LEVEL SECURITY`` migration
  today, so the app layer above is the gate that actually bites.

Do NOT restate the orphan assertions as ``.exclude(school=X)``.
``NOT (school_id = X)`` evaluates to NULL -- not true -- for exactly the NULL
rows being hunted, so they drop out of the queryset meant to catch them. These
tests compare in Python.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.services_year_setup import clone_academic_year
from apps.schools.models import School


def _make_school(slug: str, name: str, **extra) -> School:
    """A School with an explicit subdomain.

    ``School.subdomain`` is unique, and a blank one is unique too -- so the
    SECOND school created without one is what crashes, not the first.
    """
    return School.objects.create(
        name=name,
        slug=slug,
        subdomain=slug,
        country_code="CM",
        **extra,
    )


class YearRolloverSchoolScopeTests(TestCase):
    """clone_academic_year with a rival tenant sitting on the derived code."""

    def setUp(self):
        self.mine = _make_school("roll-mine-0901", "Rollover Mine", is_active=True)
        self.rival = _make_school("roll-rival-0901", "Rollover Rival", is_active=True)

        self.my_dept = Department.objects.create(
            school=self.mine, name="General", code="GEN"
        )
        self.rival_dept = Department.objects.create(
            school=self.rival, name="General", code="GEN"
        )

        self.from_year = AcademicYear.objects.create(
            school=self.mine,
            name="2024/2025",
            start_date="2024-09-01",
            end_date="2025-06-30",
        )
        self.to_year = AcademicYear.objects.create(
            school=self.mine,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )
        self.source_class = Classroom.objects.create(
            school=self.mine,
            academic_year=self.from_year,
            department=self.my_dept,
            name="Form 1",
            code="F1",
        )
        # clone_academic_year derives "<code>-<suffix>", suffix = the target year
        # name with "/" and spaces stripped, truncated to 8.
        self.contested_code = "F1-20252026"

        self.rival_year = AcademicYear.objects.create(
            school=self.rival,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )
        self.rival_class = Classroom.objects.create(
            school=self.rival,
            academic_year=self.rival_year,
            department=self.rival_dept,
            name="Rival Form 1",
            code=self.contested_code,
        )

    def _assert_trap_armed(self):
        """A cross-tenant test proves nothing unless the rival row is selectable.

        Assert the rival exists, that the importing school does NOT hold the
        code, and that the unscoped probe really resolves the rival's row. A
        suite whose rival is absent goes green for the wrong reason and stays
        green through the mutation it is supposed to catch.
        """
        self.assertEqual(
            Classroom.objects.filter(
                school=self.rival, code=self.contested_code
            ).count(),
            1,
            "the rival school must hold exactly one classroom on the contested code",
        )
        self.assertEqual(
            Classroom.objects.filter(
                school=self.mine, code=self.contested_code
            ).count(),
            0,
            "the importing school must NOT already hold the contested code",
        )
        unscoped = list(Classroom.objects.filter(code=self.contested_code))
        self.assertEqual(
            [c.pk for c in unscoped],
            [self.rival_class.pk],
            "the UNSCOPED probe must really resolve the rival's row, or the "
            "scoping under test is never exercised",
        )

    def _clone_classrooms_only(self):
        return clone_academic_year(
            self.from_year,
            self.to_year,
            copy_terms=False,
            copy_subject_assignments=False,
            copy_promotion_rules=False,
        )

    def test_rival_tenant_cannot_push_my_classroom_onto_another_code(self):
        self._assert_trap_armed()
        stats = self._clone_classrooms_only()
        self.assertEqual(stats["classrooms_created"], 1)
        cloned = Classroom.objects.get(academic_year=self.to_year)
        self.assertEqual(
            cloned.code,
            self.contested_code,
            "the rollover took a code decision from a DIFFERENT tenant's row; "
            "Classroom.code is unique per school, not globally, so the rival "
            "holding this code says nothing about whether this school may use it",
        )

    def test_cloned_classrooms_belong_to_the_school_that_owns_the_year(self):
        self._assert_trap_armed()
        self._clone_classrooms_only()
        cloned = list(Classroom.objects.filter(academic_year=self.to_year))
        self.assertEqual(len(cloned), 1)
        orphans = [c for c in cloned if c.school_id is None]
        self.assertEqual(
            orphans,
            [],
            "the rollover created classrooms owned by NOBODY (school_id IS NULL); "
            "compared in Python because .exclude(school=X) drops NULL rows",
        )
        self.assertEqual([c.school_id for c in cloned], [self.mine.id])

    def test_cloned_classrooms_are_visible_to_school_scoped_reads(self):
        self._clone_classrooms_only()
        self.assertEqual(
            Classroom.objects.filter(
                school=self.mine, academic_year=self.to_year
            ).count(),
            1,
            "an orphan row is invisible to every school-scoped read in the app "
            "(hub counts, OneRoster export, comms pickers, teaching grid): the "
            "rollover reports success and the school sees nothing",
        )

    def test_cloned_terms_and_subject_assignments_carry_the_school(self):
        term = Term.objects.create(
            school=self.mine,
            academic_year=self.from_year,
            name="FIRST",
            position=1,
            start_date="2024-09-01",
            end_date="2024-12-15",
        )
        specialty = Specialty.objects.create(
            school=self.mine, department=self.my_dept, name="General", code="GENSP"
        )
        subject = Subject.objects.create(school=self.mine, name="Mathematics")
        SubjectAssignment.objects.create(
            school=self.mine,
            academic_year=self.from_year,
            term=term,
            classroom=self.source_class,
            specialty=specialty,
            subject=subject,
        )

        clone_academic_year(self.from_year, self.to_year, copy_promotion_rules=False)

        new_terms = list(Term.objects.filter(academic_year=self.to_year))
        self.assertTrue(new_terms, "no term was cloned; the assertion below is vacuous")
        self.assertEqual(
            [t.pk for t in new_terms if t.school_id is None],
            [],
            "cloned Terms are orphans (school_id IS NULL)",
        )

        new_rows = list(SubjectAssignment.objects.filter(academic_year=self.to_year))
        self.assertTrue(
            new_rows, "no subject assignment was cloned; the assertion below is vacuous"
        )
        self.assertEqual(
            [s.pk for s in new_rows if s.school_id is None],
            [],
            "cloned SubjectAssignments are orphans (school_id IS NULL)",
        )

    def test_running_the_rollover_twice_is_idempotent(self):
        """A re-run must match its own output, not escalate onto a fallback code.

        The probe asks whether the derived code is already taken. Rows in the
        TARGET year are this clone's own output, so counting them made run 2
        rename its own classroom and clone the year a second time. Scoping the
        probe to the school without also excluding the target year would have
        left that intact.
        """
        first = self._clone_classrooms_only()
        self.assertEqual(first["classrooms_created"], 1)

        second = self._clone_classrooms_only()
        self.assertEqual(
            second["classrooms_created"],
            0,
            "a second rollover into the same year must match the first run's "
            "classroom instead of minting a renamed duplicate",
        )
        self.assertEqual(
            Classroom.objects.filter(academic_year=self.to_year).count(),
            1,
            "the target year holds one classroom per source classroom",
        )

    def test_a_pre_fix_orphan_in_the_target_year_does_not_break_a_re_run(self):
        """The rows the OLD code left behind must not blow up the new code.

        Any tenant that ran a rollover before this fix has orphan Terms and
        Classrooms sitting in the target year. The new lookups are
        school-scoped, so they do not match those orphans -- this pins what
        happens when they collide with a natural key that is NOT school-scoped
        (Term.unique_together is (academic_year, name)). Healing the orphans
        themselves would need a data migration and is out of scope here.
        """
        Term.objects.create(
            school=None,
            academic_year=self.to_year,
            name="FIRST",
            position=1,
            start_date="2025-09-01",
            end_date="2025-12-15",
        )
        Classroom.objects.create(
            school=None,
            academic_year=self.to_year,
            department=self.my_dept,
            name="Form 1",
            code=self.contested_code,
        )
        Term.objects.create(
            school=self.mine,
            academic_year=self.from_year,
            name="FIRST",
            position=1,
            start_date="2024-09-01",
            end_date="2024-12-15",
        )

        clone_academic_year(
            self.from_year,
            self.to_year,
            copy_subject_assignments=False,
            copy_promotion_rules=False,
        )

        owned = [
            c
            for c in Classroom.objects.filter(academic_year=self.to_year)
            if c.school_id == self.mine.id
        ]
        self.assertEqual(
            len(owned),
            1,
            "the re-run must still produce exactly one classroom this school owns",
        )

    def test_rollover_leaves_the_rival_tenant_untouched(self):
        self._assert_trap_armed()
        self._clone_classrooms_only()
        self.rival_class.refresh_from_db()
        self.assertEqual(self.rival_class.school_id, self.rival.id)
        self.assertEqual(self.rival_class.code, self.contested_code)
        self.assertEqual(
            Classroom.objects.filter(school=self.rival).count(),
            1,
            "the rollover must not create or adopt rows for another tenant",
        )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ProvisioningClassroomSeedScopeTests(TestCase):
    """apps/schools/tasks.py: a near-impossible probe with a real veto.

    The seed builds the code from the school slug and ``School.slug`` is
    ``unique=True``, so a natural cross-tenant collision is near-impossible. The
    CONSEQUENCE of a hit is not: the loop ``continue``s, silently skipping the
    classroom and leaving the created-counter un-incremented, so the school is
    provisioned a classroom short with no event, no log and no error. This test
    plants the collision the slug makes unlikely, because scoping the probe
    costs nothing and the veto costs a classroom.
    """

    def setUp(self):
        self.mine = _make_school("seed-a-0901", "Seed Scope A", is_active=False)
        self.rival = _make_school("seed-b-0901", "Seed Scope B", is_active=True)

        # The exact code apps/schools/tasks.py derives for `mine`.
        self.contested_code = "seed-a-0901-GEN-C1"

        rival_dept = Department.objects.create(
            school=self.rival, name="General", code="RIVGEN"
        )
        rival_year = AcademicYear.objects.create(
            school=self.rival,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )
        self.rival_class = Classroom.objects.create(
            school=self.rival,
            academic_year=rival_year,
            department=rival_dept,
            name="Rival Seeded",
            code=self.contested_code,
        )

    def _assert_trap_armed(self):
        self.assertEqual(
            Classroom.objects.filter(
                school=self.rival, code=self.contested_code
            ).count(),
            1,
            "the rival must hold the contested seed code",
        )
        self.assertEqual(
            Classroom.objects.filter(
                school=self.mine, code=self.contested_code
            ).count(),
            0,
            "the school being provisioned must not already hold it",
        )
        unscoped = list(Classroom.objects.filter(code=self.contested_code))
        self.assertEqual(
            [c.pk for c in unscoped],
            [self.rival_class.pk],
            "the UNSCOPED seed probe must really resolve the rival's row",
        )

    def test_a_rival_holding_the_code_cannot_veto_the_seeded_classroom(self):
        self._assert_trap_armed()
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.mine.id), contact_email="owner@seed.test")

        self.assertTrue(
            Classroom.objects.filter(
                school=self.mine, code=self.contested_code
            ).exists(),
            "provisioning silently skipped a classroom because ANOTHER tenant "
            "held its code; Classroom.code is unique per school, not globally",
        )

    def test_slug_is_embedded_in_the_seeded_classroom_code(self):
        """The premise of "near-impossible": the code is namespaced by slug.

        School.slug is unique=True, so a code built from it cannot collide with
        another live school's seeded code. If this stops holding, the veto above
        stops being near-impossible and becomes reachable.
        """
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.mine.id), contact_email="owner@seed.test")

        seeded = list(Classroom.objects.filter(school=self.mine))
        self.assertTrue(seeded, "provisioning seeded no classrooms at all")
        namespaced = [c for c in seeded if self.mine.slug in c.code]
        self.assertTrue(
            namespaced,
            "no seeded classroom code embeds the school slug -- the collision "
            "argument for this call site no longer holds",
        )
