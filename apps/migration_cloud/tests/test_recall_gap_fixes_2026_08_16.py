"""Recall gap fixes (2026-08-16 gap-analysis follow-up).

DB-free guards for the four recall holes found by the ingest-99 gap analysis:

* B1 — source classifier diluted a full required-header match below threshold.
* B2 — domain classifier scored by exact synonym intersection only, so a padded/
  qualified real roster ("Student Mobile Number", ...) matched no domain and
  quarantined wholesale before the field mapper's containment ever ran.
* B3 — punctuated acronyms ("D.O.B.") normalized away from their compact synonym.
* B4 — a trailing unit ("Amount (USD)") pushed a real header below threshold.

Each test fails on the pre-fix code and passes after.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.classifiers.domain import _score_domains
from apps.migration_cloud.classifiers.source import (
    SOURCE_HEADER_SIGNATURES,
    _score_signatures,
)
from apps.migration_cloud.mapper import (
    _CONTAINMENT_STRONG,
    _containment_strength,
    _header_match_keys,
)


class DomainClassifierContainmentTests(SimpleTestCase):
    """B2 — a messy-but-valid roster must reach its domain via containment."""

    def test_padded_student_roster_classifies_as_students(self) -> None:
        # None of these headers are EXACT synonyms; each only *contains* one.
        messy = {
            "student_full_name",
            "student_mobile_number",
            "student_date_of_birth",
            "student_place_of_birth",
        }
        ranked = _score_domains(messy)
        self.assertTrue(ranked, "no domain candidate produced for a padded roster")
        self.assertEqual(
            ranked[0].domain,
            "students",
            msg=f"padded roster misclassified: {[(c.domain, c.confidence) for c in ranked[:3]]}",
        )

    def test_containment_guard_does_not_drag_unrelated_headers_into_students(self) -> None:
        # "Class Teacher" / "Marital Status" carry a meaningful non-student token,
        # so the STRONG-only guard must NOT classify them as a student roster.
        ranked = _score_domains({"class_teacher_name", "marital_status"})
        if ranked:
            self.assertNotEqual(ranked[0].domain, "students")


class SourceClassifierDilutionTests(SimpleTestCase):
    """B1 — a full required-header match must clear source_min_confidence (0.65)."""

    def test_full_required_match_clears_threshold(self) -> None:
        # Use a real signature; feed exactly its required headers (zero suggested).
        src_name, sig = next(iter(SOURCE_HEADER_SIGNATURES.items()))
        required = list(sig.get("required", []))
        self.assertTrue(required, f"signature {src_name!r} has no required headers to test")
        scored = _score_signatures(list(required))
        cand = next((c for c in scored if c.source == src_name), None)
        self.assertIsNotNone(cand, f"{src_name!r} not scored on its own required headers")
        self.assertGreaterEqual(
            cand.confidence,
            0.65,
            msg=f"full required match for {src_name!r} diluted to {cand.confidence}",
        )


class HeaderMatchKeyTests(SimpleTestCase):
    """B3 / B4 — acronym-compact and unit-stripped keys for the exact-alias layer."""

    def test_punctuated_acronym_emits_compact_key(self) -> None:
        keys = _header_match_keys({"name": "D.O.B.", "normalized": "d_o_b"})
        self.assertIn("dob", keys, msg=f"no compact acronym key: {keys}")

    def test_slash_acronym_emits_compact_key(self) -> None:
        keys = _header_match_keys({"name": "S/N", "normalized": "s_n"})
        self.assertIn("sn", keys, msg=f"no compact acronym key: {keys}")

    def test_trailing_unit_parenthetical_emits_base_key(self) -> None:
        keys = _header_match_keys({"name": "Amount (USD)", "normalized": "amount_usd"})
        self.assertIn("amount", keys, msg=f"no de-parenthesized base key: {keys}")

    def test_unit_token_is_filler_for_containment(self) -> None:
        strength, _syn = _containment_strength({"amount", "usd"}, ["amount", "total_amount"])
        self.assertGreaterEqual(
            strength,
            _CONTAINMENT_STRONG,
            msg=f"unit-suffixed header did not STRONG-contain its base field: {strength}",
        )
