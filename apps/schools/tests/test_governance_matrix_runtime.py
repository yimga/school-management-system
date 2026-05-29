"""Phase 3A — matrix runtime wiring (signup + statutory hints for all ISO rows)."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.governance.country_matrix_service import (
    get_matrix_row,
    resolve_statutory_jurisdiction_hint,
    signup_governance_defaults,
)


class GovernanceMatrixRuntimeTests(SimpleTestCase):
    def _matrix_rows(self) -> list[dict]:
        path = (
            Path(settings.BASE_DIR)
            / "docs"
            / "generated"
            / "country_governance_matrix.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("rows") or [])

    def test_all_matrix_rows_resolve_statutory_hint(self):
        for row in self._matrix_rows():
            iso = str(row.get("iso_alpha2") or "")
            hint = resolve_statutory_jurisdiction_hint(iso)
            self.assertIn("label", hint, msg=iso)
            self.assertIn("framework", hint, msg=iso)
            self.assertTrue(str(hint["label"]).strip(), msg=iso)
            self.assertTrue(str(hint["framework"]).strip(), msg=iso)

    def test_curated_hint_preserved_for_cm(self):
        hint = resolve_statutory_jurisdiction_hint("CM")
        self.assertEqual(hint["label"], "Cameroon")
        self.assertIn("MoE", hint["framework"])

    def test_matrix_fallback_for_unlisted_iso(self):
        hint = resolve_statutory_jurisdiction_hint("JP")
        self.assertIn("Japan", hint["label"])

    def test_signup_defaults_standalone(self):
        defaults = signup_governance_defaults("CM")
        self.assertEqual(defaults["operating_mode"], "standalone")
        self.assertEqual(defaults["matrix_iso"], "CM")
        self.assertEqual(defaults["governance_archetype"], "federation_equals")
        self.assertIsInstance(defaults["admin_level_labels"], list)
        self.assertGreater(len(defaults["admin_level_labels"]), 0)

    def test_get_matrix_row_cm_shard(self):
        row = get_matrix_row("CM")
        self.assertIsNotNone(row)
        self.assertEqual(row.get("iso_alpha2"), "CM")
