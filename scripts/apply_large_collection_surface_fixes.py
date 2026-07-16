#!/usr/bin/env python3
"""Apply mechanical large-collection surface remediations from audit findings.

Fixes per file (when audit JSON is present):
  1. data-rmc-scroll-policy="paginate" on page shell / fragment wrapper
  2. table-sm + table-sticky-head on wide tables missing density markers
  3. Row action cells: wrap inline forms in <details class="rmc-row-disclosure">

Usage:
  python scripts/apply_large_collection_surface_fixes.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
REPORT_PATH = ROOT / "docs" / "generated" / "large_collection_surface_audit.json"

SCROLL_ATTR = 'data-rmc-scroll-policy="paginate"'
SCROLL_RE = re.compile(r'data-rmc-scroll-policy\s*=\s*"paginate"')
TABLE_RE = re.compile(r"<table\b(?P<attrs>[^>]*)>", re.IGNORECASE)
DENSITY_RE = re.compile(r"table-sm|table-density|data-density|rmc-data-table|table-sticky-head", re.IGNORECASE)
CONTAINER_RE = re.compile(
    r"(<(?:main|motion|div)\b(?P<attrs>[^>]*)(?:class=\"[^\"]*(?:container|rmc-page)[^\"]*\"[^>]*)>)",
    re.IGNORECASE,
)
FORM_IN_TD_RE = re.compile(
    r"<td\b[^>]*>((?:(?!<td\b|<tr\b).)*?<form\b(?:(?!<td\b|<tr\b).)*?)</td>",
    re.IGNORECASE | re.DOTALL,
)
DETAILS_IN_BODY_RE = re.compile(r"<details\b", re.IGNORECASE)

PRINT_ALLOW_PREFIXES = (
    "templates/reports/term_report",
    "templates/reports/evaluation_grid",
    "templates/evals/grade_import_upload",
    "templates/siteconfig/partials/reportcard_style_preview",
    "templates/analytics/master_sheet",
)


def _needs_scroll_policy(text: str, findings: list[dict]) -> bool:
    if SCROLL_RE.search(text):
        return False
    return any(not f.get("has_paginate_scroll_policy") for f in findings)


def _inject_scroll_policy(text: str) -> str:
    if SCROLL_RE.search(text):
        return text

    for pattern in (
        r'(<main\b[^>]*)(>)',
        r'(<div\b[^>]*class="[^"]*container[^"]*"[^>]*)(>)',
        r'(<motion\b[^>]*class="[^"]*container[^"]*"[^>]*)(>)',
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            attrs = match.group(1)
            if SCROLL_RE.search(attrs):
                return text
            return text[: match.start()] + attrs + f" {SCROLL_ATTR}" + match.group(2) + text[match.end() :]

    if "{% extends" not in text and "<table" in text:
        return f'<div {SCROLL_ATTR}>\n{text}\n</div>\n'

    return text


def _add_table_density(text: str, findings: list[dict]) -> str:
    wide_lines = {
        f["line"]
        for f in findings
        if "wide table without compact density marker" in f.get("reasons", [])
    }
    if not wide_lines:
        wide_lines = {f["line"] for f in findings if f.get("columns", 0) >= 7}

    offset = 0
    for match in TABLE_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        if wide_lines and line not in wide_lines:
            continue
        attrs = match.group("attrs")
        if DENSITY_RE.search(attrs):
            continue
        new_attrs = attrs
        if "class=" in attrs:
            new_attrs = re.sub(
                r'class="([^"]*)"',
                lambda m: f'class="{m.group(1)} table-sm table-sticky-head rmc-data-table"',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            new_attrs = f'{attrs} class="table table-sm table-sticky-head rmc-data-table"'
        replacement = f"<table{new_attrs}>"
        start = match.start() + offset
        end = match.end() + offset
        text = text[:start] + replacement + text[end:]
        offset += len(replacement) - len(match.group(0))
    return text


def _wrap_row_forms(text: str, findings: list[dict]) -> str:
    needs_wrap = any(
        "form(s) inside repeated rows" in " ".join(f.get("reasons", []))
        for f in findings
    )
    if not needs_wrap:
        return text

    def _wrap_td(match: re.Match[str]) -> str:
        full = match.group(0)
        if DETAILS_IN_BODY_RE.search(full):
            return full
        inner = re.match(r"<td\b[^>]*>(?P<body>.*)</td>", full, re.IGNORECASE | re.DOTALL)
        if not inner:
            return full
        body = inner.group("body")
        if "<form" not in body.lower():
            return full
        open_td = full[: full.index(">") + 1]
        wrapped = (
            f"{open_td}\n"
            '                <details class="rmc-row-disclosure">\n'
            '                  <summary class="btn btn-sm btn-outline-secondary">{% trans "Actions" %}</summary>\n'
            '                  <div class="rmc-row-disclosure__body mt-1">\n'
            f"{body.strip()}\n"
            "                  </div>\n"
            "                </details></td>"
        )
        return wrapped

    return FORM_IN_TD_RE.sub(_wrap_td, text)


def _add_print_allow_marker(text: str, rel: str) -> str:
    if not any(rel.replace("\\", "/").startswith(p) for p in PRINT_ALLOW_PREFIXES):
        return text
    if "large-collection-allow:" in text:
        return text
    return re.sub(
        r"(<table\b)",
        r'<!-- large-collection-allow: print-report-fixed-layout -->\n\1',
        text,
        count=1,
        flags=re.IGNORECASE,
    )


def apply_file(rel_path: str, findings: list[dict], dry_run: bool) -> bool:
    path = ROOT / rel_path.replace("/", "\\") if "\\" in str(ROOT) else ROOT / rel_path
    if not path.is_file():
        path = ROOT / rel_path
    if not path.is_file():
        print(f"  skip missing {rel_path}")
        return False

    original = path.read_text(encoding="utf-8", errors="replace")
    updated = original
    updated = _add_print_allow_marker(updated, rel_path)
    if _needs_scroll_policy(original, findings):
        updated = _inject_scroll_policy(updated)
    updated = _add_table_density(updated, findings)
    updated = _wrap_row_forms(updated, findings)

    if updated != original:
        if dry_run:
            print(f"  would update {rel_path}")
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"  updated {rel_path}")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not REPORT_PATH.is_file():
        print(f"Missing audit report: {REPORT_PATH}", file=sys.stderr)
        return 1

    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    by_file: dict[str, list[dict]] = {}
    for finding in data.get("findings", []):
        by_file.setdefault(finding["file"], []).append(finding)

    changed = 0
    for rel_path, findings in sorted(by_file.items()):
        if apply_file(rel_path, findings, args.dry_run):
            changed += 1

    print(f"{'Would update' if args.dry_run else 'Updated'} {changed} template(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
