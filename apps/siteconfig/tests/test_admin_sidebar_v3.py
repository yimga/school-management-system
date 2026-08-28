import sys
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class AdminSidebarV3SourceTests(SimpleTestCase):
    def test_one_shared_asset_owner_serves_tenant_and_operator(self):
        base = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertEqual(base.count("rmc-admin-sidebar-v3.css"), 1)
        self.assertEqual(base.count("rmc-admin-sidebar-v3.js"), 1)
        for retired in (
            "rmc-tenant-admin-sidebar-v2.css",
            "rmc-tenant-admin-sidebar-v2.js",
            "rmc-operator-admin-sidebar-v2.css",
            "rmc-operator-admin-sidebar-v2.js",
        ):
            self.assertNotIn(retired, base)

    def test_both_sidebars_mount_the_shared_page_aware_body(self):
        tenant = (ROOT / "templates/admin/sidebar_inner.html").read_text(encoding="utf-8")
        operator = (ROOT / "templates/partials/manager_platform_admin_sidebar.html").read_text(encoding="utf-8")
        body = (ROOT / "templates/admin/sidebar_v3_body.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-admin-sidebar-scope="tenant"', tenant)
        self.assertIn('data-rmc-admin-sidebar-scope="operator"', operator)
        self.assertIn('include "admin/sidebar_v3_body.html"', tenant)
        self.assertIn('include "admin/sidebar_v3_body.html"', operator)
        for token in (
            "data-rmc-admin-command-open",
            "data-rmc-admin-now",
            "data-rmc-admin-this-page",
            "data-rmc-admin-pinned-wrap",
            "data-rmc-admin-work-areas",
            "data-rmc-admin-recent-wrap",
            "data-rmc-admin-undo",
        ):
            self.assertIn(token, body)

    def test_runtime_has_conflict_offline_keyboard_and_accessibility_contracts(self):
        javascript = (ROOT / "static/js/rmc-admin-sidebar-v3.js").read_text(encoding="utf-8")
        for token in (
            'method: "PATCH"',
            "revision_conflict",
            "expected_revision",
            "BroadcastChannel",
            'addEventListener("offline"',
            'event.key === "ArrowDown"',
            'event.key === "Tab"',
            "inert = open",
            "mutation_retry",
            "Math.min(30000",
        ):
            self.assertIn(token, javascript)

    def test_build_cache_and_service_worker_move_together(self):
        base = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
        shell = (ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
        worker = (ROOT / "static/js/service-worker.js").read_text(encoding="utf-8")
        sys.path.insert(0, str(ROOT / "scripts"))
        import admin_build_lock

        # The approved build lock is the single source for these ids; pinning
        # them as literals here is how the same assertion drifts from the file
        # it is supposed to be checking.
        lock = admin_build_lock.load()
        self.assertIn(lock["build_id"], base + shell)
        self.assertIn(lock["cache_bust"], base)
        # Monotonic, not exact: CACHE_VERSION belongs to whichever wave shipped
        # last, and a peer bumping it forward is correct, not a regression. An
        # exact pin is what made the v22 admin gates unwireable until 2026-08-21.
        ok, explanation = admin_build_lock.sw_at_least(lock["sw_version"], worker)
        self.assertTrue(ok, explanation)
        self.assertIn("/static/css/rmc-admin-sidebar-v3.css", worker)
        self.assertIn("/static/js/rmc-admin-sidebar-v3.js", worker)
