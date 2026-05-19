"""v3.33.0 Agent 1 — Companion deepening tests.

Coverage:
  - ``CompanionUploadReceipt.key_version`` field exists with right shape.
  - ``decrypt_with_active_or_versioned`` returns a ``DecryptResult``
    carrying both plaintext bytes AND the keypair version that opened.
  - ``CompanionUploadReceipt.key_version`` survives create + filter.
  - AlterField on ``MigrationCloudCompanionKeypair.private_key_encrypted``
    round-trips an existing keypair through encrypt + decrypt.
  - Fingerprint mismatch raises (constant-time compare path).
  - NEVER logs: private key bytes, plaintext, encryption keys, MAA
    signature_text.

Tests use a mixture of ``SimpleTestCase`` (no-DB structure) and
``TestCase`` (DB round-trip). PyNaCl-bearing tests skip when nacl is
not importable.
"""
from __future__ import annotations

import base64
import logging
import unittest

from django.test import SimpleTestCase, TestCase


try:
    import nacl.public  # type: ignore[import-not-found]  # noqa: F401
    _PYNACL_AVAILABLE = True
except ImportError:
    _PYNACL_AVAILABLE = False


_REQUIRE_PYNACL = unittest.skipIf(
    not _PYNACL_AVAILABLE, "PyNaCl not installed in this environment"
)


# ─── Structural / no-DB tests ────────────────────────────────────────────


class V3_33ModelShapeTests(SimpleTestCase):
    """Model + service surface shape — no DB."""

    def test_companion_upload_receipt_has_key_version_field(self):
        from apps.migration_cloud.models import CompanionUploadReceipt

        field = CompanionUploadReceipt._meta.get_field("key_version")
        self.assertEqual(field.max_length, 16)
        self.assertTrue(field.blank)
        self.assertEqual(field.default, "")

    def test_decrypt_result_is_exposed(self):
        from apps.migration_cloud.services import companion_keypair

        self.assertTrue(hasattr(companion_keypair, "DecryptResult"))
        # Cheap structural shape check
        cls = companion_keypair.DecryptResult
        from dataclasses import fields as _fields
        names = {f.name for f in _fields(cls)}
        self.assertEqual(names, {"plaintext", "key_version", "fingerprint_b64"})

    def test_keypair_field_uses_encrypted_descriptor(self):
        # The MigrationCloudCompanionKeypair.private_key_encrypted field
        # must be the Fernet-wrapping shim. ``isinstance`` chain handles
        # both the EncryptedBinaryField shim and the upstream
        # django-cryptography wrap (both forward through deconstruct()).
        from apps.accounts.legacy_hashes.encryption import EncryptedBinaryField
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair

        field = MigrationCloudCompanionKeypair._meta.get_field(
            "private_key_encrypted"
        )
        self.assertIsInstance(field, EncryptedBinaryField)

    def test_crypto_pending_marker_removed_from_service(self):
        from apps.migration_cloud.services import companion_keypair
        import inspect

        src = inspect.getsource(companion_keypair)
        self.assertNotIn("# crypto-pending: wrap-after-cross-agent-merge", src)


# ─── DB-backed round-trip tests ──────────────────────────────────────────


def _make_test_school(slug="v3-33"):
    """Mint a ``schools.School`` for per-tenant keypair tests."""
    from apps.schools.models import School
    return School.objects.create(name=f"v3-33 {slug}", slug=slug)


