"""External dependency register source + deterministic flatten."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from django.test import SimpleTestCase


class ExternalDependenciesRegisterTests(SimpleTestCase):
    def test_source_contains_required_payment_dependencies(self):
        root = Path(__file__).resolve().parents[3]
        src = root / "docs" / "external_dependencies_register.json"
        data = json.loads(src.read_text(encoding="utf-8"))
        ids = {
            e["id"]
            for sec in data.get("sections") or []
            for e in sec.get("entries") or []
        }
        required = {
            "stripe_global_cards",
            "paystack_wa",
            "flutterwave_multi_country",
            "mtn_momo",
            "orange_money",
            "bank_sepa_card_partner",
            "manual_fallback_operations",
        }
        self.assertTrue(required.issubset(ids))

    def test_flatten_groups_blocking_levels(self):
        root = Path(__file__).resolve().parents[3]
        script = root / "scripts" / "generate_external_dependencies_register.py"
        spec = importlib.util.spec_from_file_location("ext_dep_gen", script)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        raw = json.loads(
            (root / "docs" / "external_dependencies_register.json").read_text(encoding="utf-8")
        )
        gen = mod._flatten(raw)
        counts = gen.get("blocking_level_counts") or {}
        self.assertIn("blocks_full_market", counts)
        self.assertTrue(gen.get("systems_impacted"))

    def test_category_scope_review_links_generated_register_when_present(self):
        root = Path(__file__).resolve().parents[3]
        csr = root / "docs" / "generated" / "category_scope_review.json"
        self.assertTrue(csr.is_file())
        data = json.loads(csr.read_text(encoding="utf-8"))
        self.assertGreaterEqual(int(data.get("schema_version") or 0), 3)
        path = data.get("external_dependency_register_path")
        self.assertEqual(path, "docs/generated/external_dependencies_register.json")
        self.assertIsInstance(data.get("external_blockers_by_blocking_level"), dict)

    def test_generated_markdown_does_not_truncate_command_center_cells(self):
        root = Path(__file__).resolve().parents[3]
        md = (
            root / "docs" / "generated" / "external_dependencies_register.md"
        ).read_text(encoding="utf-8")
        self.assertIn("metadata health command", md)
        self.assertIn("without PSP", md)
        self.assertIn("External action", md)
