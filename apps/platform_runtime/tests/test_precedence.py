from django.test import SimpleTestCase

from apps.platform_runtime.registry_snapshots import (
    build_blueprint_lifecycle_snapshot,
    build_entitlement_registry_snapshot,
    build_marketplace_install_snapshot,
)
from apps.platform_runtime.precedence import (
    PRECEDENCE_ORDER,
    describe_precedence_chain,
    merge_by_precedence,
    merge_feature_flags_by_runtime_precedence,
    normalize_scope,
    precedence_rank,
)
from apps.platform_runtime.registry_snapshots import (
    build_blueprint_lifecycle_snapshot,
    build_entitlement_registry_snapshot,
    build_marketplace_install_snapshot,
)


class RegistrySnapshotTests(SimpleTestCase):
    """Phase 6: canonical registries are stable and non-empty schema."""

    def test_entitlement_registry_snapshot_schema(self):
        snap = build_entitlement_registry_snapshot(None, {}, None)
        self.assertEqual(snap["registry_schema_version"], 1)
        self.assertIn("effective_modules", snap)
        self.assertIn("gates", snap)

    def test_blueprint_lifecycle_empty_without_school(self):
        self.assertEqual(build_blueprint_lifecycle_snapshot(None), {})

    def test_marketplace_install_snapshot_minimal_runtime(self):
        class _M:
            installed_apps = []
            granted_scopes = []

        class _R:
            marketplace = _M()

        snap = build_marketplace_install_snapshot(_R())
        self.assertEqual(snap["registry_schema_version"], 1)
        self.assertEqual(snap["active_installation_count"], 0)


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

    def test_merge_feature_flags_tenant_over_policy_sandbox_over_tenant(self):
        out = merge_feature_flags_by_runtime_precedence(
            policy_features={"beta_ui": False, "only_policy": True},
            tenant_feature_flags={"beta_ui": True},
            sandbox_feature_flags={"beta_ui": False, "preview_only": True},
        )
        self.assertFalse(out["beta_ui"])
        self.assertTrue(out["only_policy"])
        self.assertTrue(out["preview_only"])
