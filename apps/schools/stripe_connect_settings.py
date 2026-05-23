"""School.settings[\"stripe_connect\"] bridge — tenant Stripe Connect Express onboarding."""

from __future__ import annotations

from typing import Any

ONBOARDING_PENDING = "pending"
ONBOARDING_COMPLETE = "complete"
ONBOARDING_RESTRICTED = "restricted"


def get_stripe_connect_payload(school) -> dict[str, Any]:
    """Normalized tenant Stripe Connect settings (no secret material)."""
    raw: dict[str, Any] = {}
    if school is not None:
        settings_json = getattr(school, "settings", None) or {}
        if isinstance(settings_json, dict):
            raw = settings_json.get("stripe_connect") or {}
    status = str(raw.get("onboarding_status") or ONBOARDING_PENDING).strip().lower()
    if status not in {ONBOARDING_PENDING, ONBOARDING_COMPLETE, ONBOARDING_RESTRICTED}:
        status = ONBOARDING_PENDING
    return {
        "account_id": (raw.get("account_id") or "").strip()[:120],
        "account_type": (raw.get("account_type") or "express").strip()[:32],
        "charges_enabled": bool(raw.get("charges_enabled")),
        "payouts_enabled": bool(raw.get("payouts_enabled")),
        "details_submitted": bool(raw.get("details_submitted")),
        "onboarding_status": status,
        "connected_at": (raw.get("connected_at") or "").strip()[:40],
    }


def is_stripe_connected(school) -> bool:
    payload = get_stripe_connect_payload(school)
    return bool(
        payload.get("account_id")
        and payload.get("charges_enabled")
        and payload.get("details_submitted")
        and payload.get("onboarding_status") == ONBOARDING_COMPLETE
    )


def set_stripe_connect_payload(school, payload: dict[str, Any]) -> None:
    """Persist stripe_connect into School.settings (does not save)."""
    if not isinstance(school.settings, dict):
        school.settings = {}
    prior = {}
    if isinstance(school.settings.get("stripe_connect"), dict):
        prior = dict(school.settings["stripe_connect"])
    merged = {
        "account_id": (payload.get("account_id") or prior.get("account_id") or "").strip()[:120],
        "account_type": (payload.get("account_type") or prior.get("account_type") or "express").strip()[
            :32
        ],
        "charges_enabled": bool(payload.get("charges_enabled", prior.get("charges_enabled"))),
        "payouts_enabled": bool(payload.get("payouts_enabled", prior.get("payouts_enabled"))),
        "details_submitted": bool(
            payload.get("details_submitted", prior.get("details_submitted"))
        ),
        "onboarding_status": str(
            payload.get("onboarding_status") or prior.get("onboarding_status") or ONBOARDING_PENDING
        ).strip()[:32],
        "connected_at": (payload.get("connected_at") or prior.get("connected_at") or "").strip()[:40],
    }
    school.settings["stripe_connect"] = merged


def merge_stripe_account_object(school, account: dict[str, Any]) -> dict[str, Any]:
    """Map Stripe Account API object → tenant payload and persist on school (no save)."""
    from django.utils import timezone

    charges = bool(account.get("charges_enabled"))
    payouts = bool(account.get("payouts_enabled"))
    details = bool(account.get("details_submitted"))
    if charges and details:
        status = ONBOARDING_COMPLETE
    elif account.get("requirements", {}).get("disabled_reason"):
        status = ONBOARDING_RESTRICTED
    else:
        status = ONBOARDING_PENDING

    connected_at = ""
    if status == ONBOARDING_COMPLETE and not get_stripe_connect_payload(school).get("connected_at"):
        connected_at = timezone.now().isoformat()
    elif get_stripe_connect_payload(school).get("connected_at"):
        connected_at = get_stripe_connect_payload(school)["connected_at"]

    payload = {
        "account_id": str(account.get("id") or "").strip(),
        "account_type": str(account.get("type") or "express").strip(),
        "charges_enabled": charges,
        "payouts_enabled": payouts,
        "details_submitted": details,
        "onboarding_status": status,
        "connected_at": connected_at,
    }
    set_stripe_connect_payload(school, payload)
    return get_stripe_connect_payload(school)


def tenant_stripe_connect_allowed(site_settings_row) -> bool:
    """Platform operator may disable tenant Connect onboarding."""
    if site_settings_row is None:
        return True
    email_delivery = getattr(site_settings_row, "email_delivery", None) or {}
    if isinstance(email_delivery, dict) and email_delivery.get("allow_tenant_stripe_connect") is False:
        return False
    flags = getattr(site_settings_row, "feature_flags", None) or {}
    if isinstance(flags, dict) and flags.get("allow_tenant_stripe_connect") is False:
        return False
    return True
