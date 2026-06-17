"""Tests for the v3.56.0 tenant per-role dashboard cockpit sections.

Covers:
  * Each defaults factory returns a dict with ``enabled=False`` and the
    documented schema shape.
  * Each partial renders nothing when its cockpit section is disabled
    (bleed prevention: the v3 design must not leak into operator-opt-out
    surfaces).
  * Each partial renders the expected DOM marker when its cockpit section
    is enabled AND the minimum required data is supplied.
  * ``build_tenant_dashboard_cockpit()`` produces independent dicts for
    each call (no shared mutable state).
"""

from __future__ import annotations

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.siteconfig.cockpit_tenant_dashboard import (
    TENANT_DASHBOARD_DEFAULTS,
    _tenant_achievements_defaults,
    _tenant_activity_timeline_defaults,
    _tenant_quick_actions_defaults,
    _tenant_teacher_spotlight_defaults,
    _tenant_today_snapshot_defaults,
    _tenant_upcoming_events_defaults,
    _tenant_workspace_context_dashboard_defaults,
    build_tenant_dashboard_cockpit,
)


# ============================================================
# A. Defaults factories — shape + enabled=False
# ============================================================


class TenantDashboardDefaultsShapeTests(SimpleTestCase):
    """Enabled-state defaults: the parent child-context card stays opt-in
    (``enabled=False``); the canvas sections default ON (v4.04.x — populated
    tenant dashboards out of the box, honest empty states until data hydrates)."""

    def test_workspace_context_defaults_disabled_with_expected_keys(self):
        d = _tenant_workspace_context_dashboard_defaults()
        self.assertIs(d["enabled"], False)
        self.assertIn("child", d)
        self.assertIn("initials", d["child"])
        self.assertIn("name", d["child"])
        self.assertIn("subline", d["child"])
        self.assertIn("online", d["child"])
        self.assertIn("siblings", d)
        self.assertEqual(d["siblings"], [])
        self.assertIn("add_child", d)
        self.assertEqual(d["add_child"]["url"], "")

    def test_today_snapshot_defaults_enabled_with_empty_cards(self):
        d = _tenant_today_snapshot_defaults()
        self.assertIs(d["enabled"], True)
        self.assertIs(d["live_dot"], True)
        self.assertEqual(d["cards"], [])
        self.assertIn("switch_link", d)
        self.assertEqual(d["switch_link"]["url"], "")

    def test_quick_actions_defaults_enabled_with_empty_tiles(self):
        d = _tenant_quick_actions_defaults()
        self.assertIs(d["enabled"], True)
        self.assertEqual(d["tiles"], [])
        self.assertIn("section_label", d)

    def test_upcoming_events_defaults_enabled_with_empty_events(self):
        d = _tenant_upcoming_events_defaults()
        self.assertIs(d["enabled"], True)
        self.assertEqual(d["events"], [])
        self.assertIn("view_all_link", d)

    def test_activity_timeline_defaults_enabled_with_empty_items(self):
        d = _tenant_activity_timeline_defaults()
        self.assertIs(d["enabled"], True)
        self.assertEqual(d["items"], [])
        self.assertIn("view_all_link", d)
        self.assertIn("title", d)

    def test_achievements_defaults_enabled_with_empty_list(self):
        d = _tenant_achievements_defaults()
        self.assertIs(d["enabled"], True)
        self.assertEqual(d["list"], [])
        self.assertIn("count_label", d)

    def test_teacher_spotlight_defaults_enabled_with_empty_name(self):
        d = _tenant_teacher_spotlight_defaults()
        self.assertIs(d["enabled"], True)
        self.assertEqual(d["teacher_name"], "")
        self.assertEqual(d["actions"], [])

    def test_tenant_dashboard_defaults_registry_covers_all_sections(self):
        self.assertEqual(
            set(TENANT_DASHBOARD_DEFAULTS.keys()),
            {
                "workspace_context_tenant",
                "today_snapshot",
                "quick_actions",
                "upcoming_events",
                "activity_timeline",
                "achievements",
                "teacher_spotlight",
                "tenant_activity_ticker",
                "year_progress",
                "calendar_subscribe",
            },
        )

    def test_build_tenant_dashboard_cockpit_returns_independent_dicts(self):
        a = build_tenant_dashboard_cockpit()
        b = build_tenant_dashboard_cockpit()
        # Same shape but independent — mutating one must not change the other.
        a["today_snapshot"]["cards"].append({"head": "X", "value": "Y"})
        self.assertEqual(b["today_snapshot"]["cards"], [])
        self.assertEqual(set(a.keys()), set(TENANT_DASHBOARD_DEFAULTS.keys()))


# ============================================================
# B. Bleed prevention — disabled partials render empty
# ============================================================


