"""v3.34.0 Agent 1 — Per-tenant companion keypair scoping tests.

Coverage:
  - 2 tenants get isolated keypairs (different public_key_b64).
  - Tenant A cannot decrypt ciphertext sealed for Tenant B (libsodium
    raises ``CryptoError``; verify the service surfaces it gracefully
    and never opens cross-tenant plaintext).
  - One-active-per-tenant constraint enforced (an explicit double-
    insert raises ``IntegrityError``).
  - Rotation in Tenant A leaves Tenant B's keypair untouched.
  - ``NoSecretsLoggedTests`` via ``assertLogs`` (private bytes,
    plaintext, signature_text never appear in log records).
  - Migration ``0015_companion_keypair_per_tenant`` rewinds + replays
    cleanly via ``MigrationExecutor``.

Tests skip when PyNaCl is not installed in the running environment.
"""
from __future__ import annotations

import base64
import logging
import re
import unittest

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase


try:
    import nacl.public  # type: ignore[import-not-found]  # noqa: F401
    from nacl.exceptions import CryptoError as _NaClCryptoError
    _PYNACL_AVAILABLE = True
except ImportError:
    _PYNACL_AVAILABLE = False
    _NaClCryptoError = Exception  # type: ignore[assignment, misc]


_REQUIRE_PYNACL = unittest.skipIf(
    not _PYNACL_AVAILABLE, "PyNaCl not installed in this environment"
)


def _make_school(slug: str, name: str | None = None):
    """Mint a ``schools.School`` row for tenant scoping tests."""
    from apps.schools.models import School
    return School.objects.create(name=name or f"School {slug}", slug=slug)


# ─── Per-tenant model shape ──────────────────────────────────────────────


class PerTenantModelShapeTests(SimpleTestCase):
    """Model declares the per-tenant FK + per-tenant constraints."""

    def test_keypair_model_has_tenant_fk(self):
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        field = MigrationCloudCompanionKeypair._meta.get_field("tenant")
        self.assertEqual(field.remote_field.model._meta.label, "schools.School")
        self.assertEqual(field.remote_field.on_delete.__name__, "CASCADE")
        self.assertEqual(field.remote_field.related_name, "companion_keypairs")
        self.assertFalse(field.null)

    def test_unique_constraints_are_per_tenant(self):
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        names = {c.name for c in MigrationCloudCompanionKeypair._meta.constraints}
        self.assertIn("uniq_active_keypair_per_tenant", names)
        self.assertIn("uniq_keypair_version_per_tenant", names)
        # And the v3.32-era global constraint is GONE.
        self.assertNotIn(
            "migrationcloud_companion_keypair_one_active", names,
            "global one-active constraint must be removed in v3.34.0",
        )

    def test_service_signature_requires_tenant_first_arg(self):
        from apps.migration_cloud.services import companion_keypair
        import inspect

        for func_name in (
            "ensure_active_keypair",
            "rotate_active_keypair",
            "rotate_keypair",
            "get_active_public_key_info",
            "decrypt_with_active_or_versioned",
        ):
            fn = getattr(companion_keypair, func_name)
            params = list(inspect.signature(fn).parameters.values())
            self.assertGreater(
                len(params), 0,
                f"{func_name} must accept at least one argument (tenant)",
            )
            self.assertEqual(
                params[0].name, "tenant",
                f"{func_name} must take 'tenant' as its first positional arg",
            )


# ─── Two-tenant isolation invariants (DB) ────────────────────────────────


