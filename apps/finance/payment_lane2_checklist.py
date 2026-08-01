"""
Lane 2 operator checklist for PSP corridors (SFDP Phase 2 — cannot fake in git).

Maps external_dependencies_register ids to concrete Integration + evidence steps.
Build agents use this for honest status; operators flip register rows to verified_live
only after evidence files exist under var/evidence/geos-99/psp/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Lane2CorridorChecklist:
    register_id: str
    psp_slug: str
    corridors: tuple[str, ...]
    integration_provider: str
    integration_slug_hints: tuple[str, ...]
    verification_command: str
    verification_mode: str
    evidence_dir: str
    evidence_filename: str
    external_blockers: tuple[str, ...]
    flip_register_status: str = "verified_live"


LANE2_PILOT_CORRIDORS: tuple[Lane2CorridorChecklist, ...] = (
    Lane2CorridorChecklist(
        register_id="stripe_global_cards",
        psp_slug="stripe",
        corridors=("GLOBAL",),
        integration_provider="payments",
        integration_slug_hints=("stripe", "stripe_cards"),
        verification_command="python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=production_ping",
        verification_mode="production_ping",
        evidence_dir="var/evidence/geos-99/psp/stripe",
        evidence_filename="phase1_platform_charge_evidence.json",
        external_blockers=(
            "Tenant Stripe merchant KYB complete for school-fee collection",
            "Tenant pk_live/sk_live + webhook secret stored in its Integration only",
            "One supervised charge + refund on staging then prod",
        ),
    ),
    Lane2CorridorChecklist(
        register_id="stripe_connect_platform",
        psp_slug="stripe",
        corridors=("GLOBAL",),
        integration_provider="payments",
        integration_slug_hints=("stripe", "stripe_connect"),
        verification_command="python scripts/verify_stripe_platform_settlement_scaffold.py",
        verification_mode="scaffold_then_pilot",
        evidence_dir="var/evidence/geos-99/psp/stripe",
        evidence_filename="phase2_connect_pilot_evidence.json",
        external_blockers=(
            "Tenant connected-account onboarding and merchant identity complete",
            "Pilot school completes Express onboarding at /siteconfig/billing-stripe/",
            "Direct charge on connected account with tenant payout proof; no destination charge or application fee",
        ),
    ),
    Lane2CorridorChecklist(
        register_id="paystack_wa",
        psp_slug="paystack",
        corridors=("NG", "GH"),
        integration_provider="payments",
        integration_slug_hints=("paystack",),
        verification_command="python manage.py check_payment_gateways --school=<slug> --provider=paystack --mode=production_ping",
        verification_mode="production_ping",
        evidence_dir="var/evidence/geos-99/psp/paystack",
        evidence_filename="phase1_paystack_charge_evidence.json",
        external_blockers=(
            "Paystack merchant KYC approved",
            "sk_live_* + webhook signing secret in Integration(provider=payments)",
            "Webhook URL: /finance/payments/webhook/paystack/",
        ),
    ),
    Lane2CorridorChecklist(
        register_id="flutterwave_multi_country",
        psp_slug="flutterwave",
        corridors=("CM", "NG", "GH", "KE", "UG", "TZ", "RW", "ZA"),
        integration_provider="payments",
        integration_slug_hints=("flutterwave", "flw"),
        verification_command="python manage.py check_payment_gateways --school=<slug> --provider=flutterwave --mode=production_ping",
        verification_mode="production_ping",
        evidence_dir="var/evidence/geos-99/psp/flutterwave",
        evidence_filename="phase1_flutterwave_charge_evidence.json",
        external_blockers=(
            "Flutterwave merchant verification",
            "FLUTTERWAVE_* live keys + FLW_SECRET_HASH for webhooks",
        ),
    ),
    Lane2CorridorChecklist(
        register_id="mtn_momo",
        psp_slug="mtn_momo",
        corridors=("CM", "GH", "UG"),
        integration_provider="payments",
        integration_slug_hints=("mtn_momo", "mtn"),
        verification_command="python manage.py check_payment_gateways --school=<slug> --provider=mtn_momo --mode=metadata",
        verification_mode="metadata",
        evidence_dir="var/evidence/geos-99/psp/mtn_momo",
        evidence_filename="phase1_mtn_momo_charge_evidence.json",
        external_blockers=(
            "MTN / aggregator production API approval",
            "Callback URL registered with telco",
            "Supervised live collection txn (no non-charge probe)",
        ),
    ),
    Lane2CorridorChecklist(
        register_id="orange_money",
        psp_slug="orange_money",
        corridors=("CM", "CI", "SN"),
        integration_provider="payments",
        integration_slug_hints=("orange_momo", "orange_money", "orange"),
        verification_command="python manage.py check_payment_gateways --school=<slug> --provider=orange_momo --mode=metadata",
        verification_mode="metadata",
        evidence_dir="var/evidence/geos-99/psp/orange_money",
        evidence_filename="phase1_orange_money_charge_evidence.json",
        external_blockers=(
            "Orange / partner merchant profile",
            "Partner API credentials + callback registration",
        ),
    ),
    Lane2CorridorChecklist(
        register_id="live_reconciliation_1174",
        psp_slug="*",
        corridors=("GLOBAL",),
        integration_provider="payments",
        integration_slug_hints=(),
        verification_command="python manage.py check_payment_gateways --school=<slug> --mode=metadata",
        verification_mode="metadata",
        evidence_dir="var/evidence/geos-99/psp",
        evidence_filename="live_reconciliation_evidence.json",
        external_blockers=(
            "Supervised live charge on any pilot corridor",
            "PaymentGatewayHealthSnapshot from check_payment_gateways",
            "Settlement artifact reference (redacted IDs only in JSON)",
        ),
    ),
)


DEFERRED_V1_PSP_SLUGS: frozenset[str] = frozenset(
    {
        "razorpay",
        "pesapal",
        "mercado_pago",
        "dlocal",
    }
)

COUNSEL_BLOCKED_FEATURES: frozenset[str] = frozenset(
    {
        "paystack_subaccounts",
        "flutterwave_marketplace_split",
        "desk_to_desk_client_replication_mesh",
    }
)


def get_lane2_checklist(register_id: str) -> Lane2CorridorChecklist | None:
    for row in LANE2_PILOT_CORRIDORS:
        if row.register_id == register_id:
            return row
    return None


def lane2_matrix_for_operator() -> list[dict[str, Any]]:
    """Serializable matrix for docs/generated and operator runbooks."""
    return [
        {
            "register_id": row.register_id,
            "psp_slug": row.psp_slug,
            "corridors": list(row.corridors),
            "verification_command": row.verification_command,
            "verification_mode": row.verification_mode,
            "evidence_path": f"{row.evidence_dir}/{row.evidence_filename}",
            "external_blockers": list(row.external_blockers),
            "flip_to": row.flip_register_status,
        }
        for row in LANE2_PILOT_CORRIDORS
    ]