class TenantDashboardPartialBleedPreventionTests(SimpleTestCase):
    """Each partial must render nothing when its section is disabled.

    Mirrors the v3.55.2 community_band bleed-prevention contract.
    """

    def _assert_renders_empty(self, template: str, ctx: dict) -> None:
        rendered = render_to_string(template, ctx).strip()
        self.assertHTMLEqual(rendered, "")

    def test_today_snapshot_renders_empty_when_disabled(self):
        ctx = {"cockpit": {"today_snapshot": _tenant_today_snapshot_defaults()}}
        self._assert_renders_empty("partials/cockpit/_today_snapshot.html", ctx)

    def test_today_snapshot_renders_empty_when_enabled_but_no_cards(self):
        d = _tenant_today_snapshot_defaults()
        d["enabled"] = True  # but no cards -> still nothing
        self._assert_renders_empty(
            "partials/cockpit/_today_snapshot.html", {"cockpit": {"today_snapshot": d}}
        )

    def test_quick_actions_renders_empty_when_disabled(self):
        ctx = {"cockpit": {"quick_actions": _tenant_quick_actions_defaults()}}
        self._assert_renders_empty("partials/cockpit/_quick_actions_grid.html", ctx)

    def test_upcoming_events_renders_empty_when_disabled(self):
        ctx = {"cockpit": {"upcoming_events": _tenant_upcoming_events_defaults()}}
        self._assert_renders_empty("partials/cockpit/_upcoming_events_strip.html", ctx)

    def test_activity_timeline_renders_empty_when_disabled(self):
        ctx = {"cockpit": {"activity_timeline": _tenant_activity_timeline_defaults()}}
        self._assert_renders_empty("partials/cockpit/_activity_timeline.html", ctx)

    def test_achievements_renders_empty_when_disabled(self):
        ctx = {"cockpit": {"achievements": _tenant_achievements_defaults()}}
        self._assert_renders_empty("partials/cockpit/_achievements_card.html", ctx)

    def test_teacher_spotlight_renders_empty_when_disabled(self):
        ctx = {"cockpit": {"teacher_spotlight": _tenant_teacher_spotlight_defaults()}}
        self._assert_renders_empty(
            "partials/cockpit/_teacher_spotlight_card.html", ctx
        )

    def test_workspace_context_tenant_renders_empty_when_disabled(self):
        ctx = {
            "cockpit": {
                "workspace_context_tenant": _tenant_workspace_context_dashboard_defaults()
            }
        }
        self._assert_renders_empty(
            "partials/cockpit/_workspace_context_tenant.html", ctx
        )


# ============================================================
# C. Render-when-enabled — DOM markers present
# ============================================================


