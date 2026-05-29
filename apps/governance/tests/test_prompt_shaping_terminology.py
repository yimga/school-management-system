"""Phase 3C — LiteLLM institution terminology wiring."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.prompt_shaping import institution_terminology_system_lines, shape


class InstitutionTerminologyTests(SimpleTestCase):
    def test_cm_matrix_yields_local_terms(self):
        lines = institution_terminology_system_lines("CM")
        joined = " ".join(lines).lower()
        self.assertIn("cameroon", joined)
        self.assertTrue(any("teacher" in line.lower() for line in lines))

    def test_unknown_country_returns_empty_tuple(self):
        self.assertEqual(institution_terminology_system_lines("ZZ"), ())

    def test_shape_appends_country_lines(self):
        shaped = shape(
            "Summarize fees.",
            viewport="B",
            country_code="CM",
            institution_type="lycee-2nd-cycle",
        )
        joined = " ".join(shaped.system_messages).lower()
        self.assertIn("cameroon", joined)
        self.assertIn("2nd cycle", joined)
