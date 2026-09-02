"""A deploy log that cries wolf hides the one line that matters.

``ForgivingCompressedManifestStaticFilesStorage`` refuses to fail a deploy over a
referenced asset that was not collected -- correct, and the reason hashed static
files could be turned on at all. But it logged every such miss at WARNING, and
manifest post-processing makes several passes, so a production deploy printed
roughly two dozen identical source-map warnings.

Buried among them on 2026-09-02 was this:

    leaving 'vendor/bootstrap-icons/css/fonts/bootstrap-icons.woff?dd670306...'
    un-hashed (missing reference: ...)

That one is not a source map. It is a font the CSS asks for and the vendoring
step never copied -- only ``.woff2`` was shipped. It read exactly like the noise
around it, which is how it survived unnoticed.

So the level now carries the meaning: a missing ``.map`` is expected and logs at
INFO, anything else is a real gap in the shipped asset set and stays at WARNING.

The subtle part is the query string. Upstream writes cache-busting references
like ``fonts/bootstrap-icons.woff?dd670306...``, so a naive ``endswith(".map")``
against the raw name is not the bug -- the bug would be a naive check that let a
``.map?v=1`` through as a real asset, or that failed to strip the query and
mis-set the level. Both directions are pinned below.
"""

from __future__ import annotations

import logging

from django.test import SimpleTestCase

from apps.siteconfig.staticfiles_storage import (
    ForgivingCompressedManifestStaticFilesStorage as Storage,
)


class WhatCountsAsDevOnlyTests(SimpleTestCase):
    """Classification only -- no storage backend, no collected tree, no DB."""

    def setUp(self):
        self.classify = Storage._reference_is_dev_only.__get__(
            Storage.__new__(Storage), Storage
        )

    def test_a_plain_source_map_is_dev_only(self):
        self.assertTrue(self.classify("js/vendor/dexie.min.js.map"))

    def test_a_css_source_map_is_dev_only(self):
        self.assertTrue(self.classify("vendor/bootstrap/css/bootstrap.min.css.map"))

    def test_a_source_map_with_a_trailing_space_is_still_dev_only(self):
        """The vendored bootstrap CSS really does carry a trailing space.

        ``sourceMappingURL=bootstrap.min.css.map `` -- verified with ``cat -A``.
        Without the rstrip this would be classified as a missing shipped asset
        and shout on every deploy forever.
        """
        self.assertTrue(self.classify("vendor/bootstrap/css/bootstrap.min.css.map "))

    def test_a_source_map_behind_a_query_string_is_dev_only(self):
        self.assertTrue(self.classify("js/thing.js.map?v=3"))

    def test_a_source_map_behind_a_fragment_is_dev_only(self):
        self.assertTrue(self.classify("js/thing.js.map#sourceMappingURL"))

    # --- the direction that actually mattered --------------------------------

    def test_a_font_with_a_cache_busting_query_is_NOT_dev_only(self):
        """The exact reference that hid in the noise."""
        self.assertFalse(
            self.classify(
                "vendor/bootstrap-icons/css/fonts/bootstrap-icons.woff"
                "?dd67030699838ea613ee6dbda90effa6"
            )
        )

    def test_a_plain_font_is_not_dev_only(self):
        self.assertFalse(self.classify("fonts/bootstrap-icons.woff2"))

    def test_a_script_is_not_dev_only(self):
        self.assertFalse(self.classify("js/app.js"))

    def test_a_stylesheet_is_not_dev_only(self):
        self.assertFalse(self.classify("css/app.css"))

    def test_a_name_that_merely_contains_map_is_not_dev_only(self):
        """``.endswith`` on the stripped base, not a substring search."""
        self.assertFalse(self.classify("img/sitemap.png"))
        self.assertFalse(self.classify("js/mapbox.js"))


