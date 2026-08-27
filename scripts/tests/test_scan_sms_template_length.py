"""The length check behind `scripts/scan_sms_template_length.py`.

WHY THIS FILE EXISTS
--------------------
The scanner reported a clean zero for its entire life, and the zero was a
fiction. ``_is_sms_module`` only opens files whose NAME says sms, which in this
tree matches exactly one module -- and that module holds no SMS the platform
actually sends. Every real body lives in ``apps/communication/template_catalog.py``
under entries that declare ``"sms"`` in their ``channels`` list, and the scanner
had never opened it.

A gate that cannot fail is worse than no gate, because it is a green light
nobody re-checks. So these tests do not assert "the tree is clean" -- they
assert the MATCHER FIRES, by driving the threshold down until known bodies must
be caught, and that it stays silent when nothing exceeds the limit. The clean
tree is then a measurement rather than an article of faith.

They also pin the two ratchet properties the scanner was missing: it enforces
without being asked (`--strict` raises the bar, it does not switch enforcement
on), and a checking run refuses to author the baseline it is checking against.

Stdlib only -- no Django, so this runs in the deps-free boundary job.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scan_sms_template_length.py"
_spec = importlib.util.spec_from_file_location("scan_sms_template_length", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["scan_sms_template_length"] = mod
_spec.loader.exec_module(mod)


@contextlib.contextmanager
def threshold(chars: int):
    """Move the segment limit instead of editing a product file to force a hit."""
    original = mod.MAX_SMS_CHARS
    mod.MAX_SMS_CHARS = chars
    try:
        yield
    finally:
        mod.MAX_SMS_CHARS = original


class CatalogIsActuallyReadTests(unittest.TestCase):
    """The bodies are in a catalog, not in a file whose name says sms."""

    def setUp(self):
        self.rel, self.spec = next(iter(mod.CHANNEL_CATALOGS.items()))

    def test_the_declared_catalog_exists(self):
        """A typo'd path would silently return [] and read as 'all clear'."""
        self.assertTrue(
            (mod.REPO_ROOT / self.rel).is_file(),
            f"{self.rel} is declared in CHANNEL_CATALOGS but is not in the tree",
        )

    def test_the_census_finds_sms_bodies(self):
        """The failure this gate shipped with: reading a file, finding nothing."""
        census = mod._catalog_census(self.rel, self.spec)
        self.assertGreater(
            len(census),
            0,
            "no sms bodies found in the catalog -- the scanner is looking in the "
            "wrong place again, which is exactly how it reported 0 for so long",
        )

    def test_every_census_row_is_rendered_not_raw(self):
        """A body measured with its {placeholders} intact is not a measurement."""
        for length, _lineno, name in mod._catalog_census(self.rel, self.spec):
            with self.subTest(entry=name):
                self.assertGreater(length, 0, f"{name} rendered to nothing")


class MatcherCanFailTests(unittest.TestCase):
    """Prove a non-zero before believing a zero."""

    def setUp(self):
        self.rel, self.spec = next(iter(mod.CHANNEL_CATALOGS.items()))

    def test_findings_appear_when_the_limit_is_lowered(self):
        with threshold(60):
            hits = mod._catalog_findings(self.rel, self.spec)
        self.assertGreater(
            len(hits),
            0,
            "lowering the limit below every known body produced no findings, so "
            "the finding path is dead code",
        )

    def test_a_finding_names_the_entry_and_the_cost(self):
        with threshold(60):
            hits = mod._catalog_findings(self.rel, self.spec)
        joined = " ".join(hits)
        self.assertIn("SMS segments", joined)
        self.assertIn(self.rel, joined)

    def test_no_findings_when_the_limit_is_generous(self):
        """The other half of the proof: it is not simply flagging everything."""
        with threshold(5000):
            self.assertEqual(mod._catalog_findings(self.rel, self.spec), [])

    def test_scan_all_includes_the_catalog(self):
        """_catalog_findings existed but was never called -- that shipped once."""
        with threshold(60):
            self.assertGreater(
                len(mod.scan_all()),
                0,
                "scan_all() does not consult CHANNEL_CATALOGS, so the catalog "
                "scan is unreachable no matter how correct it is",
            )


class RatchetDisciplineTests(unittest.TestCase):
    """A ratchet must enforce by default and must not write its own reference."""

    def test_compare_run_refuses_to_author_a_missing_baseline(self):
        original = mod.BASELINE_PATH
        missing = Path(str(original) + ".test-does-not-exist")
        mod.BASELINE_PATH = missing
        try:
            buf, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                sys.argv = ["scan_sms_template_length.py", "--compare"]
                rc = mod.main()
            self.assertEqual(rc, 1, "a --compare run with no baseline passed")
            self.assertFalse(
                missing.exists(),
                "the checking run CREATED the baseline it was checking against, "
                "which re-anchors the ratchet to whatever it happened to find",
            )
        finally:
            mod.BASELINE_PATH = original
            missing.unlink(missing_ok=True)

    def test_strict_is_a_tighter_bar_not_the_on_switch(self):
        """Enforcement must not depend on the runner remembering a flag."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn(
            "if args.strict and total > baseline_total",
            source,
            "enforcement is gated behind --strict again; the gate then passes "
            "for any runner that forgets the flag",
        )
        self.assertIn("limit = 0 if args.strict else baseline_total", source)


if __name__ == "__main__":
    unittest.main()
