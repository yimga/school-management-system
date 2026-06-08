#!/usr/bin/env python3
"""Verify KB ODT round-trip wiring (batch 1647).

Staff can re-upload edited ODT/DOCX onto an existing published article; locale
families gain per-article publish + missing-locale coverage badges.
Exit 0 + KB_ODT_ROUND_TRIP_VERIFY: PASS on clean tree.
"""
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

    if not _ok("apps/portal/kb_office_service.py", "reimport_odt_into_kb_article"):
        errors.append("kb_office_service missing reimport_odt_into_kb_article")
    if not _ok("apps/portal/views_kb_docs.py", "kb_article_reimport_odt"):
        errors.append("views_kb_docs missing kb_article_reimport_odt")
    if not _ok("apps/portal/urls_kb.py", "kb_article_reimport_odt"):
        errors.append("urls_kb missing kb_article_reimport_odt route")
    if not (ROOT / "templates/portal/partials/kb_article_staff_reimport.html").is_file():
        errors.append("missing kb_article_staff_reimport.html partial")
    if not _ok("templates/portal/kb_article.html", "kb_article_staff_reimport.html"):
        errors.append("kb_article.html missing staff reimport partial")
    if not _ok("templates/portal/operator/kb_article_body.html", "kb_article_staff_reimport.html"):
        errors.append("operator kb_article_body missing staff reimport partial")

    if not _ok("apps/portal/kb_locale_ops.py", "publish_locale_article"):
        errors.append("kb_locale_ops missing publish_locale_article")
    if not _ok("config/manager_kb_locale_families.py", "publish_one"):
        errors.append("manager_kb_locale_families missing publish_one action")
    if not _ok("config/manager_kb_locale_families.py", "missing_locales"):
        errors.append("manager_kb_locale_families missing missing_locales context")
    if not _ok("templates/schools/partials/manager_kb_locale_families_body.html", "publish_one"):
        errors.append("locale families template missing publish_one button")
    if not _ok("templates/schools/partials/manager_kb_locale_families_body.html", "docs_hub_url"):
        errors.append("locale families template missing docs hub link")

    admin_src = _read("apps/portal/admin_kb.py")
    for needle in (
        "Locale & translation",
        "locale_group_id",
        "translation_of",
        "Office export",
        "odt_file",
        "regenerate_odt_files",
        "regenerate_kb_article_odt",
    ):
        if needle not in admin_src:
            errors.append(f"admin_kb.py missing {needle!r}")
    if not _ok("apps/portal/kb_office_service.py", "regenerate_kb_article_odt"):
        errors.append("kb_office_service missing regenerate_kb_article_odt")

    test_path = ROOT / "apps/portal/tests/test_kb_odt_round_trip.py"
    if not test_path.is_file():
        errors.append("missing test_kb_odt_round_trip.py")
    else:
        ast.parse(test_path.read_text(encoding="utf-8"))

    try:
        import os

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import django
        from django.conf import settings

        if not settings.configured:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
            django.setup()
        from django.urls import reverse

        reverse("kb:kb_article_reimport_odt", kwargs={"article_slug": "test-slug"})
    except Exception as exc:
        errors.append(f"url reverse kb_article_reimport_odt failed: {exc}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print("KB_ODT_ROUND_TRIP_VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
