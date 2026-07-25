"""MAX page-status tags + configuration enrichment tests."""

from __future__ import annotations

from django.test import SimpleTestCase


class PageStatusTagsTests(SimpleTestCase):
    def test_locked_vocabulary_and_no_wallpaper_helpers(self):
        from apps.platform_runtime.page_status_tags import (
            STATUS_HEALTHY,
            STATUS_LABELS,
            build_masthead,
            chip,
            is_wallpaper_badge,
            normalize_status_key,
            status_badge,
        )

        self.assertEqual(normalize_status_key("past due"), "attention")
        self.assertEqual(status_badge(STATUS_HEALTHY)["text"], STATUS_LABELS[STATUS_HEALTHY])
        self.assertTrue(is_wallpaper_badge("Operational"))
        self.assertTrue(is_wallpaper_badge("ready"))
        self.assertFalse(is_wallpaper_badge("Healthy"))
        mh = build_masthead(
            archetype="money",
            host="operator",
            eyebrow="Money · fleet",
            title="Platform billing",
            chips=[chip(label="PSP healthy", tone="success")],
            status_key=STATUS_HEALTHY,
            freshness_label="Updated just now",
        )
        self.assertEqual(mh["page_archetype"], "money")
        self.assertEqual(mh["masthead_status_variant"], "success")
        self.assertGreaterEqual(len(mh["masthead_chips"]), 2)

        from apps.platform_runtime.page_status_tags import (
            mission_role_chips,
            resolve_mission_role_key,
            resolve_operational_season,
        )

        self.assertEqual(resolve_mission_role_key("BURSAR"), "bursar")
        self.assertTrue(mission_role_chips("bursar"))
        self.assertIn("label", resolve_operational_season(9))

        from apps.platform_runtime.page_status_tags import (
            build_mission_role_tabs,
            sparkline_from_count,
            sparkline_polyline,
        )

        self.assertTrue(sparkline_polyline(sparkline_from_count(5)))
        tabs = build_mission_role_tabs(active="admin", base_url="/x/", host="tenant")
        self.assertTrue(all("mission_role=" in t["href"] for t in tabs))

    def test_chip_value_makes_a_two_line_tile(self):
        """A live value turns a chip into a label+value tile; absent value stays single-line.

        Must-fire: drop the ``value`` field from chip() and this goes red.
        """
        from apps.platform_runtime.page_status_tags import chip

        tile = chip(label="Platform", value="Warning", tone="warning")
        self.assertEqual(tile["value"], "Warning")
        plain = chip(label="PSP healthy", tone="success")
        self.assertEqual(plain["value"], "")

    def test_role_tabs_carry_live_per_role_counts(self):
        """counts= flows through to a per-tab badge; roles absent from the map show none.

        Must-fire: unwire the ``count`` field and this goes red.
        """
        from apps.platform_runtime.page_status_tags import build_mission_role_tabs

        tabs = build_mission_role_tabs(
            active="admin",
            base_url="/x/",
            host="operator",
            counts={"principal": 2, "admin": 5, "registrar": 0},
        )
        by_key = {t["key"]: t for t in tabs}
        self.assertEqual(by_key["principal"]["count"], 2)
        self.assertEqual(by_key["admin"]["count"], 5)
        self.assertEqual(by_key["registrar"]["count"], 0)
        self.assertIsNone(by_key["bursar"]["count"])
        # Backward-compatible: without counts, no role shows a badge.
        plain = build_mission_role_tabs(active="admin", base_url="/x/", host="tenant")
        self.assertTrue(all(t["count"] is None for t in plain))


class SuperFrameDefaultsTests(SimpleTestCase):
    def test_resolve_super_operational_frame_has_no_operational_default(self):
        from apps.platform_runtime.super_operational_frames import (
            resolve_super_operational_frame,
        )

        frame = resolve_super_operational_frame(
            "slo_dashboard",
            center_title="SLO",
            center_purpose="Clocks",
        )
        self.assertEqual(frame.get("status_badge_text"), "")
