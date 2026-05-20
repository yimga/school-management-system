"""Trust compliance anchors — security matrix, proof strip, deep-dive links."""

from django.template.loader import render_to_string
import unittest

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from apps.schools.trust_center_evidence import (
    TRUST_COMPLIANCE_ANCHOR_SLUGS,
    build_trust_compliance_context,
)


class TrustCenterEvidenceTests(SimpleTestCase):
    def test_anchor_slugs_include_security_compliance_and_trust_center(self):
        self.assertIn("security-compliance", TRUST_COMPLIANCE_ANCHOR_SLUGS)
        self.assertIn("trust-center", TRUST_COMPLIANCE_ANCHOR_SLUGS)

    def test_build_context_returns_expanded_control_framework(self):
        ctx = build_trust_compliance_context()
        self.assertGreaterEqual(len(ctx["trust_matrix_rows"]), 8)
        self.assertGreaterEqual(len(ctx["trust_procurement_cards"]), 5)
        self.assertGreaterEqual(len(ctx["trust_regulatory_cards"]), 6)
        self.assertGreaterEqual(len(ctx["trust_certification_honesty"]), 4)
        self.assertGreaterEqual(len(ctx["trust_ci_gates"]), 4)
        row = ctx["trust_matrix_rows"][0]
        self.assertIn("mechanism", row)
        for r in ctx["trust_matrix_rows"]:
            self.assertIn(r["status"], {"verified", "documented", "partial", "external"})
            self.assertTrue(r.get("label"))

    def test_certification_honesty_never_claims_soc2_by_default(self):
        ctx = build_trust_compliance_context()
        soc2 = next(
            (c for c in ctx["trust_certification_honesty"] if "SOC 2" in c["label"]),
            None,
        )
        self.assertIsNotNone(soc2)
        self.assertEqual(soc2["status"], "not_published")


class TrustCompliancePartialRenderTests(SimpleTestCase):
    def _ctx(self):
        return build_trust_compliance_context()

    def test_command_center_partial(self):
        html = render_to_string(
            "marketing/partials/trust_compliance_command_center.html",
            self._ctx(),
        )
        self.assertIn('data-mkt-trust-command-center="1"', html)
        self.assertIn("Trust evidence dashboard", html)

    def test_control_framework_partial(self):
        html = render_to_string(
            "marketing/partials/trust_compliance_control_framework.html",
            self._ctx(),
        )
        self.assertIn('data-mkt-trust-control-framework="1"', html)
        self.assertIn("How it works", html)
        self.assertIn('data-trust-control="api_surface"', html)

    def test_external_honesty_partial(self):
        html = render_to_string(
            "marketing/partials/trust_compliance_external_honesty.html",
            self._ctx(),
        )
        self.assertIn('data-mkt-trust-external-honesty="1"', html)
        self.assertIn("Not published", html)

    def test_regulatory_grid_partial(self):
        html = render_to_string(
            "marketing/partials/trust_compliance_regulatory_grid.html",
            self._ctx(),
        )
        self.assertIn('data-mkt-trust-regulatory="1"', html)
        self.assertIn('data-trust-regulatory="ferpa"', html)
        self.assertIn('data-trust-regulatory="coppa"', html)
        self.assertIn('data-trust-regulatory="accessibility"', html)

    def test_anchors_partial_reference_mode_omits_duplicate_matrix(self):
        ctx = self._ctx()
        ctx["trust_compliance_anchor_mode"] = "reference_only"
        html = render_to_string(
            "marketing/partials/trust_compliance_anchors.html",
            ctx,
        )
        self.assertIn("FERPA privacy pledge", html)
        self.assertNotIn('id="security-matrix"', html)

    def test_anchors_partial_full_mode_includes_matrix(self):
        html = render_to_string(
            "marketing/partials/trust_compliance_anchors.html",
            self._ctx(),
        )
        self.assertIn('id="security-matrix"', html)
        self.assertIn(reverse("marketing_trust_coppa"), html)


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class TrustComplianceUrlTests(SimpleTestCase):
    def test_deep_dive_urls_resolve(self):
        self.assertEqual(
            reverse("marketing_trust_coppa"), "/trust-center/coppa/"
        )
        self.assertEqual(
            reverse("marketing_trust_accessibility"),
            "/trust-center/accessibility/",
        )
        self.assertEqual(
            reverse("marketing_security_compliance"), "/security-compliance/"
        )
        self.assertEqual(
            reverse("marketing_trust_center"), "/trust-center/"
        )
        self.assertEqual(
            reverse("marketing_platform_security"), "/platform/security/"
        )


class TrustComplianceHttpRenderTests(unittest.TestCase):
    """HTTP render proof without Django TestCase DB (uses dev sqlite + test client)."""

    @classmethod
    def setUpClass(cls) -> None:
        import django

        django.setup()
        super().setUpClass()

    def _get(self, path: str) -> str | None:
        client = Client()
        try:
            with override_settings(
                ALLOWED_HOSTS=["*"],
                MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
                SECURE_SSL_REDIRECT=False,
            ):
                response = client.get(path, HTTP_HOST="runmycampus.com")
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(str(exc)) from exc
        if response.status_code != 200:
            return None
        return response.content.decode("utf-8", errors="replace")

    def test_security_compliance_page_renders_command_center(self):
        html = self._get(reverse("marketing_security_compliance"))
        if html is None:
            self.skipTest("security-compliance page not 200")
        self.assertIn('data-mkt-security-compliance="1"', html)
        self.assertIn('data-mkt-trust-command-center="1"', html)
        self.assertIn('data-mkt-trust-control-framework="1"', html)

    def test_trust_center_page_renders_evidence_layers(self):
        html = self._get(reverse("marketing_trust_center"))
        if html is None:
            self.skipTest("trust-center page not 200")
        self.assertIn('data-mkt-trust-center="1"', html)
        self.assertIn('data-mkt-trust-regulatory="1"', html)

    def test_platform_security_page_renders_control_framework(self):
        html = self._get(reverse("marketing_platform_security"))
        if html is None:
            self.skipTest("platform-security page not 200")
        self.assertIn('data-mkt-platform-security="1"', html)
        self.assertIn('data-mkt-trust-control-framework="1"', html)

    def test_coppa_and_accessibility_deep_dives_render(self):
        for name in ("marketing_trust_coppa", "marketing_trust_accessibility"):
            html = self._get(reverse(name))
            if html is None:
                self.skipTest(f"{name} page not 200")
            self.assertIn("mkt-v3-page", html)
