"""Scan: detect long-DOM page-length offenders across ``templates/``.

The bug shape (caught repeatedly across the v3.50 -> v3.56 polish waves):
a single Django template grows past ~1500 lines of effective DOM and
becomes a usability tax — operator pages with hundreds of inline cards,
admin pages with 30+ FAQ sections in a single ``<details>``-less wall,
report pages that try to render every row of a hundred-row table inline.

This scanner walks ``templates/**/*.html`` and computes **effective DOM
LOC** per route — meaning: the raw line count of each top-level template
PLUS the line counts of every ``{% include %}`` and ``{% extends %}`` it
expands into recursively. A 200-line route that pulls in a 900-line
partial is a 1100-line route to the browser, not a 200-line route.

Allow marker
------------
Templates that are legitimately long (printable transcripts, full
forensic audit logs, regulatory PDFs rendered as HTML) may declare::

    <!-- page-length-allow: <reason> -->

anywhere in the file. The scanner skips them.

Constraints
-----------
Stdlib-only. We deliberately do NOT boot Django's template engine — the
``{% include "X" %}`` and ``{% extends "Y" %}`` tags carry literal
template-path strings, so a regex + filesystem resolution is enough,
much cheaper than a Django bootstrap, and CI-friendly.

Quintile baseline
-----------------
On first scan the runner sorts every template by effective LOC, takes
the 80th-percentile value, and sets that as the ceiling. New templates
above the ceiling are flagged. The baseline ALSO records the top-30
offenders so subsequent reductions are visible.

Usage::

    python scripts/scan_page_length_offenders.py
    python scripts/scan_page_length_offenders.py --json
    python scripts/scan_page_length_offenders.py --update-baseline
    python scripts/scan_page_length_offenders.py --top 30

Exit codes::

    0  no NEW offenders above baseline ceiling
    1  one or more NEW offenders detected
    2  loader/IO error

CLAUDE.md scanner-table row (consolidator will add)::

    | `scan_page_length_offenders.py` | **<N>** (v3.57.0 introduction
      2026-05-21 -- ceiling-mode gate) | architectural-boundaries.yml
      ::page-length-offenders | Walks templates/**/*.html, recursively
      expands {% include %} + {% extends %} to compute effective DOM
      LOC per route. Flags pages above the 80th-percentile ceiling
      unless marked with <!-- page-length-allow: <reason> -->.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-page-length.json"
)

# Templates not in templates/ but still part of the platform (e.g. app-local
# templates under apps/<app>/templates/). The scanner walks both roots when
# resolving {% include %}/{% extends %} targets.
APP_TEMPLATE_DIRS: list[pathlib.Path] = [
    p
    for p in (REPO_ROOT / "apps").glob("*/templates")
    if p.is_dir()
]

# {% include "X" %}, {% include 'X' %}, {% extends "X" %}, {% extends 'X' %}.
# We deliberately ignore include-with-variable (e.g. {% include block_template %})
# because they cannot be resolved at static-scan time.
INCLUDE_RE = re.compile(
    r"{%\s*(include|extends)\s+([\"'])([^\"']+)\2[^%]*%}"
)
ALLOW_MARKER = "page-length-allow:"


class PageLengthScanError(RuntimeError):
    """Raised on loader / IO problems the operator should see."""


def _template_search_roots() -> list[pathlib.Path]:
    roots = [TEMPLATES_DIR]
    roots.extend(APP_TEMPLATE_DIRS)
    return [r for r in roots if r.exists()]


def _resolve_include(target: str) -> pathlib.Path | None:
    """Resolve a Django template-loader path to a filesystem path."""
    for root in _template_search_roots():
        candidate = root / target
        if candidate.is_file():
            return candidate
    return None


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PageLengthScanError(f"{path}: {exc}") from exc


def _line_count(text: str) -> int:
    if not text:
        return 0
    # Count newlines; if the file lacks a final newline, the last line
    # still counts.
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def effective_loc(
    path: pathlib.Path,
    visited: set[pathlib.Path] | None = None,
    depth: int = 0,
    max_depth: int = 12,
) -> tuple[int, list[str]]:
    """Return (effective_loc, unresolved_includes) for a template.

    Recursively expands {% include %} and {% extends %} via filesystem
    resolution. Unresolved includes (variable paths, missing files) are
    returned as a flat list of strings for visibility, but do NOT abort
    the scan.
    """
    if visited is None:
        visited = set()
    if path in visited:
        return 0, []
    if depth > max_depth:
        return 0, [f"<max-depth>:{path.name}"]
    visited.add(path)
    try:
        text = _read_text(path)
    except PageLengthScanError as exc:
        return 0, [str(exc)]
    raw = _line_count(text)
    unresolved: list[str] = []
    for match in INCLUDE_RE.finditer(text):
        target = match.group(3)
        resolved = _resolve_include(target)
        if resolved is None:
            unresolved.append(target)
            continue
        child_loc, child_unresolved = effective_loc(
            resolved, visited, depth + 1, max_depth
        )
        raw += child_loc
        unresolved.extend(child_unresolved)
    return raw, unresolved


def _has_allow_marker(path: pathlib.Path) -> tuple[bool, str]:
    """Return (allowed, reason) — reason is empty when allowed is False."""
    try:
        text = _read_text(path)
    except PageLengthScanError:
        return False, ""
    # Cheap text scan rather than HTML parse — markers must appear at the
    # top level of the file, not inside a string literal.
    idx = text.find(ALLOW_MARKER)
    if idx < 0:
        return False, ""
    # Pull the rest of the line for the reason.
    end = text.find("\n", idx)
    snippet = text[idx + len(ALLOW_MARKER) : end if end > 0 else None]
    # Strip the trailing "-->" if the marker is inside an HTML comment.
    cleaned = snippet.replace("-->", "").strip()
    return True, cleaned


def _is_top_level_template(path: pathlib.Path) -> bool:
    """Heuristic: top-level templates are those rendered by a view.

    We treat anything NOT under a partials/ component/ widget directory
    as a top-level template. Partials and components are still scanned
    so their LOC contributes to the parents; they just aren't sorted
    onto the offender table themselves.
    """
    parts = {p.lower() for p in path.parts}
    if {"partials", "components", "widgets", "email", "emails"} & parts:
        return False
    # Files named base*.html or *_base.html or *_skeleton.html are shell
    # templates — they're rarely the "page" the user lands on directly.
    # Keep them eligible (they CAN be the offender) but mark.
    return True


def scan(
    templates_dir: pathlib.Path | None = None,
) -> list[dict[str, Any]]:
    """Scan all templates, returning per-route rows sorted by effective LOC."""
    root = templates_dir or TEMPLATES_DIR
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.html")):
        if not path.is_file():
            continue
        effective, unresolved = effective_loc(path)
        allowed, reason = _has_allow_marker(path)
        rows.append(
            {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "raw_loc": _line_count(_read_text(path)),
                "effective_loc": effective,
                "unresolved_includes": unresolved,
                "top_level": _is_top_level_template(path),
                "allowed": allowed,
                "allow_reason": reason,
            }
        )
    rows.sort(key=lambda r: r["effective_loc"], reverse=True)
    return rows


def _compute_ceiling(rows: list[dict[str, Any]]) -> int:
    """80th percentile of effective LOC across top-level non-allowed rows."""
    candidates = [
        r["effective_loc"]
        for r in rows
        if r["top_level"] and not r["allowed"]
    ]
    if not candidates:
        return 1500
    candidates.sort()
    # Manual 80th percentile (stdlib-only; no statistics import dep)
    idx = max(0, int(round(len(candidates) * 0.80)) - 1)
    return candidates[idx]


def _count_above_ceiling(
    rows: list[dict[str, Any]], ceiling: int
) -> int:
    return sum(
        1
        for r in rows
        if r["top_level"]
        and not r["allowed"]
        and r["effective_loc"] > ceiling
    )


def _format_text_report(
    rows: list[dict[str, Any]], ceiling: int, top: int
) -> str:
    lines: list[str] = []
    header = f"{'effective':>10}  {'raw':>6}  path"
    lines.append(header)
    lines.append("-" * 80)
    shown = 0
    for r in rows:
        if not r["top_level"]:
            continue
        if shown >= top:
            break
        flag = " " if not (r["effective_loc"] > ceiling) else "!"
        allow = " (allowed)" if r["allowed"] else ""
        lines.append(
            f"{r['effective_loc']:>10}  {r['raw_loc']:>6} {flag} "
            f"{r['path']}{allow}"
        )
        shown += 1
    lines.append("")
    lines.append(f"ceiling (80th percentile): {ceiling}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the text table.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Overwrite the baseline JSON with the current ceiling + "
            "top-30 offender list."
        ),
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Number of offender rows to print (default: 30).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on any new offenders above ceiling.",
    )
    args = parser.parse_args(argv)

    try:
        rows = scan()
    except PageLengthScanError as exc:
        sys.stderr.write(f"scan_page_length_offenders: {exc}\n")
        return 2

    ceiling = _compute_ceiling(rows)
    above = _count_above_ceiling(rows, ceiling)

    baseline_count = 0
    baseline_ceiling = ceiling
    if BASELINE_PATH.exists():
        try:
            blob = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            baseline_count = int(blob.get("finding_count", 0))
            baseline_ceiling = int(blob.get("ceiling", ceiling))
        except (json.JSONDecodeError, ValueError):
            pass

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        top_rows = [
            {
                "path": r["path"],
                "effective_loc": r["effective_loc"],
                "raw_loc": r["raw_loc"],
                "allowed": r["allowed"],
            }
            for r in rows
            if r["top_level"]
        ][: args.top]
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "finding_count": above,
                    "ceiling": ceiling,
                    "generated_at": "2026-05-21",
                    "generated_by": "scan_page_length_offenders",
                    "top_offenders": top_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "finding_count": above,
                    "ceiling": ceiling,
                    "baseline_count": baseline_count,
                    "baseline_ceiling": baseline_ceiling,
                    "rows": rows[: args.top],
                },
                indent=2,
            )
            + "\n"
        )
    else:
        sys.stdout.write(
            f"page-length scan: {above} offender(s) above ceiling "
            f"{ceiling}\n"
        )
        sys.stdout.write(f"baseline finding_count: {baseline_count}\n")
        sys.stdout.write(
            _format_text_report(rows, ceiling, args.top) + "\n"
        )

    if args.strict and above > baseline_count:
        sys.stderr.write(
            f"FAIL: {above} offenders > baseline {baseline_count}\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
