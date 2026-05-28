#!/usr/bin/env python3
"""Batch 1518 — real public status probes gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []
    rel = "apps/observability/public_status.py"

    for fn in (
        "_probe_auth",
        "_probe_parent_finance_health",
        "_probe_webhook_heartbeat",
        "_probe_celery_queue_depth",
        "enrollment_peak_mode_enabled",
        "PlatformStatusIncident",
    ):
        if not _contains(rel, fn):
            failures.append(f"{rel} missing {fn}")

    if not (ROOT / "apps/observability/platform_status_incident.py").is_file():
        failures.append("apps/observability/platform_status_incident.py missing")
    if not (ROOT / "apps/observability/migrations/0004_platformstatusincident.py").is_file():
        failures.append("migration 0004_platformstatusincident missing")
    if not _contains("templates/marketing/public_status.html", "enrollment_peak"):
        failures.append("public_status.html missing enrollment peak banner")
    if not _contains("apps/portal/urls.py", "parent_finance_health"):
        failures.append("portal parent_finance_health route missing")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print("PUBLIC_STATUS_REAL_PROBES_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
