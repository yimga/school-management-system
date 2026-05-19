#!/usr/bin/env python3
"""
Verify hot list views use bounded list_search helpers (Google pillar).

Fails when portal/people list view modules use raw icontains without importing
apps.siteconfig.list_search.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = (
    ROOT / "apps" / "people" / "views_backend.py",
    ROOT / "apps" / "portal" / "views_documents.py",
    ROOT / "apps" / "portal" / "views_kb.py",
)

ICONTAINS_RE = re.compile(r"__icontains")
IMPORT_RE = re.compile(
    r"apps\.siteconfig\.list_search|apps\.people\.student_search|apps\.portal\.document_search"
)


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if not ICONTAINS_RE.search(text):
        return []
    if IMPORT_RE.search(text):
        return []
    rel = path.relative_to(ROOT)
    return [f"{rel}: uses __icontains without apps.siteconfig.list_search import"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    errors: list[str] = []
    for path in TARGETS:
        if path.is_file():
            errors.extend(scan_file(path))
    if errors:
        for err in errors:
            print(f"verify_list_search_adoption: {err}", file=sys.stderr)
        return 1
    print("verify_list_search_adoption: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
