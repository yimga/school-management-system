"""
API Center: catalog of tenant-configurable integration types.
Each tenant can add credentials in API Center; runtime resolves via resolve_active_integration(school, service_key).
Config schema hints drive admin/UI form and validation.

Cost guardrails (optional per integration):
- daily_cap: max API calls per tenant per day; exceed → use fallback_channel or block.
- cooldown_seconds: min seconds between calls; throttle to avoid burst cost.
- fallback_channel: service_key to use when over cap or throttled (e.g. "email" when "whatsapp" is capped).
"""
from __future__ import annotations

from typing import Any, Callable

from django.db import DatabaseError

# Service key → config schema and provider/category for API Center
INTEGRATION_CATALOG: dict[str, dict[str, Any]] = {
    "whatsapp": {
        "label": "WhatsApp Business API",
        "provider": "whatsapp",
        "category": "MESSAGING",
        "service_type": "WHATSAPP",
        "daily_cap": 1000,
        "cooldown_seconds": 1,
        "fallback_channel": "email",
        "config_schema": {
            "phone_number_id": {"type": "string", "label": "Phone Number ID", "required": True},
            "access_token": {"type": "password", "label": "Access Token", "required": True},
            "webhook_verify_token": {"type": "string", "label": "Webhook Verify Token"},
            "api_version": {"type": "string", "label": "API Version", "default": "v18.0"},
        },
        "description": "Send templates and session messages to parents/guardians. Configure in Meta Developer Console.",
    },
    "push": {
        "label": "Push Notifications",
        "provider": "push",
        "category": "MESSAGING",
        "service_type": "PUSH",
        "config_schema": {
            "provider": {"type": "string", "label": "Provider", "choices": ["fcm", "apns", "web_push", "other"]},
            "server_key": {"type": "password", "label": "FCM Server Key (if FCM)"},
            "bundle_id": {"type": "string", "label": "APNS Bundle ID (if APNS)"},
            "endpoint_url": {"type": "url", "label": "Webhook URL (if other)"},
        },
        "description": "Send push notifications (absent alert, fee reminder). FCM, APNS, or custom webhook.",
    },
    "stripe": {
        "label": "Stripe",
        "provider": "stripe",
        "category": "PAYMENT",
        "service_type": "OAUTH",
        "daily_cap": 5000,
        "cooldown_seconds": 0,
        "fallback_channel": None,
        "config_schema": {
            "publishable_key": {"type": "string", "label": "Publishable Key"},
            "secret_key": {"type": "password", "label": "Secret Key", "required": True},
            "webhook_secret": {"type": "string", "label": "Webhook Secret"},
        },
        "description": "Card payments and subscriptions. Per-tenant Stripe account or platform Stripe with Connect.",
    },
    "stripe_platform": {
        "label": "Stripe (Platform Billing)",
        "provider": "stripe",
        "category": "BILLING",
        "service_type": "STRIPE",
        "config_schema": {
            "secret_key": {"type": "password", "label": "Platform Secret Key", "required": True},
            "webhook_secret": {"type": "string", "label": "Webhook Secret"},
            "price_id_per_school": {"type": "string", "label": "Price ID for per-school subscription"},
        },
        "description": "Super-admin: bill each school (e.g. monthly). Use school=null for platform-level integration.",
    },
    "badges": {
        "label": "Digital Badges (Open Badges)",
        "provider": "badges",
        "category": "BADGES",
        "service_type": "BADGES",
        "config_schema": {
            "issuer_id": {"type": "string", "label": "Issuer ID"},
            "issuer_url": {"type": "url", "label": "Issuer URL"},
            "api_key": {"type": "password", "label": "API Key"},
        },
        "description": "Issue competency badges. Optional Open Badges or custom issuer.",
    },
    "lms": {
        "label": "LMS (LTI 1.3)",
        "provider": "lms",
        "category": "LMS",
        "service_type": "LTI",
        "config_schema": {
            "client_id": {"type": "string", "label": "Client ID"},
            "deployment_id": {"type": "string", "label": "Deployment ID"},
            "keyset_url": {"type": "url", "label": "JWKS URL"},
            "login_url": {"type": "url", "label": "Login URL"},
        },
        "description": "Moodle, Canvas, Google Classroom, etc. LTI 1.3 deep link and grade passback.",
    },
    "email": {
        "label": "Email (SMTP)",
        "provider": "email",
        "category": "MESSAGING",
        "service_type": "WEBHOOK",
        "config_schema": {
            "host": {"type": "string", "label": "SMTP Host"},
            "port": {"type": "number", "label": "Port", "default": 587},
            "user": {"type": "string", "label": "Username"},
            "password": {"type": "password", "label": "Password"},
            "use_tls": {"type": "boolean", "label": "Use TLS", "default": True},
        },
        "description": "Transactional email. Override default site email.",
    },
    "sms": {
        "label": "SMS",
        "provider": "sms",
        "category": "MESSAGING",
        "service_type": "WEBHOOK",
        "daily_cap": 500,
        "cooldown_seconds": 2,
        "fallback_channel": "email",
        "config_schema": {
            "provider": {"type": "string", "label": "Provider", "choices": ["twilio", "nexmo", "other"]},
            "account_sid": {"type": "string", "label": "Account SID (Twilio)"},
            "auth_token": {"type": "password", "label": "Auth Token"},
            "from_number": {"type": "string", "label": "From Number"},
        },
        "description": "SMS for reminders and alerts.",
    },
}


