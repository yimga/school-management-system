"""Wizard-UI tests for the canonical-template picker page + intake panel.

Locks down four invariants:

1. The new ``canonical_template_picker`` URL reverses cleanly in BOTH the
   operator (``migration_cloud_super``) and tenant (``migration_cloud_portal``)
   namespaces — same view, two mount points.
2. The intake-page partial ``_canonical_template_panel.html`` renders
   without raising for a representative context, in both shells.
3. The full picker page renders all 20 canonical domains end-to-end so
   the operator never lands on an empty grid if the accelerator's
   ``DOMAIN_CANONICAL_HEADERS`` registry changes shape.

Pure ``SimpleTestCase`` — no DB writes, no tenant fixtures. The picker
view is render-only over an in-memory accelerator constant.
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import NoReverseMatch, reverse


def _stub_request(path: str = "/"):
    """Build a minimal anonymous request so shell-level context processors
    that hit the request (locale, site, theme) have something to bind to.
    Tests render the picker page via control_plane_skeleton.html, which
    pulls a number of context-processor values off the request."""
    rf = RequestFactory()
    req = rf.get(path)
    req.user = AnonymousUser()
    return req


class CanonicalTemplatePickerUrlTests(SimpleTestCase):
    """The new URL must mount in both the super and portal namespaces."""

    def test_picker_url_resolves_in_super_shell(self) -> None:
        try:
            path = reverse(
                "migration_cloud_super:canonical_template_picker",
                urlconf="config.urls",
            )
        except NoReverseMatch as exc:
            self.fail(
                "migration_cloud_super:canonical_template_picker must resolve: "
                f"{exc}"
            )
        self.assertIn("/template/picker/", path)

    def test_picker_url_resolves_in_portal_shell(self) -> None:
        try:
            path = reverse(
                "migration_cloud_portal:canonical_template_picker",
                urlconf="config.urls",
            )
        except NoReverseMatch as exc:
            self.fail(
                "migration_cloud_portal:canonical_template_picker must resolve: "
                f"{exc}"
            )
        self.assertIn("/template/picker/", path)


class CanonicalTemplatePanelTemplateTests(SimpleTestCase):
    """The intake-page partial renders without raising for both shells."""

    def test_panel_template_renders(self) -> None:
        # super shell
        html_super = render_to_string(
            "migration_cloud/_canonical_template_panel.html",
            {"shell": "super"},
        )
        self.assertIn("canonical template", html_super.lower())
        self.assertIn("Download all", html_super)
        # portal shell — both {% url %} branches must resolve
        html_portal = render_to_string(
            "migration_cloud/_canonical_template_panel.html",
            {"shell": "portal"},
        )
        self.assertIn("canonical template", html_portal.lower())
        self.assertIn("Download all", html_portal)


class CanonicalTemplatePickerTemplateTests(SimpleTestCase):
    """The full picker page must render every canonical domain in context.

    The picker extends ``control_plane_skeleton.html`` which pulls
    tenant + brand + locale context processors that read DB-backed
    settings. ``databases = "__all__"`` permits those read-only lookups
    inside a ``SimpleTestCase`` so we don't need a full ``TestCase``
    transaction-wrap for what is essentially a template-render smoke
    test.
    """

    databases = "__all__"

    def test_picker_template_renders_with_all_20_domains(self) -> None:
        from apps.migration_cloud.accelerators.runmycampus_canonical import (
            DOMAIN_CANONICAL_HEADERS,
        )

        # The registry was 20 domains at v3.26 introduction. The test
        # asserts AT LEAST 20 so future agents can extend the canonical
        # surface (e.g. cafeteria_assignments / hostel_assignments /
        # transport_assignments long-tail rows) without breaking us —
        # but a regression that drops below 20 will trip the gate.
        self.assertGreaterEqual(
            len(DOMAIN_CANONICAL_HEADERS), 20,
            "DOMAIN_CANONICAL_HEADERS regressed below 20 domains — "
            "the picker UI claims '20 templates' in its headline copy.",
        )

        domains = []
        for slug, headers in sorted(DOMAIN_CANONICAL_HEADERS.items()):
            sorted_headers = sorted(headers)
            domains.append({
                "slug": slug,
                "headers": sorted_headers,
                "header_count": len(sorted_headers),
                "required": [],
                "sample_row": ",".join(sorted_headers) + "\n",
            })

        html = render_to_string(
            "migration_cloud/canonical_template_picker.html",
            {"shell": "super", "domains": domains, "page_title": "Canonical template picker"},
            request=_stub_request(),
        )

        for slug in DOMAIN_CANONICAL_HEADERS:
            with self.subTest(domain=slug):
                self.assertIn(
                    f"{slug}.csv", html,
                    f"picker page missing canonical domain {slug!r}",
                )

        # Top-level "Download all (zip)" must be present.
        self.assertIn("Download all", html)