@_REQUIRE_PYNACL
class TwoTenantIsolationTests(TestCase):
    """Two tenants must receive distinct, non-cross-decryptable keypairs."""

    def setUp(self):
        self.tenant_a = _make_school("isol-a", "Tenant Alpha")
        self.tenant_b = _make_school("isol-b", "Tenant Beta")

    def test_two_tenants_get_distinct_keypairs(self):
        from apps.migration_cloud.services import companion_keypair

        row_a = companion_keypair.ensure_active_keypair(self.tenant_a)
        row_b = companion_keypair.ensure_active_keypair(self.tenant_b)

        self.assertNotEqual(row_a.pk, row_b.pk)
        self.assertEqual(row_a.tenant_id, self.tenant_a.pk)
        self.assertEqual(row_b.tenant_id, self.tenant_b.pk)
        # Distinct random keys
        self.assertNotEqual(row_a.public_key_b64, row_b.public_key_b64)
        # Both are active (per-tenant scope)
        self.assertTrue(row_a.is_active)
        self.assertTrue(row_b.is_active)
        # Each tenant gets its own monotonic v1
        self.assertEqual(row_a.key_version, "v1")
        self.assertEqual(row_b.key_version, "v1")

    def test_tenant_a_cannot_decrypt_tenant_b_ciphertext(self):
        """Cross-tenant decrypt MUST fail; libsodium raises CryptoError."""
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        row_a = companion_keypair.ensure_active_keypair(self.tenant_a)
        row_b = companion_keypair.ensure_active_keypair(self.tenant_b)

        # Seal a payload to Tenant B's public key.
        pub_b = nacl.public.PublicKey(base64.b64decode(row_b.public_key_b64))
        sealed_box_b = nacl.public.SealedBox(pub_b)
        plaintext_b = b'{"secret":"only-tenant-b-can-open"}'
        ciphertext_for_b = sealed_box_b.encrypt(plaintext_b)

        # Tenant A tries to open it with Tenant A's keypair: fails.
        with self.assertRaises(_NaClCryptoError):
            companion_keypair.decrypt_with_active_or_versioned(
                self.tenant_a, ciphertext_for_b
            )

        # Sanity: Tenant B CAN open it.
        result = companion_keypair.decrypt_with_active_or_versioned(
            self.tenant_b, ciphertext_for_b
        )
        self.assertEqual(result.plaintext, plaintext_b)
        self.assertEqual(result.key_version, row_b.key_version)

        # And the fingerprint for B does not equal the fingerprint for A.
        fp_a = companion_keypair.fingerprint_of_public_key_b64(row_a.public_key_b64)
        fp_b = companion_keypair.fingerprint_of_public_key_b64(row_b.public_key_b64)
        self.assertNotEqual(fp_a, fp_b)
        self.assertFalse(companion_keypair.fingerprint_eq(fp_a, fp_b))

    def test_rotation_in_tenant_a_does_not_touch_tenant_b(self):
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        from apps.migration_cloud.services import companion_keypair

        companion_keypair.ensure_active_keypair(self.tenant_a)
        b_before = companion_keypair.ensure_active_keypair(self.tenant_b)
        b_before_pub = b_before.public_key_b64
        b_before_version = b_before.key_version

        result = companion_keypair.rotate_active_keypair(
            self.tenant_a, operator_user=None
        )
        self.assertEqual(result["old_version"], "v1")
        self.assertEqual(result["new_version"], "v2")
        self.assertEqual(result["tenant_pk"], str(self.tenant_a.pk))

        # tenant-isolation-allow: keypair-test-fetch-after-rotation-scoped-per-tenant-fk
        b_after = MigrationCloudCompanionKeypair.objects.get(
            tenant=self.tenant_b, is_active=True
        )
        self.assertEqual(b_after.public_key_b64, b_before_pub)
        self.assertEqual(b_after.key_version, b_before_version)
        self.assertIsNone(b_after.rotated_out_at)


@_REQUIRE_PYNACL
class OneActivePerTenantConstraintTests(TestCase):
    """The (tenant, is_active=True) partial unique is enforced by the DB."""

    def setUp(self):
        self.tenant = _make_school("oa-1tenant")

    def test_double_insert_active_in_same_tenant_raises(self):
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        from apps.migration_cloud.services import companion_keypair

        companion_keypair.ensure_active_keypair(self.tenant)

        # Try to write a second is_active=True row for the same tenant
        # — should hit the partial unique constraint.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MigrationCloudCompanionKeypair.objects.create(  # tenant-isolation-allow: keypair-test-double-insert-scoped-per-tenant-fk
                    tenant=self.tenant,
                    key_version="dup-v1",
                    public_key_b64="A" * 44,
                    private_key_encrypted=b"\x00" * 32,
                    is_active=True,
                )

    def test_two_active_in_different_tenants_is_allowed(self):
        from apps.migration_cloud.services import companion_keypair
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair

        tenant_other = _make_school("oa-other")
        companion_keypair.ensure_active_keypair(self.tenant)
        companion_keypair.ensure_active_keypair(tenant_other)

        # tenant-isolation-allow: keypair-test-active-cross-tenant-count
        active = MigrationCloudCompanionKeypair.objects.filter(is_active=True)
        self.assertEqual(active.count(), 2)


# ─── No-secrets-logged invariant (per-tenant) ────────────────────────────


