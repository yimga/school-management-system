"""
Pass 8.B: read-only progress endpoint for the async Migration Wizard task.

`GET /api/v1/migration-jobs/<job_id>/` returns the current snapshot stored
under the cache key `migration_job:<job_id>`. The wizard UI polls this every
2-3 seconds while a job is running to drive a progress bar.
"""

from __future__ import annotations

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
