"""The seam: a name column on a history file must reach the lander as a name.

Adding ``student_name`` to the ontology and teaching ``resolve_student`` to use
it are each necessary and neither is sufficient -- between them sits the mapper,
which only maps a column if a synonym clears the confidence threshold. A gap
there means the ontology field exists, the resolver can use it, and the column
still lands in ``custom_fields`` where nobody looks.

These are the real header spellings from West/Central African school exports,
which are the files this path exists for.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.mapper import map_artifact
from apps.migration_cloud.models import MigrationArtifact, MigrationBundle
from apps.schools.models import School


class NameColumnMappingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Mapping School",
            slug="mapping-school",
            subdomain="mapping-school",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)

    def _mapped(self, domain: str, headers: list[str]) -> dict[str, str]:
        artifact = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle=f"{domain}.xlsx",
            filename=f"{domain}.xlsx",
            sha256="m" * 64,
            locale_hints={},
            profile={
                "columns": [
                    {
                        "name": h,
                        "normalized": h.strip().lower().replace(" ", "_").replace("'", "_"),
                        "samples": ["ANDONGMAD FAVOUR ANGU"],
                    }
                    for h in headers
                ]
            },
        )
        return {
            m.source_column: m.canonical_field for m in map_artifact(artifact=artifact, domain=domain)
        }

    def test_a_french_attendance_sheet_maps_its_name_column(self):
        mapped = self._mapped("attendance", ["Nom", "Date", "Presence"])
        self.assertEqual(
            mapped["Nom"],
            "student_name",
            f"the pupil's name landed as {mapped['Nom']!r} — the row will not resolve",
        )

    def test_an_english_grades_sheet_maps_its_name_column(self):
        mapped = self._mapped("grades", ["Student Name", "Term", "Subject", "Score"])
        self.assertEqual(mapped["Student Name"], "student_name")

    def test_a_fee_sheet_maps_its_name_column(self):
        mapped = self._mapped("finance", ["Name", "Reference", "Amount"])
        self.assertEqual(mapped["Name"], "student_name")

    def test_an_id_column_still_wins_where_both_exist(self):
        mapped = self._mapped("attendance", ["Student ID", "Nom", "Date", "Presence"])
        self.assertEqual(mapped["Student ID"], "student_external_id")
        self.assertEqual(mapped["Nom"], "student_name")

    def test_a_guardian_file_name_column_stays_the_guardians(self):
        """A guardian sheet's "Name" is the guardian's, and must not be stolen."""
        mapped = self._mapped("guardians", ["Name", "Relationship", "Phone"])
        self.assertNotEqual(
            mapped["Name"],
            "student_name",
            "the guardian's own name was mapped to the student's name",
        )

    def test_a_guardian_file_can_still_name_the_child_explicitly(self):
        mapped = self._mapped("guardians", ["Child Name", "Name", "Relationship"])
        self.assertEqual(mapped["Child Name"], "student_name")
