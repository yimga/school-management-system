"""The gate that would have caught a middleware nobody registered.

Stdlib only — no Django — so these run in the deps-free boundary job alongside
the scanner itself.
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "scan_unregistered_middleware.py"


def _load():
    spec = importlib.util.spec_from_file_location("scan_unregistered_middleware", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()


class RegistrationCandidateTests(unittest.TestCase):
    def test_defining_path_is_a_candidate(self):
        candidates = MOD._registration_candidates("apps.sync_engine.middleware_x.FooMiddleware")
        self.assertIn("apps.sync_engine.middleware_x.FooMiddleware", candidates)

    def test_package_reexport_is_accepted(self):
        """apps/siteconfig/middleware/__init__.py re-exports; both forms are correct."""
        candidates = MOD._registration_candidates(
            "apps.siteconfig.middleware.maintenance_mode.MaintenanceModeMiddleware"
        )
        self.assertIn(
            "apps.siteconfig.middleware.MaintenanceModeMiddleware", candidates
        )

    def test_an_unrelated_class_of_the_same_name_is_not_matched(self):
        candidates = MOD._registration_candidates("apps.a.b.FooMiddleware")
        self.assertNotIn("apps.zzz.FooMiddleware", candidates)


class LiveTreeTests(unittest.TestCase):
    def test_the_tree_scans_clean(self):
        """Calibration: if this fails, something real is unwired — fix it, don't skip."""
        haystack = MOD._config_text()
        unregistered = [
            dotted
            for dotted, _rel, _line in MOD._iter_middleware_classes()
            if dotted not in MOD.ALLOWLIST
            and not any(c in haystack for c in MOD._registration_candidates(dotted))
        ]
        self.assertEqual(unregistered, [], f"unregistered middleware: {unregistered}")

    def test_the_edge_autosync_middleware_is_actually_registered(self):
        """The specific regression. It was dead for months; keep it wired."""
        self.assertIn(
            "apps.sync_engine.middleware_edge_autosync.EdgeAutosyncMiddleware",
            MOD._config_text(),
        )

    def test_every_allowlist_entry_still_names_a_real_class(self):
        """A stale allowlist silently re-opens the hole for the next class of that name."""
        defined = {dotted for dotted, _r, _l in MOD._iter_middleware_classes()}
        stale = sorted(set(MOD.ALLOWLIST) - defined)
        self.assertEqual(stale, [], f"remove these stale allowlist entries: {stale}")

    def test_allowlist_reasons_are_real_reasons(self):
        for entry, reason in MOD.ALLOWLIST.items():
            self.assertGreater(len(reason.strip()), 20, f"lazy allowlist reason for {entry}")


class DiscoveryTests(unittest.TestCase):
    def test_tests_directories_are_skipped(self):
        """A test double is not production wiring; flagging it teaches people to ignore
        the gate, which is how the real finding gets buried."""
        found = [str(rel) for _d, rel, _l in MOD._iter_middleware_classes()]
        self.assertFalse(
            [p for p in found if "tests" in p.replace("\\", "/").split("/")],
            "test files must not be scanned",
        )

    def test_private_classes_are_skipped(self):
        found = [d for d, _r, _l in MOD._iter_middleware_classes()]
        self.assertFalse([d for d in found if d.rsplit(".", 1)[-1].startswith("_")])

    def test_it_finds_a_meaningful_number_of_classes(self):
        """Guards against a discovery bug making the gate vacuously green."""
        self.assertGreater(len(list(MOD._iter_middleware_classes())), 50)

    def test_class_regex_matches_plain_and_subclassed_forms(self):
        source = textwrap.dedent(
            """
            class PlainMiddleware:
                pass

            class SubclassedMiddleware(MiddlewareMixin):
                pass

            class NotRelated:
                pass
            """
        )
        names = [m.group(1) for m in MOD.CLASS_RE.finditer(source)]
        self.assertEqual(names, ["PlainMiddleware", "SubclassedMiddleware"])


if __name__ == "__main__":
    unittest.main()
