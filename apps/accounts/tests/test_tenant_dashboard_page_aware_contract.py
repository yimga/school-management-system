"""Regression contract for the approved page-aware tenant dashboard palette."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TenantDashboardPageAwareContractTests(SimpleTestCase):
    def setUp(self):
        base = Path(settings.BASE_DIR)
        self.template = (base / "templates/accounts/backend_dashboard.html").read_text(encoding="utf-8")
        self.css = (base / "static/css/backend-dashboard-v2-contract.css").read_text(encoding="utf-8")

    def test_tenant_brand_tokens_remain_authoritative(self):
        for marker in (
            "--brand-primary: var(--school-primary",
            "--brand-accent: var(--school-accent",
            "--brand-success: var(--school-success",
            "--brand-warning: var(--school-warning",
            "--brand-danger: var(--school-danger",
        ):
            self.assertIn(marker, self.template)

    def test_semantic_status_never_depends_on_color_alone(self):
        for marker in ("rmc-badge--success", "is-warn", "is-danger", "aria-label"):
            self.assertIn(marker, self.template + self.css)
        for token in ("--brand-success", "--brand-warning", "--brand-danger"):
            self.assertIn(token, self.css)

    def test_cards_use_page_aware_accent_contract(self):
        for marker in (
            "--card-accent",
            "--dashboard-theme-primary",
            "color-mix(in srgb",
            "grid-template-columns: repeat(4, minmax(0, 1fr))",
        ):
            self.assertIn(marker, self.css)

    def test_dashboard_reflows_without_hidden_frames(self):
        self.assertIn("@media (max-width:", self.css)
        self.assertIn("minmax(0, 1fr)", self.css)
        self.assertIn("min-width: 0", self.css)
        self.assertNotIn("overflow: hidden; /* rmc-dashboard-content */", self.css)

    def test_dashboard_is_role_and_surface_aware(self):
        for marker in (
            "backend-admin-role-home",
            "data-rmc-admin-workspace=\"command-center\"",
            "data-page-archetype=\"mission\"",
            "mission_role_tabs",
        ):
            self.assertIn(marker, self.template)
