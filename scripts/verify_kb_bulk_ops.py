#!/usr/bin/env python3
"""Verify manager KB bulk ops UI wires import_docs_to_kb + generate_kb_odt."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    errors: list[str] = []

    required = [
        "apps/portal/kb_bulk_ops_service.py",
        "config/manager_kb_bulk_ops.py",
        "templates/schools/partials/manager_kb_bulk_ops_body.html",
    ]
    for rel in required:
        if not (ROOT / rel).is_file():
            errors.append(f"missing file: {rel}")

    checks = [
        ("apps/portal/kb_bulk_ops_service.py", "run_import_docs_to_kb"),
        ("apps/portal/kb_bulk_ops_service.py", "run_generate_kb_odt"),
        ("apps/portal/kb_bulk_ops_service.py", "import_docs_to_kb"),
        ("apps/portal/kb_bulk_ops_service.py", "generate_kb_odt"),
        ("config/manager_kb_bulk_ops.py", "manager_kb_bulk_ops"),
        ("config/manager_urls.py", "manager_kb_bulk_ops"),
        ("config/manager_help_center.py", "manager_kb_bulk_ops"),
        ("templates/schools/partials/manager_kb_bulk_ops_body.html", "import_docs"),
        ("templates/schools/partials/manager_kb_bulk_ops_body.html", "generate_odt"),
    ]
    for rel, needle in checks:
        if needle not in _read(rel):
            errors.append(f"{rel} missing {needle}")

    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import os
        import django
        from django.conf import settings

        if not settings.configured:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
            django.setup()
        from django.urls import reverse

        reverse("manager_kb_bulk_ops")
    except Exception as exc:
        errors.append(f"url reverse manager_kb_bulk_ops failed: {exc}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        print("KB_BULK_OPS_VERIFY: FAIL")
        return 1

    print("KB_BULK_OPS_VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
