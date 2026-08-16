"""Increment (q) — subject codes gain the term-window override cascade.

``resolve_subject_code`` previously went straight *curated table → mnemonic*, with
no DB override layer — so reaching a country's real official codes meant editing
every ``Subject.code`` in every school. This proves the new read-side cascade —
per-school ``settings['subject_codes']`` → per-profile ``config['subject_codes']``
→ curated → mnemonic — the exact twin of
``country_term_calendars._lookup_windows``. An operator now enters a country's real
codes ONCE at the profile level and every school in that country inherits them,
with no code change and no deploy.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.academics.country_subject_codes import (
    _code_from_override_map,
    effective_subject_code_map,
    _profile_subject_codes,
    resolve_subject_code,
)
from apps.schools.models import School


class SchoolOverrideLayerTests(SimpleTestCase):
    """The per-school ``settings['subject_codes']`` layer — highest precedence."""

    def test_school_override_beats_curated(self):
        # Curated KE English is the KNEC numeric "101"; the school override wins.
        ke = School(country_code="KE", settings={"subject_codes": {"English": "ENG-CUSTOM"}})
        self.assertEqual(resolve_subject_code(ke, "English"), "ENG-CUSTOM")

    def test_override_is_case_insensitive_on_name(self):
        ke = School(country_code="KE", settings={"subject_codes": {"mathematics": "MATH-X"}})
        self.assertEqual(resolve_subject_code(ke, "  MATHEMATICS "), "MATH-X")

    def test_override_for_uncurated_country_beats_mnemonic(self):
        xx = School(country_code="XX", settings={"subject_codes": {"Welding Theory": "WELD-01"}})
        self.assertEqual(resolve_subject_code(xx, "Welding Theory"), "WELD-01")

    def test_blank_or_nonstring_values_fall_through(self):
        # A blank string and a non-string int are ignored → curated KNEC codes stand.
        ke = School(
            country_code="KE",
            settings={"subject_codes": {"English": "   ", "Mathematics": 121}},
        )
        self.assertEqual(resolve_subject_code(ke, "English"), "101")
        self.assertEqual(resolve_subject_code(ke, "Mathematics"), "121")

    def test_non_dict_settings_is_safe(self):
        self.assertEqual(resolve_subject_code(School(country_code="KE", settings=["x"]), "English"), "101")
        self.assertEqual(resolve_subject_code(School(country_code="KE"), "English"), "101")


class ProfileLayerTests(SimpleTestCase):
    """The per-education-system ``config['subject_codes']`` layer.

    Proven via a patched ``_profile_subject_codes`` — the real profile machinery
    needs DB + policy wiring, but the cascade ORDER is what this contract locks."""

    def test_profile_override_beats_curated(self):
        ke = School(country_code="KE")
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            return_value={"english": "PROF-ENG"},
        ):
            self.assertEqual(resolve_subject_code(ke, "English"), "PROF-ENG")

    def test_school_layer_beats_profile_layer(self):
        ke = School(country_code="KE", settings={"subject_codes": {"English": "SCHOOL-ENG"}})
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            return_value={"english": "PROF-ENG"},
        ):
            self.assertEqual(resolve_subject_code(ke, "English"), "SCHOOL-ENG")

    def test_profile_override_beats_mnemonic_for_uncurated_country(self):
        xx = School(country_code="XX")
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            return_value={"welding theory": "PROF-WELD"},
        ):
            self.assertEqual(resolve_subject_code(xx, "Welding Theory"), "PROF-WELD")

    def test_unsaved_school_short_circuits_profile_layer_no_db(self):
        # _state.adding is True for an unsaved instance → the profile lookup returns
        # {} without a DB hit, so pure-resolution callers (the coverage ratchet)
        # stay DB-free. SimpleTestCase would raise on any query.
        self.assertEqual(_profile_subject_codes(School(country_code="KE")), {})


class CodeFromOverrideMapTests(SimpleTestCase):
    def test_exact_and_case_insensitive(self):
        m = {"Mathematics": "M1"}
        self.assertEqual(_code_from_override_map(m, "mathematics"), "M1")
        self.assertEqual(_code_from_override_map(m, "MATHEMATICS"), "M1")

    def test_ignores_bad_shapes(self):
        self.assertEqual(_code_from_override_map(None, "x"), "")
        self.assertEqual(_code_from_override_map({"x": 3}, "x"), "")
        self.assertEqual(_code_from_override_map({"x": "  "}, "x"), "")
        self.assertEqual(_code_from_override_map({}, ""), "")


class NoRegressionTests(SimpleTestCase):
    """The pre-existing curated + mnemonic behaviour is untouched when nothing
    overrides — the (k–p) coverage guarantee still holds."""

    def test_curated_then_mnemonic_without_override(self):
        ke = School(country_code="KE")
        self.assertEqual(resolve_subject_code(ke, "Biology"), "231")          # KNEC numeric
        self.assertEqual(resolve_subject_code(ke, "Basket Weaving"), "BW")    # mnemonic initials
        self.assertEqual(resolve_subject_code(School(country_code="IN"), "Mathematics"), "041")  # CBSE
        self.assertEqual(resolve_subject_code(School(country_code="CM"), "French"), "0545")       # curated GCE


class EffectiveMapTests(SimpleTestCase):
    def test_merges_curated_with_school_override(self):
        ke = School(
            country_code="KE",
            settings={"subject_codes": {"English": "ENG-X", "Robotics": "ROB"}},
        )
        merged = effective_subject_code_map(ke)
        self.assertEqual(merged["english"], "ENG-X")     # override wins
        self.assertEqual(merged["mathematics"], "121")   # curated survives
        self.assertEqual(merged["robotics"], "ROB")      # override-only subject added

    def test_profile_overlays_between_curated_and_school(self):
        ke = School(country_code="KE", settings={"subject_codes": {"English": "SCHOOL"}})
        with patch(
            "apps.academics.country_subject_codes._profile_subject_codes",
            return_value={"english": "PROF", "biology": "PROF-BIO"},
        ):
            merged = effective_subject_code_map(ke)
        self.assertEqual(merged["english"], "SCHOOL")     # school beats profile
        self.assertEqual(merged["biology"], "PROF-BIO")   # profile beats curated (231)
        self.assertEqual(merged["mathematics"], "121")    # curated where nobody overrides
