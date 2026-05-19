"""v3.33.0 Agent 1 — Companion keypair encryption + receipt key_version.

Two coordinated changes that close v3.32 companion deferred items:

  1. ``MigrationCloudCompanionKeypair.private_key_encrypted`` is
     promoted from plain ``BinaryField`` to
     :class:`apps.accounts.legacy_hashes.encryption.EncryptedBinaryField`
     (Fernet-wrapping shim that round-trips bytes transparently).
     The column shape is unchanged (bytea/BLOB); only the value
     transform on read/write differs. A ``RunPython`` forward step
     re-encrypts every existing row's raw private bytes — rows whose
     bytes are already Fernet-wrapped pass through unchanged because
     the descriptor's ``from_db_value`` tolerates pre-wrap plaintext.

  2. ``CompanionUploadReceipt.key_version`` is added (CharField,
     blank=True, default=""). The receiver writes the keypair version
     that successfully decrypted the bundle, so a later audit can pin
     each receipt to the exact server key half that opened it.

Forward + backward operations are pure: ``apps.get_model(...)`` only,
no live model imports — ``scan_migration_model_imports`` clean.
``# tenant-isolation-allow:`` markers are 5-part-hyphenated.

NEVER logs: private key bytes, plaintext content, encryption keys.
"""
from __future__ import annotations

import logging

from django.db import migrations, models

from apps.accounts.legacy_hashes.encryption import EncryptedBinaryField

logger = logging.getLogger(__name__)


def re_encrypt_existing_private_keys_forward(apps, schema_editor):
    """Re-save each keypair row so the raw private bytes become Fernet-wrapped.

    The :class:`EncryptedBinaryField` descriptor encrypts on save and
    decrypts on read, tolerating pre-wrap plaintext rows. We therefore
    read each row's current value (pre-wrap = raw bytes; post-wrap =
    transparent plaintext), assign back, and save — the descriptor
    encrypts the bytes on the way out.

    Idempotent: re-running this RunPython on a DB whose rows are
    already wrapped is a no-op because the descriptor decrypts on
    read, then encrypts on write, yielding equivalent ciphertext (the
    Fernet token bytes will differ because Fernet adds an IV, but the
    round-trip plaintext is byte-identical).

    On a freshly initialized DB with no keypair rows this is a no-op.
    """
    Keypair = apps.get_model("migration_cloud", "MigrationCloudCompanionKeypair")
    # tenant-isolation-allow: migration-layer-global-keypair-not-per-tenant-no-tenant-fk
    raw_pks = list(Keypair.objects.values_list("pk", flat=True))
    rewrapped = 0
    skipped = 0
    for pk in raw_pks:
        try:
            # tenant-isolation-allow: migration-layer-by-pk-no-tenant-context
            row = Keypair.objects.get(pk=pk)
        except Keypair.DoesNotExist:
            skipped += 1
            continue
        raw = row.private_key_encrypted
        if raw is None or bytes(raw or b"") == b"":
            skipped += 1
            continue
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        # Assign as-is. The new descriptor will encrypt on save.
        row.private_key_encrypted = bytes(raw)
        row.save(update_fields=["private_key_encrypted"])
        rewrapped += 1
    logger.info(
        "migration_cloud_companion_keypair_encrypt_forward",
        extra={"rewrapped": rewrapped, "skipped": skipped, "result": "ok"},
    )


def re_encrypt_existing_private_keys_reverse(apps, schema_editor):
    """Reverse: decrypt + store raw bytes so the field can drop the wrap.

    Symmetric to the forward op — at the reverse point the descriptor
    still decrypts on read, so reading + saving back through the (now
    plain) BinaryField produces the un-wrapped form. NEVER log the
    bytes themselves.
    """
    Keypair = apps.get_model("migration_cloud", "MigrationCloudCompanionKeypair")
    # tenant-isolation-allow: migration-layer-global-keypair-not-per-tenant-no-tenant-fk
    raw_pks = list(Keypair.objects.values_list("pk", flat=True))
    unwrapped = 0
    skipped = 0
    for pk in raw_pks:
        try:
            # tenant-isolation-allow: migration-layer-by-pk-no-tenant-context
            row = Keypair.objects.get(pk=pk)
        except Keypair.DoesNotExist:
            skipped += 1
            continue
        raw = row.private_key_encrypted
        if raw is None or bytes(raw or b"") == b"":
            skipped += 1
            continue
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        row.private_key_encrypted = bytes(raw)
        row.save(update_fields=["private_key_encrypted"])
        unwrapped += 1
    logger.info(
        "migration_cloud_companion_keypair_encrypt_reverse",
        extra={"unwrapped": unwrapped, "skipped": skipped, "result": "ok"},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0010_rename_migration_c_is_acti_a8f3b1_idx_migration_c_is_acti_c68d15_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="migrationcloudcompanionkeypair",
            name="private_key_encrypted",
            field=EncryptedBinaryField(
                help_text="Encrypted X25519 private key. Never returned in responses.",
            ),
        ),
        migrations.AddField(
            model_name="companionuploadreceipt",
            name="key_version",
            field=models.CharField(
                max_length=16,
                blank=True,
                default="",
                help_text=(
                    "Server keypair version that successfully decrypted "
                    "this upload (filled at decrypt time). Empty until "
                    "the decrypt hook runs. NEVER carries private bytes."
                ),
            ),
        ),
        migrations.RunPython(
            re_encrypt_existing_private_keys_forward,
            reverse_code=re_encrypt_existing_private_keys_reverse,
        ),
    ]
