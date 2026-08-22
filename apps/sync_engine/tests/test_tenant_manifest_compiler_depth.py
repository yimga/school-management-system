"""Depth tests for apps.sync_engine.tenant_manifest_compiler (batch 1509).

Adds determinism + cross-tenant isolation + scrub depth + signature-posture
validation on top of the contract tests.
"""

from __future__ import annotations

import logging

from django.test import SimpleTestCase

from apps.sync_engine.tenant_manifest_compiler import (
    SCHEMA_VERSION,
    TenantManifestError,
    compile_manifest,
)


class TenantManifestCompilerDepthTests(SimpleTestCase):
    def test_compile_is_deterministic_for_same_inputs(self) -> None:
        m1 = compile_manifest(
            tenant_id="tenant-A",
            routes_allowlist=["/portal/", "/api/v1/sync/"],
            data_policies={"retention_days": 365},
            pwa_cache_hints={"max_age_seconds": 300},
            locale_default="en",
            feature_flags={"offline_queue": True},
        )
        m2 = compile_manifest(
            tenant_id="tenant-A",
            routes_allowlist=["/portal/", "/api/v1/sync/"],
            data_policies={"retention_days": 365},
            pwa_cache_hints={"max_age_seconds": 300},
            locale_default="en",
            feature_flags={"offline_queue": True},
        )
        self.assertEqual(m1.checksum, m2.checksum)
        self.assertEqual(m1.tenant_id_hash, m2.tenant_id_hash)

    def test_compile_order_independent_for_routes(self) -> None:
        m1 = compile_manifest(tenant_id="tenant-A", routes_allowlist=["/a/", "/b/"])
        m2 = compile_manifest(tenant_id="tenant-A", routes_allowlist=["/b/", "/a/"])
        self.assertEqual(m1.checksum, m2.checksum)
        self.assertEqual(m1.routes_allowlist, ["/a/", "/b/"])

    def test_compile_isolates_tenants(self) -> None:
        m_a = compile_manifest(tenant_id="tenant-A")
        m_b = compile_manifest(tenant_id="tenant-B")
        self.assertNotEqual(m_a.tenant_id_hash, m_b.tenant_id_hash)
        self.assertNotEqual(m_a.checksum, m_b.checksum)

    def test_compile_rejects_relative_routes(self) -> None:
        with self.assertRaises(TenantManifestError):
            compile_manifest(tenant_id="tenant-A", routes_allowlist=["portal/"])

    def test_compile_rejects_empty_tenant_id(self) -> None:
        with self.assertRaises(TenantManifestError):
            compile_manifest(tenant_id="")

    def test_compile_rejects_unknown_signature_posture(self) -> None:
        with self.assertRaises(TenantManifestError):
            compile_manifest(tenant_id="tenant-A", signature_posture="md5")

    def test_compile_accepts_known_signature_postures(self) -> None:
        for posture in ("unsigned", "hmac-sha256", "ed25519"):
            m = compile_manifest(tenant_id="tenant-A", signature_posture=posture)
            self.assertEqual(m.signature_posture, posture)

    def test_scrub_strips_sensitive_top_level_keys(self) -> None:
        m = compile_manifest(
            tenant_id="tenant-A",
            data_policies={
                "retention_days": 365,
                "password": "should-not-appear",
                "api_key": "should-not-appear",
                "secret": "should-not-appear",
            },
        )
        self.assertIn("retention_days", m.data_policies)
        self.assertNotIn("password", m.data_policies)
        self.assertNotIn("api_key", m.data_policies)
        self.assertNotIn("secret", m.data_policies)

    def test_scrub_recurses_into_nested_dicts(self) -> None:
        m = compile_manifest(
            tenant_id="tenant-A",
            data_policies={
                "nested": {
                    "harmless": "value",
                    "password": "nested-secret-value",
                },
            },
        )
        self.assertIn("nested", m.data_policies)
        self.assertNotIn("password", m.data_policies["nested"])
        self.assertEqual(m.data_policies["nested"]["harmless"], "value")

    def test_scrub_handles_lists_of_dicts(self) -> None:
        m = compile_manifest(
            tenant_id="tenant-A",
            data_policies={
                "rules": [
                    {"name": "rule-1", "token": "secret-token"},
                    {"name": "rule-2"},
                ],
            },
        )
        self.assertEqual(m.data_policies["rules"][0]["name"], "rule-1")
        self.assertNotIn("token", m.data_policies["rules"][0])

    def test_schema_version_is_at_least_one(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 1)

    def test_manifest_to_dict_round_trips_canonical_fields(self) -> None:
        m = compile_manifest(
            tenant_id="tenant-A",
            routes_allowlist=["/portal/"],
            locale_default="fr",
            feature_flags={"x": True, "y": False},
        )
        d = m.to_dict()
        self.assertEqual(d["tenant_id_hash"], m.tenant_id_hash)
        self.assertEqual(d["schema_version"], SCHEMA_VERSION)
        self.assertEqual(d["locale_default"], "fr")
        self.assertEqual(d["feature_flags"], {"x": True, "y": False})

    def test_log_emission_omits_raw_tenant_id_and_uses_hash(self) -> None:
        # config/settings_test.py calls logging.disable(logging.CRITICAL) at import, which
        # suppresses every record before assertLogs can see one -- so this test passes
        # under config.settings and fails under config.settings_test, for reasons that have
        # nothing to do with the compiler. Lift the global disable for this test only and
        # restore it on the way out, so the assertion holds under either settings module.
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable, logging.CRITICAL)
        with self.assertLogs("apps.sync_engine.tenant_manifest_compiler", level="INFO") as cm:
            compile_manifest(tenant_id="tenant-distinctive-XYZ")
        log_text = "\n".join(cm.output)
        self.assertNotIn("tenant-distinctive-XYZ", log_text)
