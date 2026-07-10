"""Regression: /school/setup/migration-cloud/ 500 (cross-host reverse leak).

The tenant Migration Cloud connector home (``connector/home.html``) reversed
``migration_cloud_portal:bundle_new``. That namespace is registered ONLY in
``config.urls`` (admin/default host) and ``config.manager_urls`` (super), NOT in
``config.tenant_urls`` — so the tenant host it actually renders on threw
``NoReverseMatch`` at template-render time and 500'd the page. The button now
targets ``school_setup_imports``, which IS registered on the tenant host.

These assertions reverse against the specific host urlconfs and need no DB.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

_TENANT_URLCONF = "config.tenant_urls"


class ConnectorHomeReverseTests(SimpleTestCase):
    def test_upload_button_target_resolves_on_tenant_host(self):
        # The new button target must exist on the host the template renders on.
        self.assertTrue(reverse("school_setup_imports", urlconf=_TENANT_URLCONF))

    def test_portal_namespace_is_absent_on_tenant_host(self):
        # This is what shipped the 500 — the portal namespace is a foreign host's.
        with self.assertRaises(NoReverseMatch):
            reverse(
                "migration_cloud_portal:bundle_new", urlconf=_TENANT_URLCONF
            )

    def test_connector_home_has_no_foreign_namespace_reverse(self):
        # Guard against the leak creeping back into the template source.
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        home = repo_root / "templates" / "migration_cloud" / "connector" / "home.html"
        text = home.read_text(encoding="utf-8")
        self.assertNotIn("migration_cloud_portal:", text)
        self.assertNotIn("migration_cloud_super:", text)
