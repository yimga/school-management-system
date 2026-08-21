"""Below the confidence threshold, a corroborated filename beats a generic match.

Every candidate list in this file is VERBATIM production output from bundle 84
(`classify_domain` run on the tenant's own artifacts on 2026-08-21). No
reconstruction, no invented headers.

The failure it pins:

    subjects_2026.xlsx   headers: ['title', 'description', 'category']
      behavior    0.40  matched ['category', 'description']
      academics   0.25  matched ['subject_name']
      -> chosen: behavior   (method: fallback)

``behavior`` won on two purely descriptive columns; ``academics`` had the one
column that identifies anything. The confidence threshold is 0.70, so BOTH were
below it -- the columns themselves said "not sure" -- and the AI arbitrator that
is supposed to settle exactly this could not run (ollama unavailable on the
cloud host, litellm refused as data_tier_disallowed). The fallback then took the
top scorer.

Consequence: the subjects artifact was applied by the sections lander, all 108
rows were rejected "missing section_code/name" while the name sat in
custom_fields.title, and 326 students referencing sections that were never
created were held as invalid_ref.

The rule added: in the fallback ONLY, prefer the filename's domain when the
columns corroborate it with a canonical field that no other domain claims. Two
independent signals agreeing beats one weak signal alone. An uncorroborated
filename changes nothing.
"""

from django.test import SimpleTestCase

from apps.migration_cloud.classifiers.domain import (
    DomainCandidate,
    _filename_led_fallback,
    _uniquely_owned_fields,
)


def _ranked(rows):
    return [DomainCandidate(d, c, list(m), "") for d, c, m in rows]


# --- verbatim production candidate lists, bundle 84 -----------------------
SUBJECTS = _ranked([
    ("behavior", 0.4, ["category", "description"]),
    ("academics", 0.25, ["subject_name"]),
    ("specialties", 0.25, ["description"]),
    ("events", 0.2, ["name"]),
    ("library", 0.167, ["title"]),
])
STUDENTS = _ranked([
    ("students", 0.429, ["admission_number", "full_name", "date_of_birth",
                         "gender", "grade_level", "specialty"]),
    ("specialties", 0.4, ["name"]),
    ("events", 0.2, ["name"]),
    ("enrollment", 0.167, ["homeroom"]),
    ("library", 0.167, ["title"]),
])
SPECIALTIES = _ranked([
    ("academics", 0.5, ["subject_code", "department"]),
    ("specialties", 0.5, ["code", "department"]),
    ("staff", 0.111, ["department"]),
])


class RealBundle84Tests(SimpleTestCase):
    def test_the_subjects_file_no_longer_lands_in_behavior(self):
        # The defect that cost 434 held rows.
        self.assertEqual(SUBJECTS[0].domain, "behavior", "guard: real top scorer")
        self.assertEqual(_filename_led_fallback("subjects_2026.xlsx", SUBJECTS), "academics")

    def test_the_specialties_file_is_also_corrected(self):
        self.assertEqual(SPECIALTIES[0].domain, "academics", "guard: real top scorer")
        self.assertEqual(
            _filename_led_fallback("specialties_2026.xlsx", SPECIALTIES), "specialties"
        )

    def test_the_student_file_is_left_exactly_as_it_was(self):
        # It was already right. A fix that changes a correct answer is a new bug.
        self.assertEqual(_filename_led_fallback("student_2026.xlsx", STUDENTS), "students")


class CorroborationIsRequiredTests(SimpleTestCase):
    def test_a_filename_with_no_matching_candidate_changes_nothing(self):
        self.assertIsNone(_filename_led_fallback("attendance_2026.xlsx", SUBJECTS))

    def test_a_filename_whose_domain_matched_only_shared_fields_changes_nothing(self):
        # specialties matched only `description`, which behavior also owns.
        # A filename alone must never be enough.
        self.assertIsNone(_filename_led_fallback("specialties.xlsx", SUBJECTS))

    def test_a_filename_with_no_recognisable_entity_token_changes_nothing(self):
        self.assertIsNone(_filename_led_fallback("export_2026_final.xlsx", SUBJECTS))

    def test_an_empty_ranking_changes_nothing(self):
        self.assertIsNone(_filename_led_fallback("subjects_2026.xlsx", []))


class UniquelyOwnedFieldsTests(SimpleTestCase):
    """The corroboration signal itself."""

    def test_subject_name_belongs_only_to_academics(self):
        self.assertEqual(_uniquely_owned_fields().get("subject_name"), "academics")

    def test_admission_number_belongs_only_to_students(self):
        self.assertEqual(_uniquely_owned_fields().get("admission_number"), "students")

    def test_shared_fields_are_not_treated_as_evidence(self):
        unique = _uniquely_owned_fields()
        for shared in ("description", "department", "name"):
            with self.subTest(field=shared):
                self.assertIsNone(
                    unique.get(shared),
                    msg="a field several domains claim cannot identify one of them",
                )

    def test_the_signal_is_symmetric_not_special_cased(self):
        # `category` is owned only by behavior, so a genuine behaviour file named
        # for it gets the same benefit. This is a rule, not a patch for one file.
        self.assertEqual(_uniquely_owned_fields().get("category"), "behavior")


class DefaultWorkbookNamesAreNotEvidenceTests(SimpleTestCase):
    """An unrenamed spreadsheet is the absence of a label, not a label.

    Making the filename hint stronger widened the blast radius of this: "Book1"
    hits the `book` token (-> library) and the FRENCH default "Classeur1" hits
    `class` (-> sections). On a francophone school's upload that turns "nobody
    renamed the file" into a confident wrong domain.
    """

    def _guess(self, name):
        from apps.migration_cloud.accelerators.runmycampus_canonical import (
            guess_domain_from_filename,
        )

        return guess_domain_from_filename(name)

    def test_every_locale_default_yields_no_hint(self):
        for name in ("Book1.xlsx", "Classeur1.xlsx", "Feuille1.xlsx", "Mappe1.xlsx",
                     "Tabelle1.xlsx", "Libro1.xlsx", "Hoja1.xlsx", "Foglio1.xlsx",
                     "Planilha1.xlsx", "sheet1.csv", "Untitled.xlsx", "Workbook1.xlsx"):
            with self.subTest(name=name):
                self.assertEqual(self._guess(name), "")

    def test_the_french_default_no_longer_reads_as_sections(self):
        # The one most likely to hit this deployment.
        self.assertEqual(self._guess("Classeur1.xlsx"), "")

    def test_a_deliberately_named_file_still_gives_its_hint(self):
        self.assertEqual(self._guess("subjects_2026.xlsx"), "academics")
        self.assertEqual(self._guess("classes_2026.xlsx"), "sections")
        self.assertEqual(self._guess("student_2026.xlsx"), "students")

    def test_a_real_book_catalogue_is_not_suppressed(self):
        # The guard must catch defaults, not every filename containing a stem.
        self.assertEqual(self._guess("book_inventory.xlsx"), "library")

    def test_a_default_name_produces_no_filename_led_fallback_either(self):
        self.assertIsNone(_filename_led_fallback("Classeur1.xlsx", SUBJECTS))
