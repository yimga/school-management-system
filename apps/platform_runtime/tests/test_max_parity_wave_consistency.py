"""MAX Waves 1–5 cross-wave consistency + residual closure tests."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
    assert_renders,
    assert_wires,
)


ROOT = Path(__file__).resolve().parents[3]

MASTHEAD = ROOT / "templates/components/rmc_page_masthead.html"
ROLE_TABS = ROOT / "templates/components/rmc_mission_role_tabs.html"
OPS_FRAME = ROOT / "templates/components/rmc_operational_center_frame_inner.html"


class MaxParityWaveConsistencyTests(SimpleTestCase):
    def test_sparklines_round_trip_on_chips(self):
        from apps.platform_runtime.page_status_tags import (
            chip,
            sparkline_from_count,
            sparkline_polyline,
        )

        pts = sparkline_polyline(sparkline_from_count(12))
        self.assertTrue(pts)
        self.assertIn(",", pts)
        c = chip(label="12 past due", tone="warning", sparkline=sparkline_from_count(12))
        self.assertEqual(c["sparkline_points"], pts)
        self.assertFalse(chip(label="fresh", tone="fresh")["sparkline_points"])

    def test_mission_role_tabs_are_url_stateful(self):
        from apps.platform_runtime.page_status_tags import (
            build_mission_role_tabs,
            mission_role_chips,
            resolve_mission_role_key,
        )

        tabs = build_mission_role_tabs(
            active="bursar",
            base_url="/authentication/backend/",
            host="tenant",
        )
        self.assertEqual(len(tabs), 4)
        active = [t for t in tabs if t["active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["key"], "bursar")
        for t in tabs:
            self.assertIn("mission_role=", t["href"])
            self.assertIn(t["key"], t["href"])

        op_chips = mission_role_chips("bursar", host="operator")
        ten_chips = mission_role_chips("bursar", host="tenant")
        self.assertNotEqual(op_chips[0]["label"], ten_chips[0]["label"])
        self.assertEqual(resolve_mission_role_key("FINANCE"), "bursar")

    def test_mission_role_from_request_prefers_query(self):
        from types import SimpleNamespace

        from apps.platform_runtime.page_status_tags import resolve_mission_role_from_request

        req = SimpleNamespace(GET={"mission_role": "registrar"}, user=SimpleNamespace(role="ADMIN"))
        self.assertEqual(resolve_mission_role_from_request(req), "registrar")

    def test_shared_templates_lock_sparkline_and_role_tabs(self):
        masthead = (ROOT / "templates/components/rmc_page_masthead.html").read_text(
            encoding="utf-8"
        )
        # sparkline_points is a context VARIABLE -- template code -- so only a
        # source read can see it. The spark class is emitted markup.
        self.assertIn("sparkline_points", masthead)
        assert_markup(self, MASTHEAD, "rmc-page-masthead__spark")

        tabs = (ROOT / "templates/components/rmc_mission_role_tabs.html").read_text(
            encoding="utf-8"
        )
        # mission_role and tab.href are template code (a querystring assembled
        # inside {% url %}/{{ }}), so they stay source reads. The tab class is
        # the part of this partial the ENGINE can confirm it really emits, and
        # it is the template this case is BOUND to.
        self.assertIn("mission_role", tabs)
        self.assertIn("tab.href", tabs)
        assert_markup(self, ROLE_TABS, "rmc-mission-role")

        css = (ROOT / "static/css/rmc-page-archetypes-max.css").read_text(encoding="utf-8")
        self.assertIn("rmc-page-masthead__spark", css)

        for rel in (
            "templates/accounts/backend_dashboard.html",
            "templates/schools/super_dashboard.html",
        ):
            path = ROOT / rel
            body = path.read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                assert_wires(self, path, "rmc_mission_role_tabs.html")
                # mission_season is a context variable: source read only.
                self.assertIn("mission_season", body)
                assert_markup(self, path, 'data-page-archetype="mission"')

    def test_money_twins_still_locked(self):
        for rel in (
            "templates/schools/billing_dashboard.html",
            "templates/finance/dashboard.html",
        ):
            path = ROOT / rel
            with self.subTest(rel=rel):
                assert_wires(self, path, "rmc_page_masthead.html")
                assert_markup(
                    self, path, 'data-page-archetype="money"', "data-rmc-work-root"
                )

    def test_ops_frame_composes_masthead_and_work_root(self):
        # The inner frame stands alone -- no extends, no context needs -- so the
        # work root can be asserted against RENDERED output, which is the
        # strongest form available for it.
        assert_wires(self, OPS_FRAME, "rmc_page_masthead.html")
        assert_renders(self, OPS_FRAME, "data-rmc-work-root")

    def test_option_a_purged_from_max_hubs(self):
        hubs = [
            "templates/platform_runtime/configuration_center.html",
            "templates/platform_runtime/pack_marketplace.html",
            "templates/platform_runtime/blueprint_marketplace.html",
            "templates/platform_runtime/change_requests.html",
            "templates/marketplace/tenant_app_catalog.html",
            "templates/finance/payment_readiness_dashboard.html",
            "templates/siteconfig/feature_control_panel.html",
            "templates/studio_os/shell.html",
        ]
        for rel in hubs:
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.assertNotIn("tenant_option_a_strip.html", text)
                self.assertNotIn("tenant_blueprint_option_a_strip.html", text)

    def test_admin_home_label_consistency_on_tenant_surfaces(self):
        surfaces = [
            "templates/partials/portal_sidebar.html",
            "templates/accounts/backend_dashboard.html",
            "templates/components/quick_actions.html",
            "templates/admin/app_list.html",
        ]
        for rel in surfaces:
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.assertIn("Admin Home", text)
                self.assertNotIn("Backend Console", text)
                self.assertNotIn("School Command Center", text)
