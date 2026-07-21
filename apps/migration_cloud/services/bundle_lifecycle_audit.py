"""Best-effort MigrationCloudAuditEvent emits for bundle advance / apply.

Never raises into the pipeline or orchestrator — audit failure must not
block an import. Payload keys stay PII-free (no slug/email/token).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _tenant_slug_for_bundle(bundle: Any) -> str:
    school = getattr(bundle, "school", None)
    if school is not None:
        return (
            getattr(school, "slug", None)
            or getattr(school, "subdomain", None)
            or ""
        )
    return ""


def safe_bundle_audit(
    bundle: Any,
    event_type: str,
    *,
    payload_summary: dict[str, Any] | None = None,
) -> None:
    """Append one hash-chain audit row; swallow all failures."""
    try:
        from apps.migration_cloud.models_audit import MigrationCloudAuditEvent

        MigrationCloudAuditEvent.objects.record(
            _tenant_slug_for_bundle(bundle),
            event_type,
            subject=str(getattr(bundle, "pk", "")),
            payload_summary=payload_summary or {},
        )
    except Exception:  # noqa: BLE001 — audit must never break flow
        logger.warning(
            "migration_cloud.bundle_audit: emit failed event_type=%s bundle_id=%s",
            event_type,
            getattr(bundle, "pk", None),
            exc_info=True,
        )
