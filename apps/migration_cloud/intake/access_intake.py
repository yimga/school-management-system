"""Microsoft Access intake — exports every table in a .mdb / .accdb to CSV.

12-year-old registrar databases are still everywhere. This adapter reads
every user table from an Access file and emits one ``ArtifactPayload`` per
table, each materialised as UTF-8 CSV in a temp file. The profiler +
classifier handle them like any other tabular artifact.

Resolution order (first available wins):
    1. ``pyodbc`` with the Microsoft Access Database Engine driver
       (Windows; install ACE redistributable).
    2. ``mdb-tools`` via subprocess (``mdb-tables`` + ``mdb-export``) —
       cross-platform (Linux/macOS), no Python deps.
    3. ``access-parser`` pure-Python reader (limited but no native deps).

Graceful degradation: if none of the above are available, raises
``IntakeError`` with the install hint.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud import defaults as mc_defaults
from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)

logger = logging.getLogger(__name__)


class AccessDbIntakeAdapter(IntakeAdapter):
    """Adapter for the ``ACCESS_DB`` intake method."""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        path = _coerce_path(handle)
        if not path.exists() or not path.is_file():
            raise IntakeError(f"Access database not found at intake: {path}")
        if path.suffix.lower() not in (".mdb", ".accdb"):
            raise IntakeError(
                f"Expected .mdb / .accdb extension; got {path.suffix!r}."
            )

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        path = _coerce_path(handle)
        max_bytes = int(mc_defaults.get("migration_cloud.intake.max_artifact_bytes"))

        tables = _list_tables(path)
        if not tables:
            raise IntakeError(
                f"Could not enumerate tables in {path.name}. "
                "Install one of: 'pyodbc' (Windows + ACE driver), 'mdbtools' "
                "(Linux/macOS), or 'access-parser'."
            )
        for table in tables:
            csv_bytes = _export_table_as_csv(path, table)
            if not csv_bytes:
                continue
            if len(csv_bytes) > max_bytes:
                raise IntakeError(
                    f"Access table {table} exported size exceeds artifact cap."
                )
            fd, tmp_name = tempfile.mkstemp(prefix="mc_access_", suffix=f"_{_safe(table)}.csv")
            os.close(fd)
            tmp = Path(tmp_name)
            tmp.write_bytes(csv_bytes)
            digest = sha256(csv_bytes).hexdigest()

            def opener(p=tmp):
                return p.open("rb")

            yield ArtifactPayload(
                path_within_bundle=f"{path.stem}/{_safe(table)}.csv",
                filename=f"{_safe(table)}.csv",
                byte_size=len(csv_bytes),
                sha256=digest,
                mime_type="text/csv",
                content_opener=opener,
            )


# --- Engine resolution ----------------------------------------------------

def _list_tables(path: Path) -> list[str]:
    """Enumerate user tables via whichever engine is available."""
    tables = _list_via_mdbtools(path)
    if tables:
        return tables
    tables = _list_via_pyodbc(path)
    if tables:
        return tables
    tables = _list_via_access_parser(path)
    return tables


def _export_table_as_csv(path: Path, table: str) -> bytes:
    bytes_ = _export_via_mdbtools(path, table)
    if bytes_:
        return bytes_
    bytes_ = _export_via_pyodbc(path, table)
    if bytes_:
        return bytes_
    return _export_via_access_parser(path, table)


# --- mdb-tools (Linux/macOS, also works in WSL) ---------------------------

def _list_via_mdbtools(path: Path) -> list[str]:
    binary = _which("mdb-tables")
    if not binary:
        return []
    try:
        proc = subprocess.run(
            [binary, "-1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [t.strip() for t in proc.stdout.splitlines() if t.strip() and not t.startswith("MSys")]


def _export_via_mdbtools(path: Path, table: str) -> bytes:
    binary = _which("mdb-export")
    if not binary:
        return b""
    try:
        proc = subprocess.run(
            [binary, str(path), table],
            capture_output=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return b""
    return proc.stdout if proc.returncode == 0 else b""


# --- pyodbc (Windows + ACE driver) ----------------------------------------

def _odbc_conn_str(path: Path) -> str:
    if path.suffix.lower() == ".accdb":
        return (
            "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            f"DBQ={path};"
        )
    return (
        "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={path};"
    )


def _list_via_pyodbc(path: Path) -> list[str]:
    try:
        import pyodbc  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return []
    try:
        conn = pyodbc.connect(_odbc_conn_str(path), autocommit=True)
    except Exception:  # noqa: BLE001
        return []
    try:
        cursor = conn.cursor()
        tables: list[str] = []
        for row in cursor.tables(tableType="TABLE"):
            name = row.table_name
            if name and not name.startswith("MSys"):
                tables.append(name)
        return tables
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _export_via_pyodbc(path: Path, table: str) -> bytes:
    try:
        import pyodbc  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return b""
    try:
        conn = pyodbc.connect(_odbc_conn_str(path), autocommit=True)
    except Exception:  # noqa: BLE001
        return b""
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM [{table}]")
        cols = [c[0] for c in cursor.description]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        for row in cursor.fetchall():
            writer.writerow(["" if v is None else v for v in row])
        return buf.getvalue().encode("utf-8")
    except Exception:  # noqa: BLE001
        return b""
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# --- access-parser (pure-Python) ------------------------------------------

def _list_via_access_parser(path: Path) -> list[str]:
    try:
        from access_parser import AccessParser  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return []
    try:
        db = AccessParser(str(path))
        tables = list(db.catalog.keys())
    except Exception:  # noqa: BLE001
        return []
    return [t for t in tables if not str(t).startswith("MSys")]


def _export_via_access_parser(path: Path, table: str) -> bytes:
    try:
        from access_parser import AccessParser  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return b""
    try:
        db = AccessParser(str(path))
        rows = db.parse_table(table)
    except Exception:  # noqa: BLE001
        return b""
    if not rows:
        return b""
    cols = list(rows.keys())
    n_rows = max(len(v) for v in rows.values()) if rows else 0
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for i in range(n_rows):
        writer.writerow([rows[c][i] if i < len(rows[c]) else "" for c in cols])
    return buf.getvalue().encode("utf-8")


# --- Misc helpers ---------------------------------------------------------

def _coerce_path(handle: Any) -> Path:
    if isinstance(handle, (str, Path)):
        return Path(handle)
    if isinstance(handle, dict) and "path" in handle:
        return Path(handle["path"])
    raise IntakeError(
        f"AccessDbIntakeAdapter does not accept handle of type {type(handle).__name__}"
    )


def _which(name: str) -> str:
    from shutil import which
    return which(name) or ""


def _safe(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_\-.]+", "_", str(name)).strip("_") or "table"


try:
    register_adapter(IntakeMethod.ACCESS_DB, AccessDbIntakeAdapter())
except AttributeError:
    pass
