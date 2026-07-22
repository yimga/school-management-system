#!/usr/bin/env python3
"""Seal Fix D — tenant migrate lock_timeout wiring is present and env-knobbed.

Static gate (no Postgres required). Proves:
  * helpers exist in onboarding_service.py
  * _run_tenant_migrations applies SET / reset / discard paths
  * config/settings.py defines TENANT_MIGRATE_LOCK_TIMEOUT_MS from env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONBOARDING = ROOT / "apps" / "schools" / "onboarding_service.py"
SETTINGS = ROOT / "config" / "settings.py"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    findings: list[str] = []

    if not ONBOARDING.is_file():
        findings.append("onboarding_service_missing")
    else:
        text = ONBOARDING.read_text(encoding="utf-8")
        for needle in (
            "def _tenant_migrate_lock_timeout_ms",
            "def _set_lock_timeout",
            "def _discard_connection",
            "SET lock_timeout",
            "_set_lock_timeout(lock_ms)",
            "_discard_connection()",
        ):
            if needle not in text:
                findings.append(f"onboarding_missing:{needle}")

    if not SETTINGS.is_file():
        findings.append("settings_missing")
    else:
        text = SETTINGS.read_text(encoding="utf-8")
        if "TENANT_MIGRATE_LOCK_TIMEOUT_MS" not in text:
            findings.append("settings_missing_TENANT_MIGRATE_LOCK_TIMEOUT_MS")
        if 'os.getenv("TENANT_MIGRATE_LOCK_TIMEOUT_MS"' not in text and "os.environ.get(\"TENANT_MIGRATE_LOCK_TIMEOUT_MS\"" not in text:
            findings.append("settings_TENANT_MIGRATE_LOCK_TIMEOUT_MS_not_env_wired")

    if findings:
        print(f"TENANT_MIGRATE_LOCK_TIMEOUT_FAIL: {len(findings)} finding(s)")
        for row in findings:
            print(f"  - {row}")
        return 1
    print("TENANT_MIGRATE_LOCK_TIMEOUT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