def get_catalog_entry(service_key: str) -> dict[str, Any] | None:
    """Return catalog entry for service_key (e.g. whatsapp, push, stripe)."""
    return INTEGRATION_CATALOG.get((service_key or "").strip().lower())


def list_catalog_keys() -> list[str]:
    """All known service keys for API Center dropdowns."""
    return list(INTEGRATION_CATALOG.keys())


def get_guardrail_config(service_key: str) -> dict[str, Any]:
    """Return daily_cap, cooldown_seconds, fallback_channel for a service (defaults if missing)."""
    entry = get_catalog_entry(service_key)
    if not entry:
        return {"daily_cap": None, "cooldown_seconds": 0, "fallback_channel": None}
    return {
        "daily_cap": entry.get("daily_cap"),
        "cooldown_seconds": int(entry.get("cooldown_seconds") or 0),
        "fallback_channel": entry.get("fallback_channel"),
    }


def check_integration_guardrail(
    service_key: str,
    school_id: int | None,
    *,
    usage_getter: Callable[[int | None, str], tuple[int, float]] | None = None,
) -> dict[str, Any]:
    """
    Check if a call to this integration is within cost guardrails.
    usage_getter(school_id, service_key) should return (today_count, last_call_ts) or (0, 0).
    Returns dict: allowed (bool), fallback_channel (str|None), reason (str).
    """
    config = get_guardrail_config(service_key)
    daily_cap = config.get("daily_cap")
    cooldown = config.get("cooldown_seconds") or 0
    fallback = config.get("fallback_channel")

    if not school_id:
        return {"allowed": True, "fallback_channel": None, "reason": "no_school"}

    today_count, last_ts = (0, 0)
    if usage_getter:
        try:
            today_count, last_ts = usage_getter(school_id, service_key)
        except (AttributeError, DatabaseError, RuntimeError, TypeError, ValueError):
            pass

    if daily_cap is not None and today_count >= daily_cap:
        return {
            "allowed": False,
            "fallback_channel": fallback,
            "reason": "daily_cap_exceeded",
        }

    import time
    if cooldown and last_ts and (time.time() - last_ts) < cooldown:
        return {
            "allowed": False,
            "fallback_channel": fallback,
            "reason": "cooldown",
        }

    return {"allowed": True, "fallback_channel": None, "reason": "ok"}
