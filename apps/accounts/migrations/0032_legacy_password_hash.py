# Generated 2026-05-18 — migration cloud "password preservation moat".
#
# Adds three fields to accounts.User that let the legacy-hash auth
# backend transparently verify foreign-vendor password hashes on first
# login and re-hash to native Argon2 (lazy-rehash pattern, same as
# Discourse / Auth0 / Keycloak).
#
# Backward-compatible: all three fields default to empty/blank so rows
# created before this migration continue to authenticate via the native
# ``password`` column unchanged. The migration uses ``apps.get_model``
# would be required if a data migration touched rows; this is a pure
# AddField migration and follows the ``scan_migration_model_imports``
# zero-tolerance gate by NOT importing any live model.
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0031_add_preferred_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="legacy_password_hash",
            field=models.CharField(
                blank=True,
                default="",
                max_length=512,
                help_text=(
                    "Foreign-vendor password hash carried over by the "
                    "migration cloud. Verified on first login, then "
                    "cleared and re-hashed via PASSWORD_HASHERS. Never "
                    "log, display, or expose this value."
                ),
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="legacy_hash_algorithm",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                help_text=(
                    "Slug registered in apps.accounts.legacy_hashes "
                    "(e.g. 'pbkdf2_sha512', 'bcrypt', 'veracross_bcrypt', "
                    "'alma_bcrypt', 'facts_auto', 'skyward_auto'). Empty "
                    "= no legacy hash; standard Django auth path applies."
                ),
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="legacy_hash_params",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Algorithm-specific parameters (e.g. salt, iterations) "
                    "needed to verify legacy_password_hash. Cleared "
                    "alongside the hash on first successful login."
                ),
            ),
        ),
    ]
