#!/usr/bin/env python3
"""Verify KB/FAQ + LibreOffice stack evidence (T0-T6)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "apps/portal/kb_context.py",
    "apps/portal/kb_office_service.py",
    "apps/portal/views_kb_docs.py",
    "apps/portal/views_office.py",
    "apps/portal/document_service.py",
    "docker-compose.collabora.yml",
    "docs/execution/KB_CONVERSION_RUNBOOK.md",
    "scripts/release/verify_collabora_wopi.sh",
    "scripts/verify_collabora_wopi_smoke.py",
    "deploy/collabora/k8s/ingress.yaml",
    "deploy/collabora/k8s/service.yaml",
    "deploy/collabora/k8s/deployment.yaml",
]

ALLOWED_SOFFICE_FILES = {
    "apps/portal/document_conversion.py",
    "apps/portal/document_generation.py",
    "docs/KB_LIBREOFFICE_ODT_INTEGRATION.md",
    "docs/execution/KB_CONVERSION_RUNBOOK.md",
    "scripts/release/verify_collabora_wopi.sh",
    "scripts/verify_collabora_wopi_smoke.py",
    "deploy/collabora/k8s/ingress.yaml",
    "deploy/collabora/k8s/service.yaml",
    "deploy/collabora/k8s/deployment.yaml",
    "scripts/verify_kb_libreoffice_stack.py",
}


def check_required_files() -> list[str]:
    errs = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            errs.append(f"missing required file: {rel}")
    return errs


def check_no_stray_soffice() -> list[str]:
    errs = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "soffice" in text and rel not in ALLOWED_SOFFICE_FILES:
            errs.append(f"stray soffice usage outside service layer: {rel}")
    return errs


def main() -> int:
    errors = []
    errors.extend(check_required_files())
    errors.extend(check_no_stray_soffice())

    if errors:
        print("KB/LIBREOFFICE STACK VERIFY: FAIL")
        for e in errors:
            print(f" - {e}")
        return 1

    print("KB/LIBREOFFICE STACK VERIFY: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
