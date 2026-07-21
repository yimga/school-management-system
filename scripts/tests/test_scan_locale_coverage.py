"""Lock the locale-coverage gate -- including its must-fire negative controls.

Stdlib-only (mirrors the gate, which runs in the dependency-free
architectural-boundaries job). Loads the script by path so it works without a
package install.

Until 2026-07-21 this gate was regression-only: it compared each locale's
translated count against a baseline and failed only when a count *dropped*. A
locale that had always been at 0% had nothing to drop from, so it was
permanently green -- and a brand-new ``locale/xx`` with zero translations was
invisible twice over, because the scan iterated a hard-coded tuple instead of
the filesystem. ``ContractMustFireTests`` reintroduces exactly that situation
and asserts the gate now turns red, while asserting in the same test that the
old regression rule still reports nothing -- i.e. proving the new check is
load-bearing rather than incidentally green.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[1] / "scan_locale_coverage.py"
_spec = importlib.util.spec_from_file_location("_locale_coverage_gate", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
# Register before exec: the module defines a @dataclass, and dataclasses
# resolves cls.__module__ through sys.modules (hard requirement on 3.12+).
sys.modules["_locale_coverage_gate"] = mod
_spec.loader.exec_module(mod)


def _po(translated: int, total: int) -> str:
    """A minimal but real .po: header pseudo-entry + ``total`` msgids."""
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        "",
    ]
    for i in range(total):
        lines.append(f'msgid "m{i}"')
        lines.append(f'msgstr "{"t" + str(i) if i < translated else ""}"')
        lines.append("")
    return "\n".join(lines)


@contextlib.contextmanager
def fake_tree(catalogs: dict[str, tuple[int, int]], declarations: dict):
    """Run the gate against a throwaway locale/ tree with its own declarations."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        locale_root = root / "locale"
        for code, (translated, total) in catalogs.items():
            d = locale_root / code / "LC_MESSAGES"
            d.mkdir(parents=True, exist_ok=True)
            (d / "django.po").write_text(_po(translated, total), encoding="utf-8")
        with mock.patch.object(mod, "REPO_ROOT", root), mock.patch.object(
            mod, "LOCALE_ROOT", locale_root
        ), mock.patch.object(
            mod, "BASELINE_PATH", root / "var" / "baseline.json"
        ), mock.patch.object(
            mod, "EXPECTED_LOCALES", tuple(declarations)
        ), mock.patch.object(
            mod, "LOCALE_DECLARATIONS", dict(declarations)
        ):
            yield


_EN = {"en": ("source", "source catalog")}


