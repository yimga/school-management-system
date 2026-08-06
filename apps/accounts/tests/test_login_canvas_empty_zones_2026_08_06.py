"""Must-fire seals: the login canvas never renders dead/empty zones (2026-08-06).

Audit-by-running showed three empty spaces on thin-data tenants + the manager
host: (1) the "Students" metric tile rendered a bare "—" when no count resolved;
(2) the "Today at your school" feed showed a single placeholder card in a tall
panel; (3) the gallery stranded one image in a fixed 3-column grid. These assert
the builder-side fixes and FAIL against the pre-fix code (the em-dash tile, the
one-row feed, and the missing is_manager parameter).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from apps.accounts import login_immersive_canvas as lic


class TileHasValueTests(SimpleTestCase):
    def test_zero_is_a_real_value_but_dash_is_not(self):
        self.assertTrue(lic._tile_has_value({"value": "0"}))  # 0 students is real
        self.assertTrue(lic._tile_has_value({"value": "Secure"}))
        self.assertFalse(lic._tile_has_value({"value": "—"}))
        self.assertFalse(lic._tile_has_value({"value": "-"}))
        self.assertFalse(lic._tile_has_value({"value": ""}))
        self.assertFalse(lic._tile_has_value({"value": None}))


class BentoNeverShowsDeadTileTests(SimpleTestCase):
    def setUp(self):
        self.req = RequestFactory().get("/authentication/login/")
        self.req.school = None
        self.now = timezone.localtime(timezone.now())

    def test_dead_student_tile_is_replaced_with_a_resolvable_one(self):
        keys = ("students_active", "today_date", "portal_secure", "support_help")
        tiles = [lic._resolve_metric(k, self.req, None, self.now) for k in keys]
        # Precondition: students_active is dead ("—") with no school bound.
        self.assertFalse(lic._tile_has_value(tiles[0]))

        out = lic._finalize_bento(tiles, self.req, None, self.now)
        self.assertEqual(len(out), 4, "tile count must be preserved (no grid gap)")
        for tile in out:
            self.assertTrue(
                lic._tile_has_value(tile),
                f"a dead '—' tile leaked into the bento grid: {tile}",
            )

    def test_all_resolvable_tiles_are_kept_in_place(self):
        keys = ("today_date", "portal_secure", "support_help", "languages_count")
        tiles = [lic._resolve_metric(k, self.req, None, self.now) for k in keys]
        out = lic._finalize_bento(tiles, self.req, None, self.now)
        self.assertEqual([t["key"] for t in out], list(keys))


class DashFeedFallbackTests(SimpleTestCase):
    def test_empty_section_gives_tenant_orientation_rows(self):
        feed = lic._dash_feed(
            {"cards": [], "announcements": []}, max_items=5, is_manager=False
        )
        self.assertEqual(len(feed), 3, "empty feed must orient, not show one card")
        self.assertEqual(feed[0]["icon"], "📣")  # translation-independent check
        for row in feed:
            self.assertTrue(row["title"] and row["tag"] and row["icon"])

    def test_empty_section_gives_operator_rows_on_manager_host(self):
        feed = lic._dash_feed({"cards": []}, max_items=5, is_manager=True)
        self.assertEqual(len(feed), 3)
        self.assertEqual(feed[0]["icon"], "🏫")  # operator, not parent/fees copy

    def test_real_cards_win_over_the_fallback(self):
        section = {"cards": [{"text": "Sports day Friday · gym", "severity": "success"}]}
        feed = lic._dash_feed(section, max_items=5, is_manager=False)
        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["title"], "Sports day Friday")


class GalleryGridAdaptsTests(SimpleTestCase):
    """CSS must adapt the gallery column count so few images leave no empty columns."""

    _CSS = (
        Path(__file__).resolve().parents[3]
        / "static"
        / "css"
        / "auth-login-canvas.css"
    )

    def test_thin_gallery_column_overrides_present(self):
        source = self._CSS.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r'\.rmc-auth-immersive__moments\[data-moment-count="1"\]',
            "no single-image gallery column override",
        )
        self.assertRegex(
            source,
            r'\.rmc-auth-immersive__moments\[data-moment-count="2"\]',
            "no two-image gallery column override",
        )
