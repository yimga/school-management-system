# v3.33.0 — AddField + backfill for MigrationAuthorizationAgreement.signature_text_sha256.
#
# Pure AddField op + forward-only RunPython backfill computes
# ``sha256(signature_text.encode("utf-8"))`` for every existing row.
# Idempotent: re-running the backfill is a no-op because the result is
# pure-function of signature_text. Reverse is a no-op — the column
# drops with the migration reversal.

from __future__ import annotations

import hashlib

from django.db import migrations, models


def _backfill_signature_sha(apps, schema_editor):
    """Populate signature_text_sha256 for every existing row.

    Uses ``apps.get_model`` (per ``scan_migration_model_imports.py``
    contract) so the migration runs against the historical model state.
    Idempotent: re-running yields the same sha for identical
    signature_text bytes.
    """
    MAA = apps.get_model("migration_cloud", "MigrationAuthorizationAgreement")
    # tenant-isolation-allow: data-migration-backfill-historical-rows-platform-wide
    for row in MAA.objects.all().iterator():
        canonical = (row.signature_text or "").encode("utf-8")
        row.signature_text_sha256 = hashlib.sha256(canonical).hexdigest()
        row.save(update_fields=["signature_text_sha256"])


def _noop_reverse(apps, schema_editor):
    """Reverse is a no-op — the column itself is dropped by AlterField reversal."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0010_rename_migration_c_is_acti_a8f3b1_idx_migration_c_is_acti_c68d15_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationauthorizationagreement",
            name="signature_text_sha256",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "sha256(signature_text.encode('utf-8')) — audit fingerprint, "
                    "auto-computed on save. Detects post-hoc tampering."
                ),
                max_length=64,
            ),
        ),
        migrations.RunPython(_backfill_signature_sha, _noop_reverse),
    ]
