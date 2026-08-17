"""Discoverability guard (2026-08-16 gap-analysis follow-up).

The seven+one real StudentProfile columns added to the ontology (and landed by
StudentLander) were invisible in the downloadable canonical template, because
``DOMAIN_CANONICAL_HEADERS`` is hand-maintained separately from the ontology and
had never been updated — so a school exporting from an old SIS was never told
these columns are understood, defeating "ingest every field" at the source.

These tests pin:
  1. every real-column student field is exposed in the downloadable template; and
  2. the template never advertises a student header that has no ontology home
     (reverse drift — advertising a column the mapper can't resolve).

Both are DB-free.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.accelerators.runmycampus_canonical import (
    DOMAIN_CANONICAL_HEADERS,
)
from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY

# The real StudentProfile columns the gap analysis added to the ontology + lander.
_REAL_STUDENT_COLUMNS = (
    "place_of_birth",
    "joined_date",
    "joined_term",
    "section",
    "parent_phone",
    "exam_candidate_number",
    "exam_center_code",
    "exam_system",
)


class CanonicalTemplateExposureTests(SimpleTestCase):
    def test_real_columns_are_in_the_downloadable_template(self):
        headers = DOMAIN_CANONICAL_HEADERS["students"]
        missing = [c for c in _REAL_STUDENT_COLUMNS if c not in headers]
        self.assertEqual(
            missing, [], msg=f"real columns hidden from the canonical template: {missing}"
        )

    def test_real_columns_are_ontology_fields(self):
        student_fields = CANONICAL_ONTOLOGY["students"]
        missing = [c for c in _REAL_STUDENT_COLUMNS if c not in student_fields]
        self.assertEqual(
            missing, [], msg=f"real columns missing from the students ontology: {missing}"
        )

    def test_template_students_headers_all_have_an_ontology_home(self):
        # Reverse drift: every advertised student header must be a real canonical
        # field so the mapper can actually resolve it (no phantom template columns).
        student_fields = set(CANONICAL_ONTOLOGY["students"].keys())
        phantom = sorted(DOMAIN_CANONICAL_HEADERS["students"] - student_fields)
        self.assertEqual(
            phantom, [], msg=f"template advertises student headers with no ontology field: {phantom}"
        )
