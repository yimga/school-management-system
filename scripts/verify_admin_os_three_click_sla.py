#!/usr/bin/env python3
"""Prove Discover → model changelist is ≤3 interactions (Admin OS v15 I12).

Static gate: operator + tenant index templates must expose searchable catalog
with direct model card links (`href="{{ model.admin_url }}"`).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INDEX_PATHS = (
    "templates/admin/index_superadmin.html",
    "templates/admin/index_tenant.html",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _check_index(rel: str) -> list[str]:
    errors: list[str] = []
    text = _read(rel)
    if 'data-rmc-admin-archetype="discover"' not in text:
        errors.append(f"{rel}: missing discover archetype marker")
    if "data-rmc-admin-catalog-search" not in text and "rmcAdminCatalogSearch" not in text:
        errors.append(f"{rel}: missing searchable catalog input")
    if "model.admin_url" not in text:
        errors.append(f"{rel}: catalog must expose model.admin_url links")
    if "rmc-admin-catalog-model-card" not in text:
        errors.append(f"{rel}: missing direct catalog model card grid")
    if not re.search(
        r'<a\s+[^>]*href="\{\{\s*model\.admin_url\s*\}\}"[^>]*class="rmc-admin-catalog-model-card"',
        text,
    ):
        errors.append(
            f"{rel}: model cards must be direct <a href=\"{{{{ model.admin_url }}}}\"> links (1-click path)"
        )
    preview_links = re.findall(
        r'<a\s+href="\{\{\s*model\.admin_url\s*\}\}"',
        text,
    )
    if not preview_links:
        errors.append(f"{rel}: no direct admin_url anchor found in catalog")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in INDEX_PATHS:
        if not (ROOT / path).is_file():
            errors.append(f"missing index template: {path}")
            continue
        errors.extend(_check_index(path))
    if errors:
        print("ADMIN_OS_THREE_CLICK_SLA_FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("ADMIN_OS_THREE_CLICK_SLA_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
