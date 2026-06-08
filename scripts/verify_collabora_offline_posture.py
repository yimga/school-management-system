#!/usr/bin/env python3
"""Repo posture: Collabora live edit optional; LibreOffice offline path required."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def main() -> int:
    findings: list[str] = []

    office = _text("apps/portal/kb_office_service.py")
    kb_offline = _text("apps/portal/views_kb_offline.py")
    reimport = _text("templates/portal/partials/kb_article_staff_reimport.html")

    if "collabora_enabled" not in office:
        findings.append("kb_office_service missing collabora_enabled flag")
    if "COLLABORA_BASE_URL" not in office:
        findings.append("kb_office_service missing COLLABORA_BASE_URL env gate")
    if "api_kb_offline_pack" not in kb_offline:
        findings.append("views_kb_offline missing offline pack API")
    if 'data-rmc-offline-form="field_capture"' not in reimport:
        findings.append("KB reimport partial missing offline queue capture")

    wopi = _text("apps/portal/urls_kb.py")
    if "wopi_check_file_info" not in wopi:
        findings.append("urls_kb missing WOPI routes")

    if findings:
        for f in findings:
            print(f"FAIL: {f}")
        return 1

    print("COLLABORA_OFFLINE_POSTURE_PASS")
    print(
        "note: live Collabora/WOPI smoke requires APP_BASE_URL + COLLABORA_BASE_URL "
        "(scripts/verify_collabora_wopi_smoke.py)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
