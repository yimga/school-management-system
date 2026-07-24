"""SQL-dump intake — splits a mysqldump / pg_dump / SQLite file into per-table artifacts.

A SQL dump is logically a *multi-table archive*. This adapter treats it
that way: parses ``COPY ... FROM stdin`` blocks (Postgres) or ``INSERT
INTO ... VALUES`` blocks (MySQL / generic) and emits one
``ArtifactPayload`` per table. The orchestrator profiles + classifies +
maps + lands each as if it were a separate CSV.

For SQLite files, opens the DB and exports each table as in-memory CSV.

Schema:
    * ``mysqldump`` — handled by line-streaming ``INSERT INTO `<t>` VALUES``
      parsing. Verbose but no external dep.
    * ``pg_dump`` — handled by ``COPY <t> FROM stdin`` block parsing.
    * ``.db`` / ``.sqlite`` / ``.sqlite3`` — opened via stdlib ``sqlite3``.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from apps.migration_cloud.models import IntakeMethod

from .base import (
    ArtifactPayload,
    IntakeAdapter,
    IntakeContext,
    IntakeError,
    register_adapter,
)

_MYSQL_INSERT_RE = re.compile(
    r"^INSERT INTO `(?P<table>[^`]+)` (?:\([^)]+\)\s+)?VALUES\s*(?P<values>.+);$",
    re.IGNORECASE,
)
_PG_COPY_START = re.compile(
    r"^COPY (?P<table>\"?[\w\.]+\"?) \((?P<cols>[^)]+)\) FROM stdin;",
    re.IGNORECASE,
)


class SqlDumpIntakeAdapter(IntakeAdapter):
    """Splits a single dump file into per-table ``ArtifactPayload`` records."""

    def validate_handle(self, handle: Any, ctx: IntakeContext) -> None:
        path = _coerce(handle)
        if not path.exists() or not path.is_file():
            raise IntakeError(f"SQL dump not found at intake: {path}")
        suffix = path.suffix.lower()
        if suffix not in (".sql", ".dump", ".db", ".sqlite", ".sqlite3"):
            raise IntakeError(
                f"Unsupported SQL dump suffix {suffix!r}; expected .sql/.dump/.db/.sqlite."
            )

    def iter_artifacts(
        self, handle: Any, ctx: IntakeContext
    ) -> Iterator[ArtifactPayload]:
        path = _coerce(handle)
        suffix = path.suffix.lower()
        if suffix in (".db", ".sqlite", ".sqlite3"):
            yield from self._iter_sqlite(path)
            return

        # Sniff dialect on the first few hundred lines.
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = "".join(fh.readline() for _ in range(200))
        dialect = "postgres" if "COPY " in head and "FROM stdin" in head else "mysql"

        if dialect == "postgres":
            yield from self._iter_pg_dump(path)
        else:
            yield from self._iter_mysql_dump(path)

    # --- Postgres pg_dump --------------------------------------------------

    def _iter_pg_dump(self, path: Path) -> Iterator[ArtifactPayload]:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            in_copy = False
            current_table = ""
            current_cols: list[str] = []
            current_rows: list[list[str]] = []

            for line in fh:
                if not in_copy:
                    m = _PG_COPY_START.match(line.strip())
                    if m:
                        in_copy = True
                        current_table = m.group("table").strip('"')
                        current_cols = [c.strip().strip('"') for c in m.group("cols").split(",")]
                        current_rows = []
                    continue
                if line.strip() == "\\.":
                    payload = _materialize_csv_payload(
                        table=current_table, columns=current_cols, rows=current_rows
                    )
                    if payload is not None:
                        yield payload
                    in_copy = False
                    current_table = ""
                    current_cols = []
                    current_rows = []
                    continue
                values = line.rstrip("\n").split("\t")
                current_rows.append([_decode_pg_copy_field(v) for v in values])

    # --- MySQL mysqldump ---------------------------------------------------

    def _iter_mysql_dump(self, path: Path) -> Iterator[ArtifactPayload]:
        table_to_rows: dict[str, list[list[str]]] = {}
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = _MYSQL_INSERT_RE.match(line.strip())
                if not m:
                    continue
                table = m.group("table")
                values_blob = m.group("values")
                rows = _parse_mysql_value_tuples(values_blob)
                table_to_rows.setdefault(table, []).extend(rows)

        for table, rows in table_to_rows.items():
            if not rows:
                continue
            max_cols = max(len(r) for r in rows)
            columns = [f"col_{i}" for i in range(max_cols)]
            payload = _materialize_csv_payload(table=table, columns=columns, rows=rows)
            if payload is not None:
                yield payload

    # --- SQLite ------------------------------------------------------------

    def _iter_sqlite(self, path: Path) -> Iterator[ArtifactPayload]:
        conn = sqlite3.connect(str(path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            for table in tables:
                if table.startswith("sqlite_"):
                    continue
                col_cur = conn.cursor()
                col_cur.execute(f"PRAGMA table_info({_quote_ident(table)})")
                columns = [r[1] for r in col_cur.fetchall()]

                row_cur = conn.cursor()
                row_cur.execute(f"SELECT * FROM {_quote_ident(table)}")
                rows = [["" if v is None else str(v) for v in row] for row in row_cur.fetchall()]
                payload = _materialize_csv_payload(table=table, columns=columns, rows=rows)
                if payload is not None:
                    yield payload
        finally:
            conn.close()


# --- Shared helpers -----------------------------------------------------

def _coerce(handle: Any) -> Path:
    if isinstance(handle, (str, Path)):
        return Path(handle)
    raise IntakeError(f"SqlDumpIntakeAdapter expects a path; got {type(handle).__name__}")


# Postgres COPY (text format) backslash escapes. ``\N`` is handled separately as
# the whole-field NULL sentinel; the rest are single-character unescapes.
_PG_COPY_ESCAPES = {
    "t": "\t",
    "n": "\n",
    "r": "\r",
    "\\": "\\",
    "b": "\b",
    "f": "\f",
    "v": "\v",
}


def _decode_pg_copy_field(field: str) -> str:
    r"""Decode one Postgres COPY text-format field value.

    A bare ``\N`` is the NULL sentinel and decodes to empty string; embedded
    escapes ``\t \n \r \\`` (plus the rarer ``\b \f \v``) unescape to the literal
    character. Without this a NULL lands as the literal string ``"\N"`` and an
    embedded tab / newline stays a visible backslash-escape in the value.
    """
    if field == "\\N":
        return ""
    if "\\" not in field:
        return field
    out: list[str] = []
    i = 0
    n = len(field)
    while i < n:
        ch = field[i]
        if ch == "\\" and i + 1 < n:
            nxt = field[i + 1]
            # Unknown escape: Postgres drops the backslash and keeps the char.
            out.append(_PG_COPY_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _materialize_csv_payload(
    *, table: str, columns: list[str], rows: list[list[str]]
) -> ArtifactPayload | None:
    """Write the table's rows as a CSV temp file, return an ``ArtifactPayload``."""
    if not rows:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for r in rows:
        # Pad short rows so CSV is rectangular.
        padded = r + [""] * (len(columns) - len(r))
        writer.writerow(padded[: len(columns)])
    body = buf.getvalue().encode("utf-8")

    fd, tmp_name = tempfile.mkstemp(prefix="mc_sql_", suffix=f"_{_safe_filename(table)}.csv")
    with open(fd, "wb") as fh:
        fh.write(body)
    tmp = Path(tmp_name)
    digest = sha256(body).hexdigest()

    def opener(p=tmp):
        return p.open("rb")

    return ArtifactPayload(
        path_within_bundle=f"{_safe_filename(table)}.csv",
        filename=f"{_safe_filename(table)}.csv",
        byte_size=len(body),
        sha256=digest,
        mime_type="text/csv",
        encoding="utf-8",
        content_opener=opener,
    )


