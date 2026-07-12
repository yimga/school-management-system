"""Explode a multi-worksheet XLSX into one TSV per sheet.

A school's SIS export almost always arrives as ONE workbook with several tabs
— Students, Staff, Classes, Grades. Every reader in the pipeline (profiler,
orchestrator) only ever reads ``sheetnames[0]``, so tabs 2+ were silently
dropped: a school uploaded four tabs and only the first landed. That is real,
invisible data loss.

This turns each non-empty worksheet into its own tabular artifact (a TSV) so
the workbook lands as its constituent record types, each independently
classified + landed — "we found Students, Staff and Grades in your workbook"
instead of "we imported Students and quietly lost the rest".

Everything degrades to an empty result when openpyxl is unavailable or the
file is unreadable, so the caller can fall back to handling the workbook as a
single artifact rather than failing.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _stringify(cell: Any) -> str:
    """Coerce a cell to the string shape the CSV/TSV readers expect.

    Integers stored as floats (``36.0``) render as ``"36"`` to match what the
    same value looks like in a CSV export.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell)


def _sheet_to_tsv(ws) -> str:
    """Serialise a worksheet to TSV, skipping fully-blank rows. ``""`` if empty.

    Uses ``csv.writer`` (tab delimiter) so cell values containing tabs, quotes
    or newlines are properly quoted and survive the downstream CSV reader.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")
    wrote_any = False
    for row in ws.iter_rows(values_only=True):
        cells = [_stringify(c) for c in row]
        if not any(c.strip() for c in cells):
            continue  # skip fully-blank row (common trailing padding)
        writer.writerow(cells)
        wrote_any = True
    return buf.getvalue() if wrote_any else ""


def count_nonempty_sheets(path) -> int:
    """Number of worksheets with at least one non-blank row. 0 if unreadable."""
    return len(explode_workbook(path))


def explode_workbook(path) -> list[tuple[str, bytes]]:
    """Return ``[(sheet_name, tsv_bytes), ...]`` for every non-empty sheet.

    Empty list when openpyxl is unavailable or the file is unreadable — the
    caller then falls back to treating the workbook as a single artifact.
    """
    try:
        from openpyxl import load_workbook  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return []
    try:
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[str, bytes]] = []
    try:
        for name in wb.sheetnames:
            try:
                ws = wb[name]
                tsv = _sheet_to_tsv(ws)
            except Exception:  # noqa: BLE001 — one bad sheet must not sink the rest
                logger.warning("xlsx_explode: could not read sheet %r", name)
                continue
            if tsv.strip():
                out.append((name, tsv.encode("utf-8")))
    finally:
        try:
            wb.close()
        except Exception:  # noqa: BLE001
            pass
    return out
