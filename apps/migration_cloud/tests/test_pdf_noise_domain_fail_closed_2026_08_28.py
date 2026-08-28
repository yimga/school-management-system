"""The zero-touch autopilot must not dismiss a row it cannot judge (2026-08-28).

``row_is_pdf_noise_hold`` asks ``row_has_domain_identity``, which answers False
both for "the identity fields are empty" and for "I have no identity keys for
this domain". Only 7 of the 28 domains the landers emit are mapped, so for
finance, payroll, guardians, transcripts, library and the rest the answer was
always False -- and every held ``missing_required`` row that came off a ``.pdf``
artifact was classified as page furniture and auto-dismissed, however much real
data it carried.

That was survivable while the pass only ran during an operator-triggered repair.
It stopped being survivable when review-open autopilot began running it on a
plain GET of the held-review page: an invoice row with amount, currency and due
date would be closed by nobody, on page load, with no click.

The fix is not more identity keys -- it is refusing to answer an unanswerable
question. Genuine noise in an unmapped domain is still closed, by the fragment
test, which reads the ROW instead of the domain.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.automation.models import MigrationQuarantineRecord, MigrationRun
from apps.migration_cloud.auto_remediate import auto_remediate_on_review_open
from apps.migration_cloud.landers._helpers import (
    domain_identity_is_known,
    row_is_pdf_noise_hold,
)
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.views import MigrationCloudAnomalyNudgeView
from apps.schools.models import School, SchoolMembership

User = get_user_model()

# One realistic held row per unmapped domain, each carrying enough to be a real
# record. None of these may be auto-dismissed.
DATA_BEARING_ROWS = {
    "finance": {
        "student_external_id": "S-1001",
        "invoice_number": "INV-2026-0042",
        "amount": "450000",
        "currency": "XAF",
        "due_date": "2026-09-30",
    },
    "payroll": {
        "employee_number": "EMP-77",
        "full_name": "A. Nkeng",
        "gross_salary": "310000",
        "period": "2026-08",
    },
    "guardians": {
        "full_name": "Marie Etonde",
        "phone": "+237600000000",
        "student_external_id": "S-1001",
    },
    "transcripts": {
        "student_external_id": "S-1001",
        "subject_code": "MATH",
        "final_grade": "A",
    },
    "library": {"isbn": "978-0-00-000000-0", "title": "Things Fall Apart"},
}

# The same domains, but rows that really are page furniture. These must close.
NOISE_ROWS = {
    "finance": {"page": "2", "line": "totals"},
    "payroll": {"custom_fields": {"raw_line": "Page 3 of 9"}},
    "guardians": {},
    "transcripts": {"page": "7"},
    "library": {"custom_fields": {"raw_line": "-- continued --"}},
}


class UnmappedDomainIsNotNoiseTests(TestCase):
    def test_the_identity_map_does_not_cover_these_domains(self):
        # If someone later maps one of these, this test says so rather than
        # quietly losing its own premise.
        for domain in DATA_BEARING_ROWS:
            self.assertFalse(
                domain_identity_is_known(domain),
                f"{domain} is mapped now -- move it out of this fixture",
            )

    def test_a_data_bearing_pdf_row_is_never_pdf_noise(self):
        for domain, row in DATA_BEARING_ROWS.items():
            with self.subTest(domain=domain):
                self.assertFalse(
                    row_is_pdf_noise_hold(domain, row, f"{domain}_2026.pdf"),
                    f"a {domain} row carrying {sorted(row)} was called PDF noise",
                )

    def test_real_page_furniture_still_closes_in_the_same_domains(self):
        for domain, row in NOISE_ROWS.items():
            with self.subTest(domain=domain):
                self.assertTrue(
                    row_is_pdf_noise_hold(domain, row, f"{domain}_2026.pdf"),
                    f"genuine {domain} page furniture stopped being auto-closed",
                )

    def test_a_mapped_domain_still_judges_by_identity(self):
        self.assertTrue(domain_identity_is_known("academics"))
        self.assertFalse(
            row_is_pdf_noise_hold("academics", {"subject_code": "MATH"}, "s.pdf")
        )
        self.assertTrue(
            row_is_pdf_noise_hold("academics", {"credits": "3"}, "s.pdf")
        )


class ReviewOpenLeavesMoneyRowsHeldTests(TestCase):
    """End to end: opening the review page must not close an invoice row."""

    def setUp(self):
        self.school = School.objects.create(
            name="Held Money School",
            slug="held-money-school",
            subdomain="held-money-school",
            is_active=True,
            is_approved=True,
        )
        self.admin = User.objects.create_user(
            username="held-money-admin", password="x", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.bundle = MigrationBundle.objects.create(
            label="held-money",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="held-money-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
        )
        self.run = MigrationRun.objects.create(
            school=self.school,
            migration_type="apply",
            execution_summary={"bundle_id": self.bundle.pk},
        )

    def _hold(self, domain: str, row: dict, artifact: str):
        return MigrationQuarantineRecord.objects.create(
            school=self.school,
            migration_run=self.run,
            domain=domain,
            row_index=1,
            issue_class="missing_required",
            payload={
                "error": "missing required field",
                "artifact": artifact,
                "source_row": row,
            },
        )

    def test_autopilot_leaves_the_invoice_row_and_closes_the_footer(self):
        invoice = self._hold(
            "finance", DATA_BEARING_ROWS["finance"], "fee_schedule_2026.pdf"
        )
        footer = self._hold(
            "finance", {"page": "2", "line": "totals"}, "fee_schedule_2026.pdf"
        )

        auto_remediate_on_review_open(self.bundle, user=self.admin)

        invoice.refresh_from_db()
        footer.refresh_from_db()
        self.assertEqual(
            invoice.status,
            MigrationQuarantineRecord.Status.PENDING,
            "a held invoice row must survive autopilot -- it is money, not noise",
        )
        self.assertNotEqual(footer.status, MigrationQuarantineRecord.Status.PENDING)

    def test_opening_the_review_page_runs_autopilot(self):
        """The wiring itself, not just the helper.

        ``maybe_autopilot_held_review`` is covered directly elsewhere; nothing
        pinned that the VIEW calls it, which is the whole claim of review-open
        autopilot.
        """
        footer = self._hold(
            "academics", {"page": "2", "line": "stats"}, "school_stats.pdf"
        )
        request = RequestFactory().get("/review/")
        request.user = self.admin

        response = MigrationCloudAnomalyNudgeView.as_view()(
            request, bundle_id=self.bundle.pk, shell="super"
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("autopilot_done=", response["Location"])
        footer.refresh_from_db()
        self.assertNotEqual(footer.status, MigrationQuarantineRecord.Status.PENDING)
