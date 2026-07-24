"""Connector workflow audit — school-scoped + platform hash-chain mirror."""

from __future__ import annotations

import logging
from typing import Any

from apps.migration_cloud.models_connectors import MigrationAuditEvent

logger = logging.getLogger(__name__)

_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "password",
        "passwd",
        "api_token",
        "token",
        "secret",
        "client_secret",
        "refresh_token",
        "access_token",
        "credential",
        "credentials",
    }
)


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in _FORBIDDEN_METADATA_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize_metadata(value)
        else:
            clean[key] = value
    return clean


def record_connector_audit(
    *,
    school,
    actor,
    event_type: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    source_connection=None,
    discovery_run=None,
    staging_batch=None,
    import_run=None,
) -> MigrationAuditEvent:
    """Write school-scoped audit row and mirror to MigrationCloudAuditEvent."""
    safe_meta = _sanitize_metadata(metadata)
    event = MigrationAuditEvent.objects.create(
        school=school,
        actor=actor,
        event_type=event_type,
        source_connection=source_connection,
        discovery_run=discovery_run,
        staging_batch=staging_batch,
        import_run=import_run,
        message=message,
        metadata=safe_meta,
    )
    _mirror_platform_audit(
        school=school,
        actor=actor,
        event_type=event_type,
        payload_summary={
            "connector_event": event_type,
            "connection_id": str(getattr(source_connection, "id", ""))[:8] or None,
            "result": safe_meta.get("result", "ok"),
        },
    )
    return event


# The school-scoped MigrationAuditEvent.event_type is free-form + fine-grained
# (discovery_started / import_completed / credential_read / …). The tamper-
# evident MigrationCloudAuditEvent chain only accepts a registered
# MigrationCloudAuditEventType, so the mirror maps each fine-grained event to
# its coarse connector.* category. The exact fine-grained value is preserved in
# payload_summary["connector_event"], so no forensic detail is lost. A prefix
# table (not f"connector.{event_type}") means an unregistered/new connector
# event string can never again raise ValueError and get swallowed — the
# fallback category keeps every mirror write inside the hash chain.
_CONNECTOR_CATEGORY_BY_PREFIX = (
    ("credential_", "connector.credential_access"),
    ("discovery_", "connector.discovery"),
    ("import_", "connector.import"),
    ("mapping_", "connector.mapping"),
    ("rollback_", "connector.rollback"),
    ("connection_", "connector.connection"),
)
_CONNECTOR_CATEGORY_FALLBACK = "connector.event"


def _platform_audit_event_type(event_type: str) -> str:
    """Map a fine-grained connector event_type to its registered category."""
    for prefix, category in _CONNECTOR_CATEGORY_BY_PREFIX:
        if event_type.startswith(prefix):
            return category
    return _CONNECTOR_CATEGORY_FALLBACK


def _mirror_platform_audit(*, school, actor, event_type: str, payload_summary: dict) -> None:
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

        tenant_slug = getattr(school, "slug", None) or str(getattr(school, "pk", ""))
        MigrationCloudAuditEvent.objects.record(
            tenant_slug,
            _platform_audit_event_type(event_type),
            actor=getattr(actor, "email", None) or getattr(actor, "username", None),
            subject=str(getattr(school, "pk", "")),
            payload_summary=payload_summary,
        )
    except Exception:  # noqa: BLE001
        logger.warning("connector_audit: platform mirror failed for %s", event_type)
