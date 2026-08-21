"""A filename must not overrule columns that plainly disagree with it.

Bundle 84, production. A francophone technical-school SUBJECTS file -- columns
``title`` / ``description`` / ``category`` / ``coef``, values like
"FABRICATION ANALYSIS", "PLUMBING PROJECT MANAGEMENT", "APPLIED MECHANICS" --
was classified as ``sections`` because its filename carried a class/section
token. ``academics`` and ``sections`` share the CATALOG_DOMAINS ambiguous group,
so ``reconcile_domain_with_filename`` handed the win to the filename.

The columns were not ambiguous at all. ``academics.subject_name`` lists ``title``
as a synonym and ``academics.credits`` lists ``coef``; ``sections`` has no field
matching title, description or category. The content evidence was one-sided and
was discarded anyway.

Consequences, in order:

  * 108 sections rejected: "missing section_code/name" -- while the name sat in
    ``custom_fields.title``, because the mapper had filed it as a tracked custom
    field rather than the section name.
  * 326 students then failed ``invalid_ref``, pointing at sections that were
    never created.
  * 434 held rows, from one filename token.

The function's own docstring called it a tie-breaker. It never checked for a
tie. It does now -- but only when the caller supplies scores, so every existing
two-argument caller keeps the documented person-roster behaviour.

DB-free.
"""

from django.test import SimpleTestCase

from apps.migration_cloud.accelerators.runmycampus_canonical import (
    _FILENAME_OVERRIDE_MAX_MARGIN,
    reconcile_domain_with_filename,
)


class TheDocumentedBehaviourIsUnchangedTests(SimpleTestCase):
    """Two-argument callers must behave exactly as before."""

    def test_a_teacher_roster_scoring_students_still_resolves_to_staff(self):
        self.assertEqual(
            reconcile_domain_with_filename("teachers_2026-01-18.csv", "students"),
            "staff",
        )

    def test_a_specialties_file_scoring_academics_still_resolves_to_specialties(self):
        self.assertEqual(
            reconcile_domain_with_filename("specialties_2026.csv", "academics"),
            "specialties",
        )

    def test_content_outside_the_shared_group_still_wins(self):
        self.assertEqual(
            reconcile_domain_with_filename("student_grades.csv", "grades"), "grades"
        )

    def test_no_content_domain_is_still_none(self):
        self.assertIsNone(reconcile_domain_with_filename("teachers.csv", None))


class AFilenameMayOnlyBreakARealTieTests(SimpleTestCase):
    """With scores supplied, the columns win when they are not actually tied."""

    # The live case: academics scored on title + coef, sections on almost nothing.
    LOPSIDED = {"academics": 0.82, "sections": 0.34}
    # A genuine tie: the person-roster overlap the override exists for.
    TIED = {"students": 0.71, "staff": 0.66}

    def test_the_production_misclassification_no_longer_happens(self):
        self.assertEqual(
            reconcile_domain_with_filename(
                "classes_2026.csv", "academics", scores=self.LOPSIDED
            ),
            "academics",
        )

    def test_a_section_named_file_also_cannot_steal_a_strong_academics_score(self):
        self.assertEqual(
            reconcile_domain_with_filename(
                "sections.csv", "academics", scores=self.LOPSIDED
            ),
            "academics",
        )

    def test_a_genuine_tie_is_still_broken_by_the_filename(self):
        # This is the case the override was written for and must keep working.
        self.assertEqual(
            reconcile_domain_with_filename(
                "teachers_2026.csv", "students", scores=self.TIED
            ),
            "staff",
        )

    def test_the_boundary_is_inclusive_so_an_exact_margin_still_overrides(self):
        scores = {"students": 0.70, "staff": 0.70 - _FILENAME_OVERRIDE_MAX_MARGIN}
        self.assertEqual(
            reconcile_domain_with_filename(
                "teachers_2026.csv", "students", scores=scores
            ),
            "staff",
        )

    def test_just_past_the_margin_the_columns_win(self):
        scores = {"students": 0.70, "staff": 0.70 - _FILENAME_OVERRIDE_MAX_MARGIN - 0.01}
        self.assertEqual(
            reconcile_domain_with_filename(
                "teachers_2026.csv", "students", scores=scores
            ),
            "students",
        )

    def test_a_hinted_domain_absent_from_the_scores_cannot_win(self):
        # Absent means it matched nothing at all — the weakest possible evidence.
        self.assertEqual(
            reconcile_domain_with_filename(
                "classes_2026.csv", "academics", scores={"academics": 0.9}
            ),
            "academics",
        )

    def test_scores_that_favour_the_filename_still_let_it_win(self):
        self.assertEqual(
            reconcile_domain_with_filename(
                "classes_2026.csv", "academics", scores={"academics": 0.4, "sections": 0.9}
            ),
            "sections",
        )

    def test_the_margin_is_a_tie_band_not_a_licence(self):
        # A tie-breaker that fires at any distance is not a tie-breaker; that is
        # precisely the bug. Keep the band narrow.
        self.assertGreater(_FILENAME_OVERRIDE_MAX_MARGIN, 0)
        self.assertLess(_FILENAME_OVERRIDE_MAX_MARGIN, 0.5)


class TheContentEvidenceWasNeverAmbiguousTests(SimpleTestCase):
    """Guard the ontology facts this fix depends on."""

    def _syn(self, domain, field):
        from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY

        return (CANONICAL_ONTOLOGY[domain][field].get("synonyms") or {}).get("en", [])

    def test_academics_claims_title_as_a_subject_name(self):
        self.assertIn("title", self._syn("academics", "subject_name"))

    def test_academics_claims_coef_as_credits(self):
        # The francophone technical-school shape this file came from.
        self.assertIn("coef", self._syn("academics", "credits"))

    def test_sections_claims_none_of_the_columns_in_that_file(self):
        from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY

        section_syns = {
            s
            for spec in CANONICAL_ONTOLOGY["sections"].values()
            for s in (spec.get("synonyms") or {}).get("en", [])
        }
        for header in ("title", "description", "category", "coef"):
            with self.subTest(header=header):
                self.assertNotIn(header, section_syns)
