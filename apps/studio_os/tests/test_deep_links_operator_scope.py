"""Seal: metadata:* Studio rail links are operator-scoped (fail closed on tenant).

The metadata governance / lineage views are @require_super_access_with_host
(manager-host operator-only) and apps.metadata.urls is included ONLY on
config.urls + config.manager_urls, NOT config.tenant_urls. Before the fix,
studio_resolve_url treated metadata:* like an ordinary tenant namespace, so on a
tenant it fell through to the _PATHS relative path /api/internal/metadata/... —
a route that does not exist on the tenant host -> the Studio governance rail's
"Metadata governance" link rendered Page-not-found. metadata:* must fail closed
(empty) without operator scope, exactly like super:/admin:.
"""

from django.test import SimpleTestCase

from apps.studio_os.deep_links import studio_resolve_url


class MetadataOperatorScopeTest(SimpleTestCase):
    def test_metadata_links_fail_closed_without_operator_scope(self):
        # tenant plane (no request / no operator scope): the link is withheld,
        # never the dead same-origin /api/internal/metadata/... path.
        self.assertEqual(studio_resolve_url("metadata:metadata_governance"), "")
        self.assertEqual(studio_resolve_url("metadata:metadata_lineage_graph"), "")
        self.assertEqual(studio_resolve_url("metadata:metadata_lineage"), "")

    def test_metadata_governance_resolves_with_operator_scope(self):
        # operator scope: the link resolves (real route on the operator plane).
        url = studio_resolve_url("metadata:metadata_governance", allow_operator=True)
        self.assertTrue(url, "metadata governance must resolve for operators")
        self.assertIn("metadata", url)

    def test_super_links_still_fail_closed(self):
        # regression guard: the existing super:/admin: fail-closed behaviour holds.
        self.assertEqual(studio_resolve_url("super:runtime_inspector"), "")