class TenantDashboardPartialRenderTests(SimpleTestCase):
    """Partials emit their expected class markers when enabled + data present."""

    def test_today_snapshot_renders_snapshot_class_when_enabled_with_card(self):
        d = _tenant_today_snapshot_defaults()
        d["enabled"] = True
        d["section_label"] = "Today · Samuel · live"
        d["cards"] = [
            {
                "icon": "✓",
                "head": "Attendance",
                "value": "Present",
                "label": "Checked in 7:48 AM",
                "spark_points": "0,18 14,16 28,12",
                "spark_color": "#16a34a",
                "delta_text": "+2pts",
                "delta_tone": "success",
            }
        ]
        rendered = render_to_string(
            "partials/cockpit/_today_snapshot.html",
            {"cockpit": {"today_snapshot": d}},
        )
        self.assertIn('class="tp-snapshot"', rendered)
        self.assertIn("tp-snap-card", rendered)
        self.assertIn("Present", rendered)
        self.assertIn("tp-snap-card__delta--success", rendered)
        self.assertIn("Today · Samuel · live", rendered)

    def test_quick_actions_renders_grid_class_when_enabled_with_tile(self):
        d = _tenant_quick_actions_defaults()
        d["enabled"] = True
        d["tiles"] = [
            {
                "url": "/pay/",
                "icon": "💳",
                "title": "Pay fees",
                "sub": "$420 outstanding",
                "badge": "1",
            }
        ]
        rendered = render_to_string(
            "partials/cockpit/_quick_actions_grid.html",
            {"cockpit": {"quick_actions": d}},
        )
        self.assertIn('class="tp-quick-grid"', rendered)
        self.assertIn("tp-quick-tile", rendered)
        self.assertIn("/pay/", rendered)
        self.assertIn("Pay fees", rendered)

    def test_upcoming_events_renders_events_class_with_today_pill(self):
        d = _tenant_upcoming_events_defaults()
        d["enabled"] = True
        d["events"] = [
            {
                "url": "/calendar/1/",
                "day": "21",
                "month": "May",
                "pill_label": "Today",
                "pill_tone": "today",
                "title": "Math homework due",
                "meta": "⏰ 5 PM",
                "is_today": True,
            }
        ]
        rendered = render_to_string(
            "partials/cockpit/_upcoming_events_strip.html",
            {"cockpit": {"upcoming_events": d}},
        )
        self.assertIn('class="tp-events"', rendered)
        self.assertIn("tp-event--today", rendered)
        self.assertIn("tp-event__pill--today", rendered)
        self.assertIn("Math homework due", rendered)

    def test_activity_timeline_renders_timeline_class_when_enabled(self):
        d = _tenant_activity_timeline_defaults()
        d["enabled"] = True
        d["items"] = [
            {
                "icon": "📝",
                "tone": "success",
                "text_html": "<strong>B+</strong> on Algebra II midterm",
                "meta_left": "Mrs. Okonkwo",
                "meta_right": "Yesterday · 2:14 PM",
            }
        ]
        rendered = render_to_string(
            "partials/cockpit/_activity_timeline.html",
            {"cockpit": {"activity_timeline": d}},
        )
        self.assertIn('class="tp-activity"', rendered)
        self.assertIn("tp-activity__timeline", rendered)
        self.assertIn("tp-activity__icon--success", rendered)
        self.assertIn("<strong>B+</strong>", rendered)

    def test_achievements_renders_school_gradient_card_when_enabled(self):
        d = _tenant_achievements_defaults()
        d["enabled"] = True
        d["title"] = "🏆 Samuel's achievements"
        d["count_label"] = "8 of 24"
        d["list"] = [{"icon": "🎯", "label": "Perfect attendance"}]
        rendered = render_to_string(
            "partials/cockpit/_achievements_card.html",
            {"cockpit": {"achievements": d}},
        )
        self.assertIn('class="tp-achievements"', rendered)
        self.assertIn("Samuel", rendered)
        self.assertIn("8 of 24", rendered)
        self.assertIn("Perfect attendance", rendered)

    def test_teacher_spotlight_renders_spotlight_class_when_enabled(self):
        d = _tenant_teacher_spotlight_defaults()
        d["enabled"] = True
        d["avatar_initials"] = "OK"
        d["teacher_name"] = "Mrs. Adaeze Okonkwo"
        d["teacher_role"] = "Mathematics · Grade 10 Section B"
        d["quote"] = "Algebra II is going to challenge them this term."
        d["actions"] = [{"label": "Send message", "url": "/msg/", "glyph": "💬"}]
        rendered = render_to_string(
            "partials/cockpit/_teacher_spotlight_card.html",
            {"cockpit": {"teacher_spotlight": d}},
        )
        self.assertIn('class="tp-spotlight"', rendered)
        self.assertIn("tp-spotlight__quote", rendered)
        self.assertIn("Mrs. Adaeze Okonkwo", rendered)
        self.assertIn("Algebra II", rendered)

    def test_workspace_context_tenant_renders_child_context_when_enabled(self):
        d = _tenant_workspace_context_dashboard_defaults()
        d["enabled"] = True
        d["child"]["initials"] = "SA"
        d["child"]["name"] = "Samuel"
        d["child"]["subline"] = "Grade 10B · 2026/27"
        d["stats"] = [{"glyph": "✓", "label": "98% attendance", "tone": "ok"}]
        d["siblings"] = [
            {"initials": "E", "label": "Esther · Grade 7", "url": "/switch/e/"}
        ]
        d["add_child"]["url"] = "/parent/link-child/"
        rendered = render_to_string(
            "partials/cockpit/_workspace_context_tenant.html",
            {"cockpit": {"workspace_context_tenant": d}},
        )
        self.assertIn('class="tp-child-context"', rendered)
        self.assertIn("Samuel", rendered)
        self.assertIn("Grade 10B · 2026/27", rendered)
        self.assertIn("tp-child-context__sibling-plus", rendered)
        self.assertIn("tp-child-context__stat--ok", rendered)


# ============================================================
# D. Cross-section bleed — community_band disabled stays empty
#    (verifies our partials don't accidentally widen the v3.55.2 contract)
# ============================================================


class TenantDashboardCommunityBandBleedTests(SimpleTestCase):
    """When `cockpit.community_band.enabled=False` the partial renders nothing.

    Pinned regression test for the v3.55.2 contract — the v3.56.0 tenant
    dashboard wave must not regress the community_band gate.
    """

    def test_community_band_renders_empty_when_disabled(self):
        ctx = {
            "cockpit": {
                "community_band": {
                    "enabled": False,
                    "achievement": {"enabled": False},
                    "testimonial": {"enabled": False, "quotes": []},
                    "map": {"enabled": False},
                }
            }
        }
        rendered = render_to_string(
            "partials/cockpit/_community_band.html", ctx
        ).strip()
        self.assertHTMLEqual(rendered, "")
