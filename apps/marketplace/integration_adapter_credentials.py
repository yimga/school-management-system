"""
Operator credential placeholders for marketplace integration adapters.

Activate seeds empty field templates in school.settings; operators fill values
via finance/messaging/integration setup surfaces (no secrets auto-generated).
"""

from __future__ import annotations

from typing import Any

CredentialField = dict[str, Any]

# adapter_key -> list of {key, label, required}
ADAPTER_CREDENTIAL_SCHEMA: dict[str, list[CredentialField]] = {
    "payments:paystack": [
        {"key": "secret_key", "label": "Paystack secret key", "required": True},
        {"key": "public_key", "label": "Paystack public key", "required": True},
        {"key": "webhook_secret", "label": "Webhook HMAC secret", "required": False},
    ],
    "payments:flutterwave-momo": [
        {"key": "secret_key", "label": "Flutterwave secret key", "required": True},
        {"key": "public_key", "label": "Flutterwave public key", "required": True},
    ],
    "payments:stripe-connect": [
        {"key": "connect_account_id", "label": "Stripe Connect account ID", "required": True},
        {"key": "webhook_secret", "label": "Stripe webhook signing secret", "required": False},
    ],
    "payments:razorpay": [
        {"key": "key_id", "label": "Razorpay key ID", "required": True},
        {"key": "key_secret", "label": "Razorpay key secret", "required": True},
    ],
    "messaging:sms-gateway": [
        {"key": "account_sid", "label": "SMS provider account SID / ID", "required": True},
        {"key": "auth_token", "label": "SMS provider auth token", "required": True},
        {"key": "from_number", "label": "Sender phone number", "required": True},
    ],
    "sis:oneroster-v1p2": [
        {"key": "client_id", "label": "OneRoster OAuth client ID", "required": True},
        {"key": "client_secret", "label": "OneRoster OAuth client secret", "required": True},
        {"key": "base_url", "label": "SIS OneRoster base URL", "required": True},
    ],
    "platform:sso-identity": [
        {"key": "idp_metadata_url", "label": "IdP metadata URL", "required": False},
        {"key": "entity_id", "label": "Service provider entity ID", "required": False},
    ],
    "platform:migration-connector-pack": [
        {"key": "source_system", "label": "Source SIS/LMS identifier", "required": True},
        {"key": "operator_contact", "label": "Migration operator contact email", "required": False},
    ],
    "platform:api-webhooks-pack": [
        {"key": "signing_secret", "label": "Outbound webhook signing secret", "required": True},
    ],
}

_PREFIX_SCHEMA: list[tuple[str, list[CredentialField]]] = [
    (
        "payments:",
        [
            {"key": "api_key", "label": "Payment provider API key", "required": True},
            {"key": "webhook_secret", "label": "Webhook signing secret", "required": False},
        ],
    ),
    (
        "messaging:",
        [
            {"key": "api_key", "label": "Messaging provider API key", "required": True},
            {"key": "sender_id", "label": "Sender ID / from address", "required": True},
        ],
    ),
    (
        "sis:",
        [
            {"key": "api_key", "label": "SIS API key or token", "required": True},
            {"key": "base_url", "label": "SIS API base URL", "required": True},
        ],
    ),
    (
        "lms:",
        [
            {"key": "client_id", "label": "LMS OAuth client ID", "required": True},
            {"key": "client_secret", "label": "LMS OAuth client secret", "required": True},
            {"key": "base_url", "label": "LMS base URL", "required": True},
        ],
    ),
    (
        "identity:",
        [
            {"key": "client_id", "label": "Identity provider client ID", "required": True},
            {"key": "client_secret", "label": "Identity provider client secret", "required": True},
            {"key": "tenant_id", "label": "Directory tenant ID", "required": False},
        ],
    ),
    (
        "platform:",
        [
            {"key": "api_key", "label": "Platform integration API key", "required": False},
        ],
    ),
]

_SETTINGS_BUCKET = "marketplace_integration_credentials"


def credential_schema_for_adapter(adapter_key: str) -> list[CredentialField]:
    key = (adapter_key or "").strip()
    if not key:
        return []
    if key in ADAPTER_CREDENTIAL_SCHEMA:
        return list(ADAPTER_CREDENTIAL_SCHEMA[key])
    for prefix, fields in _PREFIX_SCHEMA:
        if key.startswith(prefix):
            return list(fields)
    return []


def build_credential_placeholder(
    adapter_key: str,
    *,
    app_slug: str,
) -> dict[str, Any] | None:
    schema = credential_schema_for_adapter(adapter_key)
    if not schema:
        return None
    fields: dict[str, Any] = {}
    for spec in schema:
        field_key = str(spec.get("key") or "").strip()
        if not field_key:
            continue
        fields[field_key] = {
            "label": str(spec.get("label") or field_key),
            "required": bool(spec.get("required")),
            "value": "",
        }
    return {
        "app_slug": app_slug,
        "adapter_key": adapter_key,
        "status": "pending_operator_setup",
        "fields": fields,
    }


