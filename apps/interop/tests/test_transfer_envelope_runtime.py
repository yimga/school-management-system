"""Runtime tests for apps.interop.transfer_envelope (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.interop.transfer_envelope import (
    ENVELOPE_VERSION,
    TransferEnvelopeError,
    build_envelope,
    build_student_envelope,
    build_teacher_envelope,
)


class TransferEnvelopeRuntimeTests(SimpleTestCase):
    BASE = dict(
        source_tenant_id="tenant-a",
        target_tenant_id="tenant-b",
        canonical_data={
            "identity.given_name": "Ada",
            "identity.family_name": "Lovelace",
            "enrollment.grade": "8",
        },
    )

    def test_build_student_envelope_emits_hashed_tenants(self) -> None:
        env = build_student_envelope(**self.BASE)
        self.assertEqual(env.envelope_kind, "student")
        self.assertEqual(env.schema_version, ENVELOPE_VERSION)
        self.assertNotEqual(env.source_tenant_id_hash, "tenant-a")
        self.assertNotEqual(env.target_tenant_id_hash, "tenant-b")
        self.assertEqual(len(env.source_tenant_id_hash), 12)

    def test_build_teacher_envelope_distinct_from_student(self) -> None:
        env = build_teacher_envelope(**self.BASE)
        self.assertEqual(env.envelope_kind, "teacher")

    def test_unknown_canonical_key_is_rejected(self) -> None:
        kwargs = dict(self.BASE)
        kwargs["canonical_data"] = {"not.a.real.key": "x"}
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(envelope_kind="student", **kwargs)

    def test_unmappable_custom_field_is_rejected(self) -> None:
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(
                envelope_kind="student",
                **self.BASE,
                custom_data={"favourite_pokemon": "snorlax"},
            )

    def test_source_target_must_differ(self) -> None:
        kwargs = dict(self.BASE)
        kwargs["target_tenant_id"] = "tenant-a"
        with self.assertRaises(TransferEnvelopeError):
            build_envelope(envelope_kind="student", **kwargs)

    def test_envelope_checksum_is_deterministic(self) -> None:
        a = build_student_envelope(**self.BASE)
        b = build_student_envelope(**self.BASE)
        self.assertEqual(a.checksum, b.checksum)
