"""Set — and validate at write time — the webhook signature scheme on a payment
Integration.

The live inbound rail (``views_payments.py::payment_provider_webhook``) opts an
Integration into a provider-accurate verifier via ``config["signature_scheme"]``.
Setting that key by hand risks a typo (``"strpe"``) that the request path fails
CLOSED on — correct, but the operator only discovers it as a stream of 403 /
``WebhookLog(status=INVALID)`` rows AFTER the PSP goes live. This command rejects
an unrecognised scheme up front so the misconfiguration is caught while
configuring, never in production.

Usage:
  python manage.py set_payment_webhook_signature_scheme --provider-slug stripe --scheme stripe
  python manage.py set_payment_webhook_signature_scheme --provider-slug mtn_momo --scheme generic_hmac --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.finance.webhooks.signature_dispatch import (
    GENERIC_SCHEME,
    PROVIDER_ACCURATE_SCHEMES,
    is_recognized_scheme,
    scheme_from_config,
)
from apps.integrations_marketplace.models import Integration


class Command(BaseCommand):
    help = "Set/validate the webhook signature scheme on a payment Integration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider-slug",
            required=True,
            help="Payment provider slug (matches Integration.slug or config.provider_slug).",
        )
        parser.add_argument(
            "--scheme",
            required=True,
            help="Signature scheme: "
            + " | ".join(sorted(PROVIDER_ACCURATE_SCHEMES | {GENERIC_SCHEME})),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and preview the change without saving.",
        )

    def handle(self, *args, **options):
        provider_slug = str(options["provider_slug"] or "").strip()
        scheme = str(options["scheme"] or "").strip().lower()
        valid = ", ".join(sorted(PROVIDER_ACCURATE_SCHEMES | {GENERIC_SCHEME}))

        if not is_recognized_scheme(scheme):
            raise CommandError(
                f"Unknown signature scheme {scheme!r}. Valid schemes: {valid}."
            )

        # Configure-time resolver: intentionally NOT gated on enabled/allowlist so
        # an operator can pre-configure an integration before turning it live.
        integration = (
            Integration.objects.filter(provider="payments")
            .filter(Q(config__provider_slug=provider_slug) | Q(slug=provider_slug))
            .order_by("-id")
            .first()
        )
        if integration is None:
            raise CommandError(
                f"No payment integration found for slug {provider_slug!r}."
            )

        config = dict(integration.config or {})
        old = config.get("signature_scheme")
        config["signature_scheme"] = scheme
        effective = scheme_from_config(config) or GENERIC_SCHEME

        if options.get("dry_run"):
            self.stdout.write(
                f"[dry-run] {provider_slug}: signature_scheme {old!r} -> {scheme!r} "
                f"(effective verifier: {effective})"
            )
            return

        integration.config = config
        integration.save(update_fields=["config"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{provider_slug}: signature_scheme set to {scheme!r} "
                f"(effective verifier: {effective})."
            )
        )
