#!/usr/bin/env python3
"""SODP Wave A gate — offline foundation."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def main() -> int:
    findings: list[str] = []
    for rel in (
        "apps/platform_runtime/offline_action_types.py",
        "apps/schools/offline_delivery_settings.py",
        "apps/platform_runtime/migrations/0070_sodp_offline_waves.py",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    sw = _text("static/js/service-worker.js")
    for needle in (
        "SKIP_HEADERS",
        "createdAt",
        "response.status >= 400 && response.status < 500",
        "/portal/api/offline/",
        "maxQueueItems",
    ):
        if needle not in sw:
            findings.append(f"service-worker missing {needle}")

    oqc = _text("static/js/offline-queue-client.js")
    if "SEND_EMAIL" in oqc or "smtp_password" in oqc.lower():
        findings.append("offline-queue-client must not reference client SMTP")

    py_sources = [
        ROOT / "static/js",
        ROOT / "apps",
    ]
    for base in py_sources:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "test" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r'["\']SEND_EMAIL["\']', text) and "offline_action_types" not in str(path):
                if "FORBIDDEN" not in text:
                    findings.append(f"possible client SEND_EMAIL in {path.relative_to(ROOT)}")

    if findings:
        print("verify_sovereign_offline_foundation: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_offline_foundation: SOVEREIGN_OFFLINE_FOUNDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
