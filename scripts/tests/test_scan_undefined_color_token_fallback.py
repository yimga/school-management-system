"""Unit tests for scan_undefined_color_token_fallback.py.

Covers the var() parser, tier classification, the three collapse shapes, the
excusal marker, and a live-tree-clean regression seal.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan_undefined_color_token_fallback as sut  # noqa: E402


class FirstVarParsing(unittest.TestCase):
    def test_bare(self):
        self.assertEqual(sut._first_var("var(--surface-2)"), ("--surface-2", None))

    def test_literal_fallback(self):
        self.assertEqual(sut._first_var("var(--text-danger, #b91c1c)"), ("--text-danger", "#b91c1c"))

    def test_var_fallback_nested(self):
        name, fb = sut._first_var("var(--accent-primary, var(--text-primary))")
        self.assertEqual(name, "--accent-primary")
        self.assertEqual(fb, "var(--text-primary)")

    def test_none_without_var(self):
        self.assertIsNone(sut._first_var("#ffffff"))


class TierClassification(unittest.TestCase):
    def test_surface(self):
        for n in ("--surface-bg", "--surface-canvas", "--bg-muted", "--card-bg", "--page-bg"):
            self.assertEqual(sut._tier(n), "surface", n)

    def test_text(self):
        for n in ("--text-primary", "--brand-accent-ink", "--ink-strong"):
            self.assertEqual(sut._tier(n), "text", n)

    def test_other(self):
        for n in ("--brand-primary", "--hairline", "--school-accent"):
            self.assertEqual(sut._tier(n), "other", n)


class EndToEnd(unittest.TestCase):
    def _scan(self, files):
        tmp = Path(tempfile.mkdtemp())
        for name, content in files.items():
            (tmp / name).write_text(content, encoding="utf-8")
        saved = (sut._CSS_DIRS, sut._TEMPLATE_DIRS, sut._JS_DIRS)
        sut._CSS_DIRS, sut._TEMPLATE_DIRS, sut._JS_DIRS = [tmp], [], []
        try:
            return sut.scan()
        finally:
            sut._CSS_DIRS, sut._TEMPLATE_DIRS, sut._JS_DIRS = saved

    def test_flags_bg_fallback_text(self):
        f = self._scan({"a.css": ".x{background:var(--nope,var(--text-primary));}"})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["shape"], "bg-fallback-text")

    def test_flags_color_fallback_surface(self):
        f = self._scan({"a.css": ".x{color:var(--nope,var(--surface-bg));}"})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["shape"], "text-fallback-surface")

    def test_flags_bare_undeclared(self):
        f = self._scan({"a.css": ".x{background:var(--gone);}"})
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["shape"], "bare-undeclared")

    def test_declared_token_not_flagged(self):
        f = self._scan({"a.css": ":root{--ok:#333;} .x{color:var(--ok,var(--surface-bg));}"})
        self.assertEqual(f, [])

    def test_literal_fallback_not_flagged(self):
        f = self._scan({"a.css": ".x{color:var(--nope,#fff);}"})
        self.assertEqual(f, [])

    def test_same_tier_fallback_not_flagged(self):
        # color falling back to a text token is fine (readable text)
        f = self._scan({"a.css": ".x{color:var(--nope,var(--text-secondary));}"})
        self.assertEqual(f, [])

    def test_marker_excuses(self):
        f = self._scan({"a.css": ".x{background:var(--gone); /* undefined-token-allow: test */}"})
        self.assertEqual(f, [])

    def test_inline_declared_token_not_flagged(self):
        # a token set only in a template inline style / JS is declared, not missing
        tmp = Path(tempfile.mkdtemp())
        (tmp / "a.css").write_text(".x{background:var(--runtime,var(--text-primary));}", encoding="utf-8")
        tpl = Path(tempfile.mkdtemp())
        (tpl / "t.html").write_text('<div style="--runtime: #123456;"></div>', encoding="utf-8")
        saved = (sut._CSS_DIRS, sut._TEMPLATE_DIRS, sut._JS_DIRS)
        sut._CSS_DIRS, sut._TEMPLATE_DIRS, sut._JS_DIRS = [tmp], [tpl], []
        try:
            self.assertEqual(sut.scan(), [])
        finally:
            sut._CSS_DIRS, sut._TEMPLATE_DIRS, sut._JS_DIRS = saved


class LiveTreeClean(unittest.TestCase):
    def test_live_tree_scans_clean(self):
        self.assertEqual(sut.scan(), [], "undefined-token colour collapses regressed on the live tree")


if __name__ == "__main__":
    unittest.main()
