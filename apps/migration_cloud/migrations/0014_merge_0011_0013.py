"""Merge parallel migration_cloud branches (0011 companion encryption + 0013 MAA sha256)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "migration_cloud",
            "0011_companion_keypair_encrypted_and_receipt_keyversion",
        ),
        ("migration_cloud", "0013_maa_signature_sha256"),
    ]

    operations = []
