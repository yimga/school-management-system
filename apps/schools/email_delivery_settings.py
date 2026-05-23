"""School.settings[\"email_delivery\"] bridge — tenant BYO-SMTP (SODP batch 1407)."""

from __future__ import annotations

from typing import Any


def get_email_delivery_payload(school) -> dict[str, Any]:
    """Normalized tenant email delivery settings."""
    raw: dict[str, Any] = {}
    if school is not None:
        settings_json = getattr(school, "settings", None) or {}
        if isinstance(settings_json, dict):
            raw = settings_json.get("email_delivery") or {}
    return {
        "enabled": bool(raw.get("enabled")),
        "host": (raw.get("host") or "").strip()[:255],
        "port": int(raw.get("port") or 587),
        "use_tls": bool(raw.get("use_tls", True)),
        "host_user": (raw.get("host_user") or "").strip()[:255],
        "has_password": bool(raw.get("host_password_encrypted_b64")),
        "default_from_email": (raw.get("default_from_email") or "").strip()[:254],
        "default_from_name": (raw.get("default_from_name") or "").strip()[:100],
        "default_reply_to": (raw.get("default_reply_to") or "").strip()[:254],
        "connection_timeout_seconds": int(raw.get("connection_timeout_seconds") or 10),
    }


def set_email_delivery_payload(school, payload: dict[str, Any], *, password_encrypted_b64: str = "") -> None:
    """Persist email_delivery into School.settings (does not save)."""
    if not isinstance(school.settings, dict):
        school.settings = {}
    prior = {}
    if isinstance(school.settings.get("email_delivery"), dict):
        prior = dict(school.settings["email_delivery"])
    merged = {
        "enabled": bool(payload.get("enabled", prior.get("enabled"))),
        "host": (payload.get("host") or prior.get("host") or "").strip()[:255],
        "port": int(payload.get("port") or prior.get("port") or 587),
        "use_tls": bool(payload.get("use_tls", prior.get("use_tls", True))),
        "host_user": (payload.get("host_user") or prior.get("host_user") or "").strip()[:255],
        "default_from_email": (payload.get("default_from_email") or prior.get("default_from_email") or "").strip()[:254],
        "default_from_name": (payload.get("default_from_name") or prior.get("default_from_name") or "").strip()[:100],
        "default_reply_to": (payload.get("default_reply_to") or prior.get("default_reply_to") or "").strip()[:254],
        "connection_timeout_seconds": int(
            payload.get("connection_timeout_seconds")
            or prior.get("connection_timeout_seconds")
            or 10
        ),
    }
    pwd_b64 = password_encrypted_b64 or prior.get("host_password_encrypted_b64") or ""
    if pwd_b64:
        merged["host_password_encrypted_b64"] = pwd_b64
    elif "host_password_encrypted_b64" in prior:
        merged["host_password_encrypted_b64"] = prior["host_password_encrypted_b64"]
    school.settings["email_delivery"] = merged


def tenant_email_override_allowed(site_settings_row) -> bool:
    """Platform operator may disable tenant SMTP overrides."""
    flags = getattr(site_settings_row, "backend_feature_flags", None) or {}
    if isinstance(flags, dict) and flags.get("allow_tenant_email_delivery_override") is False:
        return False
    email_delivery = getattr(site_settings_row, "email_delivery", None) or {}
    if isinstance(email_delivery, dict) and email_delivery.get("allow_tenant_email_delivery_override") is False:
        return False
    return True


__all__ = [
    "get_email_delivery_payload",
    "set_email_delivery_payload",
    "tenant_email_override_allowed",
]
