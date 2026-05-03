"""
Safe gateway health signals for tenant payment readiness (no live charges, no secret logging).

Uses Integration catalog hints where present; CARD/BANK PSP onboarding stays honestly external.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.finance.models import ComplianceProfile, TenantPaymentPolicy
from apps.finance.payment_fallback_engine import MANUAL_FALLBACK_CODE
from apps.finance.regional_payment_profiles import get_normalized_regional_profile
from apps.finance.services import get_payment_integration_by_slug

# Rail codes handled without hitting external PSP APIs (metadata-only checks).
RAIL_CODE_TO_SLUG: dict[str, str] = {
    "MTN_MOMO": "mtn_momo",
    "ORANGE_MOMO": "orange_momo",
}

HealthChecker = Callable[
    [str, dict[str, Any], TenantPaymentPolicy | None, ComplianceProfile | None],
    dict[str, Any],
]


class GatewayHealthStatus:
    READY = "ready"
    DEGRADED = "degraded"
    MISSING_CREDENTIALS = "missing_credentials"
    EXTERNAL_REQUIRED = "external_required"
    UNKNOWN = "unknown"


def default_rail_health_check(
    rail_code: str,
    catalog: dict[str, Any],
    policy: TenantPaymentPolicy | None,
    compliance_profile: ComplianceProfile | None,
) -> dict[str, Any]:
    """
    Infer status without payment API calls. Never logs secrets.
    """
    rc = (rail_code or "").strip().upper()
    manual_allowed = bool(policy.allow_manual_offline_proof) if policy else True

    if rc in ("MANUAL", MANUAL_FALLBACK_CODE, "MANUAL_RECEIPT", "CASH"):
        if manual_allowed:
            return {
                "rail_code": rc,
                "provider_key": "manual",
                "status": GatewayHealthStatus.READY,
                "message": "Manual / proof capture path enabled by tenant policy.",
                "action_required": "",
            }
        return {
            "rail_code": rc,
            "provider_key": "manual",
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "Manual fallback disabled in Tenant Payment Policy.",
            "action_required": "Enable manual/offline proof in tenant payment policy.",
        }

    slug = RAIL_CODE_TO_SLUG.get(rc)
    if slug:
        integration = get_payment_integration_by_slug(slug)
        if not integration:
            return {
                "rail_code": rc,
                "provider_key": slug,
                "status": GatewayHealthStatus.MISSING_CREDENTIALS,
                "message": "No enabled payments integration for this mobile-money rail.",
                "action_required": "Configure MoMo integration (API keys live outside logs).",
            }
        cfg = integration.config or {}
        if not cfg.get("base_url"):
            return {
                "rail_code": rc,
                "provider_key": slug,
                "status": GatewayHealthStatus.DEGRADED,
                "message": "Integration exists but callback/base URL is incomplete.",
                "action_required": "Finish integration base_url / webhook routing.",
            }
        return {
            "rail_code": rc,
            "provider_key": slug,
            "status": GatewayHealthStatus.READY,
            "message": "MoMo integration metadata present (no live transaction probe).",
            "action_required": "",
        }

    # CARD / BANK / generic — live PSP onboarding is out-of-repo.
    ext = str(catalog.get("provider_setup_status") or "external_required").lower()
    if ext == "external_required":
        return {
            "rail_code": rc,
            "provider_key": "psp",
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": catalog.get("provider_notes")
            or "Card/bank rails require tenant PSP contracts and credentials.",
            "action_required": "Complete processor onboarding (Stripe/Paystack/bank) outside this UI.",
        }
    return {
        "rail_code": rc,
        "provider_key": "unknown",
        "status": GatewayHealthStatus.UNKNOWN,
        "message": "Rail status not classified — verify corridor catalog.",
        "action_required": "Review regional profile and tenant integrations.",
    }


def build_gateway_health_rows(
    school,
    compliance_profile: ComplianceProfile | None,
    *,
    checker: HealthChecker | None = None,
) -> list[dict[str, Any]]:
    """
    One row per primary rail, backup rail, and manual fallback path (when applicable).
    """
    cc = (
        str(compliance_profile.country_code).strip().upper()[:8]
        if compliance_profile and compliance_profile.country_code
        else None
    )
    catalog = get_normalized_regional_profile(cc) or {}
    policy = (
        TenantPaymentPolicy.objects.filter(school=school).first()
        if school is not None
        else None
    )
    fn = checker or default_rail_health_check
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for key in ("primary_rail", "backup_rail"):
        rail = str(catalog.get(key) or "").strip().upper()
        if not rail or rail in seen:
            continue
        seen.add(rail)
        row = fn(rail, catalog, policy, compliance_profile)
        row["role"] = "primary" if key == "primary_rail" else "backup"
        rows.append(row)

    # Manual path row (orchestration hint rail)
    mf = catalog.get("manual_fallback")
    if mf is not False:
        man = fn("MANUAL", catalog, policy, compliance_profile)
        man["role"] = "manual_fallback"
        if not any(r.get("rail_code") == "MANUAL" for r in rows):
            rows.append(man)

    return rows


def next_operator_action(
    rows: list[dict[str, Any]],
    catalog: dict[str, Any] | None,
) -> str:
    """Short recommendation from health rows (no fake PSP success)."""
    if not rows:
        return "Configure compliance country and tenant payment policy."
    prim = next((r for r in rows if r.get("role") == "primary"), None)
    back = next((r for r in rows if r.get("role") == "backup"), None)
    man = next((r for r in rows if r.get("role") == "manual_fallback"), None)

    if prim and prim.get("status") == GatewayHealthStatus.READY:
        return "Primary rail metadata looks usable — monitor settlements in finance inbox."

    if back and back.get("status") == GatewayHealthStatus.READY:
        return "Use backup rail while primary processor onboarding completes."

    if man and man.get("status") == GatewayHealthStatus.READY:
        return "Collect manual proof / receipts and reconcile in finance queue."

    if prim and prim.get("status") == GatewayHealthStatus.DEGRADED:
        return "Fix degraded primary integration or switch to backup/manual path."

    if prim and prim.get("status") == GatewayHealthStatus.EXTERNAL_REQUIRED:
        return (
            catalog.get("operator_ready_label")
            or "Finish external PSP onboarding, then re-check readiness."
        )

    return "Complete checklist items on the compliance profile and tenant payment policy."


def record_gateway_health_snapshots(
    school,
    rows: list[dict[str, Any]],
) -> None:
    """Persist append-only snapshots for dashboard history (tenant-scoped)."""
    from apps.finance.models import PaymentGatewayHealthSnapshot

    if school is None or not rows:
        return

    now = timezone.now()
    to_create = []
    for row in rows:
        to_create.append(
            PaymentGatewayHealthSnapshot(
                school=school,
                rail_code=str(row.get("rail_code") or "")[:40],
                provider_key=str(row.get("provider_key") or "")[:64],
                status=str(row.get("status") or GatewayHealthStatus.UNKNOWN)[:32],
                message=str(row.get("message") or "")[:2000],
                action_required=str(row.get("action_required") or "")[:2000],
                checked_at=now,
            )
        )
    with transaction.atomic():
        PaymentGatewayHealthSnapshot.objects.bulk_create(to_create)


def latest_snapshots_per_rail(school) -> list[Any]:
    """Most recent snapshot per rail_code for a school (SQLite-safe)."""
    from apps.finance.models import PaymentGatewayHealthSnapshot

    if school is None:
        return []
    qs = PaymentGatewayHealthSnapshot.objects.filter(school=school).order_by(
        "-checked_at"
    )
    seen: set[str] = set()
    out: list[Any] = []
    for snap in qs:
        if snap.rail_code not in seen:
            seen.add(snap.rail_code)
            out.append(snap)
    return out


def availability_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, bool]:
    """Map rail_code -> online availability for select_effective_rail."""
    avail: dict[str, bool] = {}
    for row in rows:
        rc = str(row.get("rail_code") or "").strip().upper()
        st = row.get("status")
        if rc in ("MANUAL", MANUAL_FALLBACK_CODE):
            continue
        avail[rc] = st == GatewayHealthStatus.READY
    return avail
