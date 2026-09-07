import sys
from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
    assert_wires,
)

_TN_ROOT = Path(__file__).resolve().parents[3]


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
        # Scope attributes and the shared body are markup and a parse node.
        assert_markup(self, _TN_ROOT / "templates/admin/sidebar_inner.html",
                      'data-rmc-admin-sidebar-scope="tenant"')
        assert_wires(self, _TN_ROOT / "templates/admin/sidebar_inner.html",
                     "admin/sidebar_v3_body.html")
        assert_markup(self, _TN_ROOT / "templates/partials/manager_platform_admin_sidebar.html",
                      'data-rmc-admin-sidebar-scope="operator"')
        assert_wires(self, _TN_ROOT / "templates/partials/manager_platform_admin_sidebar.html",
                     "admin/sidebar_v3_body.html")
        assert_markup(self, _TN_ROOT / "templates/admin/sidebar_v3_body.html",
                      "data-rmc-admin-command-open")

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


class AdminSidebarV3CsrfTests(SimpleTestCase):
    """The preference writer must be able to authenticate on BOTH admin hosts.

    Found in a real browser on 2026-09-06, not by any test: every load of
    /admin/ on manager.runmycampus.com fired a PATCH to
    /admin/navigation-preferences/ that came back 403, so no operator's sidebar
    state was ever saved there. 8 admin page loads, 8 rejections.

    The cause was a single hardcoded cookie name. The reader matched only a
    cookie literally called "csrftoken", and its regex requires start-of-string
    or "; " before the name -- so "rmc_manager_csrftoken", which
    ManagerCookieIsolationMiddleware issues on the manager host, did not match
    and the function returned "".

    An EMPTY token is not a missing one, and that is why this was silent: Django
    rejects it as "CSRF token from the 'X-Csrftoken' HTTP header has incorrect
    length" (valid tokens are 32 or 64 chars) rather than as an absent header,
    and the caller is a fire-and-forget fetch whose only symptom is a console
    error nobody reads.

    These assertions are a source guard, not the proof -- a browser run is the
    proof, and it is reproducible via
    artifacts/cplane-browser-evidence/capture_control_plane_evidence.js. What a
    source guard CAN do is stop the specific regression from returning.
    """

    def _client_source(self) -> str:
        return (ROOT / "static/js/rmc-admin-sidebar-v3.js").read_text(encoding="utf-8")

    def test_preference_writer_knows_the_manager_cookie_name(self):
        source = self._client_source()
        self.assertIn(
            "rmc_manager_csrftoken",
            source,
            "the sidebar preference writer only knows the tenant CSRF cookie "
            "name, so every write from the manager admin will 403 with an "
            "empty token -- silently, on a fire-and-forget fetch",
        )

    def test_preference_writer_prefers_the_rendered_token(self):
        """The DOM token is host-independent and survives CSRF_COOKIE_HTTPONLY.

        Cookies are the fallback precisely because both of those can take them
        away; a reader that consults only cookies is one setting change from
        being empty again on every host at once.
        """
        source = self._client_source()
        self.assertIn("csrfmiddlewaretoken", source)
        dom_read = source.find("csrfmiddlewaretoken")
        cookie_read = source.find("document.cookie")
        self.assertNotEqual(dom_read, -1)
        self.assertNotEqual(cookie_read, -1)
        self.assertLess(
            dom_read,
            cookie_read,
            "the rendered csrfmiddlewaretoken input must be consulted BEFORE "
            "document.cookie, or an httponly cookie deployment silently "
            "reintroduces the empty-token 403",
        )
