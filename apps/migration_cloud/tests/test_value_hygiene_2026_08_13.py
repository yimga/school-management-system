"""Value hygiene for messy exports (G11 / G12).

Real pandas / spreadsheet dumps write NaN as the literal ``nan``, None as
``None``, and numeric-looking text ids as floats (``241904748.0``). Stored
verbatim those become a student's parent literally named "None", an admission
number "nan", or an id that no longer round-trips. These pin the central
normalization applied to every reader and domain in ``_transform_row``.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.orchestrator import _normalize_source_value, _transform_row


class NormalizeSourceValueTests(SimpleTestCase):
    def test_null_literals_become_empty(self):
        for token in ["nan", "NaN", "None", "none", "NULL", "N/A", "n/a", "#N/A", "nil", "(null)"]:
            self.assertEqual(_normalize_source_value(token), "", f"{token!r} should null out")

    def test_integer_float_string_is_repaired(self):
        self.assertEqual(_normalize_source_value("241904748.0"), "241904748")
        self.assertEqual(_normalize_source_value("36.00"), "36")
        self.assertEqual(_normalize_source_value("007.0"), "007")  # leading zeros kept

    def test_genuine_decimals_untouched(self):
        self.assertEqual(_normalize_source_value("36.5"), "36.5")
        self.assertEqual(_normalize_source_value("0.25"), "0.25")

    def test_ordinary_values_and_nonstr_untouched(self):
        self.assertEqual(_normalize_source_value("Esakenong Abel"), "Esakenong Abel")
        self.assertEqual(_normalize_source_value(""), "")
        self.assertEqual(_normalize_source_value(42), 42)
        self.assertIsNone(_normalize_source_value(None))

    def test_partial_word_not_nulled(self):
        # "Nancy" contains "nan" but is not the literal sentinel.
        self.assertEqual(_normalize_source_value("Nancy"), "Nancy")
        self.assertEqual(_normalize_source_value("Nonemour"), "Nonemour")


class TransformRowHygieneTests(SimpleTestCase):
    def test_row_is_cleaned_end_to_end(self):
        mapping_index = {
            "ID": {"source_column": "ID", "canonical_field": "external_id"},
            "Parent": {"source_column": "Parent", "canonical_field": "custom_fields.parent"},
        }
        raw_row = {"ID": "241904748.0", "Parent": "None"}
        out = _transform_row(raw_row, mapping_index, {})
        self.assertEqual(out.get("external_id"), "241904748")
        self.assertEqual(out.get("custom_fields.parent"), "")


class ResidualHeaderBindTests(SimpleTestCase):
    def test_fonction_promotes_onto_empty_role(self):
        from apps.migration_cloud.mapper import bind_residual_headers

        row = {
            "staff_external_id": "EMP-1",
            "_unmapped.Fonction": "Bursar",
            "custom_fields.badge": "keep-me",
        }
        out = bind_residual_headers(row, "staff")
        self.assertEqual(out.get("role"), "Bursar")
        self.assertNotIn("_unmapped.Fonction", out)
        self.assertEqual(out.get("custom_fields.badge"), "keep-me")

    def test_does_not_overwrite_existing_canonical(self):
        from apps.migration_cloud.mapper import bind_residual_headers

        row = {"role": "Teacher", "_unmapped.Fonction": "Bursar"}
        out = bind_residual_headers(row, "staff")
        self.assertEqual(out.get("role"), "Teacher")
        self.assertEqual(out.get("_unmapped.Fonction"), "Bursar")

    def test_designation_is_staff_role_synonym(self):
        from apps.migration_cloud.ontology import all_synonyms

        syns = all_synonyms("role", domain="staff")
        self.assertIn("designation", syns)
        self.assertIn("fonction", syns)
