"""Depth tests for apps.interop.transfer_envelope (batch 1509)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.interop.transfer_envelope import (
    ENVELOPE_VERSION,
    TransferEnvelopeError,
    build_envelope,
    build_student_envelope,
    build_teacher_envelope,
)


class TransferEnvelopeDepthTests(SimpleTestCase):
    BASE_CANONICAL = {
        "identity.given_name": "Ada",
        "identity.family_name": "Lovelace",
    }

    def test_build_rejects_unknown_kind(self) -> None:
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="not-a-kind",
                source_tenant_id="tenant-A",
                target_tenant_id="tenant-B",
                canonical_data=self.BASE_CANONICAL,
            )

    def test_build_rejects_same_source_target(self) -> None:
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="student",
                source_tenant_id="tenant-A",
                target_tenant_id="tenant-A",
                canonical_data=self.BASE_CANONICAL,
            )

    def test_build_rejects_missing_tenants(self) -> None:
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="student",
                source_tenant_id="",
                target_tenant_id="tenant-B",
                canonical_data=self.BASE_CANONICAL,
            )
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="student",
                source_tenant_id="tenant-A",
                target_tenant_id="",
                canonical_data=self.BASE_CANONICAL,
            )

    def test_build_rejects_non_canonical_key(self) -> None:
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="student",
                source_tenant_id="tenant-A",
                target_tenant_id="tenant-B",
                canonical_data={"not.canonical": "x"},
            )

    def test_build_rejects_unmappable_custom_field(self) -> None:
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="student",
                source_tenant_id="tenant-A",
                target_tenant_id="tenant-B",
                canonical_data=self.BASE_CANONICAL,
                custom_data={"some_completely_unmappable_xyz_key": "x"},
            )

    def test_envelope_uses_hashed_tenant_ids(self) -> None:
        env = build_student_envelope(
            source_tenant_id="tenant-A-distinctive",
            target_tenant_id="tenant-B-distinctive",
            canonical_data=self.BASE_CANONICAL,
        )
        self.assertNotIn("tenant-A-distinctive", env.source_tenant_id_hash)
        self.assertNotIn("tenant-B-distinctive", env.target_tenant_id_hash)
        self.assertEqual(len(env.source_tenant_id_hash), 12)
        self.assertEqual(len(env.target_tenant_id_hash), 12)

    def test_envelope_actor_hash_is_omitted_when_actor_id_blank(self) -> None:
        env = build_teacher_envelope(
            source_tenant_id="tenant-A",
            target_tenant_id="tenant-B",
            canonical_data=self.BASE_CANONICAL,
        )
        self.assertEqual(env.audit_metadata["actor_id_hash"], "")

    def test_envelope_actor_id_is_hashed_when_present(self) -> None:
        env = build_student_envelope(
            source_tenant_id="tenant-A",
            target_tenant_id="tenant-B",
            canonical_data=self.BASE_CANONICAL,
            actor_id="actor-distinctive-XYZ",
        )
        self.assertNotIn("actor-distinctive-XYZ", env.audit_metadata["actor_id_hash"])
        self.assertEqual(len(env.audit_metadata["actor_id_hash"]), 12)

    def test_envelope_checksum_is_deterministic(self) -> None:
        env1 = build_student_envelope(
            source_tenant_id="tenant-A",
            target_tenant_id="tenant-B",
            canonical_data=self.BASE_CANONICAL,
        )
        env2 = build_student_envelope(
            source_tenant_id="tenant-A",
            target_tenant_id="tenant-B",
            canonical_data=self.BASE_CANONICAL,
        )
        self.assertEqual(env1.checksum, env2.checksum)

    def test_envelope_checksum_differs_across_tenants(self) -> None:
        env1 = build_student_envelope(
            source_tenant_id="tenant-A",
            target_tenant_id="tenant-B",
            canonical_data=self.BASE_CANONICAL,
        )
        env2 = build_student_envelope(
            source_tenant_id="tenant-C",
            target_tenant_id="tenant-D",
            canonical_data=self.BASE_CANONICAL,
        )
        self.assertNotEqual(env1.checksum, env2.checksum)

    def test_log_emission_omits_raw_tenant_ids(self) -> None:
        with self.assertLogs("apps.interop.transfer_envelope", level="INFO") as cm:
            build_student_envelope(
                source_tenant_id="src-distinctive-XYZ",
                target_tenant_id="tgt-distinctive-XYZ",
                canonical_data=self.BASE_CANONICAL,
            )
        log_text = "\n".join(cm.output)
        self.assertNotIn("src-distinctive-XYZ", log_text)
        self.assertNotIn("tgt-distinctive-XYZ", log_text)

    def test_envelope_version_is_at_least_one(self) -> None:
        self.assertGreaterEqual(ENVELOPE_VERSION, 1)
