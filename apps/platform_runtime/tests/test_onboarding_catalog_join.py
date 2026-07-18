"""Tests for the onboarding ↔ catalog key bridge (§3.4)."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ONBOARDING_PY = REPO / "apps" / "platform_runtime" / "onboarding.py"
CATALOG_PY = REPO / "apps" / "siteconfig" / "onboarding_step_catalog.py"
CONCIERGE_TEMPLATE = REPO / "templates" / "lifecycle" / "concierge_modal.html"
NAVIGATOR_TEMPLATE = REPO / "templates" / "partials" / "lifecycle_journey_navigator.html"


class TestRuntimeToCatalogKeyMapping(unittest.TestCase):
    """RUNTIME_TO_CATALOG_KEY covers every runtime key and maps to real catalog entries."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        src = ONBOARDING_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)

        cls.mapping: dict[str, str | None] = {}
        for node in ast.walk(tree):
            target_name = None
            value_node = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "RUNTIME_TO_CATALOG_KEY":
                        target_name = target.id
                        value_node = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "RUNTIME_TO_CATALOG_KEY":
                    target_name = node.target.id
                    value_node = node.value
            if target_name and value_node and isinstance(value_node, ast.Dict):
                for k, v in zip(value_node.keys, value_node.values):
                    key_val = ast.literal_eval(k) if k else None
                    val_val = ast.literal_eval(v)
                    if key_val is not None:
                        cls.mapping[key_val] = val_val

        cls.runtime_keys: set[str] = set()
        add_row_pattern = re.compile(r'add_row\(\s*"([^"]+)"')
        for m in add_row_pattern.finditer(src):
            cls.runtime_keys.add(m.group(1))

        cat_src = CATALOG_PY.read_text(encoding="utf-8")
        cat_tree = ast.parse(cat_src)
        cls.catalog_keys: set[str] = set()
        for node in ast.walk(cat_tree):
            cat_name = None
            cat_value = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "ONBOARDING_STEPS":
                        cat_name = target.id
                        cat_value = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "ONBOARDING_STEPS":
                    cat_name = node.target.id
                    cat_value = node.value
            if cat_name and cat_value and isinstance(cat_value, ast.Dict):
                for k in cat_value.keys:
                    if k:
                        cls.catalog_keys.add(ast.literal_eval(k))

    def test_mapping_covers_all_runtime_keys(self):
        missing = self.runtime_keys - set(self.mapping.keys())
        self.assertEqual(missing, set(), f"Runtime keys not in RUNTIME_TO_CATALOG_KEY: {missing}")

    def test_mapped_values_exist_in_catalog(self):
        bad = []
        for rk, ck in self.mapping.items():
            if ck is not None and ck not in self.catalog_keys:
                bad.append(f"{rk} -> {ck}")
        self.assertEqual(bad, [], f"Mapped catalog keys not found in ONBOARDING_STEPS: {bad}")

    def test_known_mappings(self):
        self.assertEqual(self.mapping.get("academic_year"), "calendar.academic_year")
        self.assertEqual(self.mapping.get("teachers"), "people.teachers")
        self.assertEqual(self.mapping.get("students"), "students.import")
        self.assertEqual(self.mapping.get("classes"), "curriculum.classrooms")
        self.assertEqual(self.mapping.get("ccc"), "brand.domain")

    def test_none_mappings_skip_enrichment(self):
        for rk, ck in self.mapping.items():
            if ck is None:
                self.assertNotIn(
                    rk, self.catalog_keys,
                    f"Key {rk!r} mapped to None but exists directly in catalog — consider mapping it",
                )


class TestGetOnboardingStepsUsesBridge(unittest.TestCase):
    """Source contract: get_onboarding_steps resolves via RUNTIME_TO_CATALOG_KEY."""

    def test_source_references_mapping(self):
        src = ONBOARDING_PY.read_text(encoding="utf-8")
        self.assertIn("RUNTIME_TO_CATALOG_KEY", src)
        self.assertIn("catalog_key", src)


class TestBuildLifecycleJourneyExists(unittest.TestCase):
    """build_lifecycle_journey is defined and importable."""

    def test_function_defined(self):
        src = ONBOARDING_PY.read_text(encoding="utf-8")
        self.assertIn("def build_lifecycle_journey(", src)


class TestConciergeTemplateUsesNavigator(unittest.TestCase):
    """Concierge modal includes the journey navigator when available."""

    def test_includes_navigator(self):
        content = CONCIERGE_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("lifecycle_journey_navigator.html", content)

    def test_navigator_template_exists(self):
        self.assertTrue(NAVIGATOR_TEMPLATE.exists())


class TestNavigatorTemplateContract(unittest.TestCase):
    """Navigator partial has required data attributes and structure."""

    def test_has_data_attribute(self):
        content = NAVIGATOR_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('data-rmc-lifecycle-journey="1"', content)

    def test_has_progress_bar(self):
        content = NAVIGATOR_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("rmc-lifecycle-journey__bar", content)


class TestCatalogHelpersStillWork(unittest.TestCase):
    """Catalog module helpers remain functional after changes."""

    def test_list_step_keys(self):
        from apps.siteconfig.onboarding_step_catalog import list_step_keys

        keys = list_step_keys()
        self.assertIsInstance(keys, list)
        self.assertGreater(len(keys), 0)
        self.assertIn("calendar.academic_year", keys)

    def test_steps_for_blueprint_default(self):
        from apps.siteconfig.onboarding_step_catalog import steps_for_blueprint

        steps = steps_for_blueprint(None)
        self.assertIsInstance(steps, list)
        self.assertGreater(len(steps), 0)
        self.assertTrue(all("key" in s for s in steps))

    def test_install_key_aliases_to_pack(self):
        from apps.siteconfig.onboarding_step_catalog import (
            resolve_blueprint_steps_pack,
            steps_for_blueprint,
            STEPS_BY_BLUEPRINT_PACK,
        )

        self.assertEqual(
            resolve_blueprint_steps_pack("private-primary-school"),
            "primary-school",
        )
        primary = steps_for_blueprint("private-primary-school")
        expected = steps_for_blueprint("primary-school")
        self.assertEqual([s["key"] for s in primary], [s["key"] for s in expected])
        self.assertEqual(
            len(primary),
            len(STEPS_BY_BLUEPRINT_PACK["primary-school"]),
        )


class TestResolveStepLink(unittest.TestCase):
    """deep_link URL names become real hrefs in the journey."""

    def test_prefers_path_link(self):
        from apps.platform_runtime.onboarding import _resolve_step_link

        self.assertEqual(
            _resolve_step_link({"link": "/school/setup/", "deep_link": "siteconfig:theme_colors"}),
            "/school/setup/",
        )

    def test_resolves_deep_link_name(self):
        from apps.platform_runtime.onboarding import _resolve_step_link

        href = _resolve_step_link({"deep_link": "siteconfig:theme_colors"})
        self.assertTrue(href.startswith("/"), f"expected path, got {href!r}")


if __name__ == "__main__":
    unittest.main()
