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
from apps.finance.services import get_payment_integration_by_slug, normalize_provider_slug

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


CARD_BANK_SLUGS = frozenset({"card", "bank", "bank_transfer", "sepa"})
PSP_INTEGRATION_SLUGS = frozenset({"stripe", "paystack", "flutterwave"})


def integration_secret_hint_present(cfg: dict[str, Any] | None) -> bool:
    """True when config appears to carry credential material (never inspect/log values)."""
    cfg = cfg or {}
    for key, val in cfg.items():
        lk = str(key).lower()
        if any(tok in lk for tok in ("secret", "api_key", "private", "token", "password")):
            if isinstance(val, str) and val.strip():
                return True
            if val not in (None, "", [], {}, False):
                return True
    return False


def stripe_secret_tier(cfg: dict[str, Any] | None) -> str:
    """Return ``live``, ``test``, or empty — never exposes key material."""
    import os

    cfg = cfg or {}
    env_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""
    cfg_key = str(cfg.get("secret_key") or cfg.get("secret") or "").strip()
    cand = str(env_key or cfg_key).strip()
    if cand.startswith("sk_live_"):
        return "live"
    if cand.startswith("sk_test_"):
        return "test"
    return ""


def run_safe_production_ping(
    slug: str,
    cfg: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Non-destructive live probes only where explicitly supported (Stripe Balance.retrieve).
    Never prints secrets or raw provider payloads.
    """
    cfg = cfg or {}
    slug_l = (slug or "").strip().lower()
    base = {
        "rail_code": slug_l.upper()[:40],
        "provider_key": slug_l[:64],
        "mode": "production_ping",
        "external_action_needed": "",
    }
    if slug_l != "stripe":
        return {
            **base,
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": (
                "Production ping not implemented for this provider — collect proof via provider dashboard."
            ),
            "action_required": "",
            "external_action_needed": (
                "Run provider-supported non-charge production check per docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md."
            ),
        }

    tier = stripe_secret_tier(cfg)
    if not tier:
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "Stripe secret not present in env or integration config metadata.",
            "action_required": "Configure STRIPE_SECRET_KEY or integration secret fields.",
            "external_action_needed": "",
        }
    if tier != "live":
        return {
            **base,
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": "Production ping requires sk_live_* credentials (test keys are not live proof).",
            "action_required": "Install live Stripe keys in deployment secrets.",
            "external_action_needed": "Stripe merchant activation + live secret key rollout.",
        }

    import os

    try:
        import stripe  # type: ignore
    except ImportError:
        return {
            **base,
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": "stripe Python package not installed.",
            "action_required": "Add stripe dependency for Balance.retrieve probes.",
            "external_action_needed": "Ops dependency install",
        }

    key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or cfg.get(
        "secret_key"
    ) or cfg.get("secret")
    stripe.api_key = str(key).strip()
    try:
        stripe.Balance.retrieve()
    except Exception:
        return {
            **base,
            "status": GatewayHealthStatus.DEGRADED,
            "message": "Stripe Balance.retrieve failed (check network/API reachability).",
            "action_required": "Inspect Stripe dashboard connectivity without logging secrets.",
            "external_action_needed": "",
        }
    return {
        **base,
        "status": GatewayHealthStatus.READY,
        "message": "Stripe Balance.retrieve succeeded (non-charge production ping).",
        "action_required": "",
        "external_action_needed": "",
    }


def evaluate_named_provider_health(
    provider_slug: str,
    *,
    mode: str = "metadata",
    school=None,
    compliance_profile=None,
) -> dict[str, Any]:
    """
    Targeted PSP/mobile-money evaluation for ``check_payment_gateways``.
    Does not charge; does not log secrets.
    """
    raw = (provider_slug or "").strip()
    slug = normalize_provider_slug(raw) or raw.lower()

    base_out: dict[str, Any] = {
        "rail_code": (raw.upper() if raw.isascii() else slug.upper())[:40],
        "provider_key": slug[:64],
        "mode": mode,
        "external_action_needed": "",
    }

    ru = raw.upper()
    if slug in CARD_BANK_SLUGS or ru in {"CARD", "BANK", "SEPA"}:
        rc = ru if ru in {"CARD", "BANK", "SEPA"} else slug.upper()
        return {
            **base_out,
            "rail_code": rc[:40],
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": "Card/bank rails require PSP or sponsor bank onboarding outside the repo.",
            "action_required": "Complete merchant onboarding; store credentials only in secrets.",
            "external_action_needed": "Bank/PSP approval + settlement account verification.",
        }

    rail = ""
    if slug in {"mtn_momo", "mtn"}:
        rail = "MTN_MOMO"
    elif slug in {"orange_momo", "orange_money", "orange"}:
        rail = "ORANGE_MOMO"

    if rail:
        rows = build_gateway_health_rows(school, compliance_profile)
        hit = next((r for r in rows if str(r.get("rail_code")) == rail), None)
        if hit:
            out = dict(hit)
            out["mode"] = mode
            if out.get("status") == GatewayHealthStatus.EXTERNAL_REQUIRED:
                out.setdefault(
                    "external_action_needed",
                    out.get("action_required") or "Telco or aggregator onboarding.",
                )
            if mode == "production_ping":
                out["status"] = GatewayHealthStatus.EXTERNAL_REQUIRED
                out["message"] = (
                    "MoMo production ping not implemented — supervised live corridor proof required."
                )
                out["external_action_needed"] = (
                    "Complete aggregator callbacks + supervised transaction or portal evidence."
                )
            return out
        return {
            **base_out,
            "rail_code": rail,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "MoMo rail not surfaced from regional profile + integrations.",
            "action_required": "Configure school country + payments Integration.",
            "external_action_needed": "",
        }

    check_slug = slug
    if check_slug not in PSP_INTEGRATION_SLUGS:
        alt = normalize_provider_slug(raw)
        if alt in PSP_INTEGRATION_SLUGS:
            check_slug = alt

    if check_slug in PSP_INTEGRATION_SLUGS:
        integ = get_payment_integration_by_slug(check_slug)
        if not integ:
            return {
                **base_out,
                "rail_code": check_slug.upper(),
                "provider_key": check_slug,
                "status": GatewayHealthStatus.MISSING_CREDENTIALS,
                "message": f"No enabled payments integration resolved for '{check_slug}'.",
                "action_required": "Create Integration(provider=payments) with matching slug/config.",
                "external_action_needed": "",
            }
        cfg = integ.config or {}
        secret_ok = integration_secret_hint_present(cfg)
        stripe_tier = ""
        if check_slug == "stripe":
            stripe_tier = stripe_secret_tier(cfg)
            secret_ok = secret_ok or bool(stripe_tier)
        if not secret_ok:
            return {
                **base_out,
                "rail_code": check_slug.upper(),
                "provider_key": check_slug,
                "status": GatewayHealthStatus.MISSING_CREDENTIALS,
                "message": "Integration row exists but credential hints are absent.",
                "action_required": "Populate secret/API fields via deployment config.",
                "external_action_needed": "",
            }
        degraded_urls = False
        if check_slug != "stripe" and not (cfg.get("base_url") or cfg.get("callback_url")):
            degraded_urls = True
        if mode == "production_ping":
            return run_safe_production_ping(check_slug, cfg)
        st = GatewayHealthStatus.DEGRADED if degraded_urls else GatewayHealthStatus.READY
        msg = (
            "PSP integration metadata present (metadata mode — no payment probe)."
            if not degraded_urls
            else "Integration partially configured — finish callback/base URLs."
        )
        if check_slug == "stripe" and stripe_tier == "test" and not degraded_urls:
            st = GatewayHealthStatus.DEGRADED
            msg = "Stripe test credentials present — not live PSP proof."
        return {
            **base_out,
            "rail_code": check_slug.upper(),
            "provider_key": check_slug,
            "status": st,
            "message": msg,
            "action_required": "Finish webhook URLs per PAYMENT_ENVIRONMENT_CONTRACT.md."
            if degraded_urls
            else "",
            "external_action_needed": "",
        }

    return {
        **base_out,
        "status": GatewayHealthStatus.UNKNOWN,
        "message": "Unknown provider — use stripe, paystack, flutterwave, mtn_momo, orange_momo, card, bank.",
        "action_required": "See docs/payments/PAYMENT_ENVIRONMENT_CONTRACT.md.",
        "external_action_needed": "",
    }


def sanitize_health_payload_for_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip any nested objects that might carry secrets before CLI/HTTP emission."""

    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                lk = str(k).lower()
                if lk in {"secret", "secrets", "config", "authorization", "api_key"}:
                    continue
                if "secret" in lk or "password" in lk or "token" in lk:
                    continue
                out[k] = scrub(v)
            return out
        if isinstance(obj, list):
            return [scrub(x) for x in obj]
        return obj

    return scrub(payload)
