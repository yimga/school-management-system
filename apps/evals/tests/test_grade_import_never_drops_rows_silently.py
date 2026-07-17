"""A grade import must never lose a row and call itself complete.

Found by an A-Z audit follow-up (2026-07-16/17).

``apply_import``'s per-row handler swallowed the failure and moved on::

    except _EVALS_IMPORTERS_ROW_ERRORS:
        log_exception_with_context("evals importers apply_import row failed", ...)
        continue

    return {"created": created_count, "updated": updated_count,
            "duration_seconds": ...}

There is no failure count in that dict, so the caller cannot learn a row was
dropped. The view then wrote::

    job.created_count = result["created"]
    job.updated_count = result["updated"]
    job.status = "completed"

``job.failed_count`` is only ever touched by the OUTER except (``+= 1``, for a
whole-import crash), so it is 0 or 1 and never reflects per-row losses. A
teacher uploading 250 grades where 50 rows fail got back
``status="completed", failed_count=0`` and 50 grades silently missing --
from the one dataset a school cannot reconstruct from memory.

``analytics.services`` then computed ``total_rows = created + updated +
failed``, so even the totals agreed with the lie.

The vocabulary for telling the truth already existed and was never used:
``GradeImportJob.STATUS_CHOICES`` has carried ``("partial", "Partially
Completed")`` all along, and the model has ``failed_count``, ``total_rows`` and
``error_log`` fields the success path never populated.
"""

from __future__ import annotations



from django.test import TestCase

from apps.evals.importers import apply_import


class ApplyImportCountsWhatItDropsTests(TestCase):
    """The contract: every row is accounted for."""

    def _rows(self, n: int):
        return [
            {
                "student_code": f"S-{i}",
                "subject_assignment_id": "1",
                "term_id": "1",
                "seq1": "10",
            }
            for i in range(n)
        ]

    def test_the_result_reports_failures(self):
        """A dropped row must be counted, not just logged and forgotten."""
        result = apply_import(self._rows(3))
        self.assertIn(
            "failed", result,
            "apply_import's result has no failure key at all, so no caller can "
            "know rows were dropped -- 200 lost grades reported as a clean run",
        )

    def test_every_row_is_accounted_for(self):
        rows = self._rows(5)
        result = apply_import(rows)
        counted = result["created"] + result["updated"] + result["failed"]
        self.assertEqual(
            counted, len(rows),
            "rows went in that came out in no bucket -- silently vanished",
        )

    def test_failures_carry_a_reason(self):
        result = apply_import(self._rows(2))
        self.assertIn("errors", result)
        if result["failed"]:
            first = result["errors"][0]
            self.assertIn("row_index", first)
            self.assertIn("error", first)

    def test_a_clean_import_reports_zero_failures(self):
        """The guard must not invent failures on the happy path."""
        result = apply_import([])
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["errors"], [])


class ApplyImportResultShapeTests(TestCase):
    """The keys the view and analytics.services read must keep working."""

    def test_existing_keys_survive(self):
        result = apply_import([])
        for key in ("created", "updated", "duration_seconds"):
            self.assertIn(key, result, f"{key} is read by the import view")


class TheImportJobTellsTheTruthTests(TestCase):
    """The status a teacher actually sees."""

    def test_partial_is_a_real_status_the_model_already_offers(self):
        from apps.analytics.models import GradeImportJob

        values = [c[0] for c in GradeImportJob.STATUS_CHOICES]
        self.assertIn(
            "partial", values,
            "the honest status for a part-succeeded import already exists in "
            "the model and was never used",
        )

    def test_a_partial_import_is_not_reported_as_completed(self):
        """The lie, at the point the job's status is decided."""
        from apps.evals.views import _resolve_import_job_outcome

        status, failed = _resolve_import_job_outcome(
            {"created": 200, "updated": 0, "failed": 50, "errors": []}
        )
        self.assertEqual(
            status, "partial",
            "50 rows were dropped and the job still reported 'completed' with "
            "failed_count=0 -- grades are the one dataset a school cannot "
            "reconstruct from memory",
        )
        self.assertEqual(failed, 50)

    def test_a_clean_import_is_still_completed(self):
        from apps.evals.views import _resolve_import_job_outcome

        self.assertEqual(
            _resolve_import_job_outcome({"created": 10, "updated": 2, "failed": 0}),
            ("completed", 0),
        )

    def test_an_older_result_shape_degrades_instead_of_raising(self):
        from apps.evals.views import _resolve_import_job_outcome

        self.assertEqual(
            _resolve_import_job_outcome({"created": 1, "updated": 0}),
            ("completed", 0),
        )