def merge_credential_placeholders(
    settings: dict[str, Any],
    *,
    app_slug: str,
    adapter_keys: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Seed placeholders without overwriting operator-filled values."""
    bucket = settings.get(_SETTINGS_BUCKET)
    if not isinstance(bucket, dict):
        bucket = {}
    seeded: list[str] = []
    for adapter_key in adapter_keys:
        key = str(adapter_key or "").strip()
        if not key:
            continue
        existing = bucket.get(key)
        if isinstance(existing, dict) and any(
            (f or {}).get("value")
            for f in (existing.get("fields") or {}).values()
            if isinstance(f, dict)
        ):
            continue
        placeholder = build_credential_placeholder(key, app_slug=app_slug)
        if placeholder:
            bucket[key] = placeholder
            seeded.append(key)
    if seeded:
        settings[_SETTINGS_BUCKET] = bucket
    return settings, seeded


def clear_credential_placeholders(
    settings: dict[str, Any],
    *,
    app_slug: str,
    adapter_keys: list[str],
) -> dict[str, Any]:
    bucket = settings.get(_SETTINGS_BUCKET)
    if not isinstance(bucket, dict):
        return settings
    for adapter_key in adapter_keys:
        key = str(adapter_key or "").strip()
        entry = bucket.get(key)
        if isinstance(entry, dict) and entry.get("app_slug") == app_slug:
            has_values = any(
                (f or {}).get("value")
                for f in (entry.get("fields") or {}).values()
                if isinstance(f, dict)
            )
            if not has_values or entry.get("status") == "pending_operator_setup":
                bucket.pop(key, None)
    settings[_SETTINGS_BUCKET] = bucket
    return settings


def mask_secret_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 4:
        return "••••"
    return f"{raw[:2]}••••{raw[-2:]}"


def credential_entry_configured(entry: dict[str, Any]) -> bool:
    fields = entry.get("fields") or {}
    if not isinstance(fields, dict):
        return False
    for spec in fields.values():
        if not isinstance(spec, dict):
            continue
        if spec.get("required") and not str(spec.get("value") or "").strip():
            return False
    return any(str((spec or {}).get("value") or "").strip() for spec in fields.values())


def list_credential_entries(settings: dict[str, Any]) -> list[dict[str, Any]]:
    bucket = settings.get(_SETTINGS_BUCKET)
    if not isinstance(bucket, dict):
        return []
    rows: list[dict[str, Any]] = []
    for adapter_key in sorted(bucket.keys()):
        entry = bucket.get(adapter_key)
        if not isinstance(entry, dict):
            continue
        status = entry.get("status") or "pending_operator_setup"
        if credential_entry_configured(entry):
            status = "configured"
        rows.append(
            {
                "adapter_key": adapter_key,
                "app_slug": entry.get("app_slug") or "",
                "status": status,
                "fields": entry.get("fields") or {},
            }
        )
    return rows


def apply_credential_field_values(
    settings: dict[str, Any],
    *,
    adapter_key: str,
    field_values: dict[str, str],
) -> tuple[dict[str, Any], bool]:
    """Merge operator-submitted values; never log secrets."""
    key = (adapter_key or "").strip()
    if not key:
        return settings, False
    bucket = settings.get(_SETTINGS_BUCKET)
    if not isinstance(bucket, dict):
        bucket = {}
    entry = bucket.get(key)
    if not isinstance(entry, dict):
        schema = credential_schema_for_adapter(key)
        if not schema:
            return settings, False
        entry = build_credential_placeholder(key, app_slug="")
    fields = entry.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    changed = False
    for field_key, raw_value in (field_values or {}).items():
        fk = str(field_key or "").strip()
        if not fk or fk not in fields:
            continue
        spec = fields.get(fk)
        if not isinstance(spec, dict):
            spec = {"label": fk, "required": False, "value": ""}
        new_val = str(raw_value or "").strip()
        if spec.get("value") != new_val:
            spec["value"] = new_val
            fields[fk] = spec
            changed = True
    entry["fields"] = fields
    entry["status"] = (
        "configured" if credential_entry_configured(entry) else "pending_operator_setup"
    )
    bucket[key] = entry
    settings[_SETTINGS_BUCKET] = bucket
    return settings, changed


def adapter_schema_validation_errors() -> list[str]:
    """Every integration adapter in catalog seed has a credential schema."""
    from apps.marketplace.capability_contract import infer_capability_bindings
    from apps.marketplace.management.commands.seed_marketplace_apps import (
        FIRST_PARTY_APPS,
    )

    errors: list[str] = []
    seen: set[str] = set()
    for app_def in FIRST_PARTY_APPS:
        slug = app_def.get("slug") or ""
        bindings = infer_capability_bindings(slug, app_def.get("manifest") or {})
        for binding in bindings:
            if binding.get("kind") != "integration_adapter":
                continue
            adapter = str(binding.get("target") or "").strip()
            if not adapter or adapter in seen:
                continue
            seen.add(adapter)
            if not credential_schema_for_adapter(adapter):
                errors.append(f"{adapter}: missing credential schema (slug={slug})")
    return errors
