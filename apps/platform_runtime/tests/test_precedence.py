from django.test import SimpleTestCase

from apps.platform_runtime.precedence import (
    PRECEDENCE_ORDER,
    describe_precedence_chain,
    merge_by_precedence,
    normalize_scope,
    precedence_rank,
)


class RuntimePrecedenceTests(SimpleTestCase):
    def test_precedence_chain_matches_north_star_order(self):
        self.assertEqual(
            PRECEDENCE_ORDER,
            [
                "platform_default",
                "registry_default",
                "blueprint_default",
                "policy_bundle",
                "entitlement_gate",
                "tenant_override",
                "sandbox_override",
            ],
        )

    def test_aliases_normalize_legacy_scope_names(self):
        self.assertEqual(normalize_scope("platform"), "platform_default")
        self.assertEqual(normalize_scope("region"), "registry_default")
        self.assertEqual(normalize_scope("blueprint"), "blueprint_default")
        self.assertEqual(normalize_scope("plan"), "entitlement_gate")
        self.assertEqual(normalize_scope("tenant"), "tenant_override")
        self.assertEqual(normalize_scope("preview"), "sandbox_override")

    def test_merge_by_precedence_prefers_highest_rank(self):
        winner = merge_by_precedence(
            values=[
                ("platform", "platform"),
                ("region", "registry"),
                ("blueprint", "blueprint"),
                ("policy_bundle", "policy"),
                ("plan", "plan"),
                ("tenant", "tenant"),
                ("preview", "preview"),
            ]
        )
        self.assertEqual(winner, "preview")
        self.assertGreater(precedence_rank("tenant"), precedence_rank("plan"))

    def test_describe_precedence_chain_returns_ranked_metadata(self):
        chain = describe_precedence_chain()
        self.assertEqual(chain[0]["key"], "platform_default")
        self.assertEqual(chain[-1]["key"], "sandbox_override")
        self.assertEqual(chain[-1]["rank"], len(chain) - 1)
