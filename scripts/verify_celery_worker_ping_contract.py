#!/usr/bin/env python3
"""Seal celery worker ping contract: healthz probe + CLI + settings knob."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "apps" / "observability" / "views.py"
CMD = (
    ROOT
    / "apps"
    / "observability"
    / "management"
    / "commands"
    / "ping_celery_workers.py"
)
SETTINGS = ROOT / "config" / "settings.py"


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    findings: list[str] = []

    if not VIEWS.is_file():
        findings.append("observability_views_missing")
    else:
        text = VIEWS.read_text(encoding="utf-8")
        for needle in (
            "def _check_celery_workers",
            "inspect(timeout=2.0).ping()",
            '"celery_workers"',
            "HEALTHZ_REQUIRE_CELERY_WORKERS",
        ):
            if needle not in text:
                findings.append(f"views_missing:{needle}")

    if not CMD.is_file():
        findings.append("ping_celery_workers_command_missing")

    if not SETTINGS.is_file():
        findings.append("settings_missing")
    else:
        text = SETTINGS.read_text(encoding="utf-8")
        if "HEALTHZ_REQUIRE_CELERY_WORKERS" not in text:
            findings.append("settings_missing_HEALTHZ_REQUIRE_CELERY_WORKERS")

    if findings:
        print(f"CELERY_WORKER_PING_CONTRACT_FAIL: {len(findings)} finding(s)")
        for row in findings:
            print(f"  - {row}")
        return 1
    print("CELERY_WORKER_PING_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
