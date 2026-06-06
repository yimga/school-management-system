"""Verify InformationTag platform wiring (v4.02.51, 2026-06-02).

Exits 0 with ``INFORMATION_TAG_WIRING_PASS`` when required integration
surfaces are present. Any gap exits 1 with a single-line diagnosis.
"""

from __future__ import annotations

import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    path = REPO_ROOT / rel
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _require(text: str, needle: str, label: str, findings: list[str]) -> None:
    if needle not in text:
        findings.append(f"{label}: missing {needle!r}")


def main() -> int:
    findings: list[str] = []

    models = _read("apps/people/models.py")
    _require(models, "class InformationTag", "models", findings)
    _require(models, "InformationTag", "models StudentProfile.tags", findings)
    _require(models, 'related_name="students"', "models StudentProfile.tags", findings)

    nuance = _read("apps/siteconfig/nuance_engine.py")
    _require(nuance, '"student_tags"', "nuance_engine", findings)

    finance = _read("apps/finance/services.py")
    _require(finance, 'context["student_tags"]', "finance.services", findings)

    aid = _read("apps/finance/aid_services.py")
    _require(aid, "student_tags", "finance.aid_services", findings)

    signals = _read("apps/people/signals.py")
    _require(signals, "InformationTag", "people.signals", findings)

    admin = _read("apps/people/admin.py")
    _require(admin, "InformationTagAdmin", "people.admin", findings)
    _require(admin, '"tags"', "people.admin StudentProfile", findings)

    tag_mgr = _read("apps/siteconfig/views_tag_manager.py")
    _require(tag_mgr, "def tag_manager", "views_tag_manager", findings)

    urls = _read("apps/siteconfig/urls.py")
    _require(urls, 'name="tag_manager"', "siteconfig.urls", findings)

    one_record = _read("apps/portal/one_record.py")
    _require(one_record, "information_tags", "one_record", findings)
    _require(one_record, '"tags"', "one_record sections", findings)

    list_tpl = _read("templates/people/backend_student_list.html")
    _require(list_tpl, "student.tags.all", "backend_student_list", findings)
    _require(list_tpl, "can_see_private_tags", "backend_student_list", findings)

    detail_tpl = _read("templates/people/backend_student_detail.html")
    _require(detail_tpl, "Information tags", "backend_student_detail", findings)
    _require(detail_tpl, "d.tags.items", "backend_student_detail", findings)

    detail_view = _read("apps/people/views_backend.py")
    _require(detail_view, 'prefetch_related("tags")', "backend_student_detail view", findings)
    _require(detail_view, "can_see_private_tags", "backend_student_detail view", findings)

    s360_view = _read("apps/student360/views.py")
    _require(s360_view, 'prefetch_related("tags")', "student360.views", findings)
    _require(s360_view, "information_tags", "student360.views", findings)

    s360_tpl = _read("templates/student360/student_360_page.html")
    _require(s360_tpl, "Information tags", "student_360_page", findings)
    _require(s360_tpl, "information_tags", "student_360_page", findings)

    if findings:
        print("INFORMATION_TAG_WIRING_FAIL")
        for item in findings:
            print(item)
        return 1

    print("INFORMATION_TAG_WIRING_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
