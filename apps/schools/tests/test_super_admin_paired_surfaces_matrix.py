"""Fast matrix/bindings checks (no HTTP, no migrations)."""

from django.test import SimpleTestCase, override_settings

from apps.schools.super_admin_paired_surfaces import (
    build_browser_parity_probe_matrix,
    build_surface_parity_matrix,
    resolve_bridge_key_for_super_view,
)


# The parity matrix describes MANAGER-host operator surfaces: its browser probes
# reverse admin:* changelist names that are served by platform_admin_site on
# config.manager_urls (config.urls host-dispatches /admin/ and does not register
# the admin: namespace). Resolve the helper under the manager urlconf — the same
# urlconf UrlConfSwitcherMiddleware pins on the manager host at request time.
@override_settings(ROOT_URLCONF="config.manager_urls")
class SuperAdminPairedSurfacesMatrixTests(SimpleTestCase):
    def test_surface_parity_matrix_is_green(self):
        matrix = build_surface_parity_matrix()
        self.assertTrue(matrix["spine_ok"], matrix)
        self.assertTrue(matrix["pairs_ok"], matrix)
        self.assertTrue(matrix["bindings_ok"], matrix)
        self.assertTrue(matrix["browser_probes_ok"], matrix)

    def test_marketplace_and_security_bridge_resolution(self):
        self.assertEqual(
            resolve_bridge_key_for_super_view("marketplace_governance"),
            "marketplace_apps",
        )
        self.assertEqual(
            resolve_bridge_key_for_super_view("security_hub"),
            "compliance_audit_log",
        )
        self.assertEqual(
            resolve_bridge_key_for_super_view(
                "marketplace_sandbox_inspector",
                "/super/marketplace/sandbox/",
            ),
            "marketplace_apps",
        )

    def test_browser_probes_resolve_paths(self):
        rows = build_browser_parity_probe_matrix()
        self.assertGreaterEqual(len(rows), 8)
        self.assertTrue(all(row["path"] for row in rows))