class ContractMustFireTests(unittest.TestCase):
    """Reintroduce the defect the gate exists to catch; it must turn red."""

    def test_undeclared_locale_at_zero_percent_turns_the_gate_red(self):
        with fake_tree({"en": (10, 10), "xx": (0, 10)}, _EN):
            stats = mod._scan()
            violations = mod._contract_violations(stats)
            # MUST FIRE: the new absolute contract catches it...
            self.assertTrue(
                any(v.startswith("xx:") for v in violations),
                f"expected an 'xx' finding, got {violations}",
            )
            self.assertEqual(mod._report(stats, check_regressions=True), 1)
            # ...and the OLD regression-only rule reports nothing at all, which
            # is precisely why a 0% locale used to stay green forever.
            self.assertEqual(mod._regressions(stats), [])

    def test_new_locale_is_discovered_not_read_from_a_hardcoded_tuple(self):
        with fake_tree({"en": (10, 10), "xx": (0, 10)}, _EN):
            self.assertIn("xx", mod._discovered_locales())
            self.assertIn("xx", [s.locale for s in mod._scan()])

    def test_declared_stub_at_zero_percent_is_green(self):
        decls = dict(_EN, xx=("stub", "ships untranslated, falls back to English"))
        with fake_tree({"en": (10, 10), "xx": (0, 10)}, decls):
            stats = mod._scan()
            self.assertEqual(mod._contract_violations(stats), [])
            self.assertEqual(mod._report(stats, check_regressions=True), 0)

    def test_declared_full_below_the_floor_turns_the_gate_red(self):
        decls = dict(_EN, xx=("full", "claimed as a translated locale"))
        with fake_tree({"en": (10, 10), "xx": (1, 10)}, decls):
            violations = mod._contract_violations(mod._scan())
            self.assertTrue(any("declared 'full'" in v for v in violations), violations)

    def test_stale_stub_declaration_turns_the_gate_red(self):
        """A stub that reached the floor must be promoted, not left declared."""
        decls = dict(_EN, xx=("stub", "ships untranslated"))
        with fake_tree({"en": (10, 10), "xx": (9, 10)}, decls):
            violations = mod._contract_violations(mod._scan())
            self.assertTrue(any("stale declaration" in v for v in violations), violations)

    def test_empty_reason_turns_the_gate_red(self):
        decls = dict(_EN, xx=("stub", "   "))
        with fake_tree({"en": (10, 10), "xx": (0, 10)}, decls):
            violations = mod._contract_violations(mod._scan())
            self.assertTrue(any("empty reason" in v for v in violations), violations)

    def test_source_locale_below_its_floor_turns_the_gate_red(self):
        with fake_tree({"en": (5, 10)}, _EN):
            violations = mod._contract_violations(mod._scan())
            self.assertTrue(any("source locale" in v for v in violations), violations)

    def test_declaration_without_a_catalog_turns_the_gate_red(self):
        decls = dict(_EN, xx=("stub", "declared but never shipped"))
        with fake_tree({"en": (10, 10)}, decls):
            violations = mod._contract_violations(mod._scan())
            self.assertTrue(any("no catalog on disk" in v for v in violations), violations)

    def test_unserved_declaration_is_a_known_gap_not_a_violation(self):
        decls = dict(_EN, xx=("unserved", "tracked but not in settings.LANGUAGES"))
        with fake_tree({"en": (10, 10), "xx": (10, 10)}, decls):
            stats = mod._scan()
            self.assertEqual(mod._contract_violations(stats), [])
            self.assertTrue(any(g.startswith("xx:") for g in mod._known_gaps(stats)))

    def test_regression_check_still_fires(self):
        """The original behaviour must survive the rewrite."""
        decls = dict(_EN, xx=("stub", "ships untranslated"))
        # Baseline says xx had 4 translated strings; the tree now has 1.
        with fake_tree({"en": (10, 10), "xx": (1, 10)}, decls):
            stats = mod._scan()
            with mock.patch.object(
                mod,
                "_load_baseline",
                return_value={
                    "findings": [
                        {"locale": "en", "translated": 10},
                        {"locale": "xx", "translated": 4},
                    ]
                },
            ):
                self.assertEqual(
                    mod._regressions(stats), ["xx: translated dropped 4 -> 1"]
                )
                self.assertEqual(mod._report(stats, check_regressions=True), 1)


class RealTreeTests(unittest.TestCase):
    def test_clean_tree_is_green(self):
        stats = mod._scan()
        self.assertEqual(mod._contract_violations(stats), [])
        self.assertEqual(mod._report(stats, check_regressions=True), 0)

    def test_every_shipped_locale_is_declared_with_a_reason(self):
        for code in mod._discovered_locales():
            with self.subTest(locale=code):
                decl = mod._declaration(code)
                self.assertIsNotNone(decl, f"{code} ships a catalog but is undeclared")
                kind, reason = decl
                self.assertIn(kind, ("source", "full", "stub", "unserved"))
                self.assertTrue(reason.strip(), f"{code} declared with no reason")

    def test_every_catalog_on_disk_is_actually_scanned(self):
        # locale/pt is tracked and gated by verify_critical_msgid_depth.py but
        # was absent from EXPECTED_LOCALES, so the old scan never opened it.
        # The invariant, stated so it stays true after anyone edits the tuple:
        # nothing on disk may be skipped.
        self.assertIn("pt", mod._discovered_locales())
        scanned = {s.locale for s in mod._scan()}
        self.assertEqual(set(mod._discovered_locales()) - scanned, set())

    def test_floor_is_a_real_number_not_derived_from_current_data(self):
        self.assertGreaterEqual(mod.MINIMUM_COVERAGE_PCT, 50.0)
        self.assertGreaterEqual(mod.SOURCE_MINIMUM_PCT, 95.0)


if __name__ == "__main__":
    unittest.main()
