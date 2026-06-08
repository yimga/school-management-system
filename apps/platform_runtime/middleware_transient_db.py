"""Return 503 (not 500) during transient Postgres outages."""

from __future__ import annotations

import logging

from django.utils.deprecation import MiddlewareMixin

from apps.platform_runtime.transient_db import (
    build_transient_db_unavailable_response,
    is_transient_database_error,
    reset_broken_database_state,
)

logger = logging.getLogger(__name__)


class TransientDatabaseUnavailableMiddleware(MiddlewareMixin):
    """Map short-lived Postgres failures to a retryable 503 across operator and marketing surfaces."""

    def process_exception(self, request, exception):
        if not is_transient_database_error(exception):
            return None

        reset_broken_database_state()
        path = getattr(request, "path", "") or ""
        logger.warning(
            "transient_db_unavailable path=%s error=%s",
            path,
            str(exception)[:200],
        )
        return build_transient_db_unavailable_response(
            request,
            source="transient_db_middleware",
        )
