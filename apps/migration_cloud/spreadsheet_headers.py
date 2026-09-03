"""Detect the real header row when a worksheet leads with title/banner rows.

African school exports often open with one or two merged title lines
(``GILEAD TECHNICAL HIGH SCHOOL … TELEPHONE DIRECTORY``) before the real
column headers. Treating row 0 as the header mis-maps every column and
quarantines the roster.
"""

from __future__ import annotations

from typing import Any, Iterable

_MAX_SCAN_ROWS = 25  # magic-number-allow: spreadsheet-header-scan-window


def _nonempty_cells(row: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for cell in row:
        if cell is None:
            continue
        text = str(cell).strip()
        if text:
            out.append(text)
    return out


def score_header_candidate(row: Iterable[Any]) -> float:
    """Higher score ⇒ more likely a column-header row."""
    cells = _nonempty_cells(row)
    count = len(cells)
    if count < 2:
        return -1.0
    total_len = sum(len(c) for c in cells)
    max_len = max(len(c) for c in cells)
    if count == 1 and max_len > 30:
        return -1.0
    if total_len > 0 and max_len / total_len > 0.75 and count <= 3:
        return -1.0
    avg = total_len / count
    if avg > 55:
        return 0.25
    score = float(min(count, 12))
    if avg <= 30:
        score += 2.0
    if avg <= 18:
        score += 1.0
    return score


def pick_header_row_index(rows: list[Any]) -> int:
    if not rows:
        return 0
    best_idx = 0
    best_score = -1.0
    for i in range(min(len(rows), _MAX_SCAN_ROWS)):
        score = score_header_candidate(rows[i])
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx if best_score >= 0 else 0


def split_header_and_data_rows(rows: list[Any]) -> tuple[list[Any], list[Any]]:
    if not rows:
        return [], []
    idx = pick_header_row_index(rows)
    header = list(rows[idx]) if rows[idx] is not None else []
    return header, rows[idx + 1 :]
