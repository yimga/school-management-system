"""A resume must REPAIR the tenant, not freeze its damage in place.

Found by an A-Z provisioning audit (2026-07-16). Three seed steps shared one
root cause: ``get_or_create(defaults={...})`` IGNORES ``defaults`` when the row
already exists. So any state a partial first drive left behind was permanent —
the resume ran, reported success, and changed nothing.

  S7  ``Term`` carried ``is_active`` in ``defaults``. Terms seeded by an earlier
      partial drive (or by the structure/blueprint seeders, which never set it)
      left the year with NO active term. The teacher marks-entry surface resolves
      the current term and 403s without one => grade entry dead for the year.

  S8  ``AcademicYear`` has no single-active DB constraint and its name derives
      from ``start_month``. An academic-calendar config change between a failed
      drive and its resume mints a SECOND year, also is_active=True => every
      ``.get(is_active=True)`` caller raises MultipleObjectsReturned. A 500
      across the academic surfaces, caused by the repair.

  S9  The subject seed was gated on ``if not Subject.objects.filter(school)
      .exists()`` — all-or-nothing. A drive killed after writing 3 of 15 subjects
      meant every later resume saw "subjects exist" and skipped, so the tenant
      kept a partial subject list forever while the step reported success.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.academics.models import AcademicYear, Subject, SubjectAssignment, Term
from apps.schools.models import School


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ResumeLeavesAnActiveTermTests(TestCase):
    """S7 — a year without an active term is a dead grade-entry surface."""

    def setUp(self):
        self.school = School.objects.create(
            name="Term Repair Academy",
            slug="term-repair",
            subdomain="term-repair",
            is_active=False,
        )

    def test_resume_activates_a_term_left_inactive_by_a_partial_drive(self):
        from apps.schools.tasks import provision_school_sync

        # First drive lands the year + terms, but nothing active (the state a
        # partial drive / the structure seeder leaves behind).
        provision_school_sync(str(self.school.id), contact_email="o@term.test")
        year = AcademicYear.objects.filter(school=self.school).first()
        self.assertIsNotNone(year)
        Term.objects.filter(school=self.school, academic_year=year).update(
            is_active=False
        )
        # Re-open Phase B so the resume actually re-enters the seed.
        self.school.refresh_from_db()
        settings_blob = dict(self.school.settings or {})
        prov = dict(settings_blob.get("provisioning") or {})
        prov["phase_b_complete"] = False
        settings_blob["provisioning"] = prov
        self.school.settings = settings_blob
        self.school.save(update_fields=["settings"])

        provision_school_sync(str(self.school.id), contact_email="o@term.test")

        self.assertTrue(
            Term.objects.filter(
                school=self.school, academic_year=year, is_active=True
            ).exists(),
            "the resume must leave the year with an active term -- without one, "
            "teacher marks entry 403s and no grade can be entered all year",
        )

    def test_exactly_one_term_is_active(self):
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="o@term.test")
        year = AcademicYear.objects.filter(school=self.school).first()
        self.assertEqual(
            Term.objects.filter(
                school=self.school, academic_year=year, is_active=True
            ).count(),
            1,
        )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class SingleActiveAcademicYearTests(TestCase):
    """S8 — two active years is MultipleObjectsReturned on every read."""

    def setUp(self):
        self.school = School.objects.create(
            name="Year Guard Academy",
            slug="year-guard",
            subdomain="year-guard",
            is_active=False,
        )

    def test_a_pre_existing_active_year_is_demoted_not_duplicated(self):
        from apps.schools.tasks import provision_school_sync

        # A stale active year under a DIFFERENT name -- exactly what a start_month
        # change between a failed drive and its resume produces.
        AcademicYear.objects.create(
            school=self.school,
            name="1999/2000",
            start_date="1999-09-01",
            end_date="2000-08-31",
            is_active=True,
        )

        provision_school_sync(str(self.school.id), contact_email="o@year.test")

        active = AcademicYear.objects.filter(school=self.school, is_active=True)
        self.assertEqual(
            active.count(),
            1,
            "exactly one academic year may be active -- two makes every "
            ".get(is_active=True) raise MultipleObjectsReturned (a 500)",
        )
        self.assertNotEqual(
            active.first().name,
            "1999/2000",
            "the year this provision seeded must be the active one",
        )

    def test_the_seeded_year_is_active(self):
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="o@year.test")
        self.assertEqual(
            AcademicYear.objects.filter(school=self.school, is_active=True).count(), 1
        )


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class PartialSubjectSeedCompletesTests(TestCase):
    """S9 — a partial subject list must not be permanent."""

    def setUp(self):
        self.school = School.objects.create(
            name="Subject Repair Academy",
            slug="subject-repair",
            subdomain="subject-repair",
            is_active=False,
        )

    def test_resume_completes_a_partially_seeded_subject_list(self):
        from apps.schools.tasks import provision_school_sync

        # What a full seed produces, so the test asserts against ground truth
        # rather than a hardcoded expectation of the seed list's length.
        provision_school_sync(str(self.school.id), contact_email="o@subj.test")
        full_names = set(
            Subject.objects.filter(school=self.school).values_list("name", flat=True)
        )
        self.assertGreater(len(full_names), 1, "seed must produce several subjects")

        # Simulate a drive killed after writing only the first subject. The grid
        # goes first: SubjectAssignment.subject is a PROTECT FK, and a drive that
        # died mid-subject-seed never reached the grid step at all -- leaving the
        # rows here would model a state that cannot exist.
        survivor = sorted(full_names)[0]
        SubjectAssignment.objects.filter(school=self.school).delete()
        Subject.objects.filter(school=self.school).exclude(name=survivor).delete()
        self.assertEqual(Subject.objects.filter(school=self.school).count(), 1)
        self.school.refresh_from_db()
        settings_blob = dict(self.school.settings or {})
        prov = dict(settings_blob.get("provisioning") or {})
        prov["phase_b_complete"] = False
        settings_blob["provisioning"] = prov
        self.school.settings = settings_blob
        self.school.save(update_fields=["settings"])

        provision_school_sync(str(self.school.id), contact_email="o@subj.test")

        self.assertEqual(
            set(
                Subject.objects.filter(school=self.school).values_list(
                    "name", flat=True
                )
            ),
            full_names,
            "the resume must COMPLETE a partial subject seed -- the old "
            "exists() gate made a partial list permanent while reporting success",
        )

    def test_reseeding_creates_no_duplicates(self):
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(self.school.id), contact_email="o@subj.test")
        first = Subject.objects.filter(school=self.school).count()
        self.school.refresh_from_db()
        settings_blob = dict(self.school.settings or {})
        prov = dict(settings_blob.get("provisioning") or {})
        prov["phase_b_complete"] = False
        settings_blob["provisioning"] = prov
        self.school.settings = settings_blob
        self.school.save(update_fields=["settings"])

        provision_school_sync(str(self.school.id), contact_email="o@subj.test")

        self.assertEqual(
            Subject.objects.filter(school=self.school).count(),
            first,
            "the unconditional seed must stay idempotent",
        )
