"""Both directions for scan_dangling_static_reference: what it must catch, and what it must not.

The must-NOT-fire half is the load-bearing half here. The first cut of this
scanner reported 42 findings against the real tree; 40 were JavaScript locals
matched by a CSS ``url()`` rule, and the other 2 were a nested ``url(%23n)``
inside an inline SVG data URI. All 42 were false. Every one of those shapes is
pinned below, because a gate reporting 42 findings of which 0 are real is a gate
that gets switched off in a week.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "scan_dangling_static_reference",
    Path(__file__).resolve().parents[1] / "scan_dangling_static_reference.py",
)
scanner = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(scanner)


class _TreeCase(unittest.TestCase):
    """Build a throwaway static/ tree and scan it."""

    def scan_tree(self, files: dict) -> tuple[list, list]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative, content in files.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, str):
                    content = content.encode("utf-8")
                target.write_bytes(content)
            dev_only, shipped, _ = scanner.scan(root)
        return dev_only, shipped


class WhatItMustCatchTests(_TreeCase):
    def test_a_font_that_was_never_shipped(self):
        """The exact 2026-09-02 defect, cache-buster and all."""
        _, shipped = self.scan_tree(
            {
                "static/vendor/icons/css/icons.css": (
                    '@font-face{src:url("fonts/icons.woff2") format("woff2"),'
                    'url("fonts/icons.woff?dd67030699838ea6") format("woff")}'
                ),
                "static/vendor/icons/css/fonts/icons.woff2": b"\x00",
            }
        )
        self.assertEqual(len(shipped), 1, shipped)
        self.assertIn("icons.woff?dd67030699838ea6", shipped[0][1])

    def test_a_missing_background_image(self):
        _, shipped = self.scan_tree(
            {"static/css/app.css": "body{background:url('../img/hero.png')}"}
        )
        self.assertEqual(len(shipped), 1, shipped)

    def test_an_unquoted_url_is_still_a_reference(self):
        """url() without quotes is valid CSS, and is the shape
        verify_gates_can_fail plants. If this stops matching, that harness goes
        dead silently and reports the gate as working."""
        _, shipped = self.scan_tree(
            {"static/css/f.css": "@font-face{src:url(fonts/gone.woff2) format(woff2)}"}
        )
        self.assertEqual(len(shipped), 1, shipped)

    def test_a_missing_import(self):
        _, shipped = self.scan_tree({"static/css/app.css": '@import "partials/_gone.css";'})
        self.assertEqual(len(shipped), 1, shipped)

    def test_an_absolute_reference_resolves_from_the_repo_root(self):
        _, shipped = self.scan_tree(
            {"static/css/app.css": "body{background:url('/static/img/gone.png')}"}
        )
        self.assertEqual(len(shipped), 1, shipped)


class WhatItMustNotFireOnTests(_TreeCase):
    def test_a_url_call_in_javascript_is_not_a_css_reference(self):
        """40 of the first cut's 42 findings were exactly this."""
        dev_only, shipped = self.scan_tree(
            {
                "static/js/auth.js": (
                    "const a = url(credential.rawId);\n"
                    "const b = url(response.signature);\n"
                    "const c = url(key, fallback);\n"
                )
            }
        )
        self.assertEqual(shipped, [], shipped)
        self.assertEqual(dev_only, [], dev_only)

    def test_a_nested_url_inside_an_inline_svg_data_uri(self):
        """The other 2. `filter='url(%23n)'` is SVG-internal, not an asset."""
        _, shipped = self.scan_tree(
            {
                "static/css/noise.css": (
                    "body{background-image:url(\"data:image/svg+xml,%3Csvg%3E"
                    "%3Cfilter id='n'%3E%3C/filter%3E%3Crect filter='url(%23n)'/%3E"
                    "%3C/svg%3E\")}"
                )
            }
        )
        self.assertEqual(shipped, [], shipped)

    def test_a_bare_unquoted_data_uri(self):
        _, shipped = self.scan_tree(
            {"static/css/a.css": "i{background:url(data:image/gif;base64,R0lGOD)}"}
        )
        self.assertEqual(shipped, [], shipped)

    def test_a_remote_reference_is_not_ours_to_ship(self):
        _, shipped = self.scan_tree(
            {
                "static/css/a.css": (
                    "@import url('https://fonts.example/x.css');"
                    "b{background:url(//cdn.example/y.png)}"
                )
            }
        )
        self.assertEqual(shipped, [], shipped)

    def test_a_file_that_is_actually_present(self):
        _, shipped = self.scan_tree(
            {
                "static/css/app.css": "body{background:url('../img/hero.png')}",
                "static/img/hero.png": b"\x89PNG",
            }
        )
        self.assertEqual(shipped, [], shipped)


class SourceMapsAreCountedNotFlaggedTests(_TreeCase):
    def test_a_missing_map_is_dev_only_never_a_shipped_gap(self):
        dev_only, shipped = self.scan_tree(
            {"static/js/vendor/dexie.min.js": "//# sourceMappingURL=dexie.min.js.map"}
        )
        self.assertEqual(shipped, [], shipped)
        self.assertEqual(len(dev_only), 1, dev_only)

    def test_a_map_reference_with_a_trailing_space(self):
        """The vendored bootstrap CSS really carries one -- verified with cat -A."""
        dev_only, shipped = self.scan_tree(
            {"static/vendor/b/b.min.css": "/*# sourceMappingURL=b.min.css.map */"}
        )
        self.assertEqual(shipped, [], shipped)
        self.assertEqual(len(dev_only), 1, dev_only)

    def test_a_map_behind_a_cache_buster_is_still_dev_only(self):
        dev_only, shipped = self.scan_tree(
            {"static/js/a.js": "//# sourceMappingURL=a.js.map?v=3"}
        )
        self.assertEqual(shipped, [], shipped)
        self.assertEqual(len(dev_only), 1, dev_only)

    def test_a_name_that_merely_contains_map(self):
        _, shipped = self.scan_tree({"static/css/a.css": "b{background:url('sitemap.png')}"})
        self.assertEqual(len(shipped), 1, "sitemap.png is a shipped asset, not a source map")


class TheGateItselfTests(unittest.TestCase):
    def test_the_real_tree_is_clean(self):
        """Zero-tolerance from introduction -- there is no baseline to erode."""
        self.assertEqual(scanner.main(["--compare"]), 0)


if __name__ == "__main__":
    unittest.main()
