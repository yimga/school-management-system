"""Field-mapper recall — real student columns + multi-word synonym containment.

Closes the "0% / custom_field" mis-mapping the operator reported on the live
Migration Cloud (student roster: "Place of Birth", "Joining Date", "Mobile
Number" all landing at 0% custom_field even though StudentProfile has real
columns / an existing ``phone`` canonical field). Two seals:

1. **Ontology** — every real ``StudentProfile`` column an SIS export carries
   inline (place_of_birth / joined_date / joined_term / section / parent_phone /
   exam_candidate_number / exam_center_code) now has a canonical field, so it
   maps to its proper home instead of quarantining as a custom field.

2. **Containment scorer** — a header that fully WRAPS a specific synonym
   ("Mobile Number" ⊇ "mobile") now clears the 0.80 field_min_confidence, which
   plain Jaccard (0.375) never could — WITHOUT firing on an unrelated header
   ("Class Teacher" must NOT collapse onto grade_level's "class" synonym).

DB-free: only the ontology + pure scoring functions are exercised.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud import mapper
from apps.migration_cloud.ontology import all_synonyms, iter_canonical_fields
from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY

_THRESHOLD = 0.80  # migration_cloud.mapper.field_min_confidence seed default


def _top(header: str, inferred_type: str = "string"):
    fields = list(iter_canonical_fields("students"))
    ranked = mapper._score_token_similarity(
        header, fields, "students", inferred_type, artifact=None
    )
    return ranked[0] if ranked else None


class RealStudentColumnsInOntologyTests(SimpleTestCase):
    """The real StudentProfile columns must exist as canonical student fields."""

    def test_new_real_columns_are_canonical_fields(self):
        students = CANONICAL_ONTOLOGY["students"]
        for field in (
            "place_of_birth",
            "joined_date",
            "joined_term",
            "section",
            "parent_phone",
            "exam_candidate_number",
            "exam_center_code",
        ):
            self.assertIn(field, students, f"{field} missing from students ontology")

    def test_multi_word_forms_are_exact_synonyms(self):
        # These normalized headers are the exact-alias fast path (0.98).
        self.assertIn("mobile_number", all_synonyms("phone", domain="students"))
        self.assertIn("place_of_birth", all_synonyms("place_of_birth", domain="students"))
        self.assertIn("joining_date", all_synonyms("joined_date", domain="students"))
        self.assertIn("date_of_admission", all_synonyms("joined_date", domain="students"))


class ContainmentRecallTests(SimpleTestCase):
    """Multi-word headers wrapping a specific synonym clear the threshold."""

    def test_cell_phone_maps_to_phone(self):
        top = _top("cell_phone")
        self.assertIsNotNone(top)
        self.assertEqual(top["cf"]["canonical_field"], "phone")
        self.assertGreaterEqual(top["score"], _THRESHOLD)
        self.assertEqual(top["method"], "phrase")

    def test_telephone_no_maps_to_phone(self):
        top = _top("telephone_no")
        self.assertEqual(top["cf"]["canonical_field"], "phone")
        self.assertGreaterEqual(top["score"], _THRESHOLD)

    def test_town_of_birth_maps_to_place_of_birth(self):
        top = _top("town_of_birth")
        self.assertEqual(top["cf"]["canonical_field"], "place_of_birth")
        self.assertGreaterEqual(top["score"], _THRESHOLD)

    def test_guardian_contact_maps_to_parent_phone(self):
        top = _top("guardian_contact")
        self.assertEqual(top["cf"]["canonical_field"], "parent_phone")
        self.assertGreaterEqual(top["score"], _THRESHOLD)


class ContainmentGuardTests(SimpleTestCase):
    """The scorer must NOT over-fire on headers that merely share a token."""

    def test_class_teacher_does_not_map_to_grade_level(self):
        # "class" is a grade_level synonym, but "Class Teacher" is a staff name.
        top = _top("class_teacher")
        if top is not None:
            self.assertLess(
                top["score"],
                _THRESHOLD,
                f"class_teacher wrongly matched {top['cf']['canonical_field']}",
            )

    def test_marital_status_does_not_map_to_enrollment_status(self):
        top = _top("marital_status")
        if top is not None:
            self.assertLess(top["score"], _THRESHOLD)

    def test_all_generic_synonym_cannot_anchor_containment(self):
        # A synonym made only of generic filler ("number") never anchors a match.
        strength, _syn = mapper._containment_strength({"admission", "number"}, ["number"])
        self.assertEqual(strength, 0.0)

    def test_specific_token_with_filler_is_strong(self):
        strength, syn = mapper._containment_strength({"mobile", "number"}, ["mobile"])
        self.assertEqual(syn, "mobile")
        self.assertGreaterEqual(strength, 0.90)

    def test_specific_token_with_unrelated_extra_is_weak(self):
        # "form" is specific, but "form teacher" carries an unrelated token.
        strength, _syn = mapper._containment_strength({"form", "teacher"}, ["form"])
        self.assertLess(strength, 0.80)
