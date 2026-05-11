"""
Pass 8.B: read-only progress endpoint for the async Migration Wizard task.
Pass 8.D: CSV error-report download for the migration job snapshot.

`GET /api/v1/migration-jobs/<job_id>/` returns the current snapshot stored
under the cache key `migration_job:<job_id>`. The wizard UI polls this every
2-3 seconds while a job is running to drive a progress bar.

`GET /api/v1/migration-jobs/<job_id>/errors.csv` streams the same snapshot's
errors list as a CSV (row, message) the operator can hand back to their
data team for cleanup before re-importing.
"""

from __future__ import annotations

import csv
import io
import re

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(
    tags=["Migration"],
    summary="Get progress snapshot for a queued migration job",
    description=(
        "Returns the live progress snapshot for a Migration Wizard job — status, "
        "row counts, created/updated/skipped, and the first 50 errors. Snapshot "
        "TTL is 24h. 404 once the entry expires."
    ),
    responses={200: dict, 404: dict},
)
class MigrationJobStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        try:
            from apps.accounts.migration_async import get_migration_job_status
        except ImportError:
            return Response({"detail": "migration_async unavailable"}, status=503)

        snapshot = get_migration_job_status(job_id)
        if snapshot is None:
            return Response({"detail": "job not found or expired"}, status=404)
        return Response(snapshot)


_ROW_PREFIX_RE = re.compile(r"^Row\s+(\d+)\b[\s:\-]*", re.IGNORECASE)


def _split_row_and_message(message: str) -> tuple[str, str]:
    """Pull a leading 'Row N:' prefix out of an error message, if present."""
    m = _ROW_PREFIX_RE.match(message)
    if not m:
        return "", message.strip()
    return m.group(1), message[m.end():].strip()


class MigrationJobErrorsCsvView(APIView):
    """Pass 8.D: download `errors` from the migration_job snapshot as CSV."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Migration"],
        summary="Download migration-job errors as CSV",
        responses={200: bytes, 404: dict, 503: dict},
    )
    def get(self, request, job_id: str):
        try:
            from apps.accounts.migration_async import get_migration_job_status
        except ImportError:
            return Response({"detail": "migration_async unavailable"}, status=503)

        snapshot = get_migration_job_status(job_id)
        if snapshot is None:
            return Response({"detail": "job not found or expired"}, status=404)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["row", "message"])
        for entry in snapshot.get("errors") or []:
            row_num, msg = _split_row_and_message(str(entry))
            writer.writerow([row_num, msg])

        body = buffer.getvalue().encode("utf-8")
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="migration-{job_id}-errors.csv"'
        )
        return response
