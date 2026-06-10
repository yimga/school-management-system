"""Workflow 1 (Admission & Enrollment) — UI wiring guard.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.
Locks the chain that made the enrollment service callable in-product:

    list row → applicant detail → advance-stage / enroll → student record

The enrollment *service* (``enroll_applicant_to_student``) is covered with a
DB-backed regression in ``apps/admissions/tests/test_application_kernel.py``;
this guards the views, urls, and templates that finally call it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


class ApplicantViewWiringTests(unittest.TestCase):

    VIEWS = "apps/people/views_backend.py"
    URLS = "apps/accounts/urls.py"
    DETAIL = "templates/people/backend_applicant_detail.html"
    LISTT = "templates/people/backend_applicant_list.html"
    QUEUE = "apps/admissions/queue_depth.py"

    def test_views_defined(self) -> None:
        text = _read(self.VIEWS)
        for fn in (
            "def backend_applicant_detail(",
            "def backend_applicant_advance_stage(",
            "def backend_applicant_enroll(",
        ):
            self.assertIn(fn, text, msg=f"missing view: {fn}")

    def test_enroll_view_calls_the_service(self) -> None:
        text = _read(self.VIEWS)
        self.assertIn("enroll_applicant_to_student(", text)
        self.assertIn("advance_stage(", text)

    def test_urls_registered(self) -> None:
        text = _read(self.URLS)
        for name in (
            'name="backend_applicant_detail"',
            'name="backend_applicant_advance_stage"',
            'name="backend_applicant_enroll"',
        ):
            self.assertIn(name, text, msg=f"missing url: {name}")

    def test_list_links_to_detail(self) -> None:
        text = _read(self.LISTT)
        self.assertIn("accounts:backend_applicant_detail", text)

    def test_detail_offers_enroll_and_stage_actions(self) -> None:
        text = _read(self.DETAIL)
        self.assertIn("accounts:backend_applicant_enroll", text)
        self.assertIn("accounts:backend_applicant_advance_stage", text)
        # Enrolled record must deep-link to the created student.
        self.assertIn("accounts:backend_student_detail", text)

    def test_queue_drill_no_longer_hardcodes_dead_route(self) -> None:
        text = _read(self.QUEUE)
        # The old "/admissions/applicants/" path never resolved; tiles now reverse
        # the live backend list route.
        self.assertNotIn('"/admissions/applicants/?"', text)
        self.assertIn("backend_applicant_list", text)


if __name__ == "__main__":
    unittest.main()