def _parse_mysql_value_tuples(values_blob: str) -> list[list[str]]:
    r"""Parse ``(v1, v2, ...), (v1, v2, ...)`` into a list of value lists.

    An *unquoted* ``NULL`` or ``\N`` token normalises to empty string (SQL
    NULL), while a *quoted* ``'NULL'`` keeps the literal text — so a genuinely
    null column doesn't land as the string ``"NULL"``.
    """
    rows: list[list[str]] = []
    depth = 0
    in_string = False
    escape = False
    was_quoted = False
    current: list[str] = []
    cur_val: list[str] = []

    def _finish_value() -> None:
        nonlocal cur_val, was_quoted
        raw = "".join(cur_val).strip()
        if not was_quoted and (raw.upper() == "NULL" or raw == "\\N"):
            value = ""
        else:
            value = raw.strip("'")
        current.append(value)
        cur_val = []
        was_quoted = False

    for ch in values_blob:
        if escape:
            # Inside a quoted string the escaped char is taken literally (prior
            # behaviour). OUTSIDE a string the only escape mysqldump emits is the
            # bare \N NULL sentinel — preserve the backslash so _finish_value can
            # recognise it.
            if in_string:
                cur_val.append(ch)
            else:
                cur_val.append("\\")
                cur_val.append(ch)
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == "'":
            if not in_string:
                was_quoted = True
            in_string = not in_string
            continue
        if in_string:
            cur_val.append(ch)
            continue
        if ch == "(":
            depth += 1
            current = []
            cur_val = []
            was_quoted = False
            continue
        if ch == "," and depth == 1:
            _finish_value()
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                _finish_value()
                rows.append(current)
                current = []
                cur_val = []
                was_quoted = False
            continue
        # Any other char outside a quoted string is part of an UNQUOTED value
        # (a number, NULL, TRUE/FALSE). Capture it — the prior parser dropped
        # every unquoted token to "", silently losing numeric ids/ages. Leading
        # inter-token whitespace is removed by _finish_value's strip().
        cur_val.append(ch)
    return rows


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "table"


# Re-register over the Phase U1 stub.
register_adapter(IntakeMethod.SQL_DUMP, SqlDumpIntakeAdapter())
