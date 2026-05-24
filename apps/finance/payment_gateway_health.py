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
PSP_INTEGRATION_SLUGS = frozenset(
    {
        "stripe",
        "paystack",
        "flutterwave",
        "razorpay",
        "pesapal",
        "mercado_pago",
        "mercadopago",
        "dlocal",
    }
)


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


def _http_get_json(url: str, headers: dict[str, str], timeout: float = 8.0) -> tuple[int, dict[str, Any] | None]:
    """Non-charge read-only HTTPS GET. Returns (status_code, parsed_json_or_None).

    Uses stdlib only; never logs Authorization headers or response bodies.
    """
    import json as _json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — non-charge GET
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            body = resp.read(4096) or b""
            try:
                parsed = _json.loads(body.decode("utf-8", errors="replace") or "{}")
            except Exception:
                parsed = None
            return status, parsed
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), None
    except Exception:
        return 0, None


def _resolve_secret(cfg: dict[str, Any], env_names: tuple[str, ...], cfg_keys: tuple[str, ...]) -> str:
    import os

    for name in env_names:
        val = os.environ.get(name) or ""
        if val.strip():
            return val.strip()
    for key in cfg_keys:
        val = cfg.get(key) or ""
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _ping_paystack(cfg: dict[str, Any]) -> dict[str, Any]:
    """Non-charge read-only probe. Calls https://api.paystack.co/transaction/totals.

    Live keys start with `sk_live_*`; test keys start with `sk_test_*`.
    """
    base = {
        "rail_code": "PAYSTACK",
        "provider_key": "paystack",
        "mode": "production_ping",
        "external_action_needed": "",
    }
    secret = _resolve_secret(
        cfg,
        env_names=("PAYSTACK_SECRET_KEY", "PAYSTACK_API_KEY"),
        cfg_keys=("secret_key", "secret", "api_key"),
    )
    if not secret:
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "Paystack secret not present in env or integration config.",
            "action_required": "Configure PAYSTACK_SECRET_KEY in deployment secrets.",
        }
    if not secret.startswith("sk_live_"):
        return {
            **base,
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": "Production ping requires sk_live_* (test keys are not live proof).",
            "action_required": "Install Paystack live keys after merchant approval.",
            "external_action_needed": "Paystack merchant verification + live secret rollout.",
        }
    status, _ = _http_get_json(
        "https://api.paystack.co/transaction/totals?perPage=1",
        headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
    )
    if status == 200:
        return {
            **base,
            "status": GatewayHealthStatus.READY,
            "message": "Paystack /transaction/totals returned 200 (non-charge production ping).",
            "action_required": "",
        }
    if status in (401, 403):
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": f"Paystack rejected credentials (HTTP {status}).",
            "action_required": "Rotate PAYSTACK_SECRET_KEY; verify merchant is live.",
        }
    return {
        **base,
        "status": GatewayHealthStatus.DEGRADED,
        "message": f"Paystack non-charge probe failed (HTTP {status or 'no response'}).",
        "action_required": "Check network egress and Paystack API status without logging secrets.",
    }


def _ping_flutterwave(cfg: dict[str, Any]) -> dict[str, Any]:
    """Non-charge read-only probe. Calls https://api.flutterwave.com/v3/balances.

    Live keys start with `FLWSECK-` and end with `-X` (live indicator); test keys end with `-TEST`.
    """
    base = {
        "rail_code": "FLUTTERWAVE",
        "provider_key": "flutterwave",
        "mode": "production_ping",
        "external_action_needed": "",
    }
    secret = _resolve_secret(
        cfg,
        env_names=("FLUTTERWAVE_SECRET_KEY", "FLW_SECRET_KEY", "FLUTTERWAVE_API_KEY"),
        cfg_keys=("secret_key", "secret", "api_key"),
    )
    if not secret:
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "Flutterwave secret not present in env or integration config.",
            "action_required": "Configure FLUTTERWAVE_SECRET_KEY in deployment secrets.",
        }
    if "-TEST" in secret.upper() or "FLWSECK_TEST" in secret.upper():
        return {
            **base,
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": "Production ping requires live Flutterwave secret (test secret detected).",
            "action_required": "Install Flutterwave live keys after merchant approval.",
            "external_action_needed": "Flutterwave merchant verification + live secret rollout.",
        }
    status, _ = _http_get_json(
        "https://api.flutterwave.com/v3/balances",
        headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
    )
    if status == 200:
        return {
            **base,
            "status": GatewayHealthStatus.READY,
            "message": "Flutterwave /v3/balances returned 200 (non-charge production ping).",
            "action_required": "",
        }
    if status in (401, 403):
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": f"Flutterwave rejected credentials (HTTP {status}).",
            "action_required": "Rotate FLUTTERWAVE_SECRET_KEY; verify merchant is live.",
        }
    return {
        **base,
        "status": GatewayHealthStatus.DEGRADED,
        "message": f"Flutterwave non-charge probe failed (HTTP {status or 'no response'}).",
        "action_required": "Check network egress and Flutterwave API status without logging secrets.",
    }


