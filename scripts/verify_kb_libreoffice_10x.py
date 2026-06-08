#!/usr/bin/env python3
"""Verify KB/LibreOffice 10x hub — routes, services, tenant+operator templates."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def _ok(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def main() -> int:
    errors: list[str] = []

    required_files = [
        "apps/portal/kb_office_service.py",
        "apps/portal/views_kb_docs.py",
        "templates/portal/kb_docs_hub.html",
        "templates/portal/kb_office_upload.html",
        "templates/portal/operator/kb_docs_hub_body.html",
        "templates/portal/operator/kb_office_upload_body.html",
    ]
    for rel in required_files:
        if not (ROOT / rel).is_file():
            errors.append(f"missing file: {rel}")

    url_checks = [
        ("apps/portal/urls_kb.py", "kb_docs_hub"),
        ("apps/portal/urls_kb.py", "kb_link_office_document"),
        ("apps/portal/urls_kb.py", "kb_office_upload"),
        ("apps/portal/urls_kb.py", "office_document_download"),
        ("apps/portal/urls_kb.py", "office_document_preview_pdf"),
        ("apps/portal/urls_kb.py", "views_kb_docs"),
    ]
    for rel, needle in url_checks:
        if not _ok(rel, needle):
            errors.append(f"{rel} missing {needle}")

    service_checks = [
        ("apps/portal/kb_office_service.py", "build_docs_hub_context"),
        ("apps/portal/kb_office_service.py", "search_office_documents"),
        ("apps/portal/kb_office_service.py", "link_kb_article_to_office_document"),
        ("apps/portal/kb_office_service.py", "import_writer_file_to_kb_article"),
        ("apps/portal/kb_office_service.py", "office_document_export_bytes"),
        ("apps/portal/models_kb.py", "linked_office_document"),
        ("apps/portal/document_conversion.py", "convert_odt_to_html"),
        ("apps/portal/views_kb_docs.py", "kb_link_office_document"),
        ("apps/portal/views_kb_docs.py", "render_kb_if_operator"),
    ]
    for rel, needle in service_checks:
        if not _ok(rel, needle):
            errors.append(f"{rel} missing {needle}")

    template_checks = [
        ("templates/portal/kb_docs_hub.html", 'name="q"'),
        ("templates/portal/kb_docs_hub.html", "kb_link_office_document"),
        ("templates/portal/kb_docs_hub.html", "kb:kb_office_upload"),
        ("templates/portal/kb_docs_hub.html", "office_document_preview_pdf"),
        ("templates/portal/kb_office_upload.html", "import_kb"),
        ("templates/portal/kb_home.html", "kb:kb_docs_hub"),
        ("templates/portal/office_document_list.html", "kb:kb_docs_hub"),
    ]
    for rel, needle in template_checks:
        if not _ok(rel, needle):
            errors.append(f"{rel} missing {needle}")

    # URL names resolve in Django urlconf
    try:
        import os
        import sys

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import django
        from django.conf import settings

        if not settings.configured:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
            django.setup()
        from django.urls import reverse

        for name in (
            "kb:kb_docs_hub",
            "kb:kb_link_office_document",
            "kb:kb_office_upload",
            "kb:office_document_download",
            "kb:office_document_preview_pdf",
        ):
            try:
                reverse(name, kwargs={"document_id": 1} if "document" in name else {})
            except Exception as exc:
                errors.append(f"reverse({name}) failed: {exc}")
    except Exception as exc:
        errors.append(f"django url reverse smoke failed: {exc}")

    # kb_office_service parses
    try:
        ast.parse(_read("apps/portal/kb_office_service.py"))
        ast.parse(_read("apps/portal/views_kb_docs.py"))
    except SyntaxError as exc:
        errors.append(f"syntax error: {exc}")

    if errors:
        print("KB_LIBREOFFICE_10X_VERIFY: FAIL")
        for err in errors:
            print(f" - {err}")
        return 1

    print("KB_LIBREOFFICE_10X_VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
