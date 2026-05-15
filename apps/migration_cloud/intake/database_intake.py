"""Live-database intake stub — full implementation lands in Phase U7.

Connects to a customer database (Postgres / MySQL / SQL Server / Oracle /
SQLite) over a credentialed DSN, enumerates tables, and emits one
``MigrationArtifact`` per table. Until U7, this stub keeps the registry
complete so the wizard's source-shape picker works end-to-end.
"""

from __future__ import annotations

from typing import Any, Iterator

from apps.migration_cloud.models import IntakeMethod

from .base import ArtifactPayload, IntakeAdapter, IntakeContext, IntakeError, register_adapter


class DatabaseIntakeAdapter(IntakeAdapter):
    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        raise IntakeError(
            "Live-database intake lands in Phase U7. Export tables as CSV / "
            "Parquet and upload through FILE_UPLOAD or ARCHIVE for now."
        )


register_adapter(IntakeMethod.DATABASE, DatabaseIntakeAdapter())