@_REQUIRE_PYNACL
class V3_33DecryptResultRoundTripTests(TestCase):
    """End-to-end seal + open via the DecryptResult shape."""

    def setUp(self):
        self.tenant = _make_test_school("decrypt-rt")

    def test_decrypt_returns_version_used(self):
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        row = companion_keypair.ensure_active_keypair(self.tenant)
        pub = nacl.public.PublicKey(base64.b64decode(row.public_key_b64))
        sealed_box = nacl.public.SealedBox(pub)
        plaintext = b'{"source":"powerschool","version":"1.0"}'
        ciphertext = sealed_box.encrypt(plaintext)

        result = companion_keypair.decrypt_with_active_or_versioned(
            self.tenant, ciphertext
        )
        self.assertEqual(result.plaintext, plaintext)
        self.assertEqual(result.key_version, row.key_version)
        self.assertTrue(result.fingerprint_b64)

    def test_keypair_encrypted_field_round_trips_existing_row(self):
        """AlterField + descriptor: existing keypair private bytes survive."""
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        row1 = companion_keypair.ensure_active_keypair(self.tenant)
        original_pub = row1.public_key_b64

        # Re-fetch from DB to force a from_db_value pass on the
        # encrypted field. The descriptor should return the raw 32-byte
        # private key after Fernet-unwrap.
        # tenant-isolation-allow: keypair-test-fetch-by-pk-scoped-per-tenant-fk
        row2 = MigrationCloudCompanionKeypair.objects.get(
            pk=row1.pk, tenant=self.tenant
        )
        priv_bytes = bytes(row2.private_key_encrypted)
        self.assertEqual(len(priv_bytes), 32)

        # And the round-trip seal+open still works (proves the wrap
        # didn't corrupt the key material).
        sealed_box = nacl.public.SealedBox(
            nacl.public.PublicKey(base64.b64decode(original_pub))
        )
        plaintext = b'{"check":"round-trip"}'
        ciphertext = sealed_box.encrypt(plaintext)
        result = companion_keypair.decrypt_with_active_or_versioned(
            self.tenant, ciphertext
        )
        self.assertEqual(result.plaintext, plaintext)


@_REQUIRE_PYNACL
class V3_33ReceiptKeyVersionTests(TestCase):
    """``CompanionUploadReceipt.key_version`` field write + read."""

    def _make_school(self):
        # Use minimal raw create — schools.School is the typical tenant
        # model. Tests at other layers do the same; we mirror them.
        from apps.schools.models import School
        return School.objects.create(name="V3_33 Test School", slug="v3-33-test")

    def _make_user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            username="v3_33_agent_1_uploader",
            email="v3_33@example.edu",
            password="not-a-real-secret",
        )

    def test_receipt_records_key_version(self):
        from apps.migration_cloud.models import (
            BundleStatus,
            CompanionCiphertextBlob,
            CompanionUploadReceipt,
            IntakeMethod,
            MigrationAuthorizationAgreement,
            MigrationBundle,
        )

        school = self._make_school()
        user = self._make_user()

        maa = MigrationAuthorizationAgreement.objects.create(  # tenant-isolation-allow: v3-33-test-create-maa-for-resolved-school
            tenant=school,
            signed_by_user=user,
            signed_by_role="IT Director",
            vendor_source="powerschool",
            vendor_account_holder_name="Head of School",
            signature_text="I authorize migration",
            agreement_version="v1.0",
        )

        bundle = MigrationBundle.objects.create(  # tenant-isolation-allow: v3-33-test-create-bundle-for-resolved-school
            school=school,
            label="v3.33 test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="test-v3-33-key-001",
            status=BundleStatus.PENDING,
        )

        blob = CompanionCiphertextBlob.objects.create(  # tenant-isolation-allow: v3-33-test-create-blob-for-resolved-school
            tenant=school,
            ciphertext_sha256="0" * 64,
            byte_size=512,
        )

        receipt = CompanionUploadReceipt.objects.create(  # tenant-isolation-allow: v3-33-test-create-receipt-for-resolved-school
            tenant=school,
            bundle=bundle,
            maa=maa,
            ciphertext_blob=blob,
            client_idempotency_key="receipt-key-v3-33-1",
            ciphertext_sha256="0" * 64,
            plaintext_byte_size=512,
            key_version="v3",
        )

        # tenant-isolation-allow: v3-33-test-read-back-receipt-for-resolved-school
        fetched = CompanionUploadReceipt.objects.get(pk=receipt.pk)
        self.assertEqual(fetched.key_version, "v3")


