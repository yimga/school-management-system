#!/usr/bin/env python3
"""
Phase-1 discovery: unpaginated {% for %} loops, risky overflow-hidden, rigid widths.

Writes docs/generated/template_scroll_compression_audit.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOTS = (
    ROOT / "templates",
    ROOT / "apps",
)
OUT = ROOT / "docs" / "generated" / "template_scroll_compression_audit.json"

FOR_LOOP = re.compile(r"\{%\s*for\s+\w+\s+in\s+(\w+)", re.I)
PAGINATE_MARKERS = (
    "page_obj",
    "paginator",
    "pagination",
    "is_paginated",
    "|slice:",
    "data-rmc-scroll-policy",
)
OVERFLOW_RISKY = re.compile(
    r"overflow(?:-x|-y)?\s*:\s*hidden|overflow-hidden|overflow-x-hidden",
    re.I,
)
RIGID_WIDTH = re.compile(
    r"(?:width|max-width|min-width)\s*:\s*(?:\d{3,}px|[\d.]+rem)|w-\[(?:1[2-9]\d{2}|[2-9]\d{3})px\]",
    re.I,
)


def _iter_html_files() -> list[Path]:
    files: list[Path] = []
    for base in TEMPLATE_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.html"):
            rel = path.relative_to(ROOT).as_posix()
            if "/migrations/" in rel or "/node_modules/" in rel:
                continue
            files.append(path)
    return sorted(set(files))


def audit_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    loops: list[dict] = []
    for m in FOR_LOOP.finditer(text):
        var = m.group(1)
        if var in {"block", "blocks", "choices", "fields", "messages"}:
            continue
        start = max(0, m.start() - 400)
        window = text[start : m.start() + 200]
        if any(marker in window for marker in PAGINATE_MARKERS):
            continue
        line = text[: m.start()].count("\n") + 1
        loops.append({"line": line, "iterable": var})
    overflow_hits = [
        {"line": text[: m.start()].count("\n") + 1, "match": m.group(0)[:60]}
        for m in OVERFLOW_RISKY.finditer(text)
        if "sticky-overflow-allow" not in text[max(0, m.start() - 120) : m.end() + 80]
    ]
    width_hits = [
        {"line": text[: m.start()].count("\n") + 1, "match": m.group(0)[:60]}
        for m in RIGID_WIDTH.finditer(text)
    ]
    return {
        "path": rel,
        "unpaginated_for_loops": loops,
        "overflow_hidden": overflow_hits,
        "rigid_width": width_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows: list[dict] = []
    for path in _iter_html_files():
        if not path.is_file():
            continue
        rows.append(audit_file(path))
    hot_loops = [r for r in rows if r["unpaginated_for_loops"]]
    hot_overflow = [r for r in rows if r["overflow_hidden"]]
    hot_width = [r for r in rows if r["rigid_width"]]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_scanned": len(rows),
        "unpaginated_for_loop_files": len(hot_loops),
        "overflow_hidden_files": len(hot_overflow),
        "rigid_width_files": len(hot_width),
        "priority_unpaginated": sorted(
            hot_loops,
            key=lambda r: len(r["unpaginated_for_loops"]),
            reverse=True,
        )[:40],
        "priority_overflow": sorted(
            hot_overflow,
            key=lambda r: len(r["overflow_hidden"]),
            reverse=True,
        )[:30],
        "priority_rigid_width": sorted(
            hot_width,
            key=lambda r: len(r["rigid_width"]),
            reverse=True,
        )[:20],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"template_scroll_compression_audit: "
            f"{payload['unpaginated_for_loop_files']} unpaginated files, "
            f"{payload['overflow_hidden_files']} overflow-hidden files, "
            f"{payload['rigid_width_files']} rigid-width files"
        )
        print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
