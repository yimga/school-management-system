"""PDF noise auto-dismiss + domain-aware field flags + held-review card UI (2026-08-28)."""

from __future__ import annotations

from django.template.loader import get_template
from django.test import SimpleTestCase

from apps.migration_cloud.auto_remediate import auto_dismiss_pdf_noise_holds
from apps.migration_cloud.landers._helpers import row_is_pdf_noise_hold
from apps.migration_cloud.quarantine_resolution import infer_field_flags


class PdfNoiseHoldDetectionTests(SimpleTestCase):
    def test_pdf_without_identity_is_noise(self):
        row = {"custom_fields": {"page": "3", "line": "School stats summary"}}
        self.assertTrue(
            row_is_pdf_noise_hold(
                "academics",
                row,
                "school_stats_2026-01-18.pdf",
            )
        )

    def test_pdf_with_subject_name_is_not_noise(self):
        row = {"subject_name": "Mathematics", "subject_code": "MATH101"}
        self.assertFalse(
            row_is_pdf_noise_hold(
                "academics",
                row,
                "courses.pdf",
            )
        )

    def test_non_pdf_missing_required_stays_actionable(self):
        row = {"first_name": "", "last_name": ""}
        self.assertFalse(
            row_is_pdf_noise_hold(
                "students",
                row,
                "students_2026.xlsx",
            )
        )


class InferFieldFlagsDomainTests(SimpleTestCase):
    def test_academics_shows_subject_fields_not_student(self):
        flags = infer_field_flags(
            "missing_required",
            "academics: missing subject_name/code",
            {},
            domain="academics",
        )
        labels = {f["label"] for f in flags}
        self.assertIn("Subject / course name", labels)
        self.assertNotIn("Student name", labels)

    def test_students_shows_student_identity(self):
        flags = infer_field_flags(
            "missing_required",
            "students: missing admission_number",
            {},
            domain="students",
        )
        labels = {f["label"] for f in flags}
        self.assertIn("Student id / admission number", labels)


class HeldReviewCardTemplateTests(SimpleTestCase):
    def test_anomaly_nudge_held_rows_first_and_mapping_collapsed(self):
        source = get_template("migration_cloud/anomaly_nudge.html").template.source
        held = get_template("migration_cloud/partials/quarantine_held_rows.html").template.source
        self.assertIn("quarantine_held_rows.html", source)
        self.assertIn("rmc-quarantine-cards", held)
        self.assertNotIn("rmc-quarantine-table", source)
        self.assertIn("section-held", source)
        self.assertIn("section-mapping", source)
        self.assertIn("run_autopilot", source)
        self.assertLess(source.index("section-held"), source.index("section-mapping"))

    def test_held_rows_partial_has_no_seven_column_table(self):
        source = get_template("migration_cloud/partials/quarantine_held_rows.html").template.source
        self.assertIn("rmc-quarantine-card", source)
        self.assertNotIn("<table", source)


class AutoDismissPdfNoiseCallableTests(SimpleTestCase):
    def test_auto_dismiss_pdf_noise_is_exported(self):
        self.assertTrue(callable(auto_dismiss_pdf_noise_holds))

    def test_review_open_autopilot_is_exported(self):
        from apps.migration_cloud.auto_remediate import auto_remediate_on_review_open

        self.assertTrue(callable(auto_remediate_on_review_open))

    def test_maybe_autopilot_redirect_helper(self):
        from apps.migration_cloud.views import maybe_autopilot_held_review

        self.assertTrue(callable(maybe_autopilot_held_review))

    def test_run_autopilot_action_registered(self):
        from apps.migration_cloud.quarantine_resolution import _RESOLUTION_ACTIONS

        self.assertIn("run_autopilot", _RESOLUTION_ACTIONS)
