#!/usr/bin/env python3
"""
Performance budget enforcement (Path-to-10). Runs smoke requests against key URLs
and fails if response time exceeds budgets in docs/PERFORMANCE_BUDGETS.md.
Usage: python scripts/check_performance_budgets.py [--warn-only]
With PERF_BUDGET_STRICT=1: exit 1 if any budget exceeded. With --warn-only: always exit 0, print warnings.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Budgets (seconds) from docs/PERFORMANCE_BUDGETS.md — key surfaces only for smoke
BUDGETS = {
    "/": 2.0,                    # Home or redirect
    "/admin/": 2.0,              # Admin (control-plane proxy)
}

def main() -> int:
    warn_only = "--warn-only" in sys.argv
    strict = os.environ.get("PERF_BUDGET_STRICT", "0") == "1"
    if not strict and not warn_only:
        print("OK: Performance budget check skipped (set PERF_BUDGET_STRICT=1 or use --warn-only to run).")
        return 0

    # Use Django test client so we don't need a running server
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from django.test import Client
    from django.conf import settings
    # Allow testserver for test client (no live server needed)
    if "testserver" not in (getattr(settings, "ALLOWED_HOSTS", None) or []):
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS or []) + ["testserver"]
    client = Client()

    failed = []
    for path, budget_sec in BUDGETS.items():
        try:
            start = time.perf_counter()
            response = client.get(path, follow=True)
            elapsed = time.perf_counter() - start
            if elapsed > budget_sec:
                msg = f"{path}: {elapsed:.2f}s > {budget_sec}s budget"
                if strict and not warn_only:
                    failed.append(msg)
                else:
                    print(f"WARN: {msg}", file=sys.stderr)
        except Exception as e:
            failed.append(f"{path}: {e!s}")
            if not warn_only:
                print(f"ERROR: {path}: {e}", file=sys.stderr)

    if failed and strict and not warn_only:
        print("ERROR: Performance budget(s) exceeded:", file=sys.stderr)
        for m in failed:
            print(f"  {m}", file=sys.stderr)
        return 1
    if failed and warn_only:
        print("WARN: Some budgets exceeded (warn-only).", file=sys.stderr)
    if not failed:
        print("OK: Performance budgets within limit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
