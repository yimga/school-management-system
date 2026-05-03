"""Safe gateway metadata checks — no charges; never prints secrets."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.finance.models import ComplianceProfile
from apps.finance.payment_gateway_health import (
    build_gateway_health_rows,
    evaluate_named_provider_health,
    record_gateway_health_snapshots,
    sanitize_health_payload_for_output,
)
from apps.schools.models import School


class Command(BaseCommand):
    help = (
        "Check payment gateway readiness for a tenant (metadata-only by default). "
        "Writes PaymentGatewayHealthSnapshot rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="Tenant school slug.")
        parser.add_argument(
            "--provider",
            default="",
            help="Named PSP/mobile-money slug (stripe, paystack, flutterwave, mtn_momo, orange_momo, card, bank). Empty = regional rails.",
        )
        parser.add_argument(
            "--mode",
            default="metadata",
            choices=("metadata", "production_ping"),
            help="metadata = structural checks only; production_ping = Stripe Balance.retrieve when sk_live_* exists.",
        )

    def handle(self, *args, **options):
        slug = str(options["school"]).strip()
        school = School.objects.filter(slug=slug).first()
        if not school:
            raise CommandError(f"School slug not found: {slug}")

        cc = (getattr(school, "country_code", None) or "").strip().upper()[:2]
        cp = ComplianceProfile.objects.filter(country_code=cc).first() if cc else None

        provider = str(options.get("provider") or "").strip()
        mode = str(options.get("mode") or "metadata")

        if provider:
            row = evaluate_named_provider_health(
                provider,
                mode=mode,
                school=school,
                compliance_profile=cp,
            )
            rows = [row]
        else:
            rows = build_gateway_health_rows(school, cp)
            for r in rows:
                r["mode"] = mode

        record_gateway_health_snapshots(school, rows)

        payload = sanitize_health_payload_for_output(
            {
                "school": school.slug,
                "provider": provider or "*rails*",
                "mode": mode,
                "results": rows,
            }
        )
        self.stdout.write(json.dumps(payload, indent=2))
