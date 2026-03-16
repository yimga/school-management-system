"""
Record MetadataChangeLog entries from admin and metadata-changing APIs (metadata plan todo 6).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)


def record_metadata_changelog(
    object_type: str,
    object_id: str,
    scope: str = "tenant",
    old_value_summary: Optional[Dict[str, Any]] = None,
    new_value_summary: Optional[Dict[str, Any]] = None,
    tenants_affected: Optional[List[Any]] = None,
    actor_id: Optional[int] = None,
    reason: str = "",
) -> None:
    """Create a MetadataChangeLog entry. Safe to call from signals or admin save_model."""
    try:
        from apps.metadata.models import MetadataChangeLog
        MetadataChangeLog.objects.create(
            object_type=object_type,
            object_id=str(object_id),
            scope=scope,
            old_value_summary=old_value_summary or {},
            new_value_summary=new_value_summary or {},
            tenants_affected=tenants_affected or [],
            actor_id=actor_id,
            reason=reason[:255] if reason else "",
        )
    except (DatabaseError, IntegrityError, ValidationError) as e:
        log_exception_with_context(
            "metadata.changelog: record_metadata_changelog failed",
            school_id=None,
            extra={"object_type": object_type, "object_id": object_id, "error": str(e)},
        )
        logger.warning("record_metadata_changelog failed (object_type=%s, object_id=%s): %s", object_type, object_id, e)
