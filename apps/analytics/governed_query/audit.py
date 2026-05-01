"""Structured audit trail for governed exports (logging hook; no PII in message)."""

from __future__ import annotations

import logging

logger = logging.getLogger("rmc.governed_query.export")


def log_governed_export_event(
    *,
    user_id: int | None,
    school_id: str | None,
    dataset_id: str,
    row_count: int,
    export_format: str,
    aggregate: bool,
) -> None:
    logger.info(
        "governed_export",
        extra={
            "user_id": user_id,
            "school_id": school_id,
            "dataset_id": dataset_id,
            "row_count": row_count,
            "format": export_format,
            "aggregate": aggregate,
        },
    )
