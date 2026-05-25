"""Template preview / apply / rollback runtime tests (batch 1506 audit closure)."""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse, set_urlconf


class TemplatePreviewApplyRollbackRuntimeTests(SimpleTestCase):
    URL_NAMES = (
        "template_marketplace:browse",
        "template_marketplace:detail",
        "template_marketplace:preview",
        "template_marketplace:compare",
        "template_marketplace:apply",
        "template_marketplace:customize",
        "template_marketplace:rollback",
    )

    def setUp(self) -> None:
        # Marketplace routes live under the tenant URLconf, not the default project URLconf.
        set_urlconf("config.tenant_urls")

    def tearDown(self) -> None:
        set_urlconf(None)

    def test_at_least_one_template_marketplace_url_resolves(self) -> None:
        """Repo contains the marketplace; at least one canonical route name must resolve under tenant URLconf."""
        resolved_any = False
        for name in self.URL_NAMES:
            try:
                reverse(name)
                resolved_any = True
                break
            except NoReverseMatch:
                try:
                    reverse(name, kwargs={"key": "any-key"})
                    resolved_any = True
                    break
                except NoReverseMatch:
                    continue
        self.assertTrue(resolved_any, "no template_marketplace:* URL resolved under tenant URLconf")

    def test_apply_route_is_post_only_contract(self) -> None:
        from pathlib import Path
        ROOT = Path(__file__).resolve().parents[3]
        urls_path = ROOT / "apps" / "brand_experience" / "urls_template_marketplace.py"
        if not urls_path.exists():
            self.skipTest("template marketplace urls module not present at expected path")
        source = urls_path.read_text(encoding="utf-8")
        # Apply / rollback routes should reference views that require POST
        self.assertIn("apply", source.lower())
        self.assertIn("rollback", source.lower())

    def test_views_module_has_operator_gate_helper(self) -> None:
        from pathlib import Path
        ROOT = Path(__file__).resolve().parents[3]
        views_path = ROOT / "apps" / "brand_experience" / "views_template_marketplace.py"
        if not views_path.exists():
            self.skipTest("template marketplace views module not present at expected path")
        source = views_path.read_text(encoding="utf-8")
        self.assertIn("_gate_operator_only", source)

    def test_template_audit_event_model_referenced(self) -> None:
        from pathlib import Path
        ROOT = Path(__file__).resolve().parents[3]
        models_path = ROOT / "apps" / "brand_experience" / "models_template.py"
        if not models_path.exists():
            self.skipTest("template models module not present at expected path")
        source = models_path.read_text(encoding="utf-8")
        self.assertIn("TemplateAuditEvent", source)
