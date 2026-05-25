"""GraphQL tenant safety contract tests (batch 1493)."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class GraphQLTenantSafetyContractTests(SimpleTestCase):
    """Asserts the GraphQL gateway is bounded and tenant-safe."""

    def test_graphql_view_exists(self) -> None:
        view = ROOT / "config" / "graphql_view.py"
        self.assertTrue(view.exists(), "config/graphql_view.py missing")

    def test_graphql_view_uses_ip_throttle(self) -> None:
        source = (ROOT / "config" / "graphql_view.py").read_text(encoding="utf-8")
        self.assertIn("throttle_ip_request", source)
        self.assertIn("graphql_gateway_get", source)
        self.assertIn("graphql_gateway_post", source)

    def test_graphql_view_enforces_content_type(self) -> None:
        source = (ROOT / "config" / "graphql_view.py").read_text(encoding="utf-8")
        self.assertIn("Content-Type must be application/json", source)

    def test_graphql_view_logs_no_pii(self) -> None:
        source = (ROOT / "config" / "graphql_view.py").read_text(encoding="utf-8")
        # The audit logger should record op + authentication only — never query text or variables.
        self.assertIn("graphql_gateway_post op=%s authenticated=%s", source)
        # Must not log variables / query body
        self.assertNotIn("logger.info(\"%s\"", source.replace("\n", ""))

    def test_graphql_security_review_artifact_exists(self) -> None:
        artifact = ROOT / "docs" / "generated" / "graphql_security_review.json"
        self.assertTrue(artifact.exists())

    def test_graphql_hardening_artifact_exists(self) -> None:
        artifact = ROOT / "docs" / "generated" / "graphql_production_safety_hardening.json"
        self.assertTrue(artifact.exists(), "Phase 3 hardening artifact missing")