def _ping_razorpay(cfg: dict[str, Any]) -> dict[str, Any]:
    """Non-charge GET /v1/payments?count=1 (Basic auth)."""
    import base64

    base = {
        "rail_code": "RAZORPAY",
        "provider_key": "razorpay",
        "mode": "production_ping",
        "external_action_needed": "",
    }
    key_id = _resolve_secret(cfg, ("RAZORPAY_KEY_ID",), ("key_id", "api_key"))
    key_secret = _resolve_secret(
        cfg, ("RAZORPAY_KEY_SECRET", "RAZORPAY_SECRET_KEY"), ("key_secret", "secret_key")
    )
    if not key_id or not key_secret:
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "Razorpay key_id/key_secret not configured.",
            "action_required": "Configure RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
        }
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode("ascii")
    status, _ = _http_get_json(
        "https://api.razorpay.com/v1/payments?count=1",
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
    )
    if status == 200:
        return {
            **base,
            "status": GatewayHealthStatus.READY,
            "message": "Razorpay /v1/payments returned 200 (non-charge ping).",
            "action_required": "",
        }
    if status in (401, 403):
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": f"Razorpay rejected credentials (HTTP {status}).",
            "action_required": "Verify live keys after merchant KYC.",
        }
    return {
        **base,
        "status": GatewayHealthStatus.DEGRADED,
        "message": f"Razorpay ping failed (HTTP {status or 'no response'}).",
        "action_required": "Check network egress.",
    }


def _ping_stripe(cfg: dict[str, Any]) -> dict[str, Any]:
    """Stripe Balance.retrieve — non-charge. Prefers stripe SDK; falls back to HTTPS GET."""
    base = {
        "rail_code": "STRIPE",
        "provider_key": "stripe",
        "mode": "production_ping",
        "external_action_needed": "",
    }
    tier = stripe_secret_tier(cfg)
    if not tier:
        return {
            **base,
            "status": GatewayHealthStatus.MISSING_CREDENTIALS,
            "message": "Stripe secret not present in env or integration config metadata.",
            "action_required": "Configure STRIPE_SECRET_KEY or integration secret fields.",
        }
    if tier != "live":
        return {
            **base,
            "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
            "message": "Production ping requires sk_live_* credentials (test keys are not live proof).",
            "action_required": "Install live Stripe keys in deployment secrets.",
            "external_action_needed": "Stripe merchant activation + live secret key rollout.",
        }
    secret = _resolve_secret(
        cfg,
        env_names=("STRIPE_SECRET_KEY", "STRIPE_API_KEY"),
        cfg_keys=("secret_key", "secret"),
    )
    try:
        import stripe  # type: ignore

        stripe.api_key = secret
        stripe.Balance.retrieve()
        return {
            **base,
            "status": GatewayHealthStatus.READY,
            "message": "Stripe Balance.retrieve succeeded (non-charge production ping).",
            "action_required": "",
        }
    except ImportError:
        status, _ = _http_get_json(
            "https://api.stripe.com/v1/balance",
            headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
        )
        if status == 200:
            return {
                **base,
                "status": GatewayHealthStatus.READY,
                "message": "Stripe /v1/balance returned 200 (non-charge HTTPS ping; SDK not installed).",
                "action_required": "Optionally install stripe SDK for richer telemetry.",
            }
        if status in (401, 403):
            return {
                **base,
                "status": GatewayHealthStatus.MISSING_CREDENTIALS,
                "message": f"Stripe rejected credentials (HTTP {status}).",
                "action_required": "Rotate STRIPE_SECRET_KEY; verify account is active.",
            }
        return {
            **base,
            "status": GatewayHealthStatus.DEGRADED,
            "message": f"Stripe non-charge probe failed (HTTP {status or 'no response'}).",
            "action_required": "Inspect connectivity without logging secrets.",
        }
    except Exception:
        return {
            **base,
            "status": GatewayHealthStatus.DEGRADED,
            "message": "Stripe Balance.retrieve failed (check network/API reachability).",
            "action_required": "Inspect Stripe dashboard connectivity without logging secrets.",
        }


def run_safe_production_ping(
    slug: str,
    cfg: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Non-destructive live probes for PSPs that expose a read-only balance/totals endpoint.

    Currently supported:
      - stripe       -> Balance.retrieve (SDK or HTTPS fallback)
      - paystack     -> /transaction/totals
      - flutterwave  -> /v3/balances

    Other providers (mtn_momo, orange_momo, card, bank, sepa) remain ``external_required``
    because they have no documented non-charge production probe — supervised live txn or
    portal evidence is the only honest proof.

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
    if slug_l == "stripe":
        return _ping_stripe(cfg)
    if slug_l == "paystack":
        return _ping_paystack(cfg)
    if slug_l == "flutterwave":
        return _ping_flutterwave(cfg)
    if slug_l == "razorpay":
        return _ping_razorpay(cfg)

    return {
        **base,
        "status": GatewayHealthStatus.EXTERNAL_REQUIRED,
        "message": (
            "Production ping not implemented for this provider — collect proof via provider dashboard."
        ),
        "action_required": "",
        "external_action_needed": (
            "Run provider-supported non-charge production check per docs/payments/PSP_API_CONNECTION_GUIDE.md."
        ),
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
