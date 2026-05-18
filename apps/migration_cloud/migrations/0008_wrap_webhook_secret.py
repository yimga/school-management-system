"""v3.32.0 — Fernet-wrap MigrationCloudWebhookSubscription.secret_ciphertext.

The webhook signing secret previously stored as raw plaintext bytes
(see ``crypto-pending`` marker on 0005's CreateModel op) is now wrapped
by :class:`apps.accounts.legacy_hashes.encryption.EncryptedBinaryField`.

The wrap is transparent at the application layer — reads still return
the raw secret bytes the HMAC dispatcher needs — so only the at-rest
representation changes. The column shape (BinaryField → bytea/BLOB)
stays the same.

This migration does TWO things:

  * ``AlterField`` — swap the field descriptor to the encrypted variant.
    Django's schema editor is a no-op because the column type is
    unchanged; the AlterField is required only so the project state
    matches the model code. Depends on ``0007_token_rotation_and_webhook_deferred``
    so this branch does not fork from ``0006`` as a second leaf beside
    ``0007_companion_keypair``.
  * ``RunPython`` — read every existing row's raw ``secret_ciphertext``
    and re-save through the wrapped descriptor, which encrypts on the
    way out. Rows whose secret is empty/NULL are skipped (no-op).

Both forward and backward operations are pure: ``apps.get_model(...)``
only, no live model imports — ``scan_migration_model_imports`` clean.

Backward (``re_encrypt_existing_secrets_reverse``) is the symmetric
operation: decrypt + store raw bytes. Useful if an operator needs to
downgrade past this migration during a key-loss incident.
"""

from __future__ import annotations

import logging

from django.db import migrations, models


logger = logging.getLogger(__name__)


def re_encrypt_existing_secrets_forward(apps, schema_editor):
    """Re-save every webhook subscription so raw bytes are Fernet-wrapped.

    Reads the raw column via ``.values_list(..., flat=True)`` to bypass
    the descriptor, then assigns the raw value back to the model
    attribute and saves — the encrypted descriptor encrypts on save.

    On a freshly initialized DB with no subscriptions this is a no-op.
    """
    Subscription = apps.get_model("migration_cloud", "MigrationCloudWebhookSubscription")
    # tenant-isolation-allow: migration-layer-system-wide-data-transform-not-tenant-scoped
    raw_rows = list(
        Subscription.objects.exclude(secret_ciphertext__isnull=True).values_list(
            "pk", "secret_ciphertext"
        )
    )
    rewrapped = 0
    skipped = 0
    for pk, raw_value in raw_rows:
        if raw_value is None or bytes(raw_value or b"") == b"":
            skipped += 1
            continue
        # The descriptor's get_prep_value encrypts on save. We re-fetch
        # so the assignment path runs through the new descriptor.
        try:
            row = Subscription.objects.get(pk=pk)  # tenant-isolation-allow: migration-layer-by-pk-no-tenant-context
        except Subscription.DoesNotExist:
            skipped += 1
            continue
        # Coerce to bytes — driver may return memoryview.
        if isinstance(raw_value, memoryview):
            raw_value = raw_value.tobytes()
        row.secret_ciphertext = bytes(raw_value)
        row.save(update_fields=["secret_ciphertext", "updated_at"])
        rewrapped += 1
    logger.info(
        "migration_cloud_webhook_secret_wrap_forward",
        extra={"rewrapped": rewrapped, "skipped": skipped, "result": "ok"},
    )


def re_encrypt_existing_secrets_reverse(apps, schema_editor):
    """Reverse: decrypt + store raw bytes so the field can drop the wrap.

    Symmetric to the forward op — at the reverse point the descriptor
    still decrypts on read, so reading + saving back through the (now
    plain) BinaryField produces the un-wrapped form. NEVER log the
    bytes themselves.
    """
    Subscription = apps.get_model("migration_cloud", "MigrationCloudWebhookSubscription")
    # tenant-isolation-allow: migration-layer-system-wide-data-transform-not-tenant-scoped
    rows = list(Subscription.objects.exclude(secret_ciphertext__isnull=True))
    unwrapped = 0
    skipped = 0
    for row in rows:
        raw = row.secret_ciphertext
        if raw is None or bytes(raw or b"") == b"":
            skipped += 1
            continue
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        row.secret_ciphertext = bytes(raw)
        row.save(update_fields=["secret_ciphertext", "updated_at"])
        unwrapped += 1
    logger.info(
        "migration_cloud_webhook_secret_wrap_reverse",
        extra={"unwrapped": unwrapped, "skipped": skipped, "result": "ok"},
    )


class Migration(migrations.Migration):

    dependencies = [
        # Must stack on Agent 3's 0007 so this branch does not fork from
        # 0006 as a second leaf beside 0007_companion_keypair (that graph
        # shape breaks ``migrate`` / tests until ``0009_merge_*`` applies).
        ("migration_cloud", "0007_token_rotation_and_webhook_deferred"),
    ]

    operations = [
        migrations.AlterField(
            model_name="migrationcloudwebhooksubscription",
            name="secret_ciphertext",
            field=models.BinaryField(
                blank=True,
                help_text=(
                    "HMAC secret material used to sign outbound webhook "
                    "deliveries. Encrypted at rest via the Fernet shim; "
                    "reads transparently decrypt at the dispatcher. "
                    "NEVER log."
                ),
                null=True,
            ),
        ),
        migrations.RunPython(
            re_encrypt_existing_secrets_forward,
            reverse_code=re_encrypt_existing_secrets_reverse,
        ),
    ]
