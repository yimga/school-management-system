"""1077: backend teacher template lists CP Classrooms before advanced Django admin."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent


class BackendTeacherAdminLinkOrderTests(unittest.TestCase):
    def test_classrooms_url_before_admin_teacher_change(self) -> None:
        p = REPO / "templates" / "people" / "backend_teacher_detail.html"
        text = p.read_text(encoding="utf-8", errors="replace")
        a = text.find("accounts:backend_classroom_list")
        b = text.find("admin:people_teacherprofile_change")
        self.assertNotEqual(a, -1, msg="missing Classrooms (CP) link")
        self.assertNotEqual(b, -1, msg="missing admin teacher change link")
        self.assertLess(a, b, msg="CP Classrooms should precede admin fallback")

    def test_admin_link_has_advanced_label(self) -> None:
        p = REPO / "templates" / "people" / "backend_teacher_detail.html"
        text = p.read_text(encoding="utf-8", errors="replace")
        i = text.find("admin:people_teacherprofile_change")
        self.assertNotEqual(i, -1)
        line = [ln for ln in text.splitlines() if "admin:people_teacherprofile_change" in ln][0]
        self.assertIn("Advanced", line)
        self.assertIn("Advanced/Admin", line)

    def test_backend_student_portal_url_before_admin_in_template(self) -> None:
        p = REPO / "templates" / "people" / "backend_student_detail.html"
        text = p.read_text(encoding="utf-8", errors="replace")
        a = text.find("portal_tabbed_360")
        b = text.find("detail_urls.admin_student")
        self.assertNotEqual(a, -1)
        self.assertNotEqual(b, -1)
        self.assertLess(a, b)

    def test_backend_classroom_academic_years_before_admin_classroom_change(self) -> None:
        p = REPO / "templates" / "people" / "backend_classroom_detail.html"
        text = p.read_text(encoding="utf-8", errors="replace")
        a = text.find("academic_years_setup_evidence_url")
        b = text.find("admin:academics_classroom_change")
        self.assertNotEqual(a, -1, msg="missing academic years setup (CP) link hook")
        self.assertNotEqual(b, -1, msg="missing admin classroom change link")
        self.assertLess(a, b, msg="Academic years (setup) should precede admin fallback")

    def test_backend_classroom_admin_link_has_advanced_label(self) -> None:
        p = REPO / "templates" / "people" / "backend_classroom_detail.html"
        text = p.read_text(encoding="utf-8", errors="replace")
        line = [ln for ln in text.splitlines() if "admin:academics_classroom_change" in ln][0]
        self.assertIn("Advanced", line)
        self.assertIn("Advanced/Admin", line)

    def test_backend_student_admin_fallback_label(self) -> None:
        p = REPO / "templates" / "people" / "backend_student_detail.html"
        text = p.read_text(encoding="utf-8", errors="replace")
        line = [ln for ln in text.splitlines() if "detail_urls.admin_student" in ln][0]
        self.assertIn("Advanced/Admin", line)

    def test_backend_people_lists_use_product_detail_routes_only(self) -> None:
        for rel in (
            "templates/people/backend_student_list.html",
            "templates/people/backend_teacher_list.html",
        ):
            text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            with self.subTest(template=rel):
                self.assertNotIn("admin:", text)
                self.assertNotIn("/admin/", text)
                self.assertIn("backend_", text)
