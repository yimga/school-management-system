"""SQLite database intake — exports tables to CSV artifacts (authorized DSN/file only)."""

from __future__ import annotations

import csv
import io
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
    sha256_of_stream,
)


class DatabaseIntakeAdapter(IntakeAdapter):
    """Connect to a SQLite file and emit one CSV artifact per table.

    Handle shapes:
        * ``str`` / ``Path`` to ``.sqlite3`` / ``.db`` file
        * ``dict`` with ``{"sqlite_path": "/path/to.db", "tables": ["students"]}``

    Postgres/MySQL live connections remain operator-export → FILE_UPLOAD.
    """

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        path = _resolve_sqlite_path(handle)
        if not path.is_file():
            raise IntakeError(f"SQLite database file not found: {path}")

    def iter_artifacts(self, handle: Any, ctx: IntakeContext) -> Iterator[ArtifactPayload]:
        path = _resolve_sqlite_path(handle)
        tables = _resolve_tables(handle, path)
        for table in tables:
            payload = _table_to_csv_bytes(path, table)
            digest, byte_size = sha256_of_stream(io.BytesIO(payload))
            filename = f"{table}.csv"

            def _opener(data: bytes = payload) -> io.BytesIO:
                return io.BytesIO(data)

            yield ArtifactPayload(
                path_within_bundle=filename,
                filename=filename,
                byte_size=byte_size,
                sha256=digest,
                mime_type="text/csv",
                content_opener=_opener,
                extra={"table": table, "engine": "sqlite"},
            )


def _resolve_sqlite_path(handle: Any) -> Path:
    if isinstance(handle, dict):
        raw = handle.get("sqlite_path") or handle.get("path")
        if not raw:
            raise IntakeError("database handle dict requires sqlite_path")
        return Path(raw)
    return Path(handle)


def _resolve_tables(handle: Any, path: Path) -> list[str]:
    if isinstance(handle, dict) and handle.get("tables"):
        return [str(t) for t in handle["tables"]]
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def _table_to_csv_bytes(path: Path, table: str) -> bytes:
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute(f'SELECT * FROM "{table}"')  # noqa: S608 — table from sqlite_master
        columns = [desc[0] for desc in cursor.description or []]
        rows = cursor.fetchall()
    finally:
        conn.close()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


register_adapter(IntakeMethod.DATABASE, DatabaseIntakeAdapter())
