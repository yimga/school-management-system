"""
Phase 7 mechanical gate helpers: canonical precedence tuple and required resolver names.
Duplicated assertions also run from scripts/verify_cursor_phase7_runtime_first.py.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.precedence import PRECEDENCE_ORDER
from apps.platform_runtime.resolver_registry import RESOLVER_ENTRY_POINTS

CANONICAL_PRECEDENCE = (
    "platform_default",
    "registry_default",
    "blueprint_default",
    "policy_bundle",
    "entitlement_gate",
    "tenant_override",
    "sandbox_override",
)

REQUIRED_RESOLVERS = frozenset(
    {
        "RuntimeResolver",
        "BrandingResolver",
        "BlueprintResolver",
        "PolicyResolver",
        "WorkflowResolver",
        "DashboardResolver",
        "EntitlementResolver",
        "IntegrationResolver",
        "LocalizationResolver",
    }
)


class Phase7RuntimeGateTests(SimpleTestCase):
    def test_precedence_order_matches_canonical_documentation(self):
        self.assertEqual(tuple(PRECEDENCE_ORDER), CANONICAL_PRECEDENCE)

    def test_resolver_registry_declares_required_facets(self):
        names = {entry[0] for entry in RESOLVER_ENTRY_POINTS}
        missing = REQUIRED_RESOLVERS - names
        self.assertFalse(
            missing,
            f"RESOLVER_ENTRY_POINTS missing: {sorted(missing)}; have {sorted(names)}",
        )
