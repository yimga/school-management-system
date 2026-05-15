"""Smoke tests for the country / education-system registry.

Scoped strictly to `apps.migration_cloud.country_profiles` and the
locale-aware transformer behaviour it powers. No tenant DB setup needed.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.country_profiles import (
    ATTENDANCE_DIALECTS,
    attendance_dialect,
    get_country_profile,
    grading_scale,
    list_grading_scales,
    list_supported_countries,
    resolved_country_profile,
)
from apps.migration_cloud.transformers import TransformerContext, get_transformer


class CountryRegistryTests(SimpleTestCase):
    def test_americas_europe_asia_africa_oceania_present(self) -> None:
        codes = set(list_supported_countries())
        for required in ("US", "GB", "FR", "DE", "BR", "IN", "JP", "KE", "AU"):
            self.assertIn(required, codes)

    def test_get_country_profile_is_case_insensitive(self) -> None:
        self.assertEqual(get_country_profile("us"), get_country_profile("US"))

    def test_unknown_country_returns_none(self) -> None:
        self.assertIsNone(get_country_profile("ZZ"))

    def test_resolved_country_falls_back_to_baseline_when_no_override(self) -> None:
        base = get_country_profile("FR")
        resolved = resolved_country_profile("FR")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.code, base.code)
        self.assertEqual(resolved.default_language, "fr")

    def test_japan_is_last_first_with_cjk_attendance(self) -> None:
        jp = get_country_profile("JP")
        self.assertEqual(jp.name_order, "last_first")
        self.assertEqual(jp.attendance_code_dialect, "cjk_attendance")

    def test_mexico_is_spanish_double(self) -> None:
        self.assertEqual(get_country_profile("MX").name_order, "spanish_double")


class GradingScaleTests(SimpleTestCase):
    def test_uk_a_star_maps_to_percent(self) -> None:
        scale = grading_scale("UK_A_STAR")
        self.assertIsNotNone(scale)
        self.assertEqual(scale["A*"], "95")
        self.assertEqual(scale["U"], "0")

    def test_ng_waec_maps_to_percent(self) -> None:
        scale = grading_scale("NG_WAEC")
        self.assertEqual(scale["A1"], "90")
        self.assertEqual(scale["F9"], "0")

    def test_ib_present(self) -> None:
        self.assertIn("IB_1_7", list_grading_scales())

    def test_grading_transformer_uses_country_hint(self) -> None:
        t = get_transformer("grading_scale_to_canonical")
        self.assertIsNotNone(t)
        out = t.transform("A*", TransformerContext(canonical_field="score", hints={"country": "GB"}))
        self.assertEqual(out, "95")

    def test_grading_transformer_falls_back_to_numeric(self) -> None:
        t = get_transformer("grading_scale_to_canonical")
        out = t.transform("87.5", TransformerContext(canonical_field="score"))
        # No scale_map / slug / country → numeric fallback returns the parsed Decimal.
        self.assertEqual(out, "87.5")


class AttendanceDialectTests(SimpleTestCase):
    def test_all_required_dialects_present(self) -> None:
        for slug in ("letters_paie", "letters_de", "letters_fr", "letters_es_pt", "cjk_attendance", "letters_in"):
            self.assertIn(slug, ATTENDANCE_DIALECTS)

    def test_lookup_unknown_returns_none(self) -> None:
        self.assertIsNone(attendance_dialect("does_not_exist"))

    def test_attendance_transformer_dispatches_by_country(self) -> None:
        t = get_transformer("attendance_code_rewrite")
        self.assertEqual(
            t.transform("AB", TransformerContext(canonical_field="status", hints={"country": "FR"})),
            "absent",
        )
        self.assertEqual(
            t.transform("VS", TransformerContext(canonical_field="status", hints={"country": "DE"})),
            "late",
        )


class NameSplitLocaleTests(SimpleTestCase):
    def test_japanese_last_first_no_comma(self) -> None:
        t = get_transformer("name_split_locale")
        ctx_first = TransformerContext(canonical_field="first_name", hints={"country": "JP"})
        ctx_last = TransformerContext(canonical_field="last_name", hints={"country": "JP"})
        self.assertEqual(t.transform("Tanaka Hiroshi", ctx_first), "Hiroshi")
        self.assertEqual(t.transform("Tanaka Hiroshi", ctx_last), "Tanaka")

    def test_hispanic_double_surname_paternal_and_maternal(self) -> None:
        t = get_transformer("name_split_locale")
        ctx_p = TransformerContext(canonical_field="paternal_surname", hints={"country": "MX"}, options={"component": "paternal"})
        ctx_m = TransformerContext(canonical_field="maternal_surname", hints={"country": "MX"}, options={"component": "maternal"})
        self.assertEqual(t.transform("Juan Carlos Lopez Garcia", ctx_p), "Lopez")
        self.assertEqual(t.transform("Juan Carlos Lopez Garcia", ctx_m), "Garcia")

    def test_western_first_last_default(self) -> None:
        t = get_transformer("name_split_locale")
        ctx = TransformerContext(canonical_field="first_name", hints={"country": "US"})
        self.assertEqual(t.transform("Ada Lovelace", ctx), "Ada")
