from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Term
from apps.analytics.models import GradeImportJob
from apps.evals.views import (
    _deserialize_pending_entries,
    _extract_corrected_ocr_entries,
)


class OCRPendingEntryHelperTests(TestCase):
    def test_deserialize_pending_entries_ignores_invalid_decimal_values(self):
        entries = _deserialize_pending_entries(
            [
                {
                    "student_code": "STD-1",
                    "line_text": "STD-1 line",
                    "scores": {"seq1": "12.5", "seq2": "bad-value"},
                    "field_confidences": {"seq1": 0.9},
                }
            ]
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(str(entries[0]["scores"]["seq1"]), "12.5")
        self.assertNotIn("seq2", entries[0]["scores"])

    def test_extract_corrected_ocr_entries_skips_invalid_corrections(self):
        original_entries = [
            {
                "student_code": "STD-1",
                "scores": {"seq1_score": 10, "seq2_score": 11},
                "line_text": "STD-1 line",
                "field_confidences": {},
            }
        ]

        corrected = _extract_corrected_ocr_entries(
            {
                "ocr_correct_STD-1_seq1_score": "15.5",
                "ocr_correct_STD-1_seq2_score": "not-a-number",
            },
            original_entries,
        )

        self.assertIsNotNone(corrected)
        self.assertEqual(str(corrected[0]["scores"]["seq1_score"]), "15.5")
        self.assertNotIn("seq2_score", corrected[0]["scores"])


class GradeImportAPIViewHardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="evals-admin",
            password="testpass123",
            role=User.Role.HOD,
            is_staff=True,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()
        self.ay = AcademicYear.objects.create(
            name="GI-Y1",
            start_date="2024-09-01",
            end_date="2025-06-30",
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.ay,
            name="T1",
            start_date="2024-09-01",
            end_date="2024-12-31",
            is_active=True,
        )

    def _csv_upload(
        self, content: str = "student_code,subject_assignment_id,term_id\nSTD1,1,1\n"
    ):
        return SimpleUploadedFile(
            "grades.csv", content.encode("utf-8"), content_type="text/csv"
        )

    def test_grade_import_preview_api_returns_safe_error_when_importer_fails(self):
        with patch(
            "apps.evals.importers.preview_import_with_validation",
            side_effect=ValueError("preview failed"),
        ):
            response = self.client.post(
                reverse("evals:grade_import_preview_api"),
                {"file": self._csv_upload()},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("couldn't read your CSV", payload["error"])
        self.assertEqual(payload["detail"], "preview failed")

    def test_grade_import_apply_api_marks_job_failed_when_importer_fails(self):
        with patch(
            "apps.evals.importers.apply_import",
            side_effect=ValueError("apply failed"),
        ):
            response = self.client.post(
                reverse("evals:grade_import_apply_api"),
                {
                    "file": self._csv_upload(),
                    "academic_year_id": str(self.ay.pk),
                    "term_id": str(self.term.pk),
                },
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["detail"], "apply failed")

        job = GradeImportJob.objects.get(pk=payload["job_id"])
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.failed_count, 1)
        self.assertEqual(job.error_log, ["apply failed"])