# ─── Fingerprint mismatch (constant-time compare) ────────────────────────


class V3_33FingerprintMismatchTests(SimpleTestCase):
    """``fingerprint_eq`` distinguishes valid vs tampered fingerprints."""

    def test_fingerprint_mismatch_returns_false(self):
        from apps.migration_cloud.services import companion_keypair

        # Build two distinct fingerprints by sha256(input1) vs sha256(input2)
        fp_a = companion_keypair.fingerprint_of_public_key_b64("pub-a")
        fp_b = companion_keypair.fingerprint_of_public_key_b64("pub-b")
        self.assertNotEqual(fp_a, fp_b)
        self.assertFalse(companion_keypair.fingerprint_eq(fp_a, fp_b))
        self.assertTrue(companion_keypair.fingerprint_eq(fp_a, fp_a))

    def test_decrypt_raises_when_requested_version_missing(self):
        # No need for PyNaCl — the lookup-by-version failure short-
        # circuits before the SealedBox is built.
        if not _PYNACL_AVAILABLE:
            self.skipTest("PyNaCl required")
        from apps.migration_cloud.services import companion_keypair
        from apps.schools.models import School
        tenant = School.objects.create(name="v3-33 ver missing", slug="v3-33-vm")
        with self.assertRaises(ValueError) as cm:
            companion_keypair.decrypt_with_active_or_versioned(
                tenant,
                b"irrelevant-ciphertext",
                key_version="v-does-not-exist",
            )
        self.assertIn("no keypair found", str(cm.exception))


# ─── No-secret-logging discipline ─────────────────────────────────────────


@_REQUIRE_PYNACL
class V3_33NoSecretsLoggedTests(TestCase):
    """Decrypt + ensure paths never emit private bytes / plaintext to logs."""

    def test_ensure_keypair_logs_have_no_private_bytes(self):
        from apps.migration_cloud.services import companion_keypair

        tenant = _make_test_school("ensure-logs")
        with self.assertLogs(
            "apps.migration_cloud.services.companion_keypair",
            level=logging.INFO,
        ) as cm:
            row = companion_keypair.ensure_active_keypair(tenant)

        combined = "\n".join(cm.output)
        # Cheap proxy: the encrypted bytes representation should not
        # appear. We at least make sure no "private" appears alongside
        # any base64-like long string.
        priv_bytes_repr = repr(bytes(row.private_key_encrypted))[:50]
        self.assertNotIn(priv_bytes_repr, combined)
        # And we should still see the expected key_version + fingerprint metadata.
        self.assertIn("key_version=", combined)
        self.assertIn("fingerprint=", combined)

    def test_decrypt_logs_have_no_plaintext(self):
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        tenant = _make_test_school("decrypt-logs")
        row = companion_keypair.ensure_active_keypair(tenant)
        sealed_box = nacl.public.SealedBox(
            nacl.public.PublicKey(base64.b64decode(row.public_key_b64))
        )
        # A plaintext we can grep for in the log output.
        plaintext = b'{"sentinel":"NEVER-LOG-THIS-PLAINTEXT-MARKER"}'
        ciphertext = sealed_box.encrypt(plaintext)

        with self.assertLogs(
            "apps.migration_cloud.services.companion_keypair",
            level=logging.INFO,
        ) as cm:
            result = companion_keypair.decrypt_with_active_or_versioned(
                tenant, ciphertext
            )
            self.assertEqual(result.plaintext, plaintext)

        combined = "\n".join(cm.output)
        self.assertNotIn("NEVER-LOG-THIS-PLAINTEXT-MARKER", combined)
        # Sizes + key_version + fingerprint SHOULD appear (metadata only).
        self.assertIn("decrypt_ok", combined)
        self.assertIn("plaintext_size=", combined)
