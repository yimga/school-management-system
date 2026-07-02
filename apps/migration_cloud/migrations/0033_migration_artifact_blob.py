"""Add MigrationArtifactBlob — the Phase U5 per-artifact content store (gap #2).

Pure CreateModel. Holds an encrypted-at-rest copy of each artifact's source
bytes so archive members + multi-file / remote / OAuth-folder pulls (which have
no single top-level local path) can be profiled and applied instead of silently
resolving to zero rows.

``payload`` is an ``EncryptedBinaryField`` (Fernet-wrapping shim). It deconstructs
to ``django.db.models.BinaryField`` so the migration state matches the model and
``makemigrations --check`` stays clean; the DB column is a plain BLOB / bytea and
only the read/write value transform differs. Same key + rotation as the connector
secret / webhook secret / companion keypair (docs/SECURITY_KEYS.md).

No data migration — existing bundles keep the single-local-file fallback path.
"""

from django.db import migrations, models
import django.db.models.deletion

from apps.accounts.legacy_hashes.encryption import EncryptedBinaryField


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0032_bundle_connector_secret"),
    ]

    operations = [
        migrations.CreateModel(
            name="MigrationArtifactBlob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "payload",
                    EncryptedBinaryField(
                        help_text="Fernet-encrypted source bytes. Decrypts transparently on read; never logged.",
                    ),
                ),
                (
                    "byte_size",
                    models.BigIntegerField(
                        default=0,
                        help_text="Plaintext byte length (pre-encryption); integrity + metrics only.",
                    ),
                ),
                (
                    "sha256",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        help_text="SHA-256 of the plaintext bytes; re-verified on every read.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "expires_at",
                    models.DateTimeField(
                        db_index=True,
                        help_text="PII-minimisation clock; the daily purge sweep deletes blobs past this.",
                    ),
                ),
                (
                    "artifact",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blob",
                        to="migration_cloud.migrationartifact",
                        help_text="The artifact whose raw source bytes this blob holds.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Migration artifact blob",
                "verbose_name_plural": "Migration artifact blobs",
            },
        ),
        migrations.AddIndex(
            model_name="migrationartifactblob",
            index=models.Index(fields=["expires_at"], name="mc_artifact_blob_exp_idx"),
        ),
    ]
