#!/usr/bin/env python3
"""Verify KB/FAQ + LibreOffice stack evidence (T0-T6)."""

from __future__ import annotations

import ast
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


#: Reaching LibreOffice THROUGH these is the sanctioned path, not a stray usage.
SERVICE_MODULES = (
    "apps.portal.document_conversion",
    "apps.portal.document_generation",
)

#: Third-party trees are not ours to police, and rglob would walk every one of
#: them. node_modules alone is ~362MB.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "staticfiles", "htmlcov"}


def _service_layer_names(tree: ast.AST) -> set[str]:
    """Symbols this module imported from the conversion service layer."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in SERVICE_MODULES:
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def check_no_stray_soffice() -> list[str]:
    """Flag files that reach the LibreOffice binary directly.

    The question is whether a file goes AROUND the service layer, not whether
    the eight letters appear in it. A file that imports ``find_soffice`` from
    apps.portal.document_conversion is doing exactly what this gate wants, and
    a substring test cannot tell the two apart -- it flagged
    apps/schools/super_views_exports.py for a compliant import from 2026-06-09.

    So: blank out the symbols the file imported from the service layer, then
    look again. A literal "soffice" binary name or a hand-rolled path variable
    survives that erasure; a call to the service helper does not.
    """
    errs = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED_SOFFICE_FILES:
            continue
        if SKIP_DIRS.intersection(path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "soffice" not in text:
            continue
        try:
            imported = _service_layer_names(ast.parse(text))
        except SyntaxError:
            imported = set()  # cannot prove it is compliant, so keep flagging it
        residue = text
        for name in sorted(imported, key=len, reverse=True):
            residue = residue.replace(name, "")
        for module in SERVICE_MODULES:
            residue = residue.replace(module, "")
        if "soffice" in residue:
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
