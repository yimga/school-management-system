"""Regression: /school/setup/migration-cloud/ 500 (cross-host reverse leak).

The tenant Migration Cloud connector home (``connector/home.html``) reversed
``migration_cloud_portal:bundle_new``. That namespace is registered ONLY in
``config.urls`` (admin/default host) and ``config.manager_urls`` (super), NOT in
``config.tenant_urls`` — so the tenant host it renders on threw
``NoReverseMatch`` and 500'd the page.

The connector home actually renders on THREE hosts (tenant
``migration_cloud_connector``, operator ``migration_cloud_portal`` /
``migration_cloud_super``), so NO single hardcoded namespace is correct on all
three — a plain ``{% url 'school_setup_imports' %}`` would in turn 500 on the two
operator hosts. The fix resolves the target in the view
(``_resolve_connector_upload_url``) against the request's active urlconf and the
template renders ``{{ upload_url }}``.

These assertions reverse against the specific host urlconfs and need no DB.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

_TENANT_URLCONF = "config.tenant_urls"
_CONFIG_URLCONF = "config.urls"
_MANAGER_URLCONF = "config.manager_urls"


class ConnectorHomeUploadUrlTests(SimpleTestCase):
    def test_each_host_has_a_resolvable_upload_target(self):
        # The view's candidate list must contain a target that resolves on each
        # host the connector home renders on.
        self.assertTrue(reverse("school_setup_imports", urlconf=_TENANT_URLCONF))
        self.assertTrue(
            reverse("migration_cloud_portal:bundle_new", urlconf=_CONFIG_URLCONF)
        )
        self.assertTrue(
            reverse("migration_cloud_super:bundle_new", urlconf=_MANAGER_URLCONF)
        )

    def test_tenant_host_lacks_the_operator_namespaces(self):
        # Why a hardcoded operator reverse 500'd on the tenant host.
        with self.assertRaises(NoReverseMatch):
            reverse("migration_cloud_portal:bundle_new", urlconf=_TENANT_URLCONF)
        with self.assertRaises(NoReverseMatch):
            reverse("migration_cloud_super:bundle_new", urlconf=_TENANT_URLCONF)

    def test_operator_hosts_lack_school_setup_imports(self):
        # Why the interim tenant-only fix would in turn 500 on the operator hosts
        # (the reason the target must be resolved per-host in the view).
        with self.assertRaises(NoReverseMatch):
            reverse("school_setup_imports", urlconf=_CONFIG_URLCONF)
        with self.assertRaises(NoReverseMatch):
            reverse("school_setup_imports", urlconf=_MANAGER_URLCONF)

    def test_template_uses_view_provided_url_not_a_hardcoded_reverse(self):
        repo_root = Path(__file__).resolve().parents[3]
        home = repo_root / "templates" / "migration_cloud" / "connector" / "home.html"
        text = home.read_text(encoding="utf-8")
        self.assertIn("{{ upload_url }}", text)
        # No single-namespace hardcode of any host's reverse for the upload CTA.
        self.assertNotIn("migration_cloud_portal:", text)
        self.assertNotIn("migration_cloud_super:", text)
        self.assertNotIn("url 'school_setup_imports'", text)
        self.assertNotIn('url "school_setup_imports"', text)
