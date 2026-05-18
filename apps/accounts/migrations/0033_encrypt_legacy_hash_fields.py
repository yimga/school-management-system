# Generated 2026-05-18 — migration cloud "password preservation moat" v3.29
# productionization: wrap the three legacy_* columns in Fernet-encrypted
# field descriptors and add timestamps for the 12-month sunset job.
#
# Order of operations on apply:
#   1. AlterField on legacy_password_hash → EncryptedCharField
#   2. AlterField on legacy_hash_algorithm → EncryptedCharField
#      (the slug itself isn't credential-equivalent but encrypting it
#      removes a side-channel: a DB dump otherwise reveals "this row is
#      a Veracross migration" which leaks the source vendor.)
#   3. AlterField on legacy_hash_params → EncryptedJSONField
#   4. AddField legacy_hash_created_at — anchor for the 12-month sunset
#      clock. Defaults to NULL; the sunset query falls back to
#      User.date_joined for rows imported before this migration.
#   5. AddField legacy_hash_sunset_email_sent_at — set when the sunset
#      task emails a user; flag for the 30-day grace exit.
#   6. RunPython no-op forward: log a notice if any rows already have
#      plaintext legacy_password_hash. We intentionally do NOT
#      re-encrypt those rows here — production has none at this point
#      (the v3.28 wave shipped the columns but no extractor writes them
#      yet) and a forward data migration would have to hold the
#      encryption key, which we want kept out of migration history.
#      Operators run scripts/encrypt_existing_legacy_hashes.py if a
#      production import has happened between v3.28 and v3.29.
#
# Honors `scan_migration_model_imports` zero-tolerance gate: this
# migration does NOT import any live model. The encrypted field
# helpers are imported from `apps.accounts.legacy_hashes.encryption`
# which is not a Django model module.
#
# Backward migration is supported: AlterField back to plain CharField /
# JSONField is fine because the DB column type is the same shape; the
# stored values become opaque ciphertext that callers can no longer
# decrypt. Operators wanting a full rollback must first run the
# encryption backfill in reverse (decrypt + write plaintext) — also
# documented in v3.29 docket.
from __future__ import annotations

import logging

from django.db import migrations, models

from apps.accounts.legacy_hashes.encryption import (
    encrypt_charfield,
    encrypt_jsonfield,
)

logger = logging.getLogger(__name__)


def _log_plaintext_row_count(apps, schema_editor):
    """Forward no-op: count rows that may already hold plaintext hashes.

    We use ``apps.get_model`` (the historical-state model) per the
    `scan_migration_model_imports` zero-tolerance gate. The function
    NEVER reads the hash value itself — only ``.count()``.
    """
    User = apps.get_model("accounts", "User")
    # tenant-isolation-allow: auth-layer-system-wide-user-table-migration-time-count
    pre_encryption = User.objects.exclude(legacy_password_hash="").count()
    if pre_encryption:
        logger.warning(
            "legacy_hash_encryption_migration_existing_rows",
            extra={
                "user_count_with_plaintext_legacy_hash": pre_encryption,
                "action_required": (
                    "Run scripts/encrypt_existing_legacy_hashes.py --apply "
                    "to wrap these rows in Fernet ciphertext before the "
                    "next deploy."
                ),
            },
        )


def _noop_reverse(apps, schema_editor):
    """Reverse no-op. The AlterField reverse handles the schema half."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0032_legacy_password_hash"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="legacy_password_hash",
            field=encrypt_charfield(
                blank=True,
                default="",
                max_length=512,
                help_text=(
                    "Foreign-vendor password hash carried over by the "
                    "migration cloud, ENCRYPTED AT REST via Fernet. "
                    "Verified on first login, then cleared and "
                    "re-hashed via PASSWORD_HASHERS. Never log, "
                    "display, or expose the decrypted value."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="legacy_hash_algorithm",
            field=encrypt_charfield(
                blank=True,
                default="",
                max_length=64,
                help_text=(
                    "Slug registered in apps.accounts.legacy_hashes (e.g. "
                    "'pbkdf2_sha512', 'bcrypt', 'veracross_bcrypt', 'alma_bcrypt', "
                    "'facts_auto', 'skyward_auto'). Encrypted at rest. Empty = "
                    "standard Django auth path."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="legacy_hash_params",
            field=encrypt_jsonfield(
                blank=True,
                default=dict,
                help_text=(
                    "Algorithm-specific parameters (salt, iterations, etc.) "
                    "needed to verify legacy_password_hash. Encrypted at rest. "
                    "Cleared on first successful login alongside the hash."
                ),
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="legacy_hash_created_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text=(
                    "Timestamp when the foreign-vendor legacy hash was imported. "
                    "Anchor for the 12-month sunset task. NULL = imported before "
                    "v3.29; sunset job falls back to User.date_joined."
                ),
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="legacy_hash_sunset_email_sent_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text=(
                    "Set by sunset_stale_legacy_hashes when a one-time setup "
                    "link is mailed. Drives the 30-day grace clock before the "
                    "legacy fields are nulled and the user is forced through "
                    "password reset."
                ),
            ),
        ),
        migrations.RunPython(
            _log_plaintext_row_count,
            reverse_code=_noop_reverse,
            atomic=False,
        ),
    ]
