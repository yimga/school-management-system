"""Add MigrationBundle.connector_secret — Fernet-encrypted-at-rest connector
credentials (API bearer token / OAuth access token) captured when an operator
attaches a live source to a pending bundle.

Pure AddField. The column is TEXT (EncryptedJSONField.db_type) holding Fernet
ciphertext; empty {} round-trips as the literal "{}" so existing rows and
unattached bundles carry no ciphertext.
"""

from django.db import migrations

import apps.accounts.legacy_hashes.encryption


class Migration(migrations.Migration):

    dependencies = [
        ("migration_cloud", "0031_rls_policy_default_deny"),
    ]

    operations = [
        migrations.AddField(
            model_name="migrationbundle",
            name="connector_secret",
            field=apps.accounts.legacy_hashes.encryption.EncryptedJSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Encrypted-at-rest connector credentials for live-source "
                    "intake (API token / OAuth access token). Reconstructed into "
                    "the adapter handle at ingest; never logged or returned."
                ),
            ),
        ),
    ]