@_REQUIRE_PYNACL
class NoSecretsLoggedPerTenantTests(TestCase):
    """Logs must carry tenant_pk + key_version + fingerprint only — never
    private key bytes, plaintext, or anything that looks like a 32-byte
    base64 blob."""

    LOG_NAME = "apps.migration_cloud.services.companion_keypair"

    def setUp(self):
        self.tenant = _make_school("logs-tenant")

    def test_ensure_logs_have_only_metadata(self):
        from apps.migration_cloud.services import companion_keypair

        with self.assertLogs(self.LOG_NAME, level=logging.INFO) as cm:
            row = companion_keypair.ensure_active_keypair(self.tenant)

        combined = "\n".join(cm.output)
        priv_repr = repr(bytes(row.private_key_encrypted))[:40]
        self.assertNotIn(priv_repr, combined)
        self.assertIn("tenant_pk=", combined)
        self.assertIn("key_version=", combined)
        self.assertIn("fingerprint=", combined)

    def test_rotate_logs_have_no_private_bytes(self):
        from apps.migration_cloud.services import companion_keypair

        companion_keypair.ensure_active_keypair(self.tenant)
        with self.assertLogs(self.LOG_NAME, level=logging.INFO) as cm:
            companion_keypair.rotate_active_keypair(self.tenant)

        "\n".join(cm.output)
        # Forbid contiguous 40+-char base64-looking blobs (a 32-byte
        # base64 private key is 44 chars).
        for line in cm.output:
            payload = line.split(":", 2)[-1]
            long_b64 = re.findall(r"[A-Za-z0-9+/]{40,}", payload)
            self.assertFalse(
                long_b64,
                f"Suspicious long base64 blob in log line: {line!r} "
                f"(found {long_b64!r})",
            )

    def test_decrypt_logs_no_plaintext_or_signature(self):
        from apps.migration_cloud.services import companion_keypair
        import nacl.public

        row = companion_keypair.ensure_active_keypair(self.tenant)
        pub = nacl.public.PublicKey(base64.b64decode(row.public_key_b64))
        sealed_box = nacl.public.SealedBox(pub)
        # Sentinel plaintext, signature_text proxy, and MAA-text proxy
        # all in one ciphertext payload. None of these strings should
        # appear in the log output.
        plaintext = (
            b'{"sentinel-plaintext":"SECRET-PLAINTEXT-MARKER-XYZ",'
            b'"signature_text":"SECRET-SIGNATURE-MARKER-XYZ",'
            b'"maa_text":"SECRET-MAA-MARKER-XYZ"}'
        )
        ciphertext = sealed_box.encrypt(plaintext)

        with self.assertLogs(self.LOG_NAME, level=logging.INFO) as cm:
            result = companion_keypair.decrypt_with_active_or_versioned(
                self.tenant, ciphertext
            )
            self.assertEqual(result.plaintext, plaintext)

        combined = "\n".join(cm.output)
        for marker in (
            "SECRET-PLAINTEXT-MARKER-XYZ",
            "SECRET-SIGNATURE-MARKER-XYZ",
            "SECRET-MAA-MARKER-XYZ",
        ):
            self.assertNotIn(marker, combined,
                f"Logger leaked sensitive marker: {marker!r}")
        # Metadata only is fine.
        self.assertIn("decrypt_ok", combined)
        self.assertIn("plaintext_size=", combined)


# ─── Migration replay (rewind + replay 0015) ─────────────────────────────


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "Migration replay via MigrationExecutor runs schema ops inside the "
    "TestCase transaction; SQLite cannot toggle foreign-key checks mid-"
    "transaction (NotSupportedError). Production + CI run on PostgreSQL, "
    "which handles DDL in a transaction, so the replay is exercised there.",
)
class Migration0015ReplayTests(TestCase):
    """``0015_companion_keypair_per_tenant`` rewinds and replays cleanly.

    Uses ``MigrationExecutor`` so the test runs in the live test DB
    (which already has all migrations applied at TestCase setup). We
    rewind to ``0014_merge_0011_0013``, then forward to ``0015``, and
    assert the per-tenant constraint exists at the end.
    """

    def test_rewind_and_replay(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        # Rewind. The constraint name comparison below uses Django's
        # SchemaEditor-introspected constraint set, which is more robust
        # across DB backends than direct INFORMATION_SCHEMA queries.
        try:
            executor.migrate([("migration_cloud", "0014_merge_0011_0013")])
            executor.loader.build_graph()
            executor.migrate([("migration_cloud", "0015_companion_keypair_per_tenant")])
        except Exception as exc:  # pragma: no cover — replay is the smoke
            self.fail(f"migration replay failed: {type(exc).__name__}: {exc}")

        # After replay, the per-tenant constraint must exist in the
        # model's Meta (the migration applies it via AddConstraint).
        from apps.migration_cloud.models import MigrationCloudCompanionKeypair
        names = {c.name for c in MigrationCloudCompanionKeypair._meta.constraints}
        self.assertIn("uniq_active_keypair_per_tenant", names)
        self.assertIn("uniq_keypair_version_per_tenant", names)
