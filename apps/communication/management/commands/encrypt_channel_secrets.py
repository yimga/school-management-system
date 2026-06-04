"""Encrypt existing plaintext channel-integration secrets at rest (audit C1).

``ServiceIntegration.config`` historically stored WhatsApp / FCM / push
credentials in plaintext. ``ServiceIntegration.save()`` now encrypts secret-
named keys, and the channel resolvers decrypt on read — but rows written
before that landed are still plaintext until re-saved. This one-shot command
re-saves every row so its secrets are encrypted.

Idempotent: already-encrypted values (carrying the ENC_PREFIX) are skipped by
``encrypt_config``. Safe to run repeatedly.

    python manage.py encrypt_channel_secrets            # dry-run (report only)
    python manage.py encrypt_channel_secrets --apply    # write
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Encrypt plaintext secrets in ServiceIntegration.config (audit C1)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist changes.")

    def handle(self, *args, **options):
        from apps.communication.secret_config import (
            ENC_PREFIX,
            SECRET_KEYS,
            encrypt_config,
        )
        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        apply = bool(options.get("apply"))
        scanned = 0
        needs = 0
        wrote = 0
        # tenant-isolation-allow: platform-wide one-shot secret-encryption migration
        for row in ServiceIntegration.objects.all().iterator():
            scanned += 1
            cfg = row.config if isinstance(row.config, dict) else {}
            plaintext_secret = any(
                isinstance(v, str)
                and v
                and not v.startswith(ENC_PREFIX)
                and (
                    k.lower() in SECRET_KEYS
                    or k.lower().endswith(("_secret", "_token", "_key"))
                )
                for k, v in cfg.items()
            )
            if not plaintext_secret:
                continue
            needs += 1
            if apply:
                row.config = encrypt_config(cfg)
                # save() also runs encrypt_config (idempotent); update_fields
                # keeps it to the one column.
                row.save(update_fields=["config", "updated_at"])
                wrote += 1

        self.stdout.write(
            f"scanned={scanned} needing_encryption={needs} "
            f"written={wrote} mode={'apply' if apply else 'dry-run'}"
        )
        if not apply and needs:
            self.stdout.write("Re-run with --apply to encrypt the rows above.")
