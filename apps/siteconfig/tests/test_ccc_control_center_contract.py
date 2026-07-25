"""
Configuration Control Center — template and builder contracts (shell convergence depth).
"""

import unittest
from pathlib import Path

from django.test import RequestFactory

from apps.siteconfig.control_outcome_center import (
    PUBLISH_STAGING_HINT,
    build_ccc_staging_publish_links_for_request,
    get_ccc_source_legend_display_labels,
)


class CccBuilderContractTests(unittest.TestCase):
    def test_source_legend_is_non_trivial(self):
        leg = get_ccc_source_legend_display_labels()
        self.assertGreaterEqual(len(leg), 3)
        self.assertIn("Runtime", leg)

    def test_staging_links_include_control_studio_tenant(self):
        rf = RequestFactory()
        request = rf.get("/siteconfig/console/")
        request.public_host_kind = "school"
        # UrlConfSwitcherMiddleware sets request.urlconf on real tenant hosts; _rev
        # resolves tenant links from it (and deliberately will NOT fall back to
        # config.manager_urls for a non-manager scope). A bare RequestFactory request
        # has no urlconf, so without this every tenant link resolves to None.
        request.urlconf = "config.tenant_urls"
        links = build_ccc_staging_publish_links_for_request(request)
        self.assertTrue(any("Control Studio" in x["label"] for x in links))
        labels = {x["label"] for x in links}
        self.assertNotIn("Package rollout", labels)

    def test_staging_links_allow_rollout_on_manager(self):
        rf = RequestFactory()
        request = rf.get("/siteconfig/console/")
        request.public_host_kind = "manager"
        links = build_ccc_staging_publish_links_for_request(request)
        self.assertTrue(any("Package rollout" in x["label"] for x in links))


class CccTemplateContractTests(unittest.TestCase):
    def test_staging_and_hubs_partials_wired(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        for rel, needle in (
            (
                "templates/siteconfig/partials/configuration_control_center_staging_publish.html",
                "data-ccc-staging-strip",
            ),
            (
                "templates/siteconfig/partials/configuration_control_center_staging_publish.html",
                "data-ccc-staging-operator-footnote",
            ),
            (
                "templates/siteconfig/partials/configuration_control_center_operational_hubs.html",
                "data-ccc-operational-hubs",
            ),
            (
                "templates/siteconfig/partials/configuration_control_center_outcomes.html",
                "configuration_control_center_staging_publish.html",
            ),
        ):
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
            self.assertIn(needle, text, rel)

    def test_outcomes_includes_legend_block(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates/siteconfig/partials/configuration_control_center_outcomes.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ccc_outcome_compact", text)
        self.assertNotIn("{% if compact %}", text)

    def test_control_plane_base_shell_data_attrs(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates/control_plane_base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-shell-layout="control-plane"', text)
        self.assertIn('data-shell-main="control-plane"', text)

    def test_publish_staging_hint_constant(self):
        self.assertGreater(len(PUBLISH_STAGING_HINT), 40)
