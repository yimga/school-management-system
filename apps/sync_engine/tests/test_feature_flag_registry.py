"""Manifest feature-flag registry validation (owner-decision d)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.sync_engine import feature_flag_registry as reg
from apps.sync_engine.tenant_manifest_compiler import (
    TenantManifestError,
    compile_manifest,
)


class FeatureFlagRegistryTests(SimpleTestCase):
    def test_registry_includes_master_switch_and_bundle_flags(self):
        known = reg.known_feature_flags()
        self.assertIn("enable_offline_mode", known)
        self.assertIn("enable_offline_form_queue", known)  # from the bundle SOT

    def test_validate_returns_unknown_keys(self):
        unknown = reg.validate_feature_flags(
            {"enable_offline_mode": True, "enable_offline_quee": True}
        )
        self.assertEqual(unknown, ["enable_offline_quee"])

    def test_validate_empty_for_all_known(self):
        self.assertEqual(
            reg.validate_feature_flags({"enable_offline_form_queue": True}), []
        )

    def test_registry_covers_every_bundle_bool_flag(self):
        # Drift guard: every bool flag in the bundle SOT must be registry-known.
        from apps.platform_runtime.offline_mode_bundle import (
            OFFLINE_MODE_BACKEND_FLAG_UPDATES,
        )

        bundle_flags = {
            k for k, v in OFFLINE_MODE_BACKEND_FLAG_UPDATES.items() if isinstance(v, bool)
        }
        self.assertTrue(bundle_flags)
        self.assertTrue(bundle_flags <= reg.known_feature_flags())


class CompileManifestValidationTests(SimpleTestCase):
    def test_strict_raises_on_unknown_flag(self):
        with self.assertRaises(TenantManifestError):
            compile_manifest(
                tenant_id="t",
                feature_flags={"bogus_flag": True},
                strict_feature_flags=True,
            )

    def test_strict_passes_for_known_flag(self):
        m = compile_manifest(
            tenant_id="t",
            feature_flags={"enable_offline_form_queue": True},
            strict_feature_flags=True,
        )
        self.assertTrue(m.feature_flags["enable_offline_form_queue"])

    def test_lenient_default_passes_unknown_through(self):
        # Non-breaking: existing ad-hoc callers keep working (warn, not raise).
        m = compile_manifest(tenant_id="t", feature_flags={"a": True, "b": False})
        self.assertEqual(m.feature_flags, {"a": True, "b": False})
