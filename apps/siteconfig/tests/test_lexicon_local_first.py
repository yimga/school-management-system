"""Local-first lexicon coverage for the de-Cameroon template adoption.

The de-Gilead pass routed hardcoded "Sequence 1/2" and "Principal" in the generic
report/marks templates through ``{% term %}``. These assert the keys exist and
resolve to the English defaults (so existing tenants are unchanged) and that the
resolver never crashes on a missing key (defensive for template rendering).

All no-DB: ``resolve_term(None, ...)`` short-circuits to the registry default
without touching the database (``_build_full_overlay`` returns {} for school=None).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.lexicon_catalog import LEXICON_REGISTRY
from apps.siteconfig.terminology_service import resolve_term


class SequenceLexiconKeyTests(SimpleTestCase):
    def test_sequence_key_registered(self) -> None:
        self.assertIn("sequence", LEXICON_REGISTRY)
        singular, plural, category, _desc = LEXICON_REGISTRY["sequence"]
        self.assertEqual(singular, "Sequence")
        self.assertEqual(plural, "Sequences")
        self.assertEqual(category, "academic")

    def test_sequence_resolves_to_default_without_tenant(self) -> None:
        # No tenant override → English default, so existing tenants render unchanged.
        self.assertEqual(resolve_term(None, "sequence"), "Sequence")
        self.assertEqual(resolve_term(None, "sequence", plural=True), "Sequences")

    def test_principal_key_resolves(self) -> None:
        # annual_report.html now uses {% term "principal" %} — key must exist + default.
        self.assertIn("principal", LEXICON_REGISTRY)
        self.assertEqual(resolve_term(None, "principal"), "Principal")

    def test_unknown_key_falls_back_to_key(self) -> None:
        # Templates must never blow up on a key that isn't in the registry.
        self.assertEqual(
            resolve_term(None, "definitely_not_a_lexicon_key"),
            "definitely_not_a_lexicon_key",
        )
