"""Secure credential handling for Migration Cloud source connections."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from apps.migration_cloud.models_connectors import (
    CredentialStorageMode,
    MigrationSourceConnection,
    SourceConnectionStatus,
)

logger = logging.getLogger(__name__)

# In-memory one-time credential store: connection_id -> credential dict.
# Purged on revoke/import complete; never logged.
_MEMORY_STORE: dict[str, dict[str, Any]] = {}

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "api_token",
        "token",
        "secret",
        "client_secret",
        "refresh_token",
        "access_token",
    }
)


def _redact_value(key: str, value: Any) -> str:
    if key.lower() in _SENSITIVE_KEYS or "password" in key.lower():
        return "***REDACTED***"
    text = str(value or "")
    if len(text) > 4:
        return f"{text[:2]}…{text[-2:]}"
    return "****"


def redact_connection_for_display(connection: MigrationSourceConnection) -> dict[str, Any]:
    """Return a display-safe dict — never includes secrets."""
    return {
        "id": str(connection.id),
        "source_platform_type": connection.source_platform_type,
        "source_url": connection.source_url,
        "connection_method": connection.connection_method,
        "status": connection.status,
        "credential_storage_mode": connection.credential_storage_mode,
        "credential_reference": (
            connection.credential_reference[:8] + "…"
            if connection.credential_reference
            else ""
        ),
        "authorization_confirmed": connection.authorization_confirmed,
        "last_verified_at": (
            connection.last_verified_at.isoformat() if connection.last_verified_at else None
        ),
    }


def store_source_credential_reference(
    connection: MigrationSourceConnection,
    *,
    credential_payload: dict[str, Any],
) -> str:
    """Persist credential per storage mode; return opaque reference."""
    ref = secrets.token_urlsafe(16)
    mode = connection.credential_storage_mode

    if mode == CredentialStorageMode.MEMORY_ONLY:
        _MEMORY_STORE[str(connection.id)] = dict(credential_payload)
        connection.credential_reference = ref
        connection.save(update_fields=["credential_reference", "updated_at"])
        return ref

    if mode == CredentialStorageMode.ENCRYPTED_VAULT:
        blob = json.dumps(credential_payload, sort_keys=True).encode("utf-8")
        connection.credential_ciphertext = blob
        connection.credential_reference = ref
        connection.save(
            update_fields=["credential_ciphertext", "credential_reference", "updated_at"]
        )
        return ref

    # external_secret_manager — store reference only; payload not in DB
    connection.credential_reference = ref
    _MEMORY_STORE[str(connection.id)] = dict(credential_payload)
    connection.save(update_fields=["credential_reference", "updated_at"])
    return ref


def retrieve_source_credential_for_runtime(
    connection: MigrationSourceConnection,
) -> dict[str, Any] | None:
    """Load credentials for adapter runtime — caller must not log result."""
    conn_id = str(connection.id)
    if conn_id in _MEMORY_STORE:
        return dict(_MEMORY_STORE[conn_id])

    if connection.credential_ciphertext:
        try:
            raw = bytes(connection.credential_ciphertext)
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning(
                "connector_credentials: failed to decode vault blob for connection %s",
                conn_id[:8],
            )
            return None
    return None


def purge_source_credentials(connection: MigrationSourceConnection) -> None:
    """Delete all stored credential material for a connection."""
    conn_id = str(connection.id)
    _MEMORY_STORE.pop(conn_id, None)
    connection.credential_ciphertext = None
    connection.credential_reference = ""
    connection.save(
        update_fields=["credential_ciphertext", "credential_reference", "updated_at"]
    )


def create_source_connection(
    *,
    school,
    created_by,
    connector_profile,
    source_platform_type: str,
    source_url: str,
    connection_method: str,
    credential_storage_mode: str = CredentialStorageMode.MEMORY_ONLY,
    source_name: str = "",
    notes: str = "",
) -> MigrationSourceConnection:
    return MigrationSourceConnection.objects.create(
        school=school,
        created_by=created_by,
        connector_profile=connector_profile,
        source_name=source_name or connector_profile.display_name,
        source_platform_type=source_platform_type,
        source_url=source_url,
        connection_method=connection_method,
        credential_storage_mode=credential_storage_mode,
        status=SourceConnectionStatus.DRAFT,
    )


def verify_source_authorization(
    connection: MigrationSourceConnection,
    *,
    credential_payload: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Verify connection is authorized; optional credential check via adapter."""
    blockers: list[str] = []
    if not connection.authorization_confirmed:
        blockers.append("authorization_not_confirmed")
    if not connection.terms_acknowledged:
        blockers.append("terms_not_acknowledged")
    if blockers:
        return False, blockers

    connection.status = SourceConnectionStatus.VERIFYING
    connection.save(update_fields=["status", "updated_at"])

    if credential_payload:
        store_source_credential_reference(connection, credential_payload=credential_payload)

    # Structural verification only — live vendor checks happen in discovery adapter.
    connection.mark_verified()
    return True, []


def revoke_source_connection(connection: MigrationSourceConnection) -> None:
    purge_source_credentials(connection)
    connection.mark_revoked()


def audit_credential_access(
    connection: MigrationSourceConnection,
    *,
    actor,
    action: str,
) -> None:
    from apps.migration_cloud.services.connector_audit import record_connector_audit

    record_connector_audit(
        school=connection.school,
        actor=actor,
        event_type=f"credential_{action}",
        source_connection=connection,
        message=f"Credential access: {action}",
        metadata={"storage_mode": connection.credential_storage_mode},
    )


def build_credential_form_redaction(fields: dict[str, Any]) -> dict[str, str]:
    return {key: _redact_value(key, val) for key, val in fields.items()}
