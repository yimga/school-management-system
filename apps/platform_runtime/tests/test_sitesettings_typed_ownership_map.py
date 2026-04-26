"""1042/1043: generated typed-ownership map + migration candidate iterator."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent


class SiteSettingsTypedOwnershipMapTests(unittest.TestCase):
    def test_generated_json_is_non_empty_and_has_maintenance(self) -> None:
        p = REPO / "docs" / "generated" / "sitesettings_typed_ownership_map.json"
        self.assertTrue(p.is_file(), "run: python scripts/generate_sitesettings_typed_ownership_map.py")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 1)
        fields = data.get("fields") or {}
        self.assertGreaterEqual(len(fields), 10)
        self.assertIn("maintenance_mode", fields)
        self.assertIn("phase_b_category", fields["maintenance_mode"])

    def test_typed_migration_candidates_non_empty(self) -> None:
        from apps.platform_runtime.typed_migration_candidates import (
            iter_typed_migration_candidate_keys,
        )

        keys = iter_typed_migration_candidate_keys()
        self.assertTrue(keys, "expected at least one typed_migration_target from map")
