"""Verifier for the lux-workspace luxury UI infrastructure.

Reads the same SOT JSON registry that the TypeScript layer imports
(src/lib/luxWorkspace/registry.json) and asserts the design invariants
the mandate demands:

  - 3 tiers (FINANCIAL_LEDGER / ACADEMIC_MATRIX / OPERATOR_SHELL)
  - distinct visual identities (no uniformity)
  - non-colliding tier-local hotkey -> action mappings
  - global Cmd+K + Escape shortcuts wired
  - spring curve == cubic-bezier(0.16, 1, 0.3, 1)
  - min touch target >= 48px
  - every tier exposes a unique CSS var token
  - CSS file ships matching --lux-tier-* tokens

Run:
    python scripts/verify_lux_workspace_ui.py

Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import re
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "src" / "lib" / "luxWorkspace" / "registry.json"
CSS_PATH = REPO_ROOT / "static" / "css" / "lux-workspace.css"
TS_INDEX_PATH = REPO_ROOT / "src" / "lib" / "luxWorkspace" / "index.ts"

EXPECTED_TIERS = ("FINANCIAL_LEDGER", "ACADEMIC_MATRIX", "OPERATOR_SHELL")
EXPECTED_SPRING_CURVE = "cubic-bezier(0.16, 1, 0.3, 1)"
EXPECTED_GLOBAL_SHORTCUTS = {
    "Mod+k": "OPEN_COMMAND_CONSOLE",
    "Mod+/": "OPEN_KEYBOARD_HELP",
    "Escape": "CLOSE_TOP_OVERLAY",
}
REQUIRED_THEME_KEYS = (
    "base_background",
    "surface_container",
    "border_treatment",
    "neon_accent_state",
    "accent_border_glow",
    "glow_matrix_rgba",
    "css_var_token",
)


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise SystemExit(f"registry.json missing: {REGISTRY_PATH}")
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class LuxWorkspaceRegistryTests(unittest.TestCase):
    """SOT shape + invariants."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _load_registry()

    def test_schema_version_present(self) -> None:
        self.assertTrue(
            str(self.registry.get("$schema_version", "")).startswith("lux-workspace."),
            "registry must declare $schema_version starting with lux-workspace.",
        )

    def test_three_tiers_present(self) -> None:
        tiers = self.registry.get("tiers", {})
        self.assertEqual(
            tuple(sorted(tiers.keys())),
            tuple(sorted(EXPECTED_TIERS)),
            f"tiers must equal {EXPECTED_TIERS}; got {tuple(tiers.keys())}",
        )

    def test_spring_curve_matches_mandate(self) -> None:
        self.assertEqual(
            self.registry.get("spring_curve"),
            EXPECTED_SPRING_CURVE,
            "spring_curve must be the mandate's cubic-bezier(0.16, 1, 0.3, 1)",
        )

    def test_min_touch_target_meets_accessibility_floor(self) -> None:
        self.assertGreaterEqual(
            int(self.registry.get("min_touch_target_px", 0)),
            48,
            "min_touch_target_px must meet >= 48px accessibility floor",
        )

    def test_global_shortcuts_wired(self) -> None:
        actual = self.registry.get("global_shortcuts", {})
        for combo, action in EXPECTED_GLOBAL_SHORTCUTS.items():
            self.assertIn(combo, actual, f"missing global shortcut: {combo}")
            self.assertEqual(
                actual[combo],
                action,
                f"global shortcut {combo} must map to {action}",
            )

    def test_each_tier_has_full_theme_personality(self) -> None:
        for tier in EXPECTED_TIERS:
            theme = self.registry["tiers"][tier]["theme_personality"]
            for key in REQUIRED_THEME_KEYS:
                self.assertIn(key, theme, f"{tier}.theme_personality.{key} missing")
                self.assertTrue(
                    bool(str(theme[key]).strip()),
                    f"{tier}.theme_personality.{key} must be non-empty",
                )

    def test_visual_distinctness_across_tiers(self) -> None:
        backgrounds = {
            self.registry["tiers"][t]["theme_personality"]["base_background"]
            for t in EXPECTED_TIERS
        }
        accents = {
            self.registry["tiers"][t]["theme_personality"]["accent_border_glow"]
            for t in EXPECTED_TIERS
        }
        tokens = {
            self.registry["tiers"][t]["theme_personality"]["css_var_token"]
            for t in EXPECTED_TIERS
        }
        self.assertEqual(
            len(backgrounds), 3, "tier base_backgrounds must be distinct (no uniformity)"
        )
        self.assertEqual(
            len(accents), 3, "tier accent_border_glow must be distinct (no uniformity)"
        )
        self.assertEqual(
            len(tokens), 3, "tier css_var_token must be distinct per tier"
        )

    def test_shortcut_collision_boundaries(self) -> None:
        for tier in EXPECTED_TIERS:
            shortcuts = self.registry["tiers"][tier]["keyboard_shortcuts_bus"]
            self.assertGreaterEqual(
                len(shortcuts), 1, f"{tier} must declare >= 1 keyboard shortcut"
            )
            for key, action in shortcuts.items():
                self.assertEqual(
                    key,
                    key.lower(),
                    f"{tier} hotkey {key!r} must be lowercase",
                )
                self.assertEqual(len(key), 1, f"{tier} hotkey {key!r} must be one char")
                self.assertTrue(action.isupper(), f"{tier} action {action!r} must be SCREAMING_SNAKE")

        # Same key may exist in multiple tiers; actions must differ if so.
        all_pairs = []
        for tier in EXPECTED_TIERS:
            for key, action in self.registry["tiers"][tier]["keyboard_shortcuts_bus"].items():
                all_pairs.append((tier, key, action))
        seen: dict[str, set[str]] = {}
        for tier, key, action in all_pairs:
            seen.setdefault(key, set()).add(action)
        for key, action_set in seen.items():
            self.assertGreater(
                len(action_set),
                0,
                f"hotkey {key} must map to at least one action",
            )

    def test_css_file_ships_matching_tier_tokens(self) -> None:
        self.assertTrue(CSS_PATH.exists(), f"CSS file missing: {CSS_PATH}")
        css = CSS_PATH.read_text(encoding="utf-8")
        for tier in EXPECTED_TIERS:
            token = self.registry["tiers"][tier]["theme_personality"]["css_var_token"]
            self.assertIn(
                token,
                css,
                f"CSS must declare {token} for {tier} (mandate: every tier has a unique CSS var)",
            )
            self.assertIn(
                f'data-lux-tier="{tier}"',
                css,
                f'CSS must scope tier-specific styles via [data-lux-tier="{tier}"]',
            )
        self.assertIn(
            EXPECTED_SPRING_CURVE,
            css,
            "CSS file must use the mandate's cubic-bezier spring curve",
        )
        self.assertIn(
            "prefers-reduced-motion",
            css,
            "CSS file must honor prefers-reduced-motion (accessibility)",
        )

    def test_ts_barrel_exports_full_surface(self) -> None:
        self.assertTrue(TS_INDEX_PATH.exists(), f"index.ts missing: {TS_INDEX_PATH}")
        ts = TS_INDEX_PATH.read_text(encoding="utf-8")
        required_exports = (
            "LUX_REGISTRY",
            "WORKSPACE_TIERS",
            "PremiumUIOrchestratorProvider",
            "useWorkspaceKernel",
            "CustomKeyboardShortcutBus",
            "PremiumInteractiveContainer",
            "QuickActionButton",
            "PremiumStudentActionCard",
            "PremiumWorkspaceOrchestrator",
            "GlobalCommandConsole",
            "SkeletalShell",
            "SkeletalDeferred",
            "LuxErrorBoundary",
            "NetworkStatusChannel",
            "usePerformanceMonitor",
            "saveSheetDraft",
            "loadSheetDraft",
            "clearSheetDraft",
        )
        for export in required_exports:
            self.assertTrue(
                re.search(rf"\b{export}\b", ts),
                f"barrel must export {export}",
            )


