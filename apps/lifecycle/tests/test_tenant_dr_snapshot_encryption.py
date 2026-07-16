"""M28 — tenant DR snapshots must be ENCRYPTED at rest, not merely signed.

The snapshot was gzip + HMAC-SHA256 signed. A signature proves integrity and
authenticity but gives ZERO confidentiality: the blob sitting in
``var/tenant_snapshots/`` (and, when TENANT_SNAPSHOT_S3_BUCKET is set, in an S3
bucket) was plain gzip. Anyone able to read the file could ``gzip.decompress``
it and walk out with the tenant's student/teacher PII, the finance ledger, and
``accounts.User`` rows whose password HASHES are captured verbatim so DR keeps
credentials.

These tests pin the real security property — the bytes on disk cannot be read
without the tenant-bound key — plus the two things that make it safe to ship:
tamper still fails closed (encrypt-then-MAC), and legacy pre-encryption
snapshots stay restorable.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from django.test import TestCase, override_settings

from apps.lifecycle.tenant_dr_snapshot import (
    _GZIP_MAGIC,
    capture_daily_snapshot,
    decrypt_blob,
    restore_from_snapshot,
    sign_payload,
    verify_signature,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


@override_settings(SECRET_KEY="test-snapshot-encryption-key")
class TenantDrSnapshotEncryptionTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User

        self.school = School.objects.create(
            name="Cipher School",
            slug="cipher-school",
            subdomain="cipher-school",
        )
        self.user = User.objects.create_user(
            username="cipher-admin", password="super-secret-pw"
        )
        StudentProfile.objects.create(
            school=self.school,
            first_name="Nadia",
            last_name="Okonkwo",
            student_code="STU-CIPHER-1",
            is_active=True,
        )

    def test_stored_blob_is_not_readable_plaintext(self):
        meta = capture_daily_snapshot(self.school)
        blob = Path(meta["primary_uri"]).read_bytes()

        # The headline property: it is NOT gzip on disk any more...
        self.assertNotEqual(blob[:2], _GZIP_MAGIC, "snapshot must not be plain gzip")
        with self.assertRaises(Exception):
            gzip.decompress(blob)

        # ...and the tenant's PII / identity rows are not sitting in the bytes.
        self.assertNotIn(b"STU-CIPHER-1", blob)
        self.assertNotIn(b"cipher-admin", blob)
        self.assertNotIn(b"Okonkwo", blob)

    def test_secondary_store_is_encrypted_too(self):
        # The dual-store copy (and the S3 upload, which copies this file) must
        # not be the plaintext leak path.
        meta = capture_daily_snapshot(self.school)
        blob = Path(meta["secondary_uri"]).read_bytes()
        self.assertNotEqual(blob[:2], _GZIP_MAGIC)
        self.assertNotIn(b"STU-CIPHER-1", blob)

    def test_round_trip_still_restores(self):
        meta = capture_daily_snapshot(self.school)
        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(self.school.pk),
            expected_sig=meta["signature_hex"],
            materialize=False,
        )
        self.assertEqual(restored["school_id"], str(self.school.pk))
        self.assertIn("counts", restored)

    def test_tamper_fails_closed_before_decrypt(self):
        meta = capture_daily_snapshot(self.school)
        path = Path(meta["primary_uri"])
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaises(ValueError) as ctx:
            restore_from_snapshot(
                path,
                school_id=str(self.school.pk),
                expected_sig=meta["signature_hex"],
                materialize=False,
            )
        # Signature is checked over the ciphertext FIRST — we never get as far
        # as attempting to decrypt attacker-controlled bytes.
        self.assertEqual(str(ctx.exception), "snapshot_signature_mismatch")

    def test_wrong_tenant_key_cannot_decrypt(self):
        meta = capture_daily_snapshot(self.school)
        blob = Path(meta["primary_uri"]).read_bytes()
        # A blob is bound to its owning tenant: another school's key must not open it.
        with self.assertRaises(ValueError):
            decrypt_blob(blob, school_id="00000000-0000-0000-0000-000000000000")

    def test_legacy_plaintext_gzip_snapshot_still_restorable(self):
        """A pre-encryption backup must not become unreadable."""
        meta = capture_daily_snapshot(self.school)
        path = Path(meta["primary_uri"])
        # Reconstruct the OLD on-disk format: raw gzip, signed over the gzip.
        plain = decrypt_blob(path.read_bytes(), school_id=str(self.school.pk))
        self.assertEqual(plain[:2], _GZIP_MAGIC)
        legacy_path = path.with_name("legacy_" + path.name)
        legacy_path.write_bytes(plain)
        legacy_sig = sign_payload(plain, school_id=str(self.school.pk))
        self.assertTrue(
            verify_signature(plain, legacy_sig, school_id=str(self.school.pk))
        )

        restored = restore_from_snapshot(
            legacy_path,
            school_id=str(self.school.pk),
            expected_sig=legacy_sig,
            materialize=False,
        )
        self.assertEqual(restored["school_id"], str(self.school.pk))