class TheLevelCarriesTheMeaningTests(SimpleTestCase):
    """A missing reference must never fail the deploy -- only change volume."""

    def _run(self, name):
        """Call the real hashed_name with the superclass forced to raise."""
        storage = Storage.__new__(Storage)

        def _raise(*_a, **_k):
            raise ValueError(f"The file '{name}' could not be found")

        original = Storage.__mro__[1].hashed_name
        try:
            Storage.__mro__[1].hashed_name = _raise
            with self.assertLogs("siteconfig.staticfiles", level=logging.INFO) as caught:
                returned = Storage.hashed_name(storage, name)
            return returned, caught.records
        finally:
            Storage.__mro__[1].hashed_name = original

    def test_a_missing_source_map_is_information_not_a_warning(self):
        returned, records = self._run("js/vendor/dexie.min.js.map")
        self.assertEqual(returned, "js/vendor/dexie.min.js.map", "must serve un-hashed")
        self.assertEqual([r.levelno for r in records], [logging.INFO])

    def test_a_missing_shipped_asset_still_warns(self):
        name = "vendor/bootstrap-icons/css/fonts/bootstrap-icons.woff?dd670306"
        returned, records = self._run(name)
        self.assertEqual(returned, name, "must serve un-hashed")
        self.assertEqual([r.levelno for r in records], [logging.WARNING])
        self.assertIn("MISSING SHIPPED ASSET", records[0].getMessage())

    def test_neither_case_raises(self):
        """The whole point of the subclass: a deploy never dies over this."""
        for name in ("a/b.js.map", "a/b.woff"):
            with self.subTest(name=name):
                returned, _ = self._run(name)
                self.assertEqual(returned, name)


class TheGateAndTheStorageMustAgreeTests(SimpleTestCase):
    """Two copies of one rule, and they are not importable from each other.

    ``scripts/scan_dangling_static_reference.py`` decides the same question at
    push time that the storage decides at deploy time: is this miss a dev-only
    artifact or a real gap? The scanner is stdlib-only on purpose -- it rides the
    deps-free boundary workflow and cannot import Django app code -- so the
    suffix list is duplicated by necessity. Nothing but this test stops the two
    drifting apart, which would let the gate pass a shape the deploy still warns
    about, or the reverse."""

    def _scanner(self):
        import importlib.util
        from pathlib import Path as _Path

        path = _Path(__file__).resolve().parents[3] / (
            "scripts/scan_dangling_static_reference.py"
        )
        if not path.is_file():
            self.skipTest("scanner not present at %s" % path)
        spec = importlib.util.spec_from_file_location("_dangling_scan", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_dev_only_suffix_list_is_the_same_on_both_sides(self):
        self.assertEqual(
            tuple(self._scanner().DEV_ONLY_SUFFIXES),
            tuple(Storage.DEV_ONLY_SUFFIXES),
            "the push gate and the deploy log would disagree about what is expected",
        )

    def test_both_sides_classify_the_same_references_the_same_way(self):
        scanner = self._scanner()
        classify = Storage._reference_is_dev_only.__get__(
            Storage.__new__(Storage), Storage
        )
        for reference in (
            "js/vendor/dexie.min.js.map",
            "vendor/bootstrap/css/bootstrap.min.css.map ",
            "js/thing.js.map?v=3",
            "vendor/bootstrap-icons/css/fonts/bootstrap-icons.woff?dd670306",
            "img/sitemap.png",
            "css/app.css",
        ):
            with self.subTest(reference=reference):
                self.assertEqual(
                    scanner.is_dev_only(scanner.normalise(reference)),
                    classify(reference),
                )


class TheDeadFontReferenceIsGoneTests(SimpleTestCase):
    """Fixing the log level does not fix the asset. This does."""

    def test_the_vendored_css_no_longer_asks_for_a_woff_that_is_not_shipped(self):
        from pathlib import Path

        css = Path(
            "static/vendor/bootstrap-icons/css/bootstrap-icons.min.css"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn(
            'format("woff")',
            css,
            "the .woff fallback is still declared but only .woff2 is vendored",
        )
        self.assertIn('format("woff2")', css, "woff2 must still be declared")

    def test_only_woff2_is_actually_vendored(self):
        """Guard the guard: if someone ships the .woff, revisit the line above."""
        from pathlib import Path

        fonts = Path("static/vendor/bootstrap-icons/css/fonts")
        names = sorted(p.name for p in fonts.iterdir() if p.is_file())
        self.assertEqual(names, ["bootstrap-icons.woff2"])