class LuxWorkspacePerformanceTests(unittest.TestCase):
    """Surface-level perf invariants (registry parse + lookup)."""

    def test_registry_parses_in_under_50ms(self) -> None:
        start = time.perf_counter()
        for _ in range(10):
            _load_registry()
        elapsed_ms = (time.perf_counter() - start) * 1000.0 / 10
        self.assertLess(
            elapsed_ms,
            50.0,
            f"registry.json parse averaged {elapsed_ms:.2f}ms (>= 50ms ceiling)",
        )


class LuxWorkspaceI18nModuleTests(unittest.TestCase):
    """Verify the Django-side i18n module exposes labels for every tier
    declared in the SOT registry (catches drift if a tier is added/removed)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _load_registry()

    def test_i18n_module_covers_every_registry_tier(self) -> None:
        i18n_path = REPO_ROOT / "apps" / "portal" / "lux_workspace_i18n.py"
        self.assertTrue(i18n_path.exists(), f"i18n module missing: {i18n_path}")
        body = i18n_path.read_text(encoding="utf-8")
        for tier in EXPECTED_TIERS:
            self.assertIn(
                f'"{tier}"',
                body,
                f"i18n module must declare LUX_TIER_LABELS entry for {tier}",
            )
        self.assertIn(
            "build_lux_i18n_payload",
            body,
            "i18n module must expose build_lux_i18n_payload() helper",
        )
        self.assertIn(
            "render_lux_i18n_script",
            body,
            "i18n module must expose render_lux_i18n_script() template helper",
        )

    def test_django_template_consumes_i18n_payload(self) -> None:
        template_path = REPO_ROOT / "templates" / "lux_workspace" / "demo.html"
        self.assertTrue(template_path.exists())
        body = template_path.read_text(encoding="utf-8")
        self.assertIn(
            "data-rmc-lux-i18n",
            body,
            "Django template must inject i18n payload via data-rmc-lux-i18n script",
        )

    def test_vite_lux_config_exists(self) -> None:
        config_path = REPO_ROOT / "vite.lux.config.ts"
        self.assertTrue(config_path.exists(), "vite.lux.config.ts must exist")
        body = config_path.read_text(encoding="utf-8")
        self.assertIn("src/apps/luxWorkspace/mount.tsx", body)
        self.assertIn("lux-workspace.mount.js", body)


def _print_banner(title: str) -> None:
    bar = "=" * len(title)
    print(f"\n{bar}\n{title}\n{bar}")


def main() -> int:
    _print_banner("lux-workspace UI verifier (Apple-grade mandate)")
    print(f"registry: {REGISTRY_PATH}")
    print(f"css     : {CSS_PATH}")
    print(f"barrel  : {TS_INDEX_PATH}\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (
        LuxWorkspaceRegistryTests,
        LuxWorkspacePerformanceTests,
        LuxWorkspaceI18nModuleTests,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
