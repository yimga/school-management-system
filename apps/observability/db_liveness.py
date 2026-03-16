"""
§2.4 Raw SQL wrap: database liveness check in one place.
Used by monitoring.SystemHealthMonitor.check_database_health; keeps raw SQL out of monitoring module.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from django.db import connection
from django.db.utils import DatabaseError, InterfaceError, OperationalError, ProgrammingError

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

_DB_LIVENESS_ERRORS = (DatabaseError, OperationalError, ProgrammingError, InterfaceError)


def check_db_liveness() -> dict[str, Any]:
    """
    Run a minimal query to verify DB connectivity. Returns dict with status, response_time_ms, error (if any).
    """
    try:
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        duration_ms = (time.time() - start) * 1000
        return {
            "status": "healthy",
            "response_time_ms": round(duration_ms, 2),
            "connections": len(connection.queries) if hasattr(connection, "queries") else 0,
        }
    except _DB_LIVENESS_ERRORS as e:
        log_exception_with_context(
            "observability.db_liveness: check failed",
            school_id=None,
            extra={"error": str(e)},
        )
        logger.warning("db_liveness check failed: %s", e, exc_info=True)
        return {
            "status": "unhealthy",
            "response_time_ms": 0,
            "error": str(e)[:200],
        }
