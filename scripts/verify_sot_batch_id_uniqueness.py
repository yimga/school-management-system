#!/usr/bin/env python3
"""
Verify SOT §11.4 forward queue batch IDs are unique.

Duplicate batch IDs weaken auditability. A duplicate is allowed only when every
non-primary duplicate row is explicitly marked as a superseded alias.

Usage:
    python scripts/verify_sot_batch_id_uniqueness.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOT_RELATIVE_PATH = Path("docs") / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"

ROW_RE = re.compile(
    r"^\*\*§11\.4 forward queue - batch (?P<batch_id>\d+)(?=[\s(:])(?P<rest>.*)$"
)
ALIAS_RE = re.compile(r"\bsuperseded\s+alias\b", re.IGNORECASE)


@dataclass(frozen=True)
class BatchRow:
    batch_id: str
    line_number: int
    text: str

    @property
    def is_superseded_alias(self) -> bool:
        return bool(ALIAS_RE.search(self.text))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_sot_rows(sot_path: Path) -> list[BatchRow]:
    rows: list[BatchRow] = []
    for line_number, line in enumerate(
        sot_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        match = ROW_RE.match(line)
        if not match:
            continue
        rows.append(
            BatchRow(
                batch_id=match.group("batch_id"),
                line_number=line_number,
                text=line,
            )
        )
    return rows


def duplicate_errors(rows: list[BatchRow]) -> list[str]:
    by_batch: dict[str, list[BatchRow]] = defaultdict(list)
    for row in rows:
        by_batch[row.batch_id].append(row)

    errors: list[str] = []
    for batch_id in sorted(by_batch, key=lambda value: int(value)):
        matches = by_batch[batch_id]
        if len(matches) <= 1:
            continue

        primary_rows = [row for row in matches if not row.is_superseded_alias]
        if len(primary_rows) == 1:
            continue

        locations = ", ".join(
            f"line {row.line_number}"
            + (" (superseded alias)" if row.is_superseded_alias else "")
            for row in matches
        )
        errors.append(
            f"batch {batch_id} appears {len(matches)} times without exactly one "
            f"canonical non-alias row: {locations}"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        root = _resolve_base(args.base)
        sot_path = root / SOT_RELATIVE_PATH
        if not sot_path.is_file():
            raise FileNotFoundError(f"Missing SOT: {sot_path}")
        rows = parse_sot_rows(sot_path)
        errors = duplicate_errors(rows)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"SOT batch uniqueness verifier failed: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("SOT batch uniqueness: FAIL")
        for error in errors:
            print(f"- {error}")
        print(
            "Mark historical duplicate rows with 'superseded alias' or renumber them "
            "without changing factual claims."
        )
        return 1

    print(f"SOT batch uniqueness: OK ({len(rows)} §11.4 rows checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
