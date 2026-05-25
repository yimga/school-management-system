"""Runtime tests for apps.sync_engine.tenant_manifest_compiler (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.sync_engine.tenant_manifest_compiler import (
    SCHEMA_VERSION,
    TenantManifestError,
    compile_manifest,
)


class TenantManifestCompilerRuntimeTests(SimpleTestCase):
    def test_compile_emits_deterministic_checksum(self) -> None:
        m1 = compile_manifest(
            tenant_id="tenant-1",
            routes_allowlist=["/portal/", "/portal/dashboard/"],
            locale_default="en",
        )
        m2 = compile_manifest(
            tenant_id="tenant-1",
            routes_allowlist=["/portal/dashboard/", "/portal/"],
            locale_default="en",
        )
        self.assertEqual(m1.checksum, m2.checksum)
        self.assertEqual(m1.schema_version, SCHEMA_VERSION)

    def test_tenant_id_is_hashed(self) -> None:
        m = compile_manifest(tenant_id="real-tenant-uuid")
        self.assertNotEqual(m.tenant_id_hash, "real-tenant-uuid")
        self.assertEqual(len(m.tenant_id_hash), 12)

    def test_sensitive_payload_keys_are_scrubbed(self) -> None:
        m = compile_manifest(
            tenant_id="tenant-1",
            data_policies={
                "retention_days": 30,
                "secret": "must-not-appear",
                "nested": {"api_key": "x", "ok": True},
            },
        )
        self.assertNotIn("secret", m.data_policies)
        self.assertNotIn("api_key", m.data_policies["nested"])
        self.assertEqual(m.data_policies["nested"]["ok"], True)

    def test_relative_route_rejected(self) -> None:
        with self.assertRaises(TenantManifestError):
            compile_manifest(tenant_id="t1", routes_allowlist=["dashboard/"])

    def test_signature_posture_rejects_unknown(self) -> None:
        with self.assertRaises(TenantManifestError):
            compile_manifest(tenant_id="t1", signature_posture="md5")

    def test_serialization_round_trip(self) -> None:
        m = compile_manifest(tenant_id="t", feature_flags={"a": True, "b": False})
        d = m.to_dict()
        self.assertEqual(d["feature_flags"], {"a": True, "b": False})
        self.assertEqual(d["checksum"], m.checksum)
